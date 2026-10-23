/// Android Open Accessory identity strings, the ONLY place they are defined.
/// PLACEHOLDER: fill from docs/apk-analysis.md; keep the manifest filter in
/// android/app/src/main/res/xml/accessory_filter.xml in sync by hand.
class AoaIdentity {
  /// From the DJI app manifest filter (docs): "DJI" / "T600".
  static const String manufacturer = 'DJI';
  static const String model = 'T600';

  /// PLACEHOLDER: not yet confirmed from the APK analysis.
  static const String description = 'PLACEHOLDER-description';
  static const String version = 'PLACEHOLDER-version';
  static const String uri = 'PLACEHOLDER-uri';
  static const String serial = 'PLACEHOLDER-serial';

  /// Flip to true once description/version/uri/serial are confirmed.
  static const bool verified = false;
}
