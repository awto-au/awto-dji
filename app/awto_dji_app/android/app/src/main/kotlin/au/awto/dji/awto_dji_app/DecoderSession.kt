package au.awto.dji.awto_dji_app

import java.nio.ByteBuffer
import java.util.ArrayDeque

/** The small MediaCodec boundary, also used by the JVM lifecycle regression tests. */
internal interface VideoCodec {
    interface Events {
        fun input(index: Int)
        fun output(index: Int, size: Int)
        fun error(error: Exception)
    }

    fun start(events: Events)
    fun inputBuffer(index: Int): ByteBuffer?
    fun queueInput(index: Int, size: Int, presentationTimeUs: Long)
    fun releaseOutput(index: Int, render: Boolean)
    fun stop()
    fun release()
}

/**
 * One texture's decoder lifetime. schedule must enqueue (never inline) onto the same serial
 * worker used for VideoCodec.Events. Only offer/close/stats are called from other threads.
 * All codec operations, including configure/start/stop/release, run on that worker.
 */
internal class DecoderSession(
    private val schedule: (Long, () -> Unit) -> Unit,
    private val factory: () -> VideoCodec,
    private val bootstrap: ByteArray? = null,
    private val log: (String, Exception?) -> Unit = { _, _ -> },
) {
    private val lock = Any()
    private enum class State { NEW, RUNNING, RECOVERING, FAILED, CLOSED }
    private var state = State.NEW
    private var codec: VideoCodec? = null
    private var generation = 0L
    private var drainPosted = false
    private val pending = ArrayDeque<ByteArray>()
    private val available = ArrayDeque<Int>()
    private var queuedBytes = 0
    private var fed = 0L
    private var dropped = 0L
    private var submitted = 0L
    private var rendered = 0L
    private var errors = 0L
    private var recoveries = 0
    private var lastError: String? = null
    private var sps: ByteArray? = null
    private var pps: ByteArray? = null
    private var awaitingIdr = false

    fun start(complete: (Boolean) -> Unit) = schedule(0) {
        val ok = synchronized(lock) {
            if (state != State.NEW) false else {
                bootstrap?.let { rememberParameters(it); addPending(it) }
                startCodec()
            }
        }
        complete(ok)
    }

    fun offer(data: ByteArray) = synchronized(lock) {
        if (state != State.RUNNING && state != State.RECOVERING) return@synchronized
        fed++
        val types = rememberParameters(data)
        // A replacement decoder cannot decode the old GOP. Save SPS/PPS and wait for a new
        // IDR, then put the parameter sets and that picture in the SAME access unit.
        if (state == State.RECOVERING || (awaitingIdr && 5 !in types)) {
            dropped++
            return@synchronized
        }
        val input = if (awaitingIdr) {
            if (sps == null || pps == null) {
                dropped++
                return@synchronized
            }
            awaitingIdr = false
            sps!! + pps!! + data
        } else data
        addPending(input)
        if (!drainPosted) {
            drainPosted = true
            val expected = generation
            schedule(0) {
                synchronized(lock) {
                    if (generation == expected && state == State.RUNNING) {
                        drainPosted = false
                        drainInput()
                    }
                }
            }
        }
    }

    /** Cancel synchronously, so even callbacks ahead of queued teardown are harmless. */
    fun close(complete: () -> Unit) {
        synchronized(lock) {
            state = State.CLOSED
            generation++
            clearQueues()
        }
        schedule(0) {
            synchronized(lock) { disposeCodec() }
            complete()
        }
    }

    fun stats(): Map<String, Any?> = synchronized(lock) {
        mapOf("fed" to fed, "dropped" to dropped, "submitted" to submitted,
            "rendered" to rendered, "pending" to pending.size, "available" to available.size,
            "state" to state.name.lowercase(), "errors" to errors, "recoveries" to recoveries,
            "lastError" to lastError, "awaitingIdr" to awaitingIdr)
    }

    // Worker only, with lock held. Invalidate identity BEFORE calling stop/release.
    private fun disposeCodec() {
        val old = codec
        codec = null
        if (old != null) {
            try { old.stop() } catch (e: Exception) { log("codec stop failed", e) }
            try { old.release() } catch (e: Exception) { log("codec release failed", e) }
        }
    }

    private fun startCodec(): Boolean {
        generation++
        val expected = generation
        try {
            val c = factory()
            codec = c // Own it before configure/start, so partial initialization is cleaned up.
            c.start(object : VideoCodec.Events {
                private fun active() = codec === c && generation == expected && state == State.RUNNING

                override fun input(index: Int) = synchronized(lock) {
                    if (!active()) return@synchronized
                    available.add(index)
                    drainInput()
                }

                override fun output(index: Int, size: Int) = synchronized(lock) {
                    if (!active()) return@synchronized
                    try {
                        c.releaseOutput(index, size > 0)
                        if (size > 0) rendered++
                    } catch (e: Exception) { fail(e) }
                }

                override fun error(error: Exception) = synchronized(lock) {
                    if (active()) fail(error)
                }
            })
            state = State.RUNNING
            return true
        } catch (e: Exception) {
            recordError(e)
            disposeCodec()
            clearQueues()
            state = State.FAILED
            return false
        }
    }

    private fun drainInput() {
        val c = codec ?: return
        try {
            while (pending.isNotEmpty() && available.isNotEmpty()) {
                val index = available.removeFirst()
                val data = pending.removeFirst()
                queuedBytes -= data.size
                val buffer = c.inputBuffer(index)
                    ?: throw IllegalStateException("Missing MediaCodec input buffer")
                buffer.clear()
                if (data.size > buffer.remaining()) {
                    c.queueInput(index, 0, 0)
                    dropped++
                    continue
                }
                buffer.put(data)
                c.queueInput(index, data.size, System.nanoTime() / 1000)
                submitted++
            }
        } catch (e: Exception) {
            dropped++ // The access unit removed above was not submitted.
            fail(e)
        }
    }

    private fun recordError(e: Exception) {
        errors++
        lastError = "${e.javaClass.simpleName}: ${e.message}"
        log("video decoder failed", e)
    }

    private fun fail(e: Exception) {
        recordError(e)
        generation++
        state = State.RECOVERING
        clearQueues()
        disposeCodec()
        awaitingIdr = true
        retry()
    }

    private fun retry() {
        if (recoveries >= MAX_RECOVERIES) {
            state = State.FAILED // Video stays disabled; the DUML transport is independent.
            return
        }
        val expected = generation
        val delayMs = 250L shl recoveries
        recoveries++
        schedule(delayMs) {
            synchronized(lock) {
                if (state != State.RECOVERING || generation != expected) return@synchronized
                if (!startCodec()) {
                    state = State.RECOVERING
                    retry()
                }
            }
        }
    }

    private fun clearQueues() {
        dropped += pending.size
        pending.clear()
        available.clear()
        queuedBytes = 0
        drainPosted = false
    }

    private fun addPending(data: ByteArray) {
        if (data.size > MAX_QUEUED_BYTES) { dropped++; return }
        pending.add(data)
        queuedBytes += data.size
        while (pending.size > 300 || queuedBytes > MAX_QUEUED_BYTES) {
            queuedBytes -= pending.removeFirst().size
            dropped++
        }
    }

    /** Annex-B 3/4-byte start codes; retain only small SPS/PPS, never whole pictures. */
    private fun rememberParameters(data: ByteArray): Set<Int> {
        val starts = mutableListOf<Pair<Int, Int>>()
        var i = 0
        while (i + 3 <= data.size) {
            val length = when {
                i + 4 <= data.size && data[i] == 0.toByte() && data[i + 1] == 0.toByte()
                    && data[i + 2] == 0.toByte() && data[i + 3] == 1.toByte() -> 4
                data[i] == 0.toByte() && data[i + 1] == 0.toByte() && data[i + 2] == 1.toByte() -> 3
                else -> 0
            }
            if (length > 0) { starts.add(i to length); i += length } else i++
        }
        val types = mutableSetOf<Int>()
        starts.forEachIndexed { n, (start, length) ->
            val end = starts.getOrNull(n + 1)?.first ?: data.size
            if (start + length < end) {
                val type = data[start + length].toInt() and 31
                types.add(type)
                if (end - start <= 65536) when (type) {
                    7 -> sps = data.copyOfRange(start, end)
                    8 -> pps = data.copyOfRange(start, end)
                }
            }
        }
        return types
    }

    companion object {
        private const val MAX_RECOVERIES = 3
        private const val MAX_QUEUED_BYTES = 8 * 1024 * 1024
    }
}
