// Ad-hoc network check for the favicon fetch. Not part of the suite (needs
// internet). Run with: flutter test test/favicon_live_check.dart
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:clicx_host/iconify.dart';

void main() {
  test('fetches a real favicon as PNG', () async {
    final b64 = await faviconPngB64('https://github.com');
    expect(b64, isNotNull);
    final bytes = base64Decode(b64!);
    expect(bytes.length, greaterThan(200));
    expect(bytes.sublist(0, 4), [0x89, 0x50, 0x4E, 0x47]);
  });

  test('bare hostnames work and junk returns null', () async {
    expect(await faviconPngB64('youtube.com'), isNotNull);
    expect(await faviconPngB64(''), isNull);
  });
}
