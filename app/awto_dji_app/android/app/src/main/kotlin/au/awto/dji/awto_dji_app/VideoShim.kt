package au.awto.dji.awto_dji_app

import android.content.Context
import android.media.MediaCodec
import android.media.MediaFormat
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.view.TextureRegistry
import java.nio.ByteBuffer
import java.util.ArrayDeque

/**
 * Raw H.264 Annex-B NAL -> MediaCodec -> a Flutter Texture. No protocol logic: Dart
 * (lib/video/annexb_extractor.dart) finds the NALs in demultiplexed camera bytes and pushes them
 * here one at a time; this just re-prepends a start code and feeds the decoder.
 * Compile-checked only; untested without a real NAL stream from the aircraft.
 */
class VideoShim(
    private val context: Context,
    private val textures: TextureRegistry,
    messenger: BinaryMessenger,
) : MethodChannel.MethodCallHandler {

    private val startCode = byteArrayOf(0, 0, 0, 1)
    private var entry: TextureRegistry.SurfaceTextureEntry? = null
    private var codec: MediaCodec? = null
    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private val pending = ArrayDeque<ByteArray>()
    private val available = ArrayDeque<Int>()
    private var configured = false
    private var fedCount = 0L
    private var droppedCount = 0L
    private var submittedCount = 0L
    private var renderedCount = 0L
    private var surface: Surface? = null

    init {
        MethodChannel(messenger, "au.awto.dji/video").setMethodCallHandler(this)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "createTexture" -> createTexture(result)
            "feedNal" -> {
                val data = call.arguments as? ByteArray
                if (data == null) {
                    result.error("bad_arg", "feedNal needs bytes", null)
                } else {
                    feedNal(data)
                    result.success(null)
                }
            }
            "feedAccessUnit" -> {
                val data = call.arguments as? ByteArray
                if (data == null) result.error("bad_arg", "feedAccessUnit needs bytes", null)
                else {
                    enqueue(data)
                    result.success(null)
                }
            }
            "release" -> {
                release()
                result.success(null)
            }
            "stats" -> result.success(synchronized(pending) {
                mapOf("fed" to fedCount, "dropped" to droppedCount,
                    "submitted" to submittedCount, "rendered" to renderedCount,
                    "pending" to pending.size, "available" to available.size)
            })
            else -> result.notImplemented()
        }
    }

    private fun createTexture(result: MethodChannel.Result) {
        release()
        val e = textures.createSurfaceTexture()
        entry = e
        val thread = HandlerThread("video-decode").also { it.start() }
        this.thread = thread
        val handler = Handler(thread.looper)
        this.handler = handler

        val surface = Surface(e.surfaceTexture())
        this.surface = surface
        // 1280x720 default; MediaCodec re-negotiates actual size from the SPS once decoding
        // starts (onOutputFormatChanged), so this is just a starting hint.
        val format = MediaFormat.createVideoFormat("video/avc", 1280, 720)
        val c = MediaCodec.createDecoderByType("video/avc")
        c.setCallback(object : MediaCodec.Callback() {
            override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
                synchronized(pending) {
                    if (!configured || codec !== this@VideoShim.codec) return
                    // Keep ownership even when no NAL has arrived yet. A later
                    // feedNal must drain this index; no second callback is promised.
                    available.add(index)
                    drainInput(codec)
                }
            }

            override fun onOutputBufferAvailable(
                codec: MediaCodec,
                index: Int,
                info: MediaCodec.BufferInfo,
            ) {
                synchronized(pending) {
                    if (!configured || codec !== this@VideoShim.codec) return
                    val render = info.size > 0
                    codec.releaseOutputBuffer(index, render)
                    if (render) {
                        renderedCount++
                        if (renderedCount == 1L) android.util.Log.i("VideoShim", "first decoded frame rendered")
                    }
                }
            }

            override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
                // Surfaced to Dart only via logcat for now - no error channel wired up yet.
                android.util.Log.e("VideoShim", "codec error: ${e.diagnosticInfo}")
            }

            override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {
                android.util.Log.i("VideoShim", "output format: $format")
            }
        }, handler)
        c.configure(format, surface, null, 0)
        synchronized(pending) {
            codec = c
            configured = true
            fedCount = 0
            droppedCount = 0
            submittedCount = 0
            renderedCount = 0
            // GO uses a bundled decoder-start picture for P3 Professional's
            // 1280x720 stream. Read it from the owner's installed GO package;
            // no vendor binary is bundled or redistributed by this app.
            loadBootstrap()?.let { pending.add(it) }
        }
        c.start()
        result.success(e.id())
    }

    private fun feedNal(nal: ByteArray) {
        enqueue(startCode + nal)
    }

    private fun loadBootstrap(): ByteArray? {
        return try {
            val resources = context.packageManager.getResourcesForApplication("dji.go.v4")
            val id = resources.getIdentifier("iframe_1280x720_ins", "raw", "dji.go.v4")
            if (id == 0) {
                android.util.Log.w("VideoShim", "GO bootstrap resource unavailable")
                null
            } else resources.openRawResource(id).use {
                it.readBytes().also { bytes ->
                    android.util.Log.i("VideoShim", "loaded GO P3 bootstrap: ${bytes.size} bytes")
                }
            }
        } catch (error: Exception) {
            android.util.Log.w("VideoShim", "P3 bootstrap unavailable: ${error.message}")
            null
        }
    }

    private fun enqueue(withStartCode: ByteArray) {
        synchronized(pending) {
            if (!configured) return
            fedCount++
            pending.add(withStartCode)
            // Bound memory if Dart feeds faster than the decoder drains (shouldn't happen in
            // steady state, but a stalled decoder must not grow this unboundedly).
            while (pending.size > 300) {
                pending.poll()
                droppedCount++
            }
        }
        // Both codec callbacks and drain run on the decoder handler. In
        // particular, wake the decoder when buffers arrived before the NAL.
        handler?.post {
            synchronized(pending) {
                val c = codec
                if (configured && c != null) drainInput(c)
            }
        }
    }

    // Caller holds pending's monitor, serializing queue access with release().
    private fun drainInput(codec: MediaCodec) {
        while (pending.isNotEmpty() && available.isNotEmpty()) {
            val index = available.removeFirst()
            val nal = pending.removeFirst()
            val buf: ByteBuffer = codec.getInputBuffer(index)
                ?: throw IllegalStateException("Missing MediaCodec input buffer")
            buf.clear()
            if (nal.size > buf.remaining()) {
                droppedCount++
                codec.queueInputBuffer(index, 0, 0, 0, 0)
                android.util.Log.w("VideoShim", "NAL exceeds input capacity: ${nal.size}")
                continue
            }
            buf.put(nal)
            codec.queueInputBuffer(index, 0, nal.size, System.nanoTime() / 1000, 0)
            submittedCount++
        }
    }

    private fun release() {
        val oldCodec = synchronized(pending) {
            configured = false
            val old = codec
            codec = null
            pending.clear()
            available.clear()
            old
        }
        try {
            oldCodec?.stop()
        } catch (_: IllegalStateException) {
            // Already stopped/never started.
        }
        oldCodec?.release()
        thread?.quitSafely()
        thread = null
        handler = null
        surface?.release()
        surface = null
        entry?.release()
        entry = null
    }

    fun close() = release()
}
