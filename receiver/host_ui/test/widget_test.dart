import 'package:flutter_test/flutter_test.dart';

import 'package:clicx_host/main.dart';

void main() {
  testWidgets('app boots and shows the sidebar + connect pane',
      (WidgetTester tester) async {
    await tester.pumpWidget(ClicxApp());
    await tester.pump();
    expect(find.text('ClicX'), findsOneWidget);
    expect(find.text('Conectar'), findsWidgets);
  });
}
