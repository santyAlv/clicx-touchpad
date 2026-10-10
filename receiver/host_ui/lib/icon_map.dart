import 'package:flutter/material.dart' show IconData, Icons;

import 'models.dart';

/// Maps deck.json's Ionicons-style names (set by the phone app / defaults
/// in deck_store.py) to a Material glyph so the host UI shows a real icon
/// instead of a bare label.
final Map<String, IconData> deckIcons = {
  'copy-outline': Icons.content_copy_outlined,
  'clipboard-outline': Icons.assignment_outlined,
  'arrow-undo-outline': Icons.undo,
  'save-outline': Icons.save_outlined,
  'desktop-outline': Icons.desktop_windows_outlined,
  'layers-outline': Icons.layers_outlined,
  'search-outline': Icons.search,
  'camera-outline': Icons.camera_alt_outlined,
  'close-circle-outline': Icons.cancel_outlined,
  'close-outline': Icons.close,
  'return-down-back-outline': Icons.keyboard_return,
  'remove-outline': Icons.remove,
  'terminal-outline': Icons.terminal,
  'play-skip-back': Icons.skip_previous,
  'play': Icons.play_arrow,
  'play-skip-forward': Icons.skip_next,
  'volume-high-outline': Icons.volume_up_outlined,
  'volume-mute-outline': Icons.volume_off_outlined,
  'volume-low-outline': Icons.volume_down_outlined,
  'apps-outline': Icons.apps,
  'chevron-back-outline': Icons.chevron_left,
  'chevron-forward-outline': Icons.chevron_right,
  'chevron-up-outline': Icons.keyboard_arrow_up,
  'chevron-down-outline': Icons.keyboard_arrow_down,
  'ellipse-outline': Icons.circle_outlined,
};

IconData iconFor(String name) => deckIcons[name] ?? Icons.circle_outlined;

const _hotkeyIcons = {
  'esc': Icons.close,
  'enter': Icons.keyboard_return,
  'return': Icons.keyboard_return,
  'space': Icons.space_bar,
  'tab': Icons.keyboard_tab,
  'left': Icons.chevron_left,
  'right': Icons.chevron_right,
  'up': Icons.keyboard_arrow_up,
  'down': Icons.keyboard_arrow_down,
  'pageup': Icons.keyboard_arrow_up,
  'pagedown': Icons.keyboard_arrow_down,
  'delete': Icons.backspace_outlined,
  'backspace': Icons.backspace_outlined,
};

const _hotkeyComboIcons = {
  'c': Icons.content_copy_outlined, // ctrl+c
  'v': Icons.content_paste_outlined, // ctrl+v
  'x': Icons.content_cut_outlined, // ctrl+x
  'z': Icons.undo, // ctrl+z
  's': Icons.save_outlined, // ctrl+s
  'd': Icons.desktop_windows_outlined, // win+d
  'tab': Icons.apps, // alt+tab
  'f4': Icons.close, // alt+f4
};

/// deck.json often leaves user-added buttons on the generic default icon
/// (ellipse-outline); guess something more useful from the action so the
/// grid doesn't turn into a wall of circles, mirroring the curated defaults
/// in deck_store.py's default_config().
IconData iconForButton(DeckButton btn) {
  if (btn.icon != 'ellipse-outline' && btn.icon.isNotEmpty) {
    return iconFor(btn.icon);
  }
  switch (btn.action.kind) {
    case 'volume':
      switch (btn.action.volumeAction) {
        case 'up':
          return Icons.volume_up_outlined;
        case 'down':
          return Icons.volume_down_outlined;
        default:
          return Icons.volume_off_outlined;
      }
    case 'shell':
      return Icons.terminal;
    case 'app':
      return Icons.apps;
    case 'url':
      return Icons.language;
    case 'hotkey':
      final keys = btn.action.keys.map((k) => k.toLowerCase()).toList();
      if (keys.isEmpty) break;
      final last = keys.last;
      if (_hotkeyIcons.containsKey(last)) return _hotkeyIcons[last]!;
      if (keys.length > 1 && _hotkeyComboIcons.containsKey(last)) {
        return _hotkeyComboIcons[last]!;
      }
      return Icons.keyboard_outlined;
  }
  return Icons.circle_outlined;
}
