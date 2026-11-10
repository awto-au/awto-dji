import 'package:awto_dji_app/bench/bench_controller.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('on-screen log time is mm:ss.mmm', () {
    expect(BenchController.elapsed(const Duration(milliseconds: 0)), '00:00.000');
    expect(BenchController.elapsed(const Duration(milliseconds: 1234)), '00:01.234');
    expect(BenchController.elapsed(const Duration(minutes: 3, seconds: 21, milliseconds: 5)), '03:21.005');
    expect(BenchController.elapsed(const Duration(minutes: 61, seconds: 1)), '61:01.000');
  });
}
