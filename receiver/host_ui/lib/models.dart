/// Deck data model — mirrors the JSON shape from receiver/deck_store.py
/// (deck_for_client / save_config). Kept as plain maps under the hood so a
/// round-trip through the Python backend never drops fields we don't know
/// about yet.
class DeckAction {
  String kind; // hotkey | volume | shell | app | url
  List<String> keys; // hotkey
  String volumeAction; // up | down | mute
  String command; // shell
  String cwd; // shell
  String app; // shell (optional launcher) | app
  String url; // url

  DeckAction({
    this.kind = 'hotkey',
    List<String>? keys,
    this.volumeAction = 'mute',
    this.command = '',
    this.cwd = '',
    this.app = '',
    this.url = '',
  }) : keys = keys ?? [];

  factory DeckAction.fromJson(Map<String, dynamic>? json) {
    final j = json ?? {};
    return DeckAction(
      kind: j['kind'] as String? ?? 'hotkey',
      keys: (j['keys'] as List?)?.map((e) => e.toString()).toList() ?? [],
      volumeAction: j['action'] as String? ?? 'mute',
      command: j['command'] as String? ?? '',
      cwd: j['cwd'] as String? ?? '',
      app: j['app'] as String? ?? '',
      url: j['url'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    switch (kind) {
      case 'volume':
        return {'kind': 'volume', 'action': volumeAction};
      case 'shell':
        return {
          'kind': 'shell',
          'command': command,
          'cwd': cwd,
          if (app.isNotEmpty) 'app': app,
        };
      case 'app':
        return {'kind': 'app', 'app': app};
      case 'url':
        return {'kind': 'url', 'url': url};
      case 'hotkey':
      default:
        return {'kind': 'hotkey', 'keys': keys};
    }
  }

  String get summary {
    switch (kind) {
      case 'volume':
        return 'Volumen: $volumeAction';
      case 'shell':
        return command.isEmpty ? 'Shell (vacío)' : 'Shell: $command';
      case 'app':
        return app.isEmpty ? 'App (sin elegir)' : app.split(RegExp(r'[\\/]')).last;
      case 'url':
        return url.isEmpty ? 'Web (sin URL)' : url;
      case 'hotkey':
      default:
        return keys.isEmpty ? 'Atajo (vacío)' : keys.join(' + ');
    }
  }
}

class DeckButton {
  String id;
  String label;
  String icon;
  String color;
  String hint;
  String? iconB64;
  DeckAction action;

  DeckButton({
    required this.id,
    this.label = 'Botón',
    this.icon = 'ellipse-outline',
    this.color = '0xFF9CB080',
    this.hint = '',
    this.iconB64,
    DeckAction? action,
  }) : action = action ?? DeckAction();

  factory DeckButton.fromJson(Map<String, dynamic> json) {
    return DeckButton(
      id: json['id'] as String,
      label: json['label'] as String? ?? 'Botón',
      icon: json['icon'] as String? ?? 'ellipse-outline',
      color: json['color'] as String? ?? '#9CB080',
      hint: json['hint'] as String? ?? '',
      iconB64: json['iconB64'] as String?,
      action: DeckAction.fromJson(json['action'] as Map<String, dynamic>?),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'label': label,
        'icon': icon,
        'color': color,
        if (hint.isNotEmpty) 'hint': hint,
        if (iconB64 != null) 'iconB64': iconB64,
        'action': action.toJson(),
      };
}

class DeckPage {
  String id;
  String title;
  List<DeckButton> buttons;

  DeckPage({required this.id, this.title = 'Página', List<DeckButton>? buttons})
      : buttons = buttons ?? [];

  factory DeckPage.fromJson(Map<String, dynamic> json) {
    return DeckPage(
      id: json['id'] as String,
      title: json['title'] as String? ?? 'Página',
      buttons: (json['buttons'] as List? ?? [])
          .map((e) => DeckButton.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'buttons': buttons.map((b) => b.toJson()).toList(),
      };
}

/// An installed application the host offers as a deck-button suggestion.
class AppEntry {
  final String name;
  final String path;
  final String? iconB64;

  const AppEntry({required this.name, required this.path, this.iconB64});

  factory AppEntry.fromJson(Map<String, dynamic> json) => AppEntry(
        name: json['name'] as String? ?? '',
        path: json['path'] as String? ?? '',
        iconB64: json['iconB64'] as String?,
      );
}

class Deck {
  int version;
  List<DeckPage> pages;

  Deck({this.version = 1, List<DeckPage>? pages}) : pages = pages ?? [];

  factory Deck.fromJson(Map<String, dynamic> json) {
    return Deck(
      version: json['version'] as int? ?? 1,
      pages: (json['pages'] as List? ?? [])
          .map((e) => DeckPage.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() => {
        'version': version,
        'pages': pages.map((p) => p.toJson()).toList(),
      };
}
