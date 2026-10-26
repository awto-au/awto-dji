package au.awto.dji.awto_dji_app

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbAccessory
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.util.Log
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.FileInputStream
import java.io.FileOutputStream

/**
 * Raw byte pump between the UsbAccessory and Dart. No protocol logic.
 * The identity (manufacturer/model) comes from Dart (aoa_identity.dart).
 * Compile-checked only; untested without the RC.
 */
class AoaShim(private val ctx: Context, messenger: BinaryMessenger) :
    MethodChannel.MethodCallHandler, EventChannel.StreamHandler {

    private val usb = ctx.getSystemService(Context.USB_SERVICE) as UsbManager
    private val main = Handler(Looper.getMainLooper())
    private var sink: EventChannel.EventSink? = null
    private var pfd: ParcelFileDescriptor? = null
    private var input: FileInputStream? = null
    private var output: FileOutputStream? = null
    private var reader: Thread? = null
    private var permReceiver: BroadcastReceiver? = null
    @Volatile private var generation = 0L

    init {
        MethodChannel(messenger, "au.awto.dji/aoa").setMethodCallHandler(this)
        EventChannel(messenger, "au.awto.dji/aoa/bytes").setStreamHandler(this)
    }

    override fun onListen(args: Any?, events: EventChannel.EventSink) { sink = events }
    override fun onCancel(args: Any?) { sink = null }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "connect" -> connect(
                call.argument<String>("manufacturer"),
                call.argument<String>("model"),
                result,
            )
            "write" -> {
                val data = call.arguments as? ByteArray
                val out = output
                if (data == null || out == null) {
                    result.error("not_open", "accessory not open", null)
                } else try {
                    out.write(data)
                    result.success(null)
                } catch (e: java.io.IOException) {
                    result.error("io", e.message, null)
                }
            }
            "disconnect" -> { closeAccessory(); result.success(null) }
            else -> result.notImplemented()
        }
    }

    private fun connect(manufacturer: String?, model: String?, result: MethodChannel.Result) {
        val acc = usb.accessoryList?.firstOrNull {
            it.manufacturer == manufacturer && it.model == model
        }
        if (acc == null) {
            result.error("no_accessory", "no accessory $manufacturer/$model attached", null)
        } else if (usb.hasPermission(acc)) {
            open(acc, result)
        } else {
            requestPermission(acc, result)
        }
    }

    private fun requestPermission(acc: UsbAccessory, result: MethodChannel.Result) {
        val action = "${ctx.packageName}.USB_PERMISSION"
        val rx = object : BroadcastReceiver() {
            override fun onReceive(c: Context, i: Intent) {
                ctx.unregisterReceiver(this)
                permReceiver = null
                if (i.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)) {
                    open(acc, result)
                } else {
                    result.error("permission", "USB accessory permission denied", null)
                }
            }
        }
        permReceiver = rx
        val filter = IntentFilter(action)
        if (Build.VERSION.SDK_INT >= 33) {
            ctx.registerReceiver(rx, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            ctx.registerReceiver(rx, filter)
        }
        val flags = if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0
        val pi = PendingIntent.getBroadcast(ctx, 0, Intent(action).setPackage(ctx.packageName), flags)
        usb.requestPermission(acc, pi)
    }

    private fun open(acc: UsbAccessory, result: MethodChannel.Result) {
        val fd = usb.openAccessory(acc)
        if (fd == null) {
            result.error("open_failed", "openAccessory returned null", null)
            return
        }
        closeAccessory()
        pfd = fd
        input = FileInputStream(fd.fileDescriptor)
        output = FileOutputStream(fd.fileDescriptor)
        val stream = input!!
        val readerGeneration = generation
        reader = Thread {
            val buf = ByteArray(16384)
            try {
                while (true) {
                    val n = stream.read(buf)
                    if (n < 0) break
                    val chunk = buf.copyOf(n)
                    main.post { if (generation == readerGeneration) sink?.success(chunk) }
                }
            } catch (e: java.io.IOException) {
                main.post { if (generation == readerGeneration) sink?.error("io", e.message, null) }
            }
            main.post { if (generation == readerGeneration) sink?.endOfStream() }
        }.also { it.isDaemon = true; it.start() }
        result.success(null)
    }

    private fun closeAccessory() {
        generation++
        val oldReader = reader
        // input.close() first: closing the FileInputStream (not just the
        // ParcelFileDescriptor wrapper) is what reliably interrupts a thread
        // already blocked inside its read() call on this driver.
        try { input?.close() } catch (_: java.io.IOException) {}
        try { pfd?.close() } catch (_: java.io.IOException) {}
        pfd = null; input = null; output = null
        reader = null
        // A thread actually unblocked by the closes above returns in low
        // single-digit ms; 200ms is a ~20x margin. Past that it's not going to
        // return - it's a zombie still blocked reading the same accessory
        // device, silently competing with whatever reader opens next for the
        // RC's real data (see awto-dji#65). Logged so that's visible instead
        // of invisible, since there is no safe way to force-kill it.
        oldReader?.let {
            it.join(200)
            if (it.isAlive) {
                Log.w("AoaShim", "reader thread outlived close() by >200ms - " +
                    "likely a zombie still blocked in read(), may steal future accessory data")
            }
        }
    }

    fun close() {
        closeAccessory()
        permReceiver?.let { ctx.unregisterReceiver(it) }
        permReceiver = null
    }
}
