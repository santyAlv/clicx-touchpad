import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';

import '../control_client.dart';
import '../icon_map.dart';
import '../models.dart';
import '../theme.dart';
import 'add_button_sheet.dart';
import '../widgets.dart';

const _gridColumns = 4;
const _gridRows = 2;
const _slotsPerPanel =
    _gridColumns * _gridRows; // matches windows_apps.DECK_PAGE_SIZE

// Fixed cell metrics keep every panel the same shape, the way the phone app's
// deck is sized to its icon grid rather than to the window.
const _iconSize = 52.0;
const _plateSize = 64.0; // the glass tray each icon sits in
const _cellW = 78.0;
const _cellH = 94.0;
const _gapX = 12.0;
const _gapY = 14.0;
const _panelPad = 20.0;
const _panelGap = 14.0; // breathing room between neighbouring panels

const _panelW =
    _cellW * _gridColumns + _gapX * (_gridColumns - 1) + _panelPad * 2;
const _panelH = _cellH * _gridRows + _gapY * (_gridRows - 1) + _panelPad * 2;

/// One carousel slab: a window of at most 8 buttons into a deck page. A page
/// holding more than 8 spills into further panels instead of growing taller.
class DeckPanelRef {
  final DeckPage page;
  final int offset;
  const DeckPanelRef(this.page, this.offset);
}

List<DeckPanelRef> panelsFor(Deck deck) {
  final panels = <DeckPanelRef>[];
  for (final page in deck.pages) {
    final count = math.max(1, (page.buttons.length / _slotsPerPanel).ceil());
    for (var i = 0; i < count; i++) {
      panels.add(DeckPanelRef(page, i * _slotsPerPanel));
    }
  }
  return panels;
}

class DeckScreen extends StatefulWidget {
  final ControlClient client;
  const DeckScreen({super.key, required this.client});

  @override
  State<DeckScreen> createState() => _DeckScreenState();
}

class _DeckScreenState extends State<DeckScreen> {
  int panelIndex = 0;

  @override
  Widget build(BuildContext context) {
    return CupertinoPageScaffold(
      backgroundColor: AppColors.bg,
      child: SafeArea(
        child: ListenableBuilder(
          listenable: widget.client,
          builder: (context, _) {
            final deck = widget.client.deck;
            return Column(
              children: [
                const PaneHeader(title: 'Deck'),
                Expanded(
                  child: deck == null || deck.pages.isEmpty
                      ? Center(
                          child: CupertinoActivityIndicator(
                            color: AppColors.muted,
                          ),
                        )
                      : _DeckBody(
                          panels: panelsFor(deck),
                          index: panelIndex,
                          onPageChanged: (i) => setState(() => panelIndex = i),
                          onEdit: (page, btn) =>
                              _editButton(context, page, btn),
                          onAddPage: () => _addPage(deck),
                          onDeletePage: (page) =>
                              _confirmDeletePage(context, deck, page),
                          onSave: () => widget.client.saveDeck(deck),
                        ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  /// A new, empty page lands after the last one and the carousel moves to it,
  /// so the "+" leaves you looking at what you just made.
  void _addPage(Deck deck) {
    setState(() {
      deck.pages.add(DeckPage(id: 'p${DateTime.now().millisecondsSinceEpoch}'));
      panelIndex = panelsFor(deck).length - 1;
    });
  }

  /// Deleting a page takes its buttons with it, so it asks first.
  void _confirmDeletePage(BuildContext context, Deck deck, DeckPage page) {
    final count = page.buttons.length;
    showCupertinoDialog(
      context: context,
      barrierDismissible: true,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text('Eliminar contenedor'),
        content: Text(
          count == 0
              ? 'Está vacío, se elimina sin perder nada.'
              : 'Se van a borrar sus $count '
                    '${count == 1 ? 'botón' : 'botones'}.',
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancelar'),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () {
              Navigator.pop(dialogContext);
              setState(() {
                deck.pages.remove(page);
                final last = math.max(0, panelsFor(deck).length - 1);
                if (panelIndex > last) panelIndex = last;
              });
            },
            child: const Text('Eliminar'),
          ),
        ],
      ),
    );
  }

  /// Adding opens a separate OS window (a second instance of this executable);
  /// editing stays in place, since handing an existing button — icon bytes and
  /// all — across a command line would not fit.
  void _addButton() {
    Process.start(Platform.resolvedExecutable, [
      '--add-button',
    ], mode: ProcessStartMode.detached).ignore();
  }

  void _editButton(BuildContext context, DeckPage page, DeckButton? btn) {
    if (btn == null) {
      _addButton();
      return;
    }
    showCupertinoDialog(
      context: context,
      barrierDismissible: true,
      builder: (context) => AddButtonSheet(
        client: widget.client,
        initial: btn,
        onSubmit: (edited) =>
            setState(() => page.buttons[page.buttons.indexOf(btn)] = edited),
        onDelete: () => setState(() => page.buttons.remove(btn)),
        onTest: () => widget.client.testButton(btn.id),
      ),
    );
  }
}

class _DeckBody extends StatefulWidget {
  final List<DeckPanelRef> panels;
  final int index;
  final ValueChanged<int> onPageChanged;
  final void Function(DeckPage page, DeckButton? btn) onEdit;
  final VoidCallback onAddPage;
  final ValueChanged<DeckPage> onDeletePage;
  final VoidCallback onSave;

  const _DeckBody({
    required this.panels,
    required this.index,
    required this.onPageChanged,
    required this.onEdit,
    required this.onAddPage,
    required this.onDeletePage,
    required this.onSave,
  });

  @override
  State<_DeckBody> createState() => _DeckBodyState();
}

class _DeckBodyState extends State<_DeckBody> {
  PageController? _controller;
  double _fraction = 1;
  int _wheelAt = 0;

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  /// The panel is a fixed width, so the fraction of the viewport it occupies
  /// depends on the window — that ratio is what makes the next panel peek in
  /// from the edge instead of sitting a full screen away.
  PageController _controllerFor(double maxWidth) {
    final fraction = ((_panelW + _panelGap) / maxWidth).clamp(0.2, 1.0);
    if (_controller == null || (fraction - _fraction).abs() > 0.001) {
      _controller?.dispose();
      _fraction = fraction;
      _controller = PageController(
        viewportFraction: fraction,
        initialPage: widget.index,
      );
    }
    return _controller!;
  }

  /// One panel per wheel notch. A mouse sends a burst of scroll events per
  /// notch and a trackpad sends a continuous stream, so the first event wins
  /// and the rest of the burst is ignored until the page has settled.
  // ponytail: fixed 220 ms lockout, not real momentum tracking — swap for
  // velocity accumulation if trackpads feel sticky.
  void _onScroll(PointerSignalEvent signal, int count) {
    if (signal is! PointerScrollEvent) return;
    final now = DateTime.now().millisecondsSinceEpoch;
    if (now - _wheelAt < 220) return;
    final delta = signal.scrollDelta;
    final step = delta.dy.abs() >= delta.dx.abs() ? delta.dy : delta.dx;
    if (step == 0) return;
    final next = (widget.index + (step > 0 ? 1 : -1)).clamp(0, count - 1);
    if (next == widget.index) return;
    _wheelAt = now;
    _goTo(next);
  }

  void _goTo(int index) {
    _controller?.animateToPage(
      index,
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOutCubic,
    );
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final controller = _controllerFor(constraints.maxWidth);
        return Stack(
          children: [
            const _PanelGlow(),
            Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    height: _panelH,
                    child: Listener(
                      onPointerSignal: (signal) =>
                          _onScroll(signal, widget.panels.length + 1),
                      child: PageView.builder(
                        controller: controller,
                        itemCount: widget.panels.length + 1,
                        onPageChanged: widget.onPageChanged,
                        itemBuilder: (context, i) {
                          if (i == widget.panels.length) {
                            return Center(
                              child: _AddPanel(
                                active: i == widget.index,
                                onActivate: () => _goTo(i),
                                onAdd: widget.onAddPage,
                              ),
                            );
                          }
                          final panel = widget.panels[i];
                          return Center(
                            child: _DeckPanel(
                              panel: panel,
                              active: i == widget.index,
                              onActivate: () => _goTo(i),
                              onEdit: (btn) => widget.onEdit(panel.page, btn),
                              onDelete: () => widget.onDeletePage(panel.page),
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  _PageDots(
                    count: widget.panels.length + 1,
                    index: widget.index,
                    onSelect: _goTo,
                  ),
                ],
              ),
            ),
            Positioned(
              right: 22,
              bottom: 18,
              child: PillButton(label: 'Guardar', onPressed: widget.onSave),
            ),
          ],
        );
      },
    );
  }
}

/// Soft accent wash behind the slab — without something to sit on, the
/// translucent glass edges have nothing to catch.
class _PanelGlow extends StatelessWidget {
  const _PanelGlow();

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: Alignment.center,
            radius: 0.75,
            colors: [
              AppColors.accent.withValues(alpha: 0.13),
              AppColors.accent.withValues(alpha: 0.0),
            ],
          ),
        ),
      ),
    );
  }
}

/// The dock slab: a frosted surface holding one panel's icon grid.
class _DeckPanel extends StatelessWidget {
  final DeckPanelRef panel;
  final ValueChanged<DeckButton?> onEdit;
  final bool active;
  final VoidCallback onActivate;
  final VoidCallback onDelete;
  const _DeckPanel({
    required this.panel,
    required this.onEdit,
    required this.active,
    required this.onActivate,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    // A tap on a peeking neighbour brings it to the front rather than editing
    // a button the user can only half see.
    if (!active) {
      return GestureDetector(
        onTap: onActivate,
        // IgnorePointer below makes the panel untouchable, and a GestureDetector
        // defers its hit test to its child by default — so without an opaque
        // behaviour there was nothing left to tap and the neighbour never came
        // to the front.
        behavior: HitTestBehavior.opaque,
        child: Opacity(opacity: 0.75, child: IgnorePointer(child: _panel())),
      );
    }
    return Stack(
      clipBehavior: Clip.none,
      children: [
        _panel(),
        Positioned(
          top: 8,
          right: 8,
          child: GestureDetector(
            onTap: onDelete,
            behavior: HitTestBehavior.opaque,
            child: Padding(
              padding: const EdgeInsets.all(8),
              // Drawn like the "+" — the Cupertino glyphs come out blank in the
              // release build.
              child: SizedBox(
                width: 13,
                height: 13,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Transform.rotate(
                      angle: math.pi / 4,
                      child: Container(
                        width: 14,
                        height: 1.8,
                        color: AppColors.muted,
                      ),
                    ),
                    Transform.rotate(
                      angle: -math.pi / 4,
                      child: Container(
                        width: 14,
                        height: 1.8,
                        color: AppColors.muted,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _panel() {
    return Container(
      width: _panelW,
      height: _panelH,
      padding: const EdgeInsets.all(_panelPad),
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(
          color: CupertinoColors.white.withValues(alpha: 0.07),
          width: 1,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var row = 0; row < _gridRows; row++) ...[
            if (row > 0) const SizedBox(height: _gapY),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (var col = 0; col < _gridColumns; col++) ...[
                  if (col > 0) const SizedBox(width: _gapX),
                  SizedBox(
                    width: _cellW,
                    height: _cellH,
                    child: _cell(row * _gridColumns + col),
                  ),
                ],
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _cell(int slot) {
    final index = panel.offset + slot;
    if (index >= panel.page.buttons.length) {
      return GestureDetector(
        onTap: () => onEdit(null),
        child: const _EmptySlot(),
      );
    }
    final btn = panel.page.buttons[index];
    return GestureDetector(
      onTap: () => onEdit(btn),
      child: _DeckTile(button: btn),
    );
  }
}

class _PageDots extends StatelessWidget {
  final int count;
  final int index;
  final ValueChanged<int> onSelect;
  const _PageDots({
    required this.count,
    required this.index,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    if (count <= 1) return const SizedBox.shrink();
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(count, (i) {
        return GestureDetector(
          onTap: () => onSelect(i),
          // A 6px dot is a miserable target; pad the tap area around it.
          child: Container(
            color: CupertinoColors.transparent,
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                color: i == index ? AppColors.accent : AppColors.dim,
                shape: BoxShape.circle,
              ),
            ),
          ),
        );
      }),
    );
  }
}

/// The translucent tray every icon sits in — the outer layer of the phone
/// app's glass tile.
class _GlassPlate extends StatelessWidget {
  final Widget? child;
  const _GlassPlate({this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: _plateSize,
      height: _plateSize,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(_plateSize * 0.30),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            CupertinoColors.white.withValues(alpha: 0.10),
            CupertinoColors.white.withValues(alpha: 0.02),
          ],
        ),
        border: Border.all(
          color: CupertinoColors.white.withValues(alpha: 0.14),
          width: 1,
        ),
      ),
      alignment: Alignment.center,
      child: child,
    );
  }
}

class _EmptySlot extends StatelessWidget {
  const _EmptySlot();

  @override
  Widget build(BuildContext context) {
    return const Column(
      mainAxisSize: MainAxisSize.min,
      children: [_GlassPlate()],
    );
  }
}

class _DeckTile extends StatelessWidget {
  final DeckButton button;
  const _DeckTile({required this.button});

  static const _radius = _iconSize * 0.30;

  @override
  Widget build(BuildContext context) {
    final hasImage = button.iconB64 != null && button.iconB64!.isNotEmpty;
    final tileColor = parseHexColor(button.color);

    final Widget face = hasImage
        ? ClipRRect(
            borderRadius: BorderRadius.circular(_radius),
            child: Image.memory(
              base64Decode(button.iconB64!),
              fit: BoxFit.cover,
              width: _iconSize,
              height: _iconSize,
            ),
          )
        : Container(
            width: _iconSize,
            height: _iconSize,
            decoration: BoxDecoration(
              color: tileColor,
              borderRadius: BorderRadius.circular(_radius),
              // Bright rim — what reads as the lit edge of the glass.
              border: Border.all(
                color: CupertinoColors.white.withValues(alpha: 0.55),
                width: 1.5,
              ),
            ),
            child: Stack(
              fit: StackFit.expand,
              children: [
                Center(
                  child: Icon(
                    iconForButton(button),
                    color: glyphColorOn(tileColor),
                    size: 24,
                  ),
                ),
                IgnorePointer(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(_radius - 1.5),
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: [
                          CupertinoColors.white.withValues(alpha: 0.30),
                          CupertinoColors.white.withValues(alpha: 0.0),
                        ],
                        stops: const [0.0, 0.55],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _GlassPlate(child: face),
        const SizedBox(height: 7),
        Text(
          button.label,
          textAlign: TextAlign.center,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: AppColors.fg,
            fontSize: 11,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}

/// The slot after the last panel: tap it and a new, empty page appears here.
class _AddPanel extends StatelessWidget {
  final bool active;
  final VoidCallback onActivate;
  final VoidCallback onAdd;
  const _AddPanel({
    required this.active,
    required this.onActivate,
    required this.onAdd,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: active ? onAdd : onActivate,
      behavior: HitTestBehavior.opaque,
      child: Opacity(
        opacity: active ? 1 : 0.75,
        child: Container(
          width: _panelW,
          height: _panelH,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(28),
            border: Border.all(
              color: AppColors.accent.withValues(alpha: active ? 0.5 : 0.2),
              width: 1,
            ),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Drawn, not an icon glyph: CupertinoIcons.add came out blank in
              // the release build while the panel's own accent border rendered
              // fine, so two bars are the sure thing.
              SizedBox(
                width: 26,
                height: 26,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Container(width: 26, height: 2.5, color: AppColors.accent),
                    Container(width: 2.5, height: 26, color: AppColors.accent),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Nuevo contenedor',
                style: TextStyle(color: AppColors.muted, fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
