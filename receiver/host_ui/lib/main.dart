import 'package:flutter/cupertino.dart';

import 'control_client.dart';
import 'screens/add_button_window.dart';
import 'shell.dart';
import 'theme.dart';

/// `--add-button` launches the same executable as the "add a button" window,
/// a separate OS window rather than a modal over the main one. Both processes
/// talk to the same host over the control socket, so the deck stays in sync.
void main(List<String> args) {
  runApp(ClicxApp(addButtonWindow: args.contains('--add-button')));
}

class ClicxApp extends StatefulWidget {
  final bool addButtonWindow;
  const ClicxApp({super.key, this.addButtonWindow = false});

  @override
  State<ClicxApp> createState() => _ClicxAppState();
}

class _ClicxAppState extends State<ClicxApp> {
  final client = ControlClient();

  @override
  void dispose() {
    client.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Rebuild everything when the accent changes, since AppColors.accent is
    // read directly rather than through the theme.
    return ValueListenableBuilder<Color>(
      valueListenable: accentNotifier,
      builder: (context, _, _) => CupertinoApp(
        title: widget.addButtonWindow ? 'Agregar botón' : 'ClicX',
        debugShowCheckedModeBanner: false,
        theme: appCupertinoTheme,
        home: CupertinoPageScaffold(
          backgroundColor: AppColors.bg,
          child: widget.addButtonWindow
              ? AddButtonWindow(client: client)
              : AppShell(client: client),
        ),
      ),
    );
  }
}
