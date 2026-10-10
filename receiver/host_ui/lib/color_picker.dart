import 'package:flutter/cupertino.dart';

import 'theme.dart';

const _hueStops = [
  Color(0xFFFF0000),
  Color(0xFFFFFF00),
  Color(0xFF00FF00),
  Color(0xFF00FFFF),
  Color(0xFF0000FF),
  Color(0xFFFF00FF),
  Color(0xFFFF0000),
];

String hexOf(Color color) {
  int channel(double v) => (v * 255).round().clamp(0, 255);
  final r = channel(color.r).toRadixString(16).padLeft(2, '0');
  final g = channel(color.g).toRadixString(16).padLeft(2, '0');
  final b = channel(color.b).toRadixString(16).padLeft(2, '0');
  return '#${(r + g + b).toUpperCase()}';
}

/// Saturation/value square plus a hue strip and a hex field.
///
/// [onPreview] fires continuously while dragging so the UI can follow the
/// pointer; [onChanged] only fires when the gesture ends, so the host is not
/// flooded with a write per pixel.
class ColorPicker extends StatefulWidget {
  final Color value;
  final ValueChanged<Color> onChanged;
  final ValueChanged<Color>? onPreview;

  const ColorPicker({
    super.key,
    required this.value,
    required this.onChanged,
    this.onPreview,
  });

  @override
  State<ColorPicker> createState() => _ColorPickerState();
}

class _ColorPickerState extends State<ColorPicker> {
  late HSVColor _hsv = HSVColor.fromColor(widget.value);
  late final TextEditingController _hexCtrl =
      TextEditingController(text: hexOf(widget.value));

  static const _squareW = 260.0;
  static const _squareH = 150.0;
  static const _hueH = 16.0;

  @override
  void didUpdateWidget(ColorPicker old) {
    super.didUpdateWidget(old);
    // Follow external changes (a preset swatch), but never fight the user's
    // own drag — hue is kept when the colour round-trips to the same value.
    if (widget.value != old.value && widget.value != _hsv.toColor()) {
      _hsv = HSVColor.fromColor(widget.value);
      _hexCtrl.text = hexOf(widget.value);
    }
  }

  @override
  void dispose() {
    _hexCtrl.dispose();
    super.dispose();
  }

  void _set(HSVColor hsv, {bool commit = false}) {
    setState(() {
      _hsv = hsv;
      _hexCtrl.text = hexOf(hsv.toColor());
    });
    if (commit) {
      widget.onChanged(hsv.toColor());
    } else {
      widget.onPreview?.call(hsv.toColor());
    }
  }

  void _pickSV(Offset local, {bool commit = false}) {
    _set(
      _hsv
          .withSaturation((local.dx / _squareW).clamp(0.0, 1.0))
          .withValue((1 - local.dy / _squareH).clamp(0.0, 1.0)),
      commit: commit,
    );
  }

  void _pickHue(Offset local, {bool commit = false}) {
    _set(
      _hsv.withHue(((local.dx / _squareW).clamp(0.0, 1.0)) * 360),
      commit: commit,
    );
  }

  void _applyHex(String raw) {
    var text = raw.trim().replaceFirst('#', '');
    if (text.length != 6) return;
    final value = int.tryParse(text, radix: 16);
    if (value == null) return;
    final color = Color(0xFF000000 | value);
    _set(HSVColor.fromColor(color), commit: true);
  }

  @override
  Widget build(BuildContext context) {
    final pure = HSVColor.fromAHSV(1, _hsv.hue, 1, 1).toColor();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GestureDetector(
          onPanDown: (d) => _pickSV(d.localPosition),
          onPanUpdate: (d) => _pickSV(d.localPosition),
          onPanEnd: (_) => _set(_hsv, commit: true),
          onTapUp: (d) => _pickSV(d.localPosition, commit: true),
          child: Container(
            width: _squareW,
            height: _squareH,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(10),
              gradient: LinearGradient(
                colors: [CupertinoColors.white, pure],
              ),
            ),
            child: Stack(
              children: [
                Positioned.fill(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      gradient: const LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Color(0x00000000),
                          Color(0xFF000000),
                        ],
                      ),
                    ),
                  ),
                ),
                Positioned(
                  left: _hsv.saturation * _squareW - 7,
                  top: (1 - _hsv.value) * _squareH - 7,
                  child: _Thumb(size: 14, color: _hsv.toColor()),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        GestureDetector(
          onPanDown: (d) => _pickHue(d.localPosition),
          onPanUpdate: (d) => _pickHue(d.localPosition),
          onPanEnd: (_) => _set(_hsv, commit: true),
          onTapUp: (d) => _pickHue(d.localPosition, commit: true),
          child: Container(
            width: _squareW,
            height: _hueH,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(8),
              gradient: const LinearGradient(colors: _hueStops),
            ),
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                Positioned(
                  left: (_hsv.hue / 360) * _squareW - 7,
                  top: -1,
                  child: _Thumb(size: 14, color: pure),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Container(
              width: 34,
              height: 34,
              decoration: BoxDecoration(
                color: _hsv.toColor(),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(
                  color: CupertinoColors.white.withValues(alpha: 0.14),
                ),
              ),
            ),
            const SizedBox(width: 10),
            SizedBox(
              width: 120,
              child: CupertinoTextField(
                controller: _hexCtrl,
                onSubmitted: _applyHex,
                onEditingComplete: () => _applyHex(_hexCtrl.text),
                style: TextStyle(color: AppColors.fg, fontSize: 13),
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
                decoration: BoxDecoration(
                  color: AppColors.bg,
                  borderRadius: BorderRadius.circular(9),
                  border: Border.all(color: AppColors.border),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _Thumb extends StatelessWidget {
  final double size;
  final Color color;
  const _Thumb({required this.size, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(color: CupertinoColors.white, width: 2),
      ),
    );
  }
}
