import 'package:flutter/cupertino.dart';

import '../color_picker.dart';
import '../control_client.dart';
import '../theme.dart';
import '../widgets.dart';

/// Host-wide settings. The accent lives in deck.json alongside the buttons, so
/// changing it here reaches the phone through the same deck sync.
class OptionsScreen extends StatelessWidget {
  final ControlClient client;
  const OptionsScreen({super.key, required this.client});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: AppColors.bg,
      child: SafeArea(
        child: Column(
          children: [
            const PaneHeader(title: 'Opciones'),
            Expanded(
              child: ListenableBuilder(
                listenable: client,
                builder: (context, _) => ListView(
                  padding: const EdgeInsets.fromLTRB(22, 4, 22, 22),
                  children: [
                    _AccentCard(client: client),
                    const SizedBox(height: 14),
                    _FoldersCard(client: client),
                    const SizedBox(height: 14),
                    _ClipboardCard(client: client),
                    const SizedBox(height: 14),
                    _CapabilitiesCard(client: client),
                    const SizedBox(height: 14),
                    _AboutCard(client: client),
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


class _AccentCard extends StatelessWidget {
  final ControlClient client;
  const _AccentCard({required this.client});

  @override
  Widget build(BuildContext context) {
    return SettingsGroup(
      title: 'Color de la app',
      children: [
        SettingsRow(
          label: 'Presets',
          below: Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final hex in accentSwatches)
                _Swatch(
                  hex: hex,
                  selected: hex.toUpperCase() == client.accent.toUpperCase(),
                  onTap: () => client.setAccent(hex),
                ),
            ],
          ),
        ),
        SettingsRow(
          label: 'Personalizado',
          below: ColorPicker(
            value: parseHexColor(client.accent),
            // Follow the drag locally, then persist once on release.
            onPreview: (color) => accentNotifier.value = color,
            onChanged: (color) => client.setAccent(hexOf(color)),
          ),
        ),
        SettingsRow(
          label: 'Sincronización',
          value: 'El teléfono lo recibe con el deck',
        ),
      ],
    );
  }
}

class _Swatch extends StatelessWidget {
  final String hex;
  final bool selected;
  final VoidCallback onTap;
  const _Swatch({
    required this.hex,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: parseHexColor(hex),
          borderRadius: BorderRadius.circular(11),
          border: Border.all(
            color: selected
                ? CupertinoColors.white
                : CupertinoColors.white.withValues(alpha: 0.10),
            width: selected ? 2.5 : 1,
          ),
        ),
        child: selected
            ? Icon(
                CupertinoIcons.check_mark,
                size: 18,
                color: glyphColorOn(parseHexColor(hex)),
              )
            : null,
      ),
    );
  }
}

class _AboutCard extends StatelessWidget {
  final ControlClient client;
  const _AboutCard({required this.client});

  @override
  Widget build(BuildContext context) {
    return SettingsGroup(
      title: 'Host',
      children: [
        SettingsRow(
          label: 'Versión',
          value: client.version.isEmpty ? '—' : client.version,
        ),
        SettingsRow(
          label: 'Dirección',
          value: client.url.isEmpty ? '—' : client.url,
        ),
        SettingsRow(label: 'Clientes', value: '${client.clients}'),
      ],
    );
  }
}


/// Where file transfers land on the host. The paths come from
/// file_transfer.transfer_dir, so they always match what the phone uses.
class _FoldersCard extends StatelessWidget {
  final ControlClient client;
  const _FoldersCard({required this.client});

  @override
  Widget build(BuildContext context) {
    return SettingsGroup(
      title: 'Carpetas de archivos',
      children: [
        SettingsRow(
          label: 'From Phone',
          value: client.fromPhoneDir.isEmpty ? '—' : client.fromPhoneDir,
          trailing: PillButton(
            label: 'Abrir',
            onPressed: () => client.openFolder('fromPhone'),
          ),
        ),
        SettingsRow(
          label: 'From PC',
          value: client.fromPcDir.isEmpty ? '—' : client.fromPcDir,
          trailing: PillButton(
            label: 'Abrir',
            onPressed: () => client.openFolder('fromPc'),
          ),
        ),
        if (client.folderError case final err?)
          SettingsRow(label: 'Error', value: err),
      ],
    );
  }
}


/// Shared clipboard, metadata only. The host deliberately never hands the UI
/// the clipboard text, so this answers "is sync running?" without leaking it.
class _ClipboardCard extends StatefulWidget {
  final ControlClient client;
  const _ClipboardCard({required this.client});

  @override
  State<_ClipboardCard> createState() => _ClipboardCardState();
}

class _ClipboardCardState extends State<_ClipboardCard> {
  @override
  void initState() {
    super.initState();
    widget.client.requestClipboardHistory();
  }

  @override
  Widget build(BuildContext context) {
    final items = widget.client.clipboardHistory;
    return SettingsGroup(
      title: 'Portapapeles compartido',
      children: [
        SettingsRow(
          label: 'Historial',
          value: items.isEmpty ? 'Vacío' : '${items.length} entradas',
          trailing: PillButton(
            label: 'Actualizar',
            onPressed: widget.client.requestClipboardHistory,
          ),
        ),
        for (final entry in items.take(8))
          SettingsRow(
            label: _clock(entry.at),
            value: '${entry.length} caracteres',
          ),
        SettingsRow(
          label: 'Contenido',
          value: 'El host nunca lo muestra acá',
          trailing: PillButton(
            label: 'Vaciar',
            onPressed: items.isEmpty ? null : widget.client.clearClipboardHistory,
          ),
        ),
      ],
    );
  }

  static String _clock(DateTime t) {
    String two(int n) => n.toString().padLeft(2, '0');
    return '${two(t.hour)}:${two(t.minute)}:${two(t.second)}';
  }
}

/// What this host can actually serve, straight from protocol.HOST_FEATURES.
/// A domain that reads "No" here is why the phone hides that screen.
class _CapabilitiesCard extends StatelessWidget {
  final ControlClient client;
  const _CapabilitiesCard({required this.client});

  static const _labels = {
    'touchpad': 'Touchpad',
    'keyboard': 'Teclado',
    'deck': 'Stream Deck',
    'volume_general': 'Volumen general',
    'windows': 'Ventanas',
    'app_volume': 'Volumen por app',
    'status': 'Estado del sistema',
    'actions': 'Acciones',
    'media': 'Multimedia',
    'clipboard': 'Portapapeles',
    'file': 'Archivos',
    'screen': 'Pantalla',
    'gesture_custom': 'Gestos propios',
    'scenes': 'Escenas',
    'profiles': 'Perfiles',
    'auth': 'Autenticación',
  };

  @override
  Widget build(BuildContext context) {
    final domains = client.domains;
    return SettingsGroup(
      title: 'Protocolo y capacidades',
      children: [
        SettingsRow(
          label: 'Versión del protocolo',
          value: client.protocol.isEmpty ? '—' : 'v${client.protocol}',
        ),
        for (final entry in _labels.entries)
          if (domains.containsKey(entry.key))
            SettingsRow(
              label: entry.value,
              leading: _Dot(on: domains[entry.key] ?? false),
              value: (domains[entry.key] ?? false) ? 'Sí' : 'No',
            ),
      ],
    );
  }
}

class _Dot extends StatelessWidget {
  final bool on;
  const _Dot({required this.on});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(
        color: on ? AppColors.ok : AppColors.dim,
        shape: BoxShape.circle,
      ),
    );
  }
}
