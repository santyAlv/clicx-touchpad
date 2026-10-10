import 'package:flutter_test/flutter_test.dart';

import 'package:clicx_host/models.dart';
import 'package:clicx_host/screens/deck_screen.dart';

DeckPage _page(String id, int buttons) => DeckPage(
      id: id,
      buttons: List.generate(buttons, (i) => DeckButton(id: '$id-$i')),
    );

void main() {
  test('a page never exceeds 8 buttons per panel', () {
    final deck = Deck(pages: [
      _page('a', 12), // spills into a second panel
      _page('b', 8), // exactly one full panel
      _page('c', 3), // one partial panel
      _page('d', 0), // still gets an empty panel
    ]);

    final panels = panelsFor(deck);
    expect(panels.length, 5);
    expect(panels.map((p) => p.offset).toList(), [0, 8, 0, 0, 0]);
    expect(panels.map((p) => p.page.id).toList(), ['a', 'a', 'b', 'c', 'd']);

    // Every panel shows at most 8 of its page's buttons.
    for (final p in panels) {
      final shown = (p.page.buttons.length - p.offset).clamp(0, 8);
      expect(shown, lessThanOrEqualTo(8));
    }

    // No button is dropped: the panels cover every button of every page.
    final covered = panels.fold<int>(
      0,
      (sum, p) => sum + (p.page.buttons.length - p.offset).clamp(0, 8),
    );
    expect(covered, 12 + 8 + 3 + 0);
  });
}
