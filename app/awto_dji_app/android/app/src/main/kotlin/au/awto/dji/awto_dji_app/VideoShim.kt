package au.awto.dji.awto_dji_app

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
 * (lib/video/annexb_extractor.dart) finds the NALs in the raw AOA byte stream and pushes them
 * here one at a time; this just re-prepends a start code and feeds the decoder.
 * Compile-checked only; untested without a real NAL stream from the aircraft.
 */
class VideoShim(
    private val textures: TextureRegistry,
    messenger: BinaryMessenger,
) : MethodChannel.MethodCallHandler {

    private val startCode = byteArrayOf(0, 0, 0, 1)
    private var entry: TextureRegistry.SurfaceTextureEntry? = null
    private var codec: MediaCodec? = null
    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    private val pending = ArrayDeque<ByteArray>()
    private var configured = false

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
            "release" -> {
                release()
                result.success(null)
            }
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
        // 1280x720 default; MediaCodec re-negotiates actual size from the SPS once decoding
        // starts (onOutputFormatChanged), so this is just a starting hint.
        val format = MediaFormat.createVideoFormat("video/avc", 1280, 720)
        val c = MediaCodec.createDecoderByType("video/avc")
        c.setCallback(object : MediaCodec.Callback() {
            override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
                val nal = synchronized(pending) { if (pending.isEmpty()) null else pending.poll() }
                if (nal == null) return
                val buf: ByteBuffer = codec.getInputBuffer(index) ?: return
                buf.clear()
                buf.put(nal)
                codec.queueInputBuffer(index, 0, nal.size, 0, 0)
            }

            override fun onOutputBufferAvailable(
                codec: MediaCodec,
                index: Int,
                info: MediaCodec.BufferInfo,
            ) {
                codec.releaseOutputBuffer(index, info.size > 0)
            }

            override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
                // Surfaced to Dart only via logcat for now - no error channel wired up yet.
                android.util.Log.e("VideoShim", "codec error: ${e.diagnosticInfo}")
            }

            override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {}
        }, handler)
        c.configure(format, surface, null, 0)
        c.start()
        codec = c
        configured = true
        result.success(e.id())
    }

    private fun feedNal(nal: ByteArray) {
        if (!configured) return
        val withStartCode = startCode + nal
        synchronized(pending) {
            pending.add(withStartCode)
            // Bound memory if Dart feeds faster than the decoder drains (shouldn't happen in
            // steady state, but a stalled decoder must not grow this unboundedly).
            while (pending.size > 300) pending.poll()
        }
    }

    private fun release() {
        configured = false
        try {
            codec?.stop()
        } catch (_: IllegalStateException) {
            // Already stopped/never started.
        }
        codec?.release()
        codec = null
        thread?.quitSafely()
        thread = null
        handler = null
        synchronized(pending) { pending.clear() }
        entry?.release()
        entry = null
    }

    fun close() = release()
}
