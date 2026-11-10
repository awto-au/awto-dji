import 'package:flutter/material.dart';

import 'bench/bench_app.dart';
import 'ui/app.dart';

/// `flutter build apk --debug --dart-define=BENCH=true` builds the generic AOA bench app
/// (same package id as the DJI app); without it, the DJI app.
void main() => runApp(
  const bool.fromEnvironment('BENCH') ? const BenchApp() : const AwtoDjiApp(),
);
