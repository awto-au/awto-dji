import 'package:flutter/material.dart';

import '../link/link_host.dart';
import 'link_host_screen.dart';

class AwtoDjiApp extends StatefulWidget {
  const AwtoDjiApp({super.key});

  @override
  State<AwtoDjiApp> createState() => _AwtoDjiAppState();
}

class _AwtoDjiAppState extends State<AwtoDjiApp> {
  final _host = LinkHost();

  @override
  void dispose() {
    _host.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'awto-dji',
        theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
        darkTheme: ThemeData(
            colorSchemeSeed: Colors.indigo,
            brightness: Brightness.dark,
            useMaterial3: true),
        home: LinkHostScreen(host: _host),
      );
}
