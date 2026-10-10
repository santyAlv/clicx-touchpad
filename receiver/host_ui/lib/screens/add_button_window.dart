import 'package:flutter/cupertino.dart';

import '../control_client.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets.dart';
import 'add_button_sheet.dart';

/// The contents of the standalone "add a button" window (the `--add-button`
/// process). Buttons are handed straight to the host, which persists them and
/// tells every open window, so this window owns no deck state of its own.
class AddButtonWindow extends StatefulWidget {
  final ControlClient client;
  const AddButtonWindow({super.key, required this.client});

  @override
  State<AddButtonWindow> createState() => _AddButtonWindowState();
}

class _AddButtonWindowState extends State<AddButtonWindow> {
  String? added;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        const AppTitleBar(title: 'Agregar botón'),
        Expanded(
          child: ListenableBuilder(
            listenable: widget.client,
            builder: (context, _) {
              if (!widget.client.connected) {
                return Center(
                  child: Text(
                    'Esperando al host…',
                    style: TextStyle(color: AppColors.muted, fontSize: 13),
                  ),
                );
              }
              return AddButtonSheet(
                client: widget.client,
                embedded: true,
                onSubmit: _add,
              );
            },
          ),
        ),
        if (added != null)
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
            color: AppColors.surface,
            child: Text(
              'Agregado: $added',
              style: TextStyle(color: AppColors.accent, fontSize: 12),
            ),
          ),
      ],
    );
  }

  void _add(DeckButton button) {
    widget.client.addButton(button);
    setState(() => added = button.label);
  }
}
