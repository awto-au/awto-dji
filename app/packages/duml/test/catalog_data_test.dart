import 'package:duml/src/generated/catalog_data.dart';
import 'package:test/test.dart';

/// Verifies the generated canonical catalog (scripts/duml_catalog_gen_dart.py from
/// docs/data/duml-catalog.json) — the single source of truth for DUML commands (#102).
void main() {
  test('cmdsets include the known DJI CmdSet enums', () {
    expect(dumlCmdSets[0x00], 'COMMON'); // authoritative CmdSet enum (apk-cmdset-devicetype.tsv)
    expect(dumlCmdSets[0x02], 'CAMERA');
    expect(dumlCmdSets.length, greaterThanOrEqualTo(8));
  });

  test('catalog is non-empty and entries are well-formed', () {
    expect(dumlCatalog.length, greaterThan(40));
    for (final e in dumlCatalog) {
      expect(e.name, isNotNull);
      expect(e.sources, isNotEmpty);
    }
  });

  test('Get Version is 0x00/0x01 and corroborated by apk+dll', () {
    final gv = dumlCatalog.firstWhere(
      (e) => e.cmdSet == 0x00 && e.cmdId == 0x01,
    );
    expect(gv.name, contains('Version'));
    expect(gv.sources, containsAll(<String>['apk', 'dll']));
  });
}
