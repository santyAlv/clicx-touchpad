#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <windows.h>

#include <algorithm>

#include "flutter_window.h"
#include "utils.h"

int APIENTRY wWinMain(_In_ HINSTANCE instance, _In_opt_ HINSTANCE prev,
                      _In_ wchar_t *command_line, _In_ int show_command) {
  // Attach to console when present (e.g., 'flutter run') or create a
  // new console when running with a debugger.
  if (!::AttachConsole(ATTACH_PARENT_PROCESS) && ::IsDebuggerPresent()) {
    CreateAndAttachConsole();
  }

  // Initialize COM, so that it is available for use in the library and/or
  // plugins.
  ::CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);

  flutter::DartProject project(L"data");

  std::vector<std::string> command_line_arguments =
      GetCommandLineArguments();

  // The "add button" dialog runs as its own process so it gets a real OS
  // window; it wants a small one. Dart reads the same flag to pick its UI.
  const bool is_dialog =
      std::find(command_line_arguments.begin(), command_line_arguments.end(),
                "--add-button") != command_line_arguments.end();

  project.set_dart_entrypoint_arguments(std::move(command_line_arguments));

  FlutterWindow window(project);
  Win32Window::Size size(is_dialog ? 500 : 900, is_dialog ? 700 : 525);
  Win32Window::Point origin(10, 10);

  // Create() scales both origin and size by the monitor's factor, so a centred
  // origin has to be converted back to the unscaled units it expects.
  auto centre_in = [&size](const RECT& area, double scale) {
    return Win32Window::Point(
        static_cast<unsigned int>(
            ((area.left + area.right) / 2.0 - size.width * scale / 2.0) /
            scale),
        static_cast<unsigned int>(
            ((area.top + area.bottom) / 2.0 - size.height * scale / 2.0) /
            scale));
  };

  if (is_dialog) {
    // Centre the dialog over the main window if one is open.
    HWND main_window =
        FindWindowW(L"FLUTTER_RUNNER_WIN32_WINDOW", L"clicx_host");
    if (main_window != nullptr) {
      RECT main_rect;
      GetWindowRect(main_window, &main_rect);
      origin = centre_in(main_rect, GetDpiForWindow(main_window) / 96.0);
    }
  } else {
    RECT work_area;
    if (SystemParametersInfoW(SPI_GETWORKAREA, 0, &work_area, 0)) {
      origin = centre_in(work_area, GetDpiForSystem() / 96.0);
    }
  }

  if (!window.Create(is_dialog ? L"Agregar botón" : L"clicx_host", origin,
                     size)) {
    return EXIT_FAILURE;
  }
  window.SetQuitOnClose(true);

  ::MSG msg;
  while (::GetMessage(&msg, nullptr, 0, 0)) {
    ::TranslateMessage(&msg);
    ::DispatchMessage(&msg);
  }

  ::CoUninitialize();
  return EXIT_SUCCESS;
}
