package au.awto.dji.awto_dji_app

import android.content.Context
import android.media.MediaCodec
import android.media.MediaFormat
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.util.Log
import android.view.Surface
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import io.flutter.view.TextureRegistry

/** H.264 Annex-B -> MediaCodec -> Flutter texture. Decoder failures never own the DUML link. */
class VideoShim(
    private val context: Context,
    private val textures: TextureRegistry,
    messenger: BinaryMessenger,
) : MethodChannel.MethodCallHandler {
    private val channel = MethodChannel(messenger, "au.awto.dji/video")
    private val main = Handler(Looper.getMainLooper())
    // One worker across reconnects: old teardown is queued BEFORE replacement startup.
    private val thread = HandlerThread("video-decode").also { it.start() }
    private val worker = Handler(thread.looper)
    private var session: TextureSession? = null // Main thread only.
    private var closed = false

    private class TextureSession(
        val entry: TextureRegistry.SurfaceTextureEntry,
        val surface: Surface,
        val decoder: DecoderSession,
    )

    init { channel.setMethodCallHandler(this) }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "createTexture" -> createTexture(result)
            "feedNal", "feedAccessUnit" -> {
                val data = call.arguments as? ByteArray
                if (data == null) result.error("bad_arg", "${call.method} needs bytes", null)
                else {
                    val input = if (call.method == "feedNal") byteArrayOf(0, 0, 0, 1) + data else data
                    session?.decoder?.offer(input)
                    result.success(null)
                }
            }
            "release" -> release { result.success(null) }
            "stats" -> result.success(session?.decoder?.stats() ?: mapOf(
                "fed" to 0L, "dropped" to 0L, "submitted" to 0L, "rendered" to 0L,
                "pending" to 0, "available" to 0, "state" to "closed",
            ))
            else -> result.notImplemented()
        }
    }

    private fun createTexture(result: MethodChannel.Result) {
        if (closed) { result.error("video_closed", "Video shim is closed", null); return }
        release()
        var entry: TextureRegistry.SurfaceTextureEntry? = null
        var surface: Surface? = null
        try {
            val e = textures.createSurfaceTexture()
            entry = e
            val output = Surface(e.surfaceTexture())
            surface = output
            val decoder = DecoderSession(
                schedule = { delay, task -> worker.postDelayed({ task() }, delay) },
                factory = { AndroidVideoCodec(output, worker) },
                bootstrap = loadBootstrap(),
                log = { message, error -> Log.w("VideoShim", message, error) },
            )
            val s = TextureSession(e, output, decoder)
            session = s
            decoder.start { ok ->
                main.post {
                    if (session !== s || closed) {
                        result.error("video_cancelled", "Decoder initialization cancelled", null)
                    } else if (ok) {
                        result.success(e.id())
                    } else {
                        release()
                        result.error("video_init", "Unable to start video decoder; see logcat", null)
                    }
                }
            }
        } catch (error: Exception) {
            // Surface/texture allocation can fail before the worker owns any decoder.
            surface?.let { safely("surface release") { it.release() } }
            entry?.let { safely("texture release") { it.release() } }
            result.error("video_init", error.message, null)
        }
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

    private fun release(complete: () -> Unit = {}) {
        val old = session
        session = null // No new feed can reach a retired session.
        if (old == null) { complete(); return }
        old.decoder.close {
            // Codec release finishes before its output surface or texture is destroyed.
            safely("surface release") { old.surface.release() }
            main.post {
                safely("texture release") { old.entry.release() }
                complete()
            }
        }
    }

    fun close() {
        if (closed) return
        closed = true
        channel.setMethodCallHandler(null)
        release()
        // Already queued teardown runs; delayed recovery tasks are discarded by quitSafely.
        worker.post { thread.quitSafely() }
    }

    private fun safely(operation: String, action: () -> Unit) {
        try { action() } catch (error: Exception) { Log.w("VideoShim", "$operation failed", error) }
    }
}

/** All methods and callbacks run on VideoShim's worker. Ownership checks live in DecoderSession. */
internal class AndroidVideoCodec(private val surface: Surface, private val handler: Handler) : VideoCodec {
    private val codec = MediaCodec.createDecoderByType("video/avc")

    override fun start(events: VideoCodec.Events) {
        codec.setCallback(object : MediaCodec.Callback() {
            override fun onInputBufferAvailable(codec: MediaCodec, index: Int) = events.input(index)
            override fun onOutputBufferAvailable(codec: MediaCodec, index: Int, info: MediaCodec.BufferInfo) =
                events.output(index, info.size)
            override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) = events.error(
                IllegalStateException(
                    "${e.diagnosticInfo}; recoverable=${e.isRecoverable}; transient=${e.isTransient}", e,
                ),
            )
            override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {
                Log.i("VideoShim", "output format: $format")
            }
        }, handler)
        // Actual dimensions are negotiated from SPS, as before.
        codec.configure(MediaFormat.createVideoFormat("video/avc", 1280, 720), surface, null, 0)
        codec.start()
    }

    override fun inputBuffer(index: Int) = codec.getInputBuffer(index)
    override fun queueInput(index: Int, size: Int, presentationTimeUs: Long) =
        codec.queueInputBuffer(index, 0, size, presentationTimeUs, 0)
    override fun releaseOutput(index: Int, render: Boolean) = codec.releaseOutputBuffer(index, render)
    override fun stop() = codec.stop()
    override fun release() = codec.release()
}
