import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../control_client.dart';
import '../theme.dart';
import '../widgets.dart';

class HomeScreen extends StatelessWidget {
  final ControlClient client;
  const HomeScreen({super.key, required this.client});

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: AppColors.bg,
      child: SafeArea(
        child: Column(
          children: [
            const PaneHeader(title: 'Conectar'),
            Expanded(
              child: ListenableBuilder(
                listenable: client,
                builder: (context, _) => ListView(
                  padding: const EdgeInsets.fromLTRB(22, 4, 22, 24),
                  children: [
                    _statusGroup(),
                    const SizedBox(height: 22),
                    _pairingGroup(context),
                    const SizedBox(height: 22),
                    _activityGroup(),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statusGroup() {
    final live = client.connected && client.running;
    return SettingsGroup(
      title: 'Host',
      children: [
        SettingsRow(
          label: 'Servidor',
          leading: _Dot(on: live),
          value: !client.connected
              ? 'Sin backend'
              : (live ? 'Activo' : 'Detenido'),
          trailing: CupertinoSwitch(
            value: client.running,
            activeTrackColor: AppColors.accent,
            onChanged: client.connected
                ? (on) => on ? client.start() : client.stop()
                : null,
          ),
        ),
        SettingsRow(
          label: 'Clientes',
          value: client.clients == 1 ? '1 conectado' : '${client.clients} conectados',
        ),
        SettingsRow(
          label: 'USB',
          value: client.usbError ?? (client.usbActive ? 'adb reverse activo' : 'Por cable'),
          trailing: CupertinoSwitch(
            value: client.usbActive,
            activeTrackColor: AppColors.accent,
            onChanged: client.connected
                ? (on) => on ? client.usbOn() : client.usbOff()
                : null,
          ),
        ),
      ],
    );
  }

  static const _kindIcon = {
    'bluetooth': CupertinoIcons.bluetooth,
    'wifi': CupertinoIcons.wifi,
    'ethernet': CupertinoIcons.desktopcomputer,
  };

  Widget _pairingGroup(BuildContext context) {
    final active = client.activeAddress;
    final payload =
        active != null ? client.payloadFor(active) : client.connectPayload;
    final url = active != null ? 'ws://${active.ip}:${client.port}' : client.url;
    final hasInfo = payload.isNotEmpty;
    return SettingsGroup(
      title: 'Emparejar',
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 18),
          child: Column(
            children: [
              if (hasInfo)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: CupertinoColors.white,
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: QrImageView(
                    data: payload,
                    size: 168,
                    backgroundColor: CupertinoColors.white,
                  ),
                )
              else
                SizedBox(
                  height: 192,
                  child: Center(
                    child: CupertinoActivityIndicator(color: AppColors.muted),
                  ),
                ),
              const SizedBox(height: 16),
              Text(
                'Abrí ClicX en el teléfono y escaneá este código.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.fg, fontSize: 13),
              ),
              const SizedBox(height: 3),
              Text(
                'Misma red — o por USB o Bluetooth.',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.muted, fontSize: 12),
              ),
            ],
          ),
        ),
        SettingsRow(
          label: 'Dirección',
          value: hasInfo ? url : '—',
          trailing: hasInfo
              ? _LinkButton(
                  label: 'Copiar',
                  onTap: () => Clipboard.setData(ClipboardData(text: url)),
                )
              : null,
        ),
        // A phone tethered over Bluetooth, or plugged into a second NIC, shares a
        // different link than Wi-Fi — the QR has to point at that one instead.
        if (client.addresses.length > 1)
          SettingsRow(
            label: 'Conexión',
            below: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final address in client.addresses)
                  _AddressOption(
                    address: address,
                    icon: _kindIcon[address.kind] ?? CupertinoIcons.link,
                    selected: address.ip == active?.ip,
                    onTap: () => client.pickAddress(address.ip),
                  ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _activityGroup() {
    final lines = client.logLines.reversed.take(40).toList();
    return SettingsGroup(
      title: 'Actividad',
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
          child: SizedBox(
            height: 180,
            child: lines.isEmpty
                ? Center(
                    child: Text(
                      'Sin actividad todavía',
                      style: TextStyle(color: AppColors.dim, fontSize: 13),
                    ),
                  )
                : ListView.builder(
                    itemCount: lines.length,
                    itemBuilder: (context, i) => Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: Text(
                        lines[i],
                        style: TextStyle(
                          color: AppColors.muted,
                          fontSize: 12,
                          fontFamily: 'monospace',
                        ),
                      ),
                    ),
                  ),
          ),
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

class _LinkButton extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _LinkButton({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Text(
        label,
        style: TextStyle(color: AppColors.accent, fontSize: 13),
      ),
    );
  }
}


class _AddressOption extends StatelessWidget {
  final HostAddress address;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  const _AddressOption({
    required this.address,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: selected ? AppColors.surface2 : null,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: selected ? AppColors.accent : AppColors.border,
            width: selected ? 1.5 : 1,
          ),
        ),
        child: Row(
          children: [
            Icon(icon, size: 16, color: selected ? AppColors.accent : AppColors.muted),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                address.label,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: AppColors.fg, fontSize: 13),
              ),
            ),
            Text(
              address.ip,
              style: TextStyle(color: AppColors.muted, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}
