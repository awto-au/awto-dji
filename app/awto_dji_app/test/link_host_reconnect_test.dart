import 'dart:typed_data';

import 'package:awto_dji_app/link/link_host.dart';
import 'package:awto_dji_app/transport/link_transport.dart';
import 'package:flutter_test/flutter_test.dart';

class TestTransport extends BaseTransport {
  TestTransport({this.fail = false});
  final bool fail;
  @override
  String get name => 'test-accessory';
  @override
  Future<void> connect() async => setState(
    fail ? LinkState.failed : LinkState.connected,
    error: fail ? 'no accessory' : null,
  );
  @override
  Future<void> disconnect() async => setState(LinkState.disconnected);
  @override
  Future<void> write(Uint8List data) async {}
}

void main() {
  test(
    'hot unplug retries with settings; manual disconnect cancels retry',
    () async {
      final transports = <TestTransport>[];
      final settings = <Map<String, String>>[];
      final host = LinkHost(
        reconnectDelay: const Duration(milliseconds: 20),
        transportFactory: (source, extras) async {
          settings.add(Map.of(extras));
          final t = TestTransport();
          transports.add(t);
          return t;
        },
      );
      await host.connect({
        'relay': '192.0.2.1:9900',
        'protection': 'simple',
        'relayVideo': 'false',
      });
      transports.first.setState(LinkState.disconnected);
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await Future<void>.delayed(Duration.zero);
      expect(transports, hasLength(2));
      expect(settings.last, settings.first);
      expect(host.session!.transport, transports.last);
      transports.last.setState(LinkState.failed, error: 'unplug');
      await Future<void>.delayed(Duration.zero);
      await host.disconnect();
      await Future<void>.delayed(const Duration(milliseconds: 100));
      expect(transports, hasLength(2));
      expect(host.session, isNull);
      host.dispose();
      await Future<void>.delayed(Duration.zero);
    },
  );

  test(
    'absent accessory retries; USB attach preserves configured relay',
    () async {
      final transports = <TestTransport>[];
      final settings = <Map<String, String>>[];
      final host = LinkHost(
        reconnectDelay: const Duration(milliseconds: 20),
        transportFactory: (source, extras) async {
          settings.add(Map.of(extras));
          final t = TestTransport(fail: transports.isEmpty);
          transports.add(t);
          return t;
        },
      );
      await host.connect({'relay': '192.0.2.5:9900', 'protection': 'auto'});
      expect(host.session, isNull);
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await Future<void>.delayed(Duration.zero);
      expect(transports, hasLength(2));
      expect(host.session, isNotNull);
      await host.handle(
        'android.hardware.usb.action.USB_ACCESSORY_ATTACHED',
        {},
      );
      expect(settings.last['relay'], '192.0.2.5:9900');
      await host.handle('android.intent.action.MAIN', {});
      expect(settings.last['relay'], '192.0.2.5:9900');
      await host.disconnect();
      host.dispose();
      await Future<void>.delayed(Duration.zero);
    },
  );
}
