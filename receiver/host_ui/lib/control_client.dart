import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'models.dart';
import 'theme.dart';

const controlPort = 51236;

/// Talks to receiver/control_server.py over a local WebSocket
/// (ws://127.0.0.1:51236). Reconnects automatically if the Python
/// backend isn't up yet or drops.
class ControlClient extends ChangeNotifier {
  WebSocket? _socket;
  bool _connecting = false;
  Timer? _retryTimer;

  bool connected = false;
  bool running = false;
  int clients = 0;
  bool usbActive = false;
  String? usbError;
  String ip = '';
  int port = 0;
  String url = '';
  String connectPayload = '';
  String version = '';
  Deck? deck;
  String accent = '#9CB080';
  final List<String> logLines = [];

  /// Installed-app suggestions, filled on demand by [requestApps].
  List<AppEntry> apps = [];
  bool appsLoading = false;

  /// Folders the phone transfers files through, reported by the host.
  String fromPhoneDir = '';
  String fromPcDir = '';
  String? folderError;

  /// Every address the phone could reach the host on — Wi-Fi, Ethernet, and
  /// the Bluetooth PAN link when the phone is tethered over Bluetooth.
  List<HostAddress> addresses = [];

  /// Which of [addresses] the pairing QR points at. Null follows the host's
  /// own preferred address.
  String? pickedIp;

  /// Address the QR and the shown URL use: the pick, else the host default.
  HostAddress? get activeAddress {
    if (addresses.isEmpty) return null;
    return addresses.firstWhere(
      (a) => a.ip == (pickedIp ?? ip),
      orElse: () => addresses.first,
    );
  }

  /// Protocol version and per-domain capabilities the host advertises in
  /// "hello". Tells you at a glance which features a phone will find here.
  String protocol = '';
  Map<String, bool> domains = const {};

  /// Shared-clipboard history, metadata only (timestamp + length) — the host
  /// never exposes clipboard content to the UI or the log.
  List<ClipEntry> clipboardHistory = [];

  /// Last image the user picked through the host's file dialog.
  String? pickedIconB64;
  bool pickingImage = false;

  ControlClient() {
    _connect();
  }

  void _connect() {
    if (_connecting || _socket != null) return;
    _connecting = true;
    WebSocket.connect('ws://127.0.0.1:$controlPort').then((ws) {
      _connecting = false;
      _socket = ws;
      connected = true;
      notifyListeners();
      ws.listen(
        _onMessage,
        onDone: _onClosed,
        onError: (_) => _onClosed(),
        cancelOnError: true,
      );
      send({'t': 'getDeck'});
    }).catchError((_) {
      _connecting = false;
      _scheduleRetry();
    });
  }

  void _onClosed() {
    _socket = null;
    connected = false;
    notifyListeners();
    _scheduleRetry();
  }

  void _scheduleRetry() {
    _retryTimer?.cancel();
    _retryTimer = Timer(const Duration(seconds: 2), _connect);
  }

  void _onMessage(dynamic raw) {
    Map<String, dynamic> data;
    try {
      data = jsonDecode(raw as String) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    switch (data['t']) {
      case 'status':
      case 'connectInfo':
        running = data['running'] as bool? ?? running;
        clients = data['clients'] as int? ?? clients;
        usbActive = data['usb'] as bool? ?? usbActive;
        ip = data['ip'] as String? ?? ip;
        port = data['port'] as int? ?? port;
        url = data['url'] as String? ?? url;
        connectPayload = data['payload'] as String? ?? connectPayload;
        final addrs = data['addresses'] as List?;
        if (addrs != null) {
          addresses = addrs
              .map((e) => HostAddress.fromJson(e as Map<String, dynamic>))
              .toList();
          // Drop a pick whose link went away, so the QR never points nowhere.
          if (pickedIp != null && !addresses.any((a) => a.ip == pickedIp)) {
            pickedIp = null;
          }
        }
        version = data['version'] as String? ?? version;
        final features = data['features'] as Map<String, dynamic>?;
        if (features != null) {
          protocol = features['protocol'] as String? ?? protocol;
          final d = features['domains'] as Map<String, dynamic>?;
          if (d != null) {
            domains = {
              for (final e in d.entries) e.key: e.value == true,
            };
          }
        }
        final folders = data['folders'] as Map<String, dynamic>?;
        if (folders != null) {
          fromPhoneDir = folders['fromPhone'] as String? ?? fromPhoneDir;
          fromPcDir = folders['fromPc'] as String? ?? fromPcDir;
        }
        break;
      case 'hostStatus':
        // Text/kind is log-oriented; ask for a fresh structured snapshot.
        send({'t': 'getStatus'});
        break;
      case 'clients':
        clients = data['n'] as int? ?? clients;
        break;
      case 'log':
        logLines.add(data['msg'] as String? ?? '');
        if (logLines.length > 200) logLines.removeAt(0);
        break;
      case 'deck':
        final payload = data['deck'] as Map<String, dynamic>;
        deck = Deck.fromJson(payload);
        final hex = payload['accent'] as String?;
        if (hex != null && hex.isNotEmpty) {
          accent = hex;
          accentNotifier.value = parseHexColor(hex);
        }
        break;
      case 'usb':
        usbActive = data['active'] as bool? ?? false;
        usbError = data['error'] as String?;
        break;
      case 'apps':
        apps = (data['apps'] as List? ?? [])
            .map((e) => AppEntry.fromJson(e as Map<String, dynamic>))
            .toList();
        appsLoading = false;
        break;
      case 'clipboardHistory':
        clipboardHistory = (data['items'] as List? ?? [])
            .map((e) => ClipEntry.fromJson(e as Map<String, dynamic>))
            .toList();
        break;
      case 'folderError':
        folderError = data['msg'] as String?;
        break;
      case 'pickedImage':
        pickedIconB64 = data['iconB64'] as String?;
        pickingImage = false;
        break;
    }
    notifyListeners();
  }

  void send(Map<String, dynamic> msg) {
    _socket?.add(jsonEncode(msg));
  }

  void start() => send({'t': 'start'});
  void stop() => send({'t': 'stop'});
  void usbOn() => send({'t': 'usbOn'});
  void usbOff() => send({'t': 'usbOff'});
  void testButton(String id) => send({'t': 'testButton', 'id': id});
  void saveDeck(Deck d) => send({'t': 'saveDeck', 'deck': d.toJson()});

  /// Appends a button and lets the host persist it, so the add window (a
  /// separate process) needs no shared deck state.
  void addButton(DeckButton button, {String? pageId}) => send({
        't': 'addButton',
        'button': button.toJson(),
        'pageId': ?pageId,
      });

  /// Persists the app accent on the host, which echoes it back to every
  /// window and pushes it to the phone with the deck.
  void setAccent(String hex) => send({'t': 'setAccent', 'color': hex});

  /// Opens a transfer folder in Explorer on the host side.
  void openFolder(String folder) => send({'t': 'openFolder', 'folder': folder});

  /// Points the pairing QR at one of [addresses]. Purely local to this window:
  /// the host serves on every interface either way.
  void pickAddress(String? addressIp) {
    pickedIp = addressIp;
    notifyListeners();
  }

  /// QR payload for the picked address. Same shape the phone already parses.
  String payloadFor(HostAddress address) =>
      'clicx://connect?host=${Uri.encodeComponent(address.ip)}&port=$port';

  void requestClipboardHistory() => send({'t': 'getClipboardHistory'});
  void clearClipboardHistory() => send({'t': 'clearClipboardHistory'});

  void requestApps([String query = '']) {
    appsLoading = true;
    notifyListeners();
    send({'t': 'listApps', 'q': query});
  }

  /// Opens the host's native file dialog; the result lands in [pickedIconB64].
  void pickImage() {
    pickingImage = true;
    pickedIconB64 = null;
    notifyListeners();
    send({'t': 'pickImage'});
  }

  @override
  void dispose() {
    _retryTimer?.cancel();
    _socket?.close();
    super.dispose();
  }
}


/// One shared-clipboard entry as the host reports it: when it was captured and
/// how long it was. The text itself never leaves the host's clipboard.
class ClipEntry {
  final DateTime at;
  final int length;
  const ClipEntry({required this.at, required this.length});

  factory ClipEntry.fromJson(Map<String, dynamic> json) => ClipEntry(
        at: DateTime.fromMillisecondsSinceEpoch(
          ((json['ts'] as num? ?? 0) * 1000).round(),
        ),
        length: (json['len'] as num? ?? 0).toInt(),
      );
}


/// One address the host listens on, with the interface it belongs to.
class HostAddress {
  final String label;
  final String ip;
  final String kind; // bluetooth | wifi | ethernet | other
  const HostAddress({required this.label, required this.ip, required this.kind});

  factory HostAddress.fromJson(Map<String, dynamic> json) => HostAddress(
        label: json['label'] as String? ?? '',
        ip: json['ip'] as String? ?? '',
        kind: json['kind'] as String? ?? 'other',
      );
}
