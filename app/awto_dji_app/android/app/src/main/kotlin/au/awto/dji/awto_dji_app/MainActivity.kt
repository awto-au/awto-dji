package au.awto.dji.awto_dji_app

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * The app is driven by intents, with no on-screen connect form:
 *   adb shell am start -n au.awto.dji.awto_dji_app/.MainActivity \
 *       -a au.awto.dji.action.CONNECT --es relay 192.168.25.114:9900
 * Actions: CONNECT (source, relay, path, speed), DISCONNECT, GIMBAL (pitch, roll, yaw).
 */
class MainActivity : FlutterActivity() {
    private var shim: AoaShim? = null
    private var videoShim: VideoShim? = null
    private var intentChannel: MethodChannel? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        shim = AoaShim(this, flutterEngine.dartExecutor.binaryMessenger)
        videoShim = VideoShim(this, flutterEngine.renderer, flutterEngine.dartExecutor.binaryMessenger)

        intentChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "au.awto.dji/intents")
        intentChannel?.setMethodCallHandler { call, result ->
            if (call.method == "get") result.success(intentToMap(intent)) else result.notImplemented()
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        intentChannel?.invokeMethod("onIntent", intentToMap(intent))
    }

    private fun intentToMap(i: Intent): Map<String, Any?> {
        val extras = i.extras?.keySet()?.associateWith { i.extras?.get(it)?.toString() } ?: emptyMap()
        return mapOf("action" to i.action, "extras" to extras)
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        shim?.close()
        videoShim?.close()
        super.cleanUpFlutterEngine(flutterEngine)
    }
}
