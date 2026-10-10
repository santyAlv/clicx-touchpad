import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter_svg/flutter_svg.dart';

/// A site's favicon, as base64 PNG, for a website deck button.
///
/// Google's endpoint is used rather than fetching `/favicon.ico` directly: it
/// already normalises size and format, and answers for sites whose icon lives
/// somewhere other than the root.
Future<String?> faviconPngB64(String rawUrl, {int size = 128}) async {
  var text = rawUrl.trim();
  if (text.isEmpty) return null;
  if (!text.contains('://')) text = 'https://$text';
  final host = Uri.tryParse(text)?.host;
  if (host == null || host.isEmpty) return null;

  final uri = Uri.parse(
    'https://www.google.com/s2/favicons?domain=$host&sz=$size',
  );
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 8);
  try {
    final response = await client.getUrl(uri).then((r) => r.close());
    if (response.statusCode != 200) return null;
    final bytes = await response.fold<List<int>>(
      <int>[],
      (buffer, chunk) => buffer..addAll(chunk),
    );
    if (bytes.length < 100) return null; // the "no icon" placeholder
    return base64Encode(bytes);
  } on Exception {
    return null;
  } finally {
    client.close(force: true);
  }
}

/// Fetches an icon from Iconify by its "prefix:name" slug (e.g. `mdi:npm`)
/// and rasterises it to base64 PNG.
///
/// Storing a PNG rather than the SVG is deliberate: deck buttons already carry
/// extracted app icons as `iconB64`, so an Iconify pick travels through
/// deck.json and reaches the phone with no support needed on either side.
Future<String?> iconifyPngB64(
  String slug, {
  int size = 128,
  String colorHex = 'ffffff',
}) async {
  final clean = slug.trim().toLowerCase().replaceAll(' ', '');
  final parts = clean.split(':');
  if (parts.length != 2 || parts.any((p) => p.isEmpty)) return null;

  final uri = Uri.parse(
    'https://api.iconify.design/${parts[0]}/${parts[1]}.svg'
    '?color=%23$colorHex&height=$size',
  );

  final client = HttpClient()..connectionTimeout = const Duration(seconds: 8);
  String svg;
  try {
    final response = await client.getUrl(uri).then((r) => r.close());
    if (response.statusCode != 200) return null;
    svg = await response.transform(utf8.decoder).join();
  } on Exception {
    return null;
  } finally {
    client.close(force: true);
  }
  // A miss answers 200 with the body "404", not an SVG document.
  if (!svg.contains('<svg')) return null;

  return _svgToPngB64(svg, size);
}

Future<String?> _svgToPngB64(String svg, int size) async {
  ui.Image? image;
  try {
    final info = await vg.loadPicture(SvgStringLoader(svg), null);
    final intrinsic = math.max(info.size.width, info.size.height);
    final scale = intrinsic <= 0 ? 1.0 : size / intrinsic;

    final recorder = ui.PictureRecorder();
    ui.Canvas(recorder)
      ..scale(scale)
      ..drawPicture(info.picture);
    final scaled = recorder.endRecording();
    info.picture.dispose();

    image = await scaled.toImage(size, size);
    scaled.dispose();

    final png = await image.toByteData(format: ui.ImageByteFormat.png);
    if (png == null) return null;
    return base64Encode(png.buffer.asUint8List());
  } on Exception {
    return null;
  } finally {
    image?.dispose();
  }
}
