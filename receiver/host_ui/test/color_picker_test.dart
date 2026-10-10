import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:clicx_host/color_picker.dart';

void main() {
  test('hexOf round-trips the accent format used in deck.json', () {
    expect(hexOf(const Color(0xFF9CB080)), '#9CB080');
    expect(hexOf(const Color(0xFF0A84FF)), '#0A84FF');
    expect(hexOf(const Color(0xFF000000)), '#000000');
    expect(hexOf(const Color(0xFFFFFFFF)), '#FFFFFF');
  });

  testWidgets('dragging the picker commits a colour once, on release',
      (tester) async {
    final previews = <Color>[];
    Color? committed;

    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: ColorPicker(
            value: const Color(0xFF9CB080),
            onPreview: previews.add,
            onChanged: (c) => committed = c,
          ),
        ),
      ),
    );

    // Drag across the saturation/value square.
    final square = tester.getTopLeft(find.byType(ColorPicker));
    final gesture = await tester.startGesture(square + const Offset(20, 20));
    await tester.pump();
    await gesture.moveBy(const Offset(80, 40));
    await tester.pump();
    expect(previews, isNotEmpty, reason: 'should track the pointer live');
    expect(committed, isNull, reason: 'must not write to the host mid-drag');

    await gesture.up();
    await tester.pump();
    expect(committed, isNotNull, reason: 'commits once the drag ends');
  });
}
