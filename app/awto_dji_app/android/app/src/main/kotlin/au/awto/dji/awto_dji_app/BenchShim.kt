package au.awto.dji.awto_dji_app

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbManager
import android.os.BatteryManager
import io.flutter.plugin.common.BinaryMessenger
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File

/**
 * Read-only status queries for the bench app (lib/bench). No USB I/O, no side effects.
 * Compile-checked only; untested on a phone.
 */
class BenchShim(private val ctx: Context, messenger: BinaryMessenger) :
    MethodChannel.MethodCallHandler {

    private val usb = ctx.getSystemService(Context.USB_SERVICE) as UsbManager

    init {
        MethodChannel(messenger, "au.awto.dji/bench").setMethodCallHandler(this)
    }

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "usbInfo" -> result.success(usbInfo())
            "power" -> result.success(power())
            "logDir" -> result.success(ctx.getExternalFilesDir(null)?.absolutePath)
            else -> result.notImplemented()
        }
    }

    // Serial/description getters can throw SecurityException without permission on newer
    // Android; each field is read on its own so one denial does not blank the rest.
    private fun <T> safe(f: () -> T?): T? = try { f() } catch (_: Exception) { null }

    private fun usbInfo(): Map<String, Any?> {
        val acc = usb.accessoryList?.let { l ->
            l.firstOrNull { it.manufacturer == "DJI" && it.model == "T600" } ?: l.firstOrNull()
        }
        return mapOf(
            "attached" to (acc != null),
            "manufacturer" to safe { acc?.manufacturer },
            "model" to safe { acc?.model },
            "description" to safe { acc?.description },
            "version" to safe { acc?.version },
            "uri" to safe { acc?.uri },
            "serial" to safe { acc?.serial },
            "permission" to (acc != null && usb.hasPermission(acc)),
            // UsbAccessory exposes no endpoint info: always null, speed is inferred elsewhere.
            "maxPacket" to null,
            "udcSpeed" to udcSpeed(),
        )
    }

    // Best effort: /sys/class/udc/<udc>/current_speed is world-readable on some kernels
    // and blocked by SELinux on others.
    private fun udcSpeed(): String? = safe {
        File("/sys/class/udc").listFiles()
            ?.firstNotNullOfOrNull { d ->
                safe { File(d, "current_speed").readText().trim() }?.takeIf { it.isNotEmpty() }
            }
    }

    private fun power(): Map<String, Any?> {
        val i: Intent? = ctx.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val plugged = when (i?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) {
            BatteryManager.BATTERY_PLUGGED_USB -> "usb"
            BatteryManager.BATTERY_PLUGGED_AC -> "ac"
            BatteryManager.BATTERY_PLUGGED_WIRELESS -> "wireless"
            else -> "none"
        }
        val charging = when (i?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1) {
            BatteryManager.BATTERY_STATUS_CHARGING -> "charging"
            BatteryManager.BATTERY_STATUS_DISCHARGING -> "discharging"
            BatteryManager.BATTERY_STATUS_FULL -> "full"
            BatteryManager.BATTERY_STATUS_NOT_CHARGING -> "not_charging"
            else -> "unknown"
        }
        val bm = ctx.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val current = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CURRENT_NOW)
        return mapOf(
            "plugged" to plugged,
            "charging" to charging,
            "voltageMv" to i?.getIntExtra(BatteryManager.EXTRA_VOLTAGE, -1)?.takeIf { it >= 0 },
            // Int.MIN_VALUE = not supported by this device.
            "currentUa" to current.takeIf { it != Int.MIN_VALUE },
        )
    }
}
