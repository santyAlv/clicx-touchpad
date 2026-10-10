"""Extract Windows application icons as high-res PNG base64."""

from __future__ import annotations

import base64
import ctypes
import io
import os
import sys
from ctypes import wintypes
from pathlib import Path

if sys.platform == "win32":
    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    shell32 = ctypes.windll.shell32
    comctl32 = ctypes.windll.comctl32

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HANDLE),
            ("hbmColor", wintypes.HANDLE),
        ]

    class BITMAP(ctypes.Structure):
        _fields_ = [
            ("bmType", wintypes.LONG),
            ("bmWidth", wintypes.LONG),
            ("bmHeight", wintypes.LONG),
            ("bmWidthBytes", wintypes.LONG),
            ("bmPlanes", wintypes.WORD),
            ("bmBitsPixel", wintypes.WORD),
            ("bmBits", ctypes.c_void_p),
        ]

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [
            ("hIcon", wintypes.HANDLE),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", wintypes.DWORD),
            ("szDisplayName", wintypes.WCHAR * 260),
            ("szTypeName", wintypes.WCHAR * 80),
        ]

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    BI_RGB = 0
    DIB_RGB_COLORS = 0
    DI_NORMAL = 0x0003
    SHGFI_SYSICONINDEX = 0x00004000
    SHIL_EXTRALARGE = 2
    SHIL_JUMBO = 4
    ILD_TRANSPARENT = 0x00000001
    IID_IImageList = GUID(
        0x46EB5926,
        0x582E,
        0x4017,
        (0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50),
    )
    user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
    user32.GetIconInfo.restype = wintypes.BOOL
    user32.DrawIconEx.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HICON,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
        wintypes.HANDLE,
        wintypes.UINT,
    ]
    user32.DrawIconEx.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.DestroyIcon.restype = wintypes.BOOL
    gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
    gdi32.GetObjectW.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HANDLE,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    user32.PrivateExtractIconsW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(wintypes.HICON),
        ctypes.POINTER(wintypes.UINT),
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.PrivateExtractIconsW.restype = wintypes.UINT
    shell32.SHGetImageList.argtypes = [
        ctypes.c_int,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHGetImageList.restype = ctypes.HRESULT
    comctl32.ImageList_GetIcon.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        wintypes.UINT,
    ]
    comctl32.ImageList_GetIcon.restype = wintypes.HICON
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:  # noqa: BLE001
        pass
else:
    Image = None  # type: ignore[misc, assignment]

ICON_PX = 256
_CACHE: dict[str, tuple[float, int, str]] = {}


def resolve_lnk(lnk_path: str) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        from comtypes.client import CreateObject

        sh = CreateObject("WScript.Shell")
        sc = sh.CreateShortcut(os.path.abspath(lnk_path))
        target = str(sc.Targetpath or "").strip()
        return target if target else None
    except Exception:  # noqa: BLE001
        pass
    try:
        import subprocess

        ps = (
            f'(New-Object -ComObject WScript.Shell).CreateShortcut("{os.path.abspath(lnk_path)}").TargetPath'
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        ).strip()
        return out if out else None
    except Exception:  # noqa: BLE001
        return None


def resolve_app_path(path: str) -> str | None:
    raw = path.strip().strip('"').strip("'")
    if not raw:
        return None
    p = Path(raw)
    if not p.exists():
        return None
    if p.suffix.lower() == ".lnk":
        target = resolve_lnk(str(p))
        if target and Path(target).is_file():
            return target
        return None
    if p.suffix.lower() in {".exe", ".bat", ".cmd"}:
        return str(p)
    return None


def guess_app_from_command(command: str) -> str | None:
    line = command.replace("\r\n", "\n").split("\n")[0].strip()
    if not line:
        return None
    if line.startswith('"'):
        end = line.find('"', 1)
        token = line[1:end] if end > 1 else line.strip('"')
    else:
        parts = line.split()
        token = parts[0] if parts else line
    return resolve_app_path(token)


def _hbitmap_to_image(hbmp: int) -> Image.Image | None:
    if not hbmp or Image is None:
        return None
    handle = wintypes.HANDLE(hbmp)
    bmp = BITMAP()
    if not gdi32.GetObjectW(handle, ctypes.sizeof(bmp), ctypes.byref(bmp)):
        return None
    w, h = int(bmp.bmWidth), int(abs(bmp.bmHeight))
    if w <= 0 or h <= 0:
        return None

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = BI_RGB
    buf = (ctypes.c_char * (w * h * 4))()
    hdc = user32.GetDC(0)
    ok = gdi32.GetDIBits(hdc, handle, 0, h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
    user32.ReleaseDC(0, hdc)
    if not ok:
        return None
    return Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1).copy()


def _hicon_to_image(hicon: int, size: int) -> Image.Image | None:
    if not hicon or Image is None:
        return None
    icon = wintypes.HICON(hicon)
    info = ICONINFO()
    if user32.GetIconInfo(icon, ctypes.byref(info)):
        try:
            img = _hbitmap_to_image(info.hbmColor) if info.hbmColor else None
        finally:
            if info.hbmColor:
                gdi32.DeleteObject(wintypes.HANDLE(info.hbmColor))
            if info.hbmMask:
                gdi32.DeleteObject(wintypes.HANDLE(info.hbmMask))
        if img is not None and img.size[0] >= 16:
            if img.size[0] != size or img.size[1] != size:
                img = img.resize((size, size), Image.Resampling.LANCZOS)
            return img

    hdc = user32.GetDC(0)
    if not hdc:
        return None
    hdc_mem = gdi32.CreateCompatibleDC(hdc)
    hbmp = gdi32.CreateCompatibleBitmap(hdc, size, size)
    old = gdi32.SelectObject(hdc_mem, hbmp)
    user32.DrawIconEx(hdc_mem, 0, 0, icon, size, size, 0, 0, DI_NORMAL)
    img = _hbitmap_to_image(int(hbmp) if hbmp else 0)
    gdi32.SelectObject(hdc_mem, old)
    if hbmp:
        gdi32.DeleteObject(wintypes.HANDLE(hbmp))
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc)
    return img


def _image_to_b64(img: Image.Image) -> str:
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return base64.b64encode(out.getvalue()).decode("ascii")


def _hicon_to_png_b64(hicon: int, size: int) -> str | None:
    img = _hicon_to_image(hicon, size)
    if img is None:
        return None
    return _image_to_b64(img)


def _extract_private(path: str, size: int) -> int | None:
    hicon = wintypes.HICON()
    got = user32.PrivateExtractIconsW(
        path, 0, size, size, ctypes.byref(hicon), None, 1, 0
    )
    if got and hicon.value:
        return int(hicon.value)
    return None


def _extract_imagelist(path: str, size: int) -> int | None:
    info = SHFILEINFOW()
    if not shell32.SHGetFileInfoW(
        path, 0, ctypes.byref(info), ctypes.sizeof(info), SHGFI_SYSICONINDEX
    ):
        return None
    himl = ctypes.c_void_p()
    shil = SHIL_JUMBO if size >= 48 else SHIL_EXTRALARGE
    hr = shell32.SHGetImageList(shil, ctypes.byref(IID_IImageList), ctypes.byref(himl))
    if hr != 0 or not himl:
        return None
    hicon = comctl32.ImageList_GetIcon(himl, info.iIcon, ILD_TRANSPARENT)
    return int(hicon) if hicon else None


def _extract_legacy(path: str) -> int | None:
    large = (ctypes.c_void_p * 1)()
    small = (ctypes.c_void_p * 1)()
    try:
        count = shell32.ExtractIconExW(path, 0, large, small, 1)
    except Exception:  # noqa: BLE001
        return None
    if not count:
        return None
    hicon = large[0] or small[0]
    return int(hicon) if hicon else None


def extract_icon_b64(path: str, size: int = ICON_PX) -> str | None:
    """Return a high-res PNG base64 for a .exe / .lnk path, or None."""
    if sys.platform != "win32":
        return None
    resolved = resolve_app_path(path)
    if not resolved:
        return None
    try:
        mtime = Path(resolved).stat().st_mtime
    except OSError:
        mtime = 0.0
    cached = _CACHE.get(resolved)
    if cached and cached[0] == mtime and cached[1] == size:
        return cached[2]

    hicon = None
    try:
        try:
            hicon = _extract_private(resolved, size)
        except Exception:  # noqa: BLE001
            hicon = None
        if not hicon:
            try:
                hicon = _extract_imagelist(resolved, size)
            except Exception:  # noqa: BLE001
                hicon = None
        if not hicon:
            hicon = _extract_legacy(resolved)
        if not hicon:
            return None
        b64 = _hicon_to_png_b64(hicon, size)
        if b64:
            _CACHE[resolved] = (mtime, size, b64)
        return b64
    finally:
        if hicon:
            user32.DestroyIcon(wintypes.HICON(hicon))


def attach_button_icon(btn: dict) -> None:
    """Fill btn['iconB64'] from action.app or shell command path.

    Only executable-derived icons are written here. Icons the user supplied
    themselves — a picked image, an Iconify glyph, a site favicon — are left
    alone; this used to drop them on every save.
    """
    action = btn.get("action")
    if not isinstance(action, dict):
        return

    app = str(action.get("app", "")).strip()
    if not app and action.get("kind") == "shell":
        app = guess_app_from_command(str(action.get("command", ""))) or ""
    if not app:
        return

    b64 = extract_icon_b64(app, ICON_PX)
    if b64:
        btn["iconB64"] = b64


def attach_icons(cfg: dict) -> None:
    for page in cfg.get("pages", []):
        if not isinstance(page, dict):
            continue
        for btn in page.get("buttons", []):
            if isinstance(btn, dict):
                attach_button_icon(btn)
