package au.awto.dji.awto_dji_app

import java.nio.ByteBuffer
import java.util.PriorityQueue
import org.junit.Assert.*
import org.junit.Test

class DecoderSessionTest {
    /** Deterministic Handler replacement: preserves FIFO, supports delayed recovery. */
    private class Loop {
        private data class Job(val at: Long, val order: Int, val task: () -> Unit)
        private val jobs = PriorityQueue<Job>(compareBy<Job> { it.at }.thenBy { it.order })
        private var sequence = 0
        var now = 0L
        var onWorker = false
        val size get() = jobs.size
        fun post(delay: Long, task: () -> Unit) { jobs.add(Job(now + delay, sequence++, task)) }
        fun ready() {
            var count = 0
            while (jobs.peek()?.at?.let { it <= now } == true) {
                check(++count < 1000) { "Runaway task loop" }
                onWorker = true
                try { jobs.remove().task() } finally { onWorker = false }
            }
        }
        fun advance(ms: Long) { now += ms; ready() }
    }

    private class FakeCodec(val loop: Loop, val history: MutableList<String>) : VideoCodec {
        lateinit var events: VideoCodec.Events
        var startError = false
        var inputError = false
        var nullInput = false
        var queueError = false
        var outputError = false
        var stopError = false
        var releaseError = false
        var released = false
        var releases = 0
        var capacity = 1024
        var inputCalls = 0
        var outputCalls = 0
        private var buffer = ByteBuffer.allocate(capacity)
        val queued = mutableListOf<ByteArray>()
        val indices = mutableListOf<Int>()
        private fun operation(name: String) {
            assertTrue("$name must run on decoder worker", loop.onWorker)
            check(!released) { "Use after release: $name" }
            history.add(name)
        }
        override fun start(events: VideoCodec.Events) {
            operation("start")
            this.events = events
            if (startError) throw IllegalStateException("configure/start failed")
        }
        override fun inputBuffer(index: Int): ByteBuffer? {
            operation("input")
            inputCalls++
            // Model codec state invalidated by Android independently of our close().
            if (inputError) throw IllegalStateException("Invalid to call at Released state")
            if (nullInput) return null
            buffer = ByteBuffer.allocate(capacity)
            return buffer
        }
        override fun queueInput(index: Int, size: Int, presentationTimeUs: Long) {
            operation("queue")
            if (queueError) throw IllegalStateException("queue failed")
            indices.add(index)
            queued.add(buffer.array().copyOf(size))
        }
        override fun releaseOutput(index: Int, render: Boolean) {
            operation("output")
            outputCalls++
            if (outputError) throw IllegalStateException("output failed")
        }
        override fun stop() {
            operation("stop")
            if (stopError) throw IllegalStateException("stop failed")
        }
        override fun release() {
            operation("release")
            releases++
            released = true
            if (releaseError) throw IllegalStateException("release failed")
        }
        fun input(index: Int = 0) = loop.post(0) { events.input(index) }
        fun output() = loop.post(0) { events.output(0, 8) }
        fun error() = loop.post(0) { events.error(IllegalStateException("decoder error")) }
    }

    private class Fixture {
        val loop = Loop()
        val history = mutableListOf<String>()
        val codecs = mutableListOf<FakeCodec>()
        var configure: (FakeCodec) -> Unit = {}
        var factoryError = false
        val session = newSession()
        fun newSession() = DecoderSession(loop::post, {
            assertTrue(loop.onWorker)
            if (factoryError) throw java.io.IOException("No decoder available")
            FakeCodec(loop, history).also { configure(it); codecs.add(it) }
        })
        fun start(): Boolean {
            var ok = false
            session.start { ok = it }
            loop.ready()
            return ok
        }
        val codec get() = codecs.last()
    }

    private val sps = byteArrayOf(0, 0, 0, 1, 0x67, 0x12)
    private val pps = byteArrayOf(0, 0, 1, 0x68, 0x34)
    private val idr = byteArrayOf(0, 0, 0, 1, 0x65, 0x55)
    private val predicted = byteArrayOf(0, 0, 0, 1, 0x41, 0x66)

    @Test fun releaseCancelsQueuedDrainAndCallbacksBeforeTeardownRuns() {
        val f = Fixture(); assertTrue(f.start())
        val old = f.codec
        old.input(); f.loop.ready() // Codec owns a queued input index.
        f.session.offer(idr) // Enqueues a drain, but it hasn't run.
        old.input(1); old.output(); old.error()
        var closed = false
        f.session.close { closed = true }
        f.loop.ready()
        assertTrue(closed)
        assertEquals(0, old.inputCalls)
        assertEquals(0, old.outputCalls)
        assertEquals(1, old.releases)
        assertEquals("closed", f.session.stats()["state"])
        assertEquals(0, f.session.stats()["pending"])
        assertEquals(0L, f.session.stats()["errors"])
    }

    @Test fun releasedStateDuringInputRecoversAndWorkerKeepsRunning() {
        val f = Fixture(); f.start()
        val old = f.codec
        old.input(); f.loop.ready()
        old.inputError = true
        f.session.offer(sps + pps + idr)
        var unrelatedWorkRan = false
        f.loop.post(0) { unrelatedWorkRan = true }
        f.loop.ready()
        assertTrue(unrelatedWorkRan)
        assertTrue(old.released)
        assertEquals("recovering", f.session.stats()["state"])
        f.loop.advance(250)
        assertEquals(2, f.codecs.size)
        assertEquals("running", f.session.stats()["state"])
        f.session.offer(predicted) // No old GOP submitted to the new decoder.
        f.codec.input(9); f.loop.ready()
        assertTrue(f.codec.queued.isEmpty())
        f.session.offer(idr); f.loop.ready()
        assertArrayEquals(sps + pps + idr, f.codec.queued.single())
        assertEquals(listOf(9), f.codec.indices)
        assertEquals(1L, f.session.stats()["errors"])
    }

    @Test fun decoderErrorRetiresGenerationAndIgnoresStaleCallbacks() {
        val f = Fixture(); f.start()
        f.session.offer(sps + pps + idr); f.codec.input(); f.loop.ready()
        val old = f.codec
        old.error(); old.input(99); old.output(); old.error()
        f.loop.ready(); f.loop.advance(250)
        old.input(98); old.output(); old.error(); f.loop.ready()
        assertEquals(1L, f.session.stats()["errors"])
        assertEquals(1, f.session.stats()["recoveries"])
        assertEquals(0, f.session.stats()["available"])
        assertEquals(0, f.codec.inputCalls)
        assertEquals(0, old.outputCalls)
    }

    @Test fun nullInputQueueAndOutputFailuresAreContained() {
        for (failure in listOf("null", "queue", "output")) {
            val f = Fixture(); f.start()
            f.codec.nullInput = failure == "null"
            f.codec.queueError = failure == "queue"
            f.codec.outputError = failure == "output"
            if (failure == "output") f.codec.output() else {
                f.session.offer(idr); f.codec.input()
            }
            f.loop.ready()
            assertEquals(failure, "recovering", f.session.stats()["state"])
            assertEquals(failure, 1, f.codec.releases)
            f.loop.advance(250)
            assertEquals(failure, "running", f.session.stats()["state"])
        }
    }

    @Test fun closeCancelsDelayedRecoveryAndCompletesDespiteCleanupErrors() {
        val f = Fixture(); f.start()
        f.codec.stopError = true; f.codec.releaseError = true
        f.codec.error(); f.loop.ready()
        var closed = false
        f.session.close { closed = true }; f.loop.ready(); f.loop.advance(1000)
        assertTrue(closed)
        assertEquals(1, f.codecs.size)
        assertEquals(1, f.codec.releases)
        assertEquals("closed", f.session.stats()["state"])
    }

    @Test fun startupFailureReleasesPartiallyConfiguredCodec() {
        val f = Fixture(); f.configure = { it.startError = true; it.stopError = true }
        assertFalse(f.start())
        assertTrue(f.codec.released)
        assertEquals(1, f.codec.releases)
        assertEquals("failed", f.session.stats()["state"])
        f.session.offer(idr); f.loop.ready()
        assertEquals(0, f.session.stats()["pending"])
    }

    @Test fun factoryFailureReturnsFailureWithoutKillingWorker() {
        val f = Fixture(); f.factoryError = true
        assertFalse(f.start())
        assertEquals("failed", f.session.stats()["state"])
        assertTrue(f.codecs.isEmpty())
    }

    @Test fun initializationCancelledBeforeWorkerStartsAllocatesNothing() {
        val f = Fixture()
        var completed: Boolean? = null
        f.session.start { completed = it }
        f.session.close {}
        f.loop.ready()
        assertEquals(false, completed)
        assertTrue(f.codecs.isEmpty())
    }

    @Test fun recoveryFailuresAreBoundedWithBackoffAndNoQueueLeak() {
        val f = Fixture(); f.start(); f.codec.error(); f.loop.ready()
        f.configure = { it.startError = true }
        f.loop.advance(249); assertEquals(1, f.codecs.size)
        f.loop.advance(1); assertEquals(2, f.codecs.size)
        f.loop.advance(499); assertEquals(2, f.codecs.size)
        f.loop.advance(1); assertEquals(3, f.codecs.size)
        f.loop.advance(999); assertEquals(3, f.codecs.size)
        f.loop.advance(1); assertEquals(4, f.codecs.size)
        assertEquals("failed", f.session.stats()["state"])
        repeat(1000) { f.session.offer(idr) }
        assertEquals(0, f.session.stats()["pending"])
        assertEquals(0, f.loop.size)
        assertTrue(f.codecs.all { it.releases == 1 })
    }

    @Test fun repeatedErrorsOnSuccessfullyStartedReplacementsAlsoHitRetryLimit() {
        val f = Fixture(); f.start()
        for (delay in listOf(250L, 500L, 1000L)) {
            f.codec.error(); f.loop.ready(); f.loop.advance(delay)
            assertEquals("running", f.session.stats()["state"])
        }
        f.codec.error(); f.loop.ready()
        assertEquals("failed", f.session.stats()["state"])
        assertEquals(4, f.codecs.size)
        assertEquals(0, f.loop.size)
    }

    @Test fun reconnectAndRepeatedInitializationSerializeReleaseBeforeNextStart() {
        val f = Fixture(); f.start()
        var current = f.session
        repeat(20) {
            val retired = f.codec
            current.offer(idr); retired.input(); retired.output(); retired.error()
            current.close {}
            current = f.newSession()
            current.start { assertTrue(it) }
            f.loop.ready()
            retired.input(88); retired.output(); retired.error(); f.loop.ready()
            assertEquals("running", current.stats()["state"])
            assertTrue(retired.released)
            assertEquals(1, retired.releases)
        }
        current.close {}; f.loop.ready(); f.loop.advance(2000)
        assertEquals(21, f.codecs.size)
        assertEquals(List(21) { listOf("start", "stop", "release") }.flatten(), f.history)
    }

    @Test fun repeatedStartOnSameSessionDoesNotAllocateAnotherCodec() {
        val f = Fixture(); f.start()
        var startedAgain = true
        f.session.start { startedAgain = it }; f.loop.ready()
        assertFalse(startedAgain)
        assertEquals(1, f.codecs.size)
    }

    @Test fun inputBeforePictureAndOversizedAccessUnitsReturnBufferOwnership() {
        val f = Fixture(); f.start()
        f.codec.input(7); f.loop.ready()
        f.codec.capacity = 1
        f.session.offer(idr); f.loop.ready()
        assertEquals(0, f.codec.queued.single().size)
        f.codec.capacity = 1024
        f.codec.input(8); f.loop.ready()
        f.session.offer(idr); f.loop.ready()
        assertArrayEquals(idr, f.codec.queued.last())
        assertEquals(listOf(7, 8), f.codec.indices)
        assertEquals(1L, f.session.stats()["submitted"])
    }

    @Test fun stalledDecoderHasBoundedDataAndOnlyOnePostedDrain() {
        val f = Fixture(); f.start()
        repeat(1000) { f.session.offer(idr) }
        assertEquals(300, f.session.stats()["pending"])
        assertEquals(700L, f.session.stats()["dropped"])
        assertEquals(1, f.loop.size)
        f.loop.ready()
        repeat(100) { f.session.offer(ByteArray(256 * 1024)) }
        assertTrue((f.session.stats()["pending"] as Int) <= 32)
    }

    @Test fun parameterChangesDuringRecoveryAreUsedAndMissingParametersWait() {
        val f = Fixture(); f.start(); f.codec.error(); f.loop.ready(); f.loop.advance(250)
        f.codec.input(); f.session.offer(idr); f.loop.ready()
        assertTrue(f.codec.queued.isEmpty()) // Missing parameter sets.
        f.codec.error(); f.loop.ready()
        val newSps = byteArrayOf(0, 0, 1, 0x67, 0x22)
        f.session.offer(newSps); f.session.offer(pps)
        f.loop.advance(500)
        f.codec.input(); f.session.offer(idr); f.loop.ready()
        assertArrayEquals(newSps + pps + idr, f.codec.queued.single())
    }

    @Test fun bootstrapIsQueuedAndItsParametersRemainAvailableForRecovery() {
        val f = Fixture()
        val session = DecoderSession(f.loop::post, {
            FakeCodec(f.loop, f.history).also { f.codecs.add(it) }
        }, bootstrap = sps + pps + idr)
        session.start { assertTrue(it) }; f.loop.ready()
        f.codec.input(); f.loop.ready()
        assertArrayEquals(sps + pps + idr, f.codec.queued.single())
        f.codec.error(); f.loop.ready(); f.loop.advance(250)
        f.codec.input(); session.offer(idr); f.loop.ready()
        assertArrayEquals(sps + pps + idr, f.codec.queued.single())
    }

    @Test fun repeatedCloseCompletesWithoutReleasingCodecTwice() {
        val f = Fixture(); f.start()
        var completions = 0
        f.session.close { completions++ }
        f.session.close { completions++ }
        f.loop.ready()
        assertEquals(2, completions)
        assertEquals(1, f.codec.releases)
        assertEquals("closed", f.session.stats()["state"])
    }

}
