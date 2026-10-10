import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;

import '../control_client.dart';
import '../iconify.dart';
import '../models.dart';
import '../theme.dart';

enum SheetTab { apps, websites, hotkeys, commands }

SheetTab _tabForKind(String kind) => switch (kind) {
      'app' => SheetTab.apps,
      'url' => SheetTab.websites,
      'shell' => SheetTab.commands,
      _ => SheetTab.hotkeys,
    };

String _newId() => DateTime.now().microsecondsSinceEpoch.toRadixString(36);

/// A ready-made button offered in the "Sugerencias" list.
class _Suggestion {
  final String label;
  final String subtitle;
  final IconData icon;
  final String color;
  final DeckAction action;
  const _Suggestion(this.label, this.subtitle, this.icon, this.color, this.action);

  DeckButton toButton() => DeckButton(
        id: _newId(),
        label: label,
        color: color,
        action: action,
      );
}

final _hotkeySuggestions = <_Suggestion>[
  _Suggestion('Copiar', 'ctrl + c', Icons.content_copy_outlined, '#9CB080',
      DeckAction(kind: 'hotkey', keys: ['ctrl', 'c'])),
  _Suggestion('Pegar', 'ctrl + v', Icons.content_paste_outlined, '#9CB080',
      DeckAction(kind: 'hotkey', keys: ['ctrl', 'v'])),
  _Suggestion('Deshacer', 'ctrl + z', Icons.undo, '#9CB080',
      DeckAction(kind: 'hotkey', keys: ['ctrl', 'z'])),
  _Suggestion('Guardar', 'ctrl + s', Icons.save_outlined, '#30D158',
      DeckAction(kind: 'hotkey', keys: ['ctrl', 's'])),
  _Suggestion('Captura', 'win + shift + s', Icons.camera_alt_outlined, '#0A84FF',
      DeckAction(kind: 'hotkey', keys: ['win', 'shift', 's'])),
  _Suggestion('Escritorio', 'win + d', Icons.desktop_windows_outlined, '#0A84FF',
      DeckAction(kind: 'hotkey', keys: ['win', 'd'])),
  _Suggestion('Cambiar app', 'alt + tab', Icons.apps, '#64D2FF',
      DeckAction(kind: 'hotkey', keys: ['alt', 'tab'])),
  _Suggestion('Cerrar', 'alt + f4', Icons.close, '#FF453A',
      DeckAction(kind: 'hotkey', keys: ['alt', 'f4'])),
  _Suggestion('Subir volumen', 'volumen', Icons.volume_up_outlined, '#9CB080',
      DeckAction(kind: 'volume', volumeAction: 'up')),
  _Suggestion('Bajar volumen', 'volumen', Icons.volume_down_outlined, '#9CB080',
      DeckAction(kind: 'volume', volumeAction: 'down')),
  _Suggestion('Silenciar', 'volumen', Icons.volume_off_outlined, '#98989D',
      DeckAction(kind: 'volume', volumeAction: 'mute')),
];

/// Popular sites offered on the Websites tab; each one's favicon is fetched
/// when it is added, so the tile shows the real logo.
const _siteSuggestions = <(String, String)>[
  ('GitHub', 'https://github.com'),
  ('YouTube', 'https://youtube.com'),
  ('WhatsApp', 'https://web.whatsapp.com'),
  ('ChatGPT', 'https://chatgpt.com'),
  ('Gmail', 'https://mail.google.com'),
  ('X', 'https://x.com'),
  ('Instagram', 'https://instagram.com'),
  ('LinkedIn', 'https://linkedin.com'),
  ('Netflix', 'https://netflix.com'),
  ('Twitch', 'https://twitch.tv'),
];

final _commandSuggestions = <_Suggestion>[
  _Suggestion('npm i', 'Instalar dependencias', Icons.terminal, '#30D158',
      DeckAction(kind: 'shell', command: 'npm i')),
  _Suggestion('npm run dev', 'Levantar el proyecto', Icons.terminal, '#30D158',
      DeckAction(kind: 'shell', command: 'npm run dev')),
  _Suggestion('git status', 'Estado del repo', Icons.terminal, '#9CB080',
      DeckAction(kind: 'shell', command: 'git status')),
  _Suggestion('git pull', 'Traer cambios', Icons.terminal, '#9CB080',
      DeckAction(kind: 'shell', command: 'git pull')),
  _Suggestion('Abrir carpeta', 'explorer .', Icons.folder_open_outlined, '#0A84FF',
      DeckAction(kind: 'shell', command: 'explorer .')),
];

/// The add/edit modal — a centered card with Apps / Atajos / Comandos tabs,
/// each offering a form plus a suggestions list.
class AddButtonSheet extends StatefulWidget {
  final ControlClient client;
  final DeckButton? initial;
  final ValueChanged<DeckButton> onSubmit;
  final VoidCallback? onDelete;
  final VoidCallback? onTest;

  /// True when this fills its own window instead of floating as a card over
  /// the main one — the window then owns the chrome, so no card or close box.
  final bool embedded;

  const AddButtonSheet({
    super.key,
    required this.client,
    required this.onSubmit,
    this.initial,
    this.onDelete,
    this.onTest,
    this.embedded = false,
  });

  @override
  State<AddButtonSheet> createState() => _AddButtonSheetState();
}

class _AddButtonSheetState extends State<AddButtonSheet> {
  late SheetTab tab =
      _tabForKind(widget.initial?.action.kind ?? 'hotkey');

  bool get isEdit => widget.initial != null;

  // Shared form state (the Comandos tab uses all of it).
  late final nameCtrl = TextEditingController(text: widget.initial?.label ?? '');
  late final commandCtrl =
      TextEditingController(text: widget.initial?.action.command ?? '');
  late final hotkeyCtrl = TextEditingController(
    text: widget.initial?.action.kind == 'hotkey'
        ? widget.initial!.action.keys.join('+')
        : '',
  );
  late final appPathCtrl =
      TextEditingController(text: widget.initial?.action.app ?? '');
  final iconifyCtrl = TextEditingController();
  final appSearchCtrl = TextEditingController();
  late final urlCtrl =
      TextEditingController(text: widget.initial?.action.url ?? '');
  bool siteLoading = false;

  late String color = widget.initial?.color ?? deckSwatches.first;
  late String? iconB64 = widget.initial?.iconB64;
  bool iconifyLoading = false;
  String? iconifyError;

  @override
  void initState() {
    super.initState();
    widget.client.addListener(_onClient);
    if (tab == SheetTab.apps) widget.client.requestApps();
  }

  @override
  void dispose() {
    widget.client.removeListener(_onClient);
    nameCtrl.dispose();
    commandCtrl.dispose();
    hotkeyCtrl.dispose();
    appPathCtrl.dispose();
    iconifyCtrl.dispose();
    appSearchCtrl.dispose();
    urlCtrl.dispose();
    super.dispose();
  }

  void _onClient() {
    final picked = widget.client.pickedIconB64;
    if (picked != null && picked != iconB64) {
      setState(() => iconB64 = picked);
    }
  }

  @override
  Widget build(BuildContext context) {
    final body = Column(
      mainAxisSize: widget.embedded ? MainAxisSize.max : MainAxisSize.min,
      children: [
        _topBar(context),
        Container(height: 1, color: AppColors.border),
        Flexible(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
            child: switch (tab) {
              SheetTab.apps => _appsTab(),
              SheetTab.websites => _websitesTab(),
              SheetTab.hotkeys => _hotkeysTab(),
              SheetTab.commands => _commandsTab(),
            },
          ),
        ),
      ],
    );

    if (widget.embedded) return body;

    return Center(
      child: Container(
        width: 460,
        constraints: const BoxConstraints(maxHeight: 620),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: CupertinoColors.white.withValues(alpha: 0.08),
            width: 1,
          ),
        ),
        child: body,
      ),
    );
  }

  Widget _topBar(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 14, 12, 14),
      child: Row(
        children: [
          SizedBox(width: widget.embedded ? 0 : 28),
          Expanded(
            child: Center(
              child: CupertinoSlidingSegmentedControl<SheetTab>(
                backgroundColor: AppColors.surface2,
                thumbColor: AppColors.accent,
                groupValue: tab,
                children: {
                  SheetTab.apps: _segLabel('Apps', tab == SheetTab.apps),
                  SheetTab.websites:
                      _segLabel('Webs', tab == SheetTab.websites),
                  SheetTab.hotkeys: _segLabel('Atajos', tab == SheetTab.hotkeys),
                  SheetTab.commands:
                      _segLabel('Comandos', tab == SheetTab.commands),
                },
                onValueChanged: (v) {
                  if (v == null) return;
                  setState(() => tab = v);
                  if (v == SheetTab.apps && widget.client.apps.isEmpty) {
                    widget.client.requestApps();
                  }
                },
              ),
            ),
          ),
          if (!widget.embedded)
            GestureDetector(
              onTap: () => Navigator.pop(context),
              child: Icon(CupertinoIcons.xmark,
                  size: 16, color: AppColors.muted),
            ),
        ],
      ),
    );
  }

  Widget _segLabel(String text, bool selected) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
        child: Text(
          text,
          style: TextStyle(
            fontSize: 12.5,
            fontWeight: FontWeight.w600,
            color: selected ? AppColors.bg : AppColors.muted,
          ),
        ),
      );

  // ---------------------------------------------------------------- sections

  Widget _sectionHead(IconData icon, String title) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: AppColors.surface2,
              borderRadius: BorderRadius.circular(12),
            ),
            alignment: Alignment.center,
            child: Icon(icon, color: AppColors.accent, size: 19),
          ),
          const SizedBox(width: 12),
          Text(
            title,
            style: TextStyle(
              color: AppColors.fg,
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _label(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 7),
        child: Text(
          text,
          style: TextStyle(
            color: AppColors.muted,
            fontSize: 11.5,
            fontWeight: FontWeight.w600,
          ),
        ),
      );

  Widget _field(
    TextEditingController controller,
    String placeholder, {
    int maxLines = 1,
  }) {
    return CupertinoTextField(
      controller: controller,
      placeholder: placeholder,
      maxLines: maxLines,
      style: TextStyle(color: AppColors.fg, fontSize: 13),
      placeholderStyle: TextStyle(color: AppColors.dim, fontSize: 13),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
      decoration: BoxDecoration(
        color: AppColors.bg,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.border, width: 1),
      ),
    );
  }

  Widget _addButton(String text, VoidCallback? onTap, {bool wide = false}) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: wide ? double.infinity : null,
        padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 9),
        decoration: BoxDecoration(
          color: onTap == null ? AppColors.surface2 : AppColors.accent,
          borderRadius: BorderRadius.circular(8),
        ),
        alignment: Alignment.center,
        child: Text(
          text,
          style: TextStyle(
            color: onTap == null ? AppColors.dim : AppColors.bg,
            fontSize: 12.5,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  Widget _suggestionList(List<Widget> rows) {
    if (rows.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const SizedBox(height: 20),
        _label('SUGERENCIAS'),
        ...rows,
      ],
    );
  }

  Widget _row({
    required Widget leading,
    required String title,
    required String subtitle,
    required VoidCallback onAdd,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: AppColors.bg,
        borderRadius: BorderRadius.circular(11),
        border: Border.all(color: AppColors.border, width: 1),
      ),
      child: Row(
        children: [
          leading,
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: AppColors.fg,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: AppColors.dim, fontSize: 11),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          _addButton('Agregar', onAdd),
        ],
      ),
    );
  }

  Widget _glyphBox(IconData icon, String colorHex, {double size = 32}) {
    final tile = parseHexColor(colorHex);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: tile,
        borderRadius: BorderRadius.circular(size * 0.28),
      ),
      alignment: Alignment.center,
      child: Icon(icon, size: size * 0.5, color: glyphColorOn(tile)),
    );
  }

  // -------------------------------------------------------------------- tabs

  Widget _appsTab() {
    final client = widget.client;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _sectionHead(Icons.apps, 'Agregar app al deck'),
        Row(
          children: [
            Expanded(child: _field(appPathCtrl, r'C:\ruta\app.exe')),
            const SizedBox(width: 10),
            _addButton(
              isEdit ? 'Guardar' : 'Agregar',
              () => _submit(DeckAction(kind: 'app', app: appPathCtrl.text.trim())),
            ),
          ],
        ),
        if (isEdit) ...[
          const SizedBox(height: 14),
          _editActions(),
        ],
        if (!isEdit) ...[
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(child: _field(appSearchCtrl, 'Buscar app instalada…')),
              const SizedBox(width: 10),
              _addButton(
                'Buscar',
                () => client.requestApps(appSearchCtrl.text.trim()),
              ),
            ],
          ),
          if (client.appsLoading)
            Padding(
              padding: EdgeInsets.only(top: 22),
              child: CupertinoActivityIndicator(color: AppColors.muted),
            )
          else
            _suggestionList([
              for (final app in client.apps)
                _row(
                  leading: app.iconB64 != null && app.iconB64!.isNotEmpty
                      ? ClipRRect(
                          borderRadius: BorderRadius.circular(9),
                          child: Image.memory(
                            base64Decode(app.iconB64!),
                            width: 32,
                            height: 32,
                            fit: BoxFit.cover,
                          ),
                        )
                      : _glyphBox(Icons.apps, '#98989D'),
                  title: app.name,
                  subtitle: app.path,
                  onAdd: () => widget.onSubmit(
                    DeckButton(
                      id: _newId(),
                      label: app.name,
                      color: '#0A84FF',
                      iconB64: app.iconB64,
                      action: DeckAction(kind: 'app', app: app.path),
                    ),
                  ),
                ),
            ]),
        ],
      ],
    );
  }

  Widget _websitesTab() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _sectionHead(Icons.language, 'Agregar link al deck'),
        _label('NOMBRE'),
        _field(nameCtrl, 'GitHub'),
        const SizedBox(height: 12),
        _label('DIRECCIÓN'),
        Row(
          children: [
            Expanded(child: _field(urlCtrl, 'https://ejemplo.com')),
            const SizedBox(width: 10),
            _addButton(
              siteLoading ? '…' : (isEdit ? 'Guardar' : 'Agregar'),
              siteLoading ? null : _submitSite,
            ),
          ],
        ),
        const SizedBox(height: 12),
        _colorRow(),
        if (isEdit) ...[
          const SizedBox(height: 14),
          _editActions(),
        ],
        if (!isEdit)
          _suggestionList([
            for (final (name, url) in _siteSuggestions)
              _row(
                leading: _glyphBox(Icons.language, '#0A84FF'),
                title: name,
                subtitle: url,
                onAdd: () => _addSite(name, url),
              ),
          ]),
      ],
    );
  }

  Widget _hotkeysTab() {
    final isVolume = widget.initial?.action.kind == 'volume';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _sectionHead(Icons.keyboard_outlined, 'Agregar atajo de teclado'),
        _label('NOMBRE'),
        _field(nameCtrl, 'Copiar'),
        const SizedBox(height: 12),
        _label('TECLAS'),
        Row(
          children: [
            Expanded(child: _field(hotkeyCtrl, 'ctrl+c')),
            const SizedBox(width: 10),
            _addButton(
              isEdit ? 'Guardar' : 'Agregar',
              () => _submit(
                isVolume
                    ? widget.initial!.action
                    : DeckAction(
                        kind: 'hotkey',
                        keys: hotkeyCtrl.text
                            .split('+')
                            .map((s) => s.trim())
                            .where((s) => s.isNotEmpty)
                            .toList(),
                      ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        _colorRow(),
        if (isEdit) ...[
          const SizedBox(height: 14),
          _editActions(),
        ],
        if (!isEdit)
          _suggestionList([
            for (final s in _hotkeySuggestions)
              _row(
                leading: _glyphBox(s.icon, s.color),
                title: s.label,
                subtitle: s.subtitle,
                onAdd: () => widget.onSubmit(s.toButton()),
              ),
          ]),
      ],
    );
  }

  Widget _commandsTab() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _sectionHead(Icons.terminal, 'Agregar comando'),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _iconPreview(),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _label('NOMBRE'),
                  _field(nameCtrl, 'Instalar deps'),
                  const SizedBox(height: 10),
                  _label('ICONO'),
                  Row(
                    children: [
                      Expanded(child: _field(iconifyCtrl, 'mdi:npm  (Iconify)')),
                      const SizedBox(width: 8),
                      _addButton(
                        iconifyLoading ? '…' : 'Buscar',
                        iconifyLoading ? null : _loadIconify,
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      _addButton(
                        widget.client.pickingImage ? '…' : 'Imagen…',
                        widget.client.pickingImage
                            ? null
                            : widget.client.pickImage,
                      ),
                      if (iconB64 != null) ...[
                        const SizedBox(width: 8),
                        GestureDetector(
                          onTap: () => setState(() => iconB64 = null),
                          child: Text(
                            'Quitar',
                            style:
                                TextStyle(color: AppColors.muted, fontSize: 12),
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
        if (iconifyError != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              iconifyError!,
              style: const TextStyle(color: AppColors.err, fontSize: 11),
            ),
          ),
        const SizedBox(height: 14),
        _label('COMANDO'),
        _field(commandCtrl, 'npm i', maxLines: 4),
        const SizedBox(height: 12),
        _colorRow(),
        const SizedBox(height: 14),
        _addButton(
          isEdit ? 'Guardar' : 'Agregar al deck',
          () => _submit(
            DeckAction(kind: 'shell', command: commandCtrl.text.trim()),
          ),
          wide: true,
        ),
        if (isEdit) ...[
          const SizedBox(height: 10),
          _editActions(),
        ],
        if (!isEdit)
          _suggestionList([
            for (final s in _commandSuggestions)
              _row(
                leading: _glyphBox(s.icon, s.color),
                title: s.label,
                subtitle: s.subtitle,
                onAdd: () => widget.onSubmit(s.toButton()),
              ),
          ]),
      ],
    );
  }

  Widget _iconPreview() {
    final tile = parseHexColor(color);
    final hasImage = iconB64 != null && iconB64!.isNotEmpty;
    return Container(
      width: 64,
      height: 64,
      decoration: BoxDecoration(
        color: hasImage ? AppColors.bg : tile,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: CupertinoColors.white.withValues(alpha: 0.20),
          width: 1.5,
        ),
      ),
      alignment: Alignment.center,
      child: hasImage
          ? ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Image.memory(
                base64Decode(iconB64!),
                width: 60,
                height: 60,
                fit: BoxFit.contain,
              ),
            )
          : Icon(Icons.terminal, size: 27, color: glyphColorOn(tile)),
    );
  }

  Widget _colorRow() {
    return Row(
      children: [
        _label('COLOR'),
        const SizedBox(width: 12),
        for (final hex in deckSwatches)
          GestureDetector(
            onTap: () => setState(() => color = hex),
            child: Container(
              margin: const EdgeInsets.only(right: 8, bottom: 7),
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                color: parseHexColor(hex),
                shape: BoxShape.circle,
                border: hex == color
                    ? Border.all(color: CupertinoColors.white, width: 2)
                    : null,
              ),
            ),
          ),
      ],
    );
  }

  Widget _editActions() {
    return Row(
      children: [
        if (widget.onTest != null) ...[
          GestureDetector(
            onTap: widget.onTest,
            child: Text(
              'Probar',
              style: TextStyle(color: AppColors.accent, fontSize: 12.5),
            ),
          ),
          const SizedBox(width: 18),
        ],
        if (widget.onDelete != null)
          GestureDetector(
            onTap: () {
              widget.onDelete!();
              Navigator.pop(context);
            },
            child: const Text(
              'Eliminar',
              style: TextStyle(color: AppColors.err, fontSize: 12.5),
            ),
          ),
      ],
    );
  }

  // --------------------------------------------------------------- behaviour

  /// Adds a site straight from the suggestion list, with its favicon.
  Future<void> _addSite(String name, String url) async {
    final icon = await faviconPngB64(url);
    widget.onSubmit(
      DeckButton(
        id: _newId(),
        label: name,
        color: '#0A84FF',
        iconB64: icon,
        action: DeckAction(kind: 'url', url: url),
      ),
    );
  }

  /// Adds the site typed into the form, naming it after the host when the
  /// name field is empty.
  Future<void> _submitSite() async {
    var url = urlCtrl.text.trim();
    if (url.isEmpty) return;
    if (!url.contains('://')) url = 'https://$url';

    setState(() => siteLoading = true);
    final icon = iconB64 ?? await faviconPngB64(url);
    if (!mounted) return;
    setState(() {
      siteLoading = false;
      iconB64 = icon;
    });

    final host = Uri.tryParse(url)?.host.replaceFirst('www.', '') ?? url;
    if (nameCtrl.text.trim().isEmpty) nameCtrl.text = host;
    _submit(DeckAction(kind: 'url', url: url));
  }

  Future<void> _loadIconify() async {
    final slug = iconifyCtrl.text.trim();
    if (slug.isEmpty) return;
    setState(() {
      iconifyLoading = true;
      iconifyError = null;
    });
    final png = await iconifyPngB64(slug);
    if (!mounted) return;
    setState(() {
      iconifyLoading = false;
      if (png == null) {
        iconifyError = 'No se encontró "$slug" en Iconify.';
      } else {
        iconB64 = png;
      }
    });
  }

  void _submit(DeckAction action) {
    final fallbackLabel = switch (action.kind) {
      'shell' => action.command.isEmpty ? 'Comando' : action.command,
      'app' => action.app.split(RegExp(r'[\\/]')).last,
      'url' => Uri.tryParse(action.url)?.host.replaceFirst('www.', '') ?? 'Web',
      _ => 'Botón',
    };
    final label =
        nameCtrl.text.trim().isEmpty ? fallbackLabel : nameCtrl.text.trim();
    widget.onSubmit(
      DeckButton(
        id: widget.initial?.id ?? _newId(),
        label: label,
        icon: widget.initial?.icon ?? 'ellipse-outline',
        color: color,
        iconB64: iconB64,
        action: action,
      ),
    );
    if (isEdit) Navigator.pop(context);
  }
}
