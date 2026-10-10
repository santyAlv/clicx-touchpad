import 'package:flutter/cupertino.dart';

import 'theme.dart';

/// Left-aligned pane title, the way a macOS window titles its content area
/// (the reference app does this instead of a centered iOS-style nav title).
class PaneHeader extends StatelessWidget {
  final String title;
  const PaneHeader({super.key, required this.title});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 48,
      alignment: Alignment.centerLeft,
      padding: const EdgeInsets.symmetric(horizontal: 22),
      child: Text(
        title,
        style: TextStyle(
          color: AppColors.fg,
          fontSize: 14,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

/// An inset-grouped section, the shape macOS System Settings uses: a small
/// grey caption outside the card, then rounded rows split by hairlines.
class SettingsGroup extends StatelessWidget {
  final String? title;
  final List<Widget> children;
  const SettingsGroup({super.key, this.title, required this.children});

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0) {
        rows.add(
          Padding(
            // Hairlines start past the label, the way grouped lists inset them.
            padding: const EdgeInsets.only(left: 16),
            child: Container(height: 0.5, color: AppColors.border),
          ),
        );
      }
      rows.add(children[i]);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (title case final title?)
          Padding(
            padding: const EdgeInsets.fromLTRB(4, 0, 4, 7),
            child: Text(
              title,
              style: TextStyle(color: AppColors.muted, fontSize: 12),
            ),
          ),
        DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(children: rows),
        ),
      ],
    );
  }
}

/// One row of a [SettingsGroup]: a label, an optional secondary value, and a
/// trailing control.
class SettingsRow extends StatelessWidget {
  final String label;
  final String? value;
  final Widget? leading;
  final Widget? trailing;
  final Widget? below;

  const SettingsRow({
    super.key,
    required this.label,
    this.value,
    this.leading,
    this.trailing,
    this.below,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              if (leading case final leading?) ...[
                leading,
                const SizedBox(width: 10),
              ],
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(color: AppColors.fg, fontSize: 13),
                ),
              ),
              if (value case final value?)
                Flexible(
                  child: Text(
                    value,
                    textAlign: TextAlign.right,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(color: AppColors.muted, fontSize: 13),
                  ),
                ),
              if (trailing case final trailing?) ...[
                const SizedBox(width: 10),
                trailing,
              ],
            ],
          ),
          if (below case final below?) ...[
            const SizedBox(height: 12),
            below,
          ],
        ],
      ),
    );
  }
}

/// Height of the app-drawn title bar. Must match kTitleBarHeightDip in
/// windows/runner/win32_window.cpp, which owns the drag and button hit tests.
const double titleBarHeight = 40;
const double _captionButtonWidth = 46;

/// The window's own title bar. The native caption is removed by the runner, so
/// this paints the strip; Windows still handles dragging and the three caption
/// buttons through hit-testing, which is why they need no click handlers here.
class AppTitleBar extends StatelessWidget {
  final String title;
  const AppTitleBar({super.key, required this.title});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: titleBarHeight,
      child: Row(
        children: [
          const SizedBox(width: 18),
          Text(
            title,
            style: TextStyle(
              color: AppColors.muted,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
          const Spacer(),
          const _CaptionGlyph(icon: CupertinoIcons.minus),
          const _CaptionGlyph(icon: CupertinoIcons.stop),
          const _CaptionGlyph(icon: CupertinoIcons.xmark, danger: true),
        ],
      ),
    );
  }
}

class _CaptionGlyph extends StatefulWidget {
  final IconData icon;
  final bool danger;
  const _CaptionGlyph({required this.icon, this.danger = false});

  @override
  State<_CaptionGlyph> createState() => _CaptionGlyphState();
}

class _CaptionGlyphState extends State<_CaptionGlyph> {
  bool hovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => hovered = true),
      onExit: (_) => setState(() => hovered = false),
      child: Container(
        width: _captionButtonWidth,
        height: titleBarHeight,
        color: hovered
            ? (widget.danger
                ? AppColors.err
                : CupertinoColors.white.withValues(alpha: 0.08))
            : CupertinoColors.transparent,
        alignment: Alignment.center,
        child: Icon(
          widget.icon,
          size: widget.icon == CupertinoIcons.stop ? 11 : 13,
          color: hovered && widget.danger ? CupertinoColors.white : AppColors.muted,
        ),
      ),
    );
  }
}

/// Small rounded action button — the "Reorganizar apps" pill in the reference.
class PillButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  const PillButton({super.key, required this.label, this.onPressed});

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null;
    return GestureDetector(
      onTap: onPressed,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
        decoration: BoxDecoration(
          color: AppColors.surface2,
          borderRadius: BorderRadius.circular(9),
          border: Border.all(color: AppColors.border, width: 1),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: enabled ? AppColors.fg : AppColors.dim,
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }
}
