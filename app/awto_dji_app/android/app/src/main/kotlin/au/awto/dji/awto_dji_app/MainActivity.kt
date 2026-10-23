package au.awto.dji.awto_dji_app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Dev-only launch args, set via `adb shell am start ... --es relay HOST:PORT --ez autoconnect
 * true` instead of typing into the on-screen Connect form every time:
 *   adb shell am start -n au.awto.dji.awto_dji_app/.MainActivity \
 *       --es relay 192.168.25.114:9900 --ez autoconnect true
 */
class MainActivity : FlutterActivity() {
    private var shim: AoaShim? = null
    private var videoShim: VideoShim? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        shim = AoaShim(this, flutterEngine.dartExecutor.binaryMessenger)
        videoShim = VideoShim(flutterEngine.renderer, flutterEngine.dartExecutor.binaryMessenger)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "au.awto.dji/launchargs")
            .setMethodCallHandler { call, result ->
                if (call.method == "get") {
                    result.success(mapOf(
                        "relay" to intent.getStringExtra("relay"),
                        "autoConnect" to intent.getBooleanExtra("autoconnect", false),
                    ))
                } else {
                    result.notImplemented()
                }
            }
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        shim?.close()
        videoShim?.close()
        super.cleanUpFlutterEngine(flutterEngine)
    }
}
