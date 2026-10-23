import 'package:flutter/material.dart';

import 'connect_screen.dart';

class AwtoDjiApp extends StatelessWidget {
  const AwtoDjiApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'awto-dji',
        theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
        darkTheme: ThemeData(
            colorSchemeSeed: Colors.indigo,
            brightness: Brightness.dark,
            useMaterial3: true),
        home: const ConnectScreen(),
      );
}
