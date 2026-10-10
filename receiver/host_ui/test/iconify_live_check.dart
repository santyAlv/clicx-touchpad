// Ad-hoc network check for the Iconify fetch + rasterise path.
// Not part of the suite: it needs internet. Run with:
//   flutter test test/iconify_live_check.dart
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:clicx_host/iconify.dart';

void main() {
  test('iconify slug rasterises to a PNG', () async {
    final b64 = await iconifyPngB64('mdi:npm');
    expect(b64, isNotNull);
    final bytes = base64Decode(b64!);
    expect(bytes.length, greaterThan(200));
    // PNG magic number.
    expect(bytes.sublist(0, 4), [0x89, 0x50, 0x4E, 0x47]);
  });

  test('a bogus slug returns null instead of throwing', () async {
    expect(await iconifyPngB64('nope:definitely-not-an-icon-xyz'), isNull);
    expect(await iconifyPngB64('missing-colon'), isNull);
  });
}
