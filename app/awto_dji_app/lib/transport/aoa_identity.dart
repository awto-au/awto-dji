/// Android Open Accessory identity, the ONLY place it is defined.
///
/// Only `manufacturer`/`model` matter and both are confirmed: the RC (USB host)
/// presents them to the phone during the AOA handshake, and Android's framework
/// uses them to match `android/app/src/main/res/xml/accessory_filter.xml` and to
/// populate the `UsbAccessory` object apps query. DJI GO 4's own connection code
/// (`dji.midware.usb.P3.DJIUsbAccessoryReceiver`, confirmed via runtime unpack,
/// docs/apk-analysis.md) checks exactly these two fields and nothing else:
/// `usbAccessory.getModel() == "T600" && usbAccessory.getManufacturer() == "DJI"`.
/// Our Kotlin shim (`AoaShim.connect`) matches that logic.
///
/// `description`/`version`/`uri`/`serial` are NOT something an accessory (the
/// phone) declares — they are the HOST's (the RC's) own descriptor strings,
/// read at runtime via `UsbAccessory.getDescription()` etc. if ever needed.
/// DJI's own app never reads them either (confirmed: no call site in
/// DJIUsbAccessoryReceiver or elsewhere in the decompiled USB code), so there
/// is nothing to "confirm from the APK" for them - an earlier version of this
/// file carried placeholder constants for them, which was the wrong shape.
class AoaIdentity {
  static const String manufacturer = 'DJI';
  static const String model = 'T600';
}
