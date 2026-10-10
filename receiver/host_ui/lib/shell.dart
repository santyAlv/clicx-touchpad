import 'package:flutter/cupertino.dart';

import 'control_client.dart';
import 'screens/deck_screen.dart';
import 'screens/home_screen.dart';
import 'screens/options_screen.dart';
import 'theme.dart';
import 'widgets.dart';

/// Two-pane desktop shell — a persistent left rail plus content, the way a
/// native Mac/Windows app is laid out (not a mobile bottom tab bar).
class AppShell extends StatefulWidget {
  final ControlClient client;
  const AppShell({super.key, required this.client});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int section = 0;

  @override
  Widget build(BuildContext context) {
    final content = switch (section) {
      0 => HomeScreen(client: widget.client),
      1 => DeckScreen(client: widget.client),
      _ => OptionsScreen(client: widget.client),
    };
    return Column(
      children: [
        const AppTitleBar(title: 'ClicX Host'),
        Expanded(
          child: Row(
            children: [
              _Sidebar(
                client: widget.client,
                section: section,
                onSelect: (i) => setState(() => section = i),
              ),
              Expanded(child: content),
            ],
          ),
        ),
      ],
    );
  }
}

class _Sidebar extends StatelessWidget {
  final ControlClient client;
  final int section;
  final ValueChanged<int> onSelect;
  const _Sidebar({
    required this.client,
    required this.section,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 220,
      decoration: BoxDecoration(
        color: AppColors.bg,
        border: Border(right: BorderSide(color: AppColors.border, width: 1)),
      ),
      child: SafeArea(
        right: false,
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(22, 16, 20, 14),
              child: Row(
                children: [
                  Icon(CupertinoIcons.dot_radiowaves_left_right,
                      color: AppColors.accent, size: 16),
                  const SizedBox(width: 7),
                  Text(
                    'ClicX',
                    style: TextStyle(
                      color: AppColors.fg,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
            _NavRow(
              icon: CupertinoIcons.antenna_radiowaves_left_right,
              label: 'Conectar',
              selected: section == 0,
              onTap: () => onSelect(0),
            ),
            _NavRow(
              icon: CupertinoIcons.square_grid_2x2_fill,
              label: 'Deck',
              selected: section == 1,
              onTap: () => onSelect(1),
            ),
            _NavRow(
              icon: CupertinoIcons.slider_horizontal_3,
              label: 'Opciones',
              selected: section == 2,
              onTap: () => onSelect(2),
            ),
            const Spacer(),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
              child: ListenableBuilder(
                listenable: client,
                builder: (context, _) => Row(
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: client.connected && client.running
                            ? AppColors.ok
                            : AppColors.dim,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      client.connected
                          ? (client.running ? 'Activo' : 'Detenido')
                          : 'Sin backend',
                      style: TextStyle(
                        color: AppColors.muted,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool selected;
  final VoidCallback onTap;
  const _NavRow({
    required this.icon,
    required this.label,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
      child: GestureDetector(
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
          decoration: BoxDecoration(
            color: selected ? AppColors.accent : CupertinoColors.transparent,
            borderRadius: BorderRadius.circular(7),
          ),
          child: Row(
            children: [
              Icon(
                icon,
                size: 15,
                color: selected ? AppColors.bg : AppColors.muted,
              ),
              const SizedBox(width: 9),
              Text(
                label,
                style: TextStyle(
                  color: selected ? AppColors.bg : AppColors.muted,
                  fontSize: 13,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
