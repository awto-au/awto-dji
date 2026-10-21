# Native library analysis (DJI app)

What each native `.so` in the DJI app actually does, read from the binaries in the
env (ELF headers, dependencies, exported symbols, build strings). Goal: understand the
app's architecture so we know what must be reimplemented and what is irrelevant to
direct control. No secret/key *values* were extracted — only the structure and roles.

All libraries are 32-bit ARM (`armeabi-v7a`), built with NDK r10e.

## libmain.so — Unity loader (irrelevant to control)

20 KB. Strings: `com/unity3d/player/NativeLoader`, `libunity.so`, `Unsupported VM
version`, clang 3.6. It is just the **Unity engine bootstrap** for the app's 3D UI
(academy / visualisation). No protocol, no transport. Ignore.

## libduml_vision_bokeh.so / libduml_vision_panorama.so — OpenCV image processing

8.4 MB / 6.8 MB. Built on **OpenCV 3.0.0** (build path leaks `…/opencv-3.0.0/…`),
NEON + OpenMP. Panorama links the OpenCV `stitching`/`calib3d`/`features2d` modules and
exposes a `dji_pano` namespace (`mission_planer_pano_t::calc`, `mission_sphere_pano_t`).
Bokeh is depth/segmentation blur.

The `duml_` prefix is DJI's product branding ("DUML vision"), **not** the DUML control
protocol. These are pure photo processing — no flight, no telemetry, no transport.
Ignore for control.

## libSDKRelativeJNI.so — config / secrets / activation / video bridge

180 KB. The only one of the four that matters, and it is **not** the control codec
either. Dynamically registers its JNI methods (`JNI_OnLoad`, no exported `Java_`
symbols). Links `libdjivideo.so` + GLES (the video-decode path) and uses JsonCpp to
parse server config.

Its native methods are a vault of **endpoints and keys** hidden in native code:
`native_getServerUrl`, `native_getUpgradeUrls*`, `native_isSDKActivated`,
`native_startRegistration`, `native_getDbEncryptionAc`, `native_getRequestKey`, and a
cluster for geofence data: `native_getGeoNoFlyZonesUrl`, `native_getGeoAirmapDataUrl`,
`native_getGeoAirmapApiKey`, `native_getGeoAirmapUuid`, `native_getGeoFlyForbidUrl`,
`native_getGeoSignatureKey`, plus `airmap.zip`.

One endpoint is in cleartext:

```
http://flysafe.aasky.net/api/v3/geofence/sdk_static_data
```

That is DJI's **FlySafe geofence static-data feed** — the source the app downloads
no-fly zones from. (The AES/API/signature *keys* are present but their values were not
extracted; harvesting vendor credentials is out of scope and unnecessary.)

## What this tells us for the direct app

1. **Control/telemetry DUML is not in these native libs.** It lives in the Java
   midware (`dji.midware.*`, already verified in `protocol-verification.md`). The
   native layer is Unity UI, OpenCV vision, and this config/video blob.
2. **The transport is AOA**, handled by `libSDKRelativeJNI` (video) together with the
   Java `dji/midware/usb/P3/UsbAccessoryService`.
3. **No-fly zones are downloadable data, not binary logic.** The app fetches them from
   a FlySafe/AirMap feed. This is exactly what our `geofence` safety gate consumes — so
   the right way to get zones is the public FlySafe/AirMap/CASA feeds, which also
   settles why reverse-engineering `libFlyForbid.so` was never necessary.

Net: none of `libmain`, `libduml_vision_*`, or `libSDKRelativeJNI` is a blocker or a
source for the control protocol. The direct app needs the Java-layer DUML codec (done,
in Dart), the AOA transport shim, and public geofence data (gate done).
