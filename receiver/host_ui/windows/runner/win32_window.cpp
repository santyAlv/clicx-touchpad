#include "win32_window.h"

#include <dwmapi.h>
#include <flutter_windows.h>
#include <windowsx.h>

#include "resource.h"

namespace {

// The window draws its own title bar in Dart, so the client area is extended
// over the native caption. These are the regions the frame still has to own:
// a resize border, the draggable strip, and the min/max/close hit targets on
// its right (Windows still handles those clicks, Flutter only paints them).
constexpr int kTitleBarHeightDip = 40;
constexpr int kCaptionButtonWidthDip = 46;
constexpr int kCaptionButtonCount = 3;
constexpr int kResizeBorderDip = 6;

/// Property under which the Flutter child window finds its Win32Window.
constexpr const wchar_t kChildOwnerProp[] = L"ClicXWindowOwner";

/// Window attribute that enables dark mode window decorations.
///
/// Redefined in case the developer's machine has a Windows SDK older than
/// version 10.0.22000.0.
/// See: https://docs.microsoft.com/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
#ifndef DWMWA_USE_IMMERSIVE_DARK_MODE
#define DWMWA_USE_IMMERSIVE_DARK_MODE 20
#endif

/// Rounded-corner attributes, redefined for older Windows SDKs.
/// Removing the native caption also drops the frame's default rounding, so it
/// is asked for explicitly.
#ifndef DWMWA_WINDOW_CORNER_PREFERENCE
#define DWMWA_WINDOW_CORNER_PREFERENCE 33
#endif
#ifndef DWMWCP_ROUND
#define DWMWCP_ROUND 2
#endif

constexpr const wchar_t kWindowClassName[] = L"FLUTTER_RUNNER_WIN32_WINDOW";

/// Registry key for app theme preference.
///
/// A value of 0 indicates apps should use dark mode. A non-zero or missing
/// value indicates apps should use light mode.
constexpr const wchar_t kGetPreferredBrightnessRegKey[] =
  L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize";
constexpr const wchar_t kGetPreferredBrightnessRegValue[] = L"AppsUseLightTheme";

// The number of Win32Window objects that currently exist.
static int g_active_window_count = 0;

using EnableNonClientDpiScaling = BOOL __stdcall(HWND hwnd);

// Scale helper to convert logical scaler values to physical using passed in
// scale factor
int Scale(int source, double scale_factor) {
  return static_cast<int>(source * scale_factor);
}

// Dynamically loads the |EnableNonClientDpiScaling| from the User32 module.
// This API is only needed for PerMonitor V1 awareness mode.
void EnableFullDpiSupportIfAvailable(HWND hwnd) {
  HMODULE user32_module = LoadLibraryA("User32.dll");
  if (!user32_module) {
    return;
  }
  auto enable_non_client_dpi_scaling =
      reinterpret_cast<EnableNonClientDpiScaling*>(
          GetProcAddress(user32_module, "EnableNonClientDpiScaling"));
  if (enable_non_client_dpi_scaling != nullptr) {
    enable_non_client_dpi_scaling(hwnd);
  }
  FreeLibrary(user32_module);
}

}  // namespace

// Manages the Win32Window's window class registration.
class WindowClassRegistrar {
 public:
  ~WindowClassRegistrar() = default;

  // Returns the singleton registrar instance.
  static WindowClassRegistrar* GetInstance() {
    if (!instance_) {
      instance_ = new WindowClassRegistrar();
    }
    return instance_;
  }

  // Returns the name of the window class, registering the class if it hasn't
  // previously been registered.
  const wchar_t* GetWindowClass();

  // Unregisters the window class. Should only be called if there are no
  // instances of the window.
  void UnregisterWindowClass();

 private:
  WindowClassRegistrar() = default;

  static WindowClassRegistrar* instance_;

  bool class_registered_ = false;
};

WindowClassRegistrar* WindowClassRegistrar::instance_ = nullptr;

const wchar_t* WindowClassRegistrar::GetWindowClass() {
  if (!class_registered_) {
    WNDCLASS window_class{};
    window_class.hCursor = LoadCursor(nullptr, IDC_ARROW);
    window_class.lpszClassName = kWindowClassName;
    window_class.style = CS_HREDRAW | CS_VREDRAW;
    window_class.cbClsExtra = 0;
    window_class.cbWndExtra = 0;
    window_class.hInstance = GetModuleHandle(nullptr);
    window_class.hIcon =
        LoadIcon(window_class.hInstance, MAKEINTRESOURCE(IDI_APP_ICON));
    window_class.hbrBackground = 0;
    window_class.lpszMenuName = nullptr;
    window_class.lpfnWndProc = Win32Window::WndProc;
    RegisterClass(&window_class);
    class_registered_ = true;
  }
  return kWindowClassName;
}

void WindowClassRegistrar::UnregisterWindowClass() {
  UnregisterClass(kWindowClassName, nullptr);
  class_registered_ = false;
}

Win32Window::Win32Window() {
  ++g_active_window_count;
}

Win32Window::~Win32Window() {
  --g_active_window_count;
  Destroy();
}

bool Win32Window::Create(const std::wstring& title,
                         const Point& origin,
                         const Size& size) {
  Destroy();

  const wchar_t* window_class =
      WindowClassRegistrar::GetInstance()->GetWindowClass();

  const POINT target_point = {static_cast<LONG>(origin.x),
                              static_cast<LONG>(origin.y)};
  HMONITOR monitor = MonitorFromPoint(target_point, MONITOR_DEFAULTTONEAREST);
  UINT dpi = FlutterDesktopGetDpiForMonitor(monitor);
  double scale_factor = dpi / 96.0;

  HWND window = CreateWindow(
      window_class, title.c_str(), WS_OVERLAPPEDWINDOW,
      Scale(origin.x, scale_factor), Scale(origin.y, scale_factor),
      Scale(size.width, scale_factor), Scale(size.height, scale_factor),
      nullptr, nullptr, GetModuleHandle(nullptr), this);

  if (!window) {
    return false;
  }

  // Make Windows recompute the frame now that this window answers
  // WM_NCCALCSIZE, otherwise it keeps the native caption it sized at creation.
  SetWindowPos(window, nullptr, 0, 0, 0, 0,
               SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER |
                   SWP_NOACTIVATE);

  DWORD corner_preference = DWMWCP_ROUND;
  DwmSetWindowAttribute(window, DWMWA_WINDOW_CORNER_PREFERENCE,
                        &corner_preference, sizeof(corner_preference));

  UpdateTheme(window);

  return OnCreate();
}

bool Win32Window::Show() {
  return ShowWindow(window_handle_, SW_SHOWNORMAL);
}

// static
LRESULT CALLBACK Win32Window::WndProc(HWND const window,
                                      UINT const message,
                                      WPARAM const wparam,
                                      LPARAM const lparam) noexcept {
  if (message == WM_NCCREATE) {
    auto window_struct = reinterpret_cast<CREATESTRUCT*>(lparam);
    SetWindowLongPtr(window, GWLP_USERDATA,
                     reinterpret_cast<LONG_PTR>(window_struct->lpCreateParams));

    auto that = static_cast<Win32Window*>(window_struct->lpCreateParams);
    EnableFullDpiSupportIfAvailable(window);
    that->window_handle_ = window;
  } else if (Win32Window* that = GetThisFromHandle(window)) {
    return that->MessageHandler(window, message, wparam, lparam);
  }

  return DefWindowProc(window, message, wparam, lparam);
}

LRESULT
Win32Window::MessageHandler(HWND hwnd,
                            UINT const message,
                            WPARAM const wparam,
                            LPARAM const lparam) noexcept {
  switch (message) {
    case WM_DESTROY:
      window_handle_ = nullptr;
      Destroy();
      if (quit_on_close_) {
        PostQuitMessage(0);
      }
      return 0;

    case WM_DPICHANGED: {
      auto newRectSize = reinterpret_cast<RECT*>(lparam);
      LONG newWidth = newRectSize->right - newRectSize->left;
      LONG newHeight = newRectSize->bottom - newRectSize->top;

      SetWindowPos(hwnd, nullptr, newRectSize->left, newRectSize->top, newWidth,
                   newHeight, SWP_NOZORDER | SWP_NOACTIVATE);

      return 0;
    }
    case WM_SIZE: {
      RECT rect = GetClientArea();
      if (child_content_ != nullptr) {
        // Size and position the child window.
        MoveWindow(child_content_, rect.left, rect.top, rect.right - rect.left,
                   rect.bottom - rect.top, TRUE);
      }
      return 0;
    }

    case WM_ACTIVATE:
      if (child_content_ != nullptr) {
        SetFocus(child_content_);
      }
      return 0;

    case WM_DWMCOLORIZATIONCOLORCHANGED:
      UpdateTheme(hwnd);
      return 0;

    case WM_NCCALCSIZE: {
      if (wparam != TRUE) {
        break;
      }
      // Give the client area the whole window so Flutter paints the title bar.
      // Maximised windows still need the frame inset, or the content spills
      // past the monitor edges and under the taskbar.
      if (IsZoomed(hwnd)) {
        auto* params = reinterpret_cast<NCCALCSIZE_PARAMS*>(lparam);
        UINT dpi = FlutterDesktopGetDpiForHWND(hwnd);
        int padded = GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi);
        int frame_x = GetSystemMetricsForDpi(SM_CXFRAME, dpi) + padded;
        int frame_y = GetSystemMetricsForDpi(SM_CYFRAME, dpi) + padded;
        params->rgrc[0].left += frame_x;
        params->rgrc[0].right -= frame_x;
        params->rgrc[0].top += frame_y;
        params->rgrc[0].bottom -= frame_y;
      }
      return 0;
    }

    case WM_NCHITTEST:
      return FrameHitTest({GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)});
  }

  return DefWindowProc(window_handle_, message, wparam, lparam);
}

void Win32Window::Destroy() {
  OnDestroy();

  if (window_handle_) {
    DestroyWindow(window_handle_);
    window_handle_ = nullptr;
  }
  if (g_active_window_count == 0) {
    WindowClassRegistrar::GetInstance()->UnregisterWindowClass();
  }
}

Win32Window* Win32Window::GetThisFromHandle(HWND const window) noexcept {
  return reinterpret_cast<Win32Window*>(
      GetWindowLongPtr(window, GWLP_USERDATA));
}

LRESULT Win32Window::FrameHitTest(POINT screen_point) const {
  HWND hwnd = window_handle_;
  RECT window_rect;
  GetWindowRect(hwnd, &window_rect);

  const double scale = FlutterDesktopGetDpiForHWND(hwnd) / 96.0;
  const int border = Scale(kResizeBorderDip, scale);
  const int title_height = Scale(kTitleBarHeightDip, scale);
  const int button_width = Scale(kCaptionButtonWidthDip, scale);
  const int buttons_width = button_width * kCaptionButtonCount;

  // Resize edges — a maximised window has none.
  if (!IsZoomed(hwnd)) {
    const bool left = screen_point.x < window_rect.left + border;
    const bool right = screen_point.x >= window_rect.right - border;
    const bool top = screen_point.y < window_rect.top + border;
    const bool bottom = screen_point.y >= window_rect.bottom - border;
    if (top && left) return HTTOPLEFT;
    if (top && right) return HTTOPRIGHT;
    if (bottom && left) return HTBOTTOMLEFT;
    if (bottom && right) return HTBOTTOMRIGHT;
    if (top) return HTTOP;
    if (bottom) return HTBOTTOM;
    if (left) return HTLEFT;
    if (right) return HTRIGHT;
  }

  if (screen_point.y < window_rect.top + title_height) {
    const int from_right = window_rect.right - screen_point.x;
    if (from_right < buttons_width) {
      const int slot = from_right / button_width;
      if (slot == 0) return HTCLOSE;
      if (slot == 1) return HTMAXBUTTON;
      return HTMINBUTTON;
    }
    return HTCAPTION;
  }
  return HTCLIENT;
}

// static
LRESULT CALLBACK Win32Window::ChildWndProc(HWND window,
                                           UINT message,
                                           WPARAM wparam,
                                           LPARAM lparam) noexcept {
  auto* self =
      static_cast<Win32Window*>(GetPropW(window, kChildOwnerProp));
  if (self == nullptr) {
    return DefWindowProc(window, message, wparam, lparam);
  }

  if (message == WM_LBUTTONDOWN || message == WM_SETCURSOR ||
      message == WM_LBUTTONDBLCLK) {
    POINT cursor;
    GetCursorPos(&cursor);
    const LRESULT hit = self->FrameHitTest(cursor);
    if (hit != HTCLIENT) {
      HWND parent = self->window_handle_;
      switch (message) {
        case WM_SETCURSOR: {
          LPCWSTR shape = IDC_ARROW;
          switch (hit) {
            case HTLEFT:
            case HTRIGHT: shape = IDC_SIZEWE; break;
            case HTTOP:
            case HTBOTTOM: shape = IDC_SIZENS; break;
            case HTTOPLEFT:
            case HTBOTTOMRIGHT: shape = IDC_SIZENWSE; break;
            case HTTOPRIGHT:
            case HTBOTTOMLEFT: shape = IDC_SIZENESW; break;
            default: break;
          }
          SetCursor(LoadCursor(nullptr, shape));
          return TRUE;
        }
        case WM_LBUTTONDBLCLK:
          if (hit == HTCAPTION) {
            ShowWindow(parent, IsZoomed(parent) ? SW_RESTORE : SW_MAXIMIZE);
          }
          return 0;
        default:
          switch (hit) {
            case HTCLOSE:
              PostMessage(parent, WM_CLOSE, 0, 0);
              return 0;
            case HTMINBUTTON:
              ShowWindow(parent, SW_MINIMIZE);
              return 0;
            case HTMAXBUTTON:
              ShowWindow(parent, IsZoomed(parent) ? SW_RESTORE : SW_MAXIMIZE);
              return 0;
            default:
              // Hand the drag or resize to Windows, which runs its own modal
              // loop for the gesture.
              ReleaseCapture();
              SendMessage(parent, WM_NCLBUTTONDOWN, hit, 0);
              return 0;
          }
      }
    }
  }

  return CallWindowProc(self->child_original_proc_, window, message, wparam,
                        lparam);
}

void Win32Window::SetChildContent(HWND content) {
  child_content_ = content;
  SetParent(content, window_handle_);
  RECT frame = GetClientArea();

  MoveWindow(content, frame.left, frame.top, frame.right - frame.left,
             frame.bottom - frame.top, true);

  // Route the frame's mouse gestures back to this window (see ChildWndProc).
  SetPropW(content, kChildOwnerProp, this);
  child_original_proc_ = reinterpret_cast<WNDPROC>(SetWindowLongPtr(
      content, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(ChildWndProc)));

  SetFocus(child_content_);
}

RECT Win32Window::GetClientArea() {
  RECT frame;
  GetClientRect(window_handle_, &frame);
  return frame;
}

HWND Win32Window::GetHandle() {
  return window_handle_;
}

void Win32Window::SetQuitOnClose(bool quit_on_close) {
  quit_on_close_ = quit_on_close;
}

bool Win32Window::OnCreate() {
  // No-op; provided for subclasses.
  return true;
}

void Win32Window::OnDestroy() {
  // No-op; provided for subclasses.
}

void Win32Window::UpdateTheme(HWND const window) {
  DWORD light_mode;
  DWORD light_mode_size = sizeof(light_mode);
  LSTATUS result = RegGetValue(HKEY_CURRENT_USER, kGetPreferredBrightnessRegKey,
                               kGetPreferredBrightnessRegValue,
                               RRF_RT_REG_DWORD, nullptr, &light_mode,
                               &light_mode_size);

  if (result == ERROR_SUCCESS) {
    BOOL enable_dark_mode = light_mode == 0;
    DwmSetWindowAttribute(window, DWMWA_USE_IMMERSIVE_DARK_MODE,
                          &enable_dark_mode, sizeof(enable_dark_mode));
  }
}
