package au.awto.dji.awto_dji_app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

class MainActivity : FlutterActivity() {
    private var shim: AoaShim? = null
    private var videoShim: VideoShim? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        shim = AoaShim(this, flutterEngine.dartExecutor.binaryMessenger)
        videoShim = VideoShim(flutterEngine.renderer, flutterEngine.dartExecutor.binaryMessenger)
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        shim?.close()
        videoShim?.close()
        super.cleanUpFlutterEngine(flutterEngine)
    }
}
