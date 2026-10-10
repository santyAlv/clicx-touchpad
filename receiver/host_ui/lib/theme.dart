import 'package:flutter/cupertino.dart';

/// The app accent, chosen in Opciones and shared with the phone through
/// deck.json. Listen to it to rebuild when the user picks a new colour.
final accentNotifier = ValueNotifier<Color>(const Color(0xFF9CB080));

/// Dark glass palette. Every surface is a dark shade of the chosen accent, so
/// picking a colour re-tints the whole app — the saturation/value pairs below
/// are the ones the original forest-moss palette used, kept and re-hued.
class AppColors {
  static HSVColor get _hsv => HSVColor.fromColor(accentNotifier.value);

  static Color _shade(double saturation, double value) {
    final hsv = _hsv;
    // A greyscale accent has no meaningful hue; keep the shades grey too.
    final sat = hsv.saturation < 0.05 ? 0.0 : saturation;
    return HSVColor.fromAHSV(1, hsv.hue, sat, value).toColor();
  }

  static Color get bg => _shade(0.20, 0.06);
  static Color get surface => _shade(0.29, 0.11);
  static Color get surface2 => _shade(0.30, 0.17);
  static Color get border => _shade(0.20, 0.19);
  static Color get dim => _shade(0.19, 0.33);
  static Color get muted => _shade(0.12, 0.64);
  static Color get fg => _shade(0.03, 0.94);

  static Color get accent => accentNotifier.value;
  static Color get accentHover =>
      HSVColor.fromColor(accentNotifier.value).withValue(0.86).toColor();

  // Status colours stay fixed — green means running, red means stopped,
  // whatever the app is tinted.
  static const ok = Color(0xFF34C759);
  static const err = Color(0xFFFF453A);
}

/// The accent choices offered in Opciones.
const accentSwatches = [
  '#9CB080',
  '#30D158',
  '#0A84FF',
  '#64D2FF',
  '#FF453A',
  '#FF9F0A',
  '#BF5AF2',
  '#E8D5A3',
];

/// Deck buttons store their colour as "#RRGGBB" in deck.json.
Color parseHexColor(String hex) {
  var h = hex.replaceFirst('#', '');
  if (h.length == 6) h = 'FF$h';
  return Color(int.tryParse(h, radix: 16) ?? 0xFF9CB080);
}

/// Dark glyph on light tiles, light glyph on dark tiles — like the phone app.
Color glyphColorOn(Color tile) {
  final luminance = 0.299 * tile.r + 0.587 * tile.g + 0.114 * tile.b;
  return luminance > 0.6 ? const Color(0xFF17211C) : AppColors.fg;
}

/// The palette the phone app and deck_store.py defaults draw from.
const deckSwatches = [
  '#9CB080',
  '#30D158',
  '#0A84FF',
  '#64D2FF',
  '#FF453A',
  '#98989D',
];

CupertinoThemeData get appCupertinoTheme => CupertinoThemeData(
  brightness: Brightness.dark,
  scaffoldBackgroundColor: AppColors.bg,
  barBackgroundColor: AppColors.bg,
  primaryColor: AppColors.accent,
  textTheme: CupertinoTextThemeData(
    textStyle: TextStyle(color: AppColors.fg, fontSize: 15),
    navTitleTextStyle: TextStyle(
      color: AppColors.fg,
      fontSize: 17,
      fontWeight: FontWeight.w600,
    ),
    navLargeTitleTextStyle: TextStyle(
      color: AppColors.fg,
      fontSize: 32,
      fontWeight: FontWeight.w700,
    ),
  ),
);
