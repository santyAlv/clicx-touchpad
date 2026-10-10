"""ClicX Host — interactive Windows control panel."""

from __future__ import annotations

import base64
import io
import os
import queue
import sys
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, filedialog
from typing import Any, Callable

import main as core
import deck_store as deck
from host_backend import HostController, find_adb, run_adb  # noqa: F401
from app_picker import AppPicker
from icon_extract import attach_button_icon, extract_icon_b64, resolve_app_path
from windows_apps import DECK_PAGE_SIZE

if sys.platform == "win32":
    from PIL import Image, ImageTk
else:
    Image = None  # type: ignore[misc, assignment]
    ImageTk = None  # type: ignore[misc, assignment]

# Forest moss — #9CB080 #618764 #2B5748 #273338
BG = "#273338"
PAGE = "#2B5748"
SURFACE = "#2B5748"
SURFACE_2 = "#618764"
FG = "#E8EDE4"
MUTED = "#9CB080"
DIM = "#618764"
ACCENT = "#9CB080"
ACCENT_HOVER = "#B5C89A"
OK = "#9CB080"
WARN = "#9CB080"
ERR = "#C45C4A"
BORDER = "#618764"
HAIR = "#2B5748"
SEG = "#2B5748"
DOT = "#9CB080"
DOT_SOFT = "#618764"
DOKKE_BG = "#273338"
DOKKE_SURFACE = "#2B5748"
DOKKE_TILE = "#273338"
DOKKE_ACCENT = "#9CB080"
DOKKE_BORDER = "#618764"
BLUE = "#618764"
BLUE_HOVER = "#9CB080"




def _rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    **kwargs: Any,
) -> int:
    """Draw a rounded rectangle on a Canvas."""
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + r,
        y1,
        x2 - r,
        y1,
        x2,
        y1,
        x2,
        y1 + r,
        x2,
        y2 - r,
        x2,
        y2,
        x2 - r,
        y2,
        x1 + r,
        y2,
        x1,
        y2,
        x1,
        y2 - r,
        x1,
        y1 + r,
        x1,
        y1,
    ]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def _paint_dot_field(
    canvas: tk.Canvas,
    width: int,
    height: int,
    *,
    step: int = 18,
    radius: int = 2,
    color: str = DOT_SOFT,
    accent_color: str = DOT,
    accent_cx: float | None = None,
    accent_cy: float | None = None,
    accent_r: float = 120,
) -> None:
    """Mousely-style soft dot grid with a blue cluster."""
    canvas.delete("dots")
    if width < 8 or height < 8:
        return
    ax = accent_cx if accent_cx is not None else width * 0.78
    ay = accent_cy if accent_cy is not None else height * 0.42
    for y in range(step // 2, height, step):
        for x in range(step // 2, width, step):
            dx, dy = x - ax, y - ay
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < accent_r:
                t = 1.0 - dist / accent_r
                if t > 0.15 or (x // step + y // step) % 2 == 0:
                    fill = accent_color if t > 0.45 else color
                    r = radius + (1 if t > 0.6 else 0)
                    canvas.create_oval(
                        x - r, y - r, x + r, y + r, fill=fill, outline="", tags="dots"
                    )
            elif (x // step + y // step) % 3 == 0:
                canvas.create_oval(
                    x - 1, y - 1, x + 1, y + 1, fill=color, outline="", tags="dots"
                )


class RoundFrame(tk.Frame):
    """Content frame with a soft rounded background."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        radius: int = 22,
        fill: str = SURFACE,
        outline: str = BORDER,
        pad: int = 16,
        dots: bool = False,
    ) -> None:
        outer = master.cget("bg") if hasattr(master, "cget") else BG
        super().__init__(master, bg=outer)
        self._radius = radius
        self._fill = fill
        self._outline = outline
        self._dots = dots
        self._canvas = tk.Canvas(self, bg=outer, highlightthickness=0, bd=0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.inner = tk.Frame(self, bg=fill)
        self.inner.pack(fill="both", expand=True, padx=pad, pady=pad)
        self.bind("<Configure>", self._paint)

    def _paint(self, _event: Any = None) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w < 6 or h < 6:
            return
        self._canvas.delete("soft")
        _rounded_rect(
            self._canvas,
            1,
            1,
            w - 2,
            h - 2,
            self._radius,
            fill=self._fill,
            outline=self._outline,
            width=1,
            tags="soft",
        )
        if self._dots:
            step = 16
            for y in range(18, h - 12, step):
                for x in range(18, w - 12, step):
                    if (x // step + y // step) % 2:
                        continue
                    self._canvas.create_oval(
                        x - 1.5,
                        y - 1.5,
                        x + 1.5,
                        y + 1.5,
                        fill=DOT_SOFT,
                        outline="",
                        tags="soft",
                    )

    def set_fill(self, fill: str, outline: str | None = None) -> None:
        self._fill = fill
        if outline is not None:
            self._outline = outline
        self.inner.configure(bg=fill)
        self._paint()


class RoundButton(tk.Canvas):
    """Pill / rounded clickable button (Mousely-style)."""

    _STYLES = {
        "primary": (BLUE, BLUE_HOVER, "#FFFFFF", None),
        "secondary": (SURFACE_2, SEG, FG, BORDER),
        "quiet": (SEG, HAIR, FG, None),
        "link": (SURFACE, SURFACE, BLUE, None),
        "danger": (SURFACE_2, "#3A2020", ERR, BORDER),
        "back": (BG, BG, BLUE, None),
        "nav": (SURFACE, SURFACE_2, FG, BORDER),
        "accent": (ACCENT, ACCENT_HOVER, "#273338", None),
    }

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        kind: str = "secondary",
        radius: int = 20,
        height: int = 42,
        font_size: int = 12,
        bold: bool = False,
    ) -> None:
        outer = master.cget("bg") if hasattr(master, "cget") else BG
        super().__init__(
            master, height=height, bg=outer, highlightthickness=0, bd=0, cursor="hand2"
        )
        self._command = command
        self._radius = radius
        self._kind = kind
        self._text = text
        self._state = "normal"
        self._font = (
            ("Segoe UI Semibold", font_size)
            if bold or kind in ("primary", "link", "back")
            else ("Segoe UI", font_size)
        )
        self._fill, self._hover, self._fg, self._outline = self._STYLES.get(
            kind, self._STYLES["secondary"]
        )
        self._current = self._fill
        self.bind("<Configure>", self._paint)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _paint(self, _event: Any = None) -> None:
        w, h = max(self.winfo_width(), 2), max(self.winfo_height(), 2)
        self.delete("all")
        r = min(self._radius, h // 2)
        outline = self._outline if self._outline else self._current
        _rounded_rect(
            self,
            1,
            1,
            w - 2,
            h - 2,
            r,
            fill=self._current,
            outline=outline,
            width=1 if self._outline else 0,
        )
        self.create_text(
            w / 2,
            h / 2,
            text=self._fit_text(w),
            fill=self._fg if self._state == "normal" else DIM,
            font=self._font,
        )

    def _fit_text(self, width: int) -> str:
        text = self._text
        if width < 28:
            return text[:1] if text else ""
        max_chars = max(2, (width - 10) // 7)
        if len(text) <= max_chars:
            return text
        if max_chars < 2:
            return "…"
        return text[: max_chars - 1] + "…"

    def _on_enter(self, _event: Any = None) -> None:
        if self._state != "normal":
            return
        self._current = self._hover
        self._paint()

    def _on_leave(self, _event: Any = None) -> None:
        self._current = self._fill
        self._paint()

    def _on_click(self, _event: Any = None) -> None:
        if self._state != "normal":
            return
        self._command()

    def configure(self, cnf: Any = None, **kw: Any) -> Any:  # type: ignore[override]
        if cnf and isinstance(cnf, dict):
            kw = {**cnf, **kw}
        changed = False
        if "text" in kw:
            self._text = str(kw.pop("text"))
            changed = True
        if "state" in kw:
            self._state = str(kw.pop("state"))
            super().configure(cursor="arrow" if self._state != "normal" else "hand2")
            changed = True
        if "kind" in kw:
            self._kind = str(kw.pop("kind"))
            self._fill, self._hover, self._fg, self._outline = self._STYLES.get(
                self._kind, self._STYLES["secondary"]
            )
            self._current = self._fill
            changed = True
        if kw:
            return super().configure(**kw)
        if changed:
            self._paint()
        return None

    def config(self, cnf: Any = None, **kw: Any) -> Any:  # type: ignore[override]
        return self.configure(cnf, **kw)


class DeckSlotTile(tk.Canvas):
    """DockGridView tile — icon well or AddSlotButton (+) on hover."""

    def __init__(
        self,
        master: tk.Misc,
        command: Callable[[], None],
        *,
        height: int = 80,
    ) -> None:
        outer = master.cget("bg") if hasattr(master, "cget") else BG
        super().__init__(
            master,
            width=height,
            height=height,
            bg=outer,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self._command = command
        self._text = ""
        self._selected = False
        self._empty = False
        self._hovered = False
        self._icon_photo: Any = None
        self._icon_b64: str | None = None
        self.bind("<Configure>", self._paint)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event: Any = None) -> None:
        self._hovered = True
        self._paint()

    def _on_leave(self, _event: Any = None) -> None:
        self._hovered = False
        self._paint()

    def configure(self, cnf: Any = None, **kw: Any) -> Any:  # type: ignore[override]
        if cnf and isinstance(cnf, dict):
            kw = {**cnf, **kw}
        changed = False
        if "text" in kw:
            self._text = str(kw.pop("text"))
            changed = True
        if "selected" in kw:
            self._selected = bool(kw.pop("selected"))
            changed = True
        if "icon_b64" in kw:
            self._icon_b64 = kw.pop("icon_b64") or None
            changed = True
        if "empty" in kw:
            self._empty = bool(kw.pop("empty"))
            changed = True
        if kw:
            super().configure(**kw)
        if changed:
            self._paint()
        return None

    def _on_click(self, _event: Any = None) -> None:
        self._command()

    def _load_photo(self, b64: str, size: int) -> Any | None:
        if not Image or not ImageTk:
            return None
        try:
            raw = base64.b64decode(b64)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:  # noqa: BLE001
            return None

    def _paint(self, _event: Any = None) -> None:
        w, h = max(self.winfo_width(), 2), max(self.winfo_height(), 2)
        self.delete("all")
        r = min(28, max(8, min(w, h) // 3))
        inset = 2
        if self._empty:
            fill = "#618764" if self._hovered else "#273338"
            outline = "#9CB080" if self._hovered else "#618764"
            _rounded_rect(
                self,
                inset,
                inset,
                w - inset,
                h - inset,
                r,
                fill=fill,
                outline=outline,
                width=1,
            )
            if self._hovered:
                self.create_text(
                    w / 2,
                    h / 2,
                    text="+",
                    fill="#E8EDE4",
                    font=("Segoe UI Semibold", 18),
                )
            return
        fill = "#618764" if self._hovered else "#273338"
        outline = ACCENT if self._selected else ("#9CB080" if self._hovered else "#618764")
        _rounded_rect(
            self,
            inset,
            inset,
            w - inset,
            h - inset,
            r,
            fill=fill,
            outline=outline,
            width=2 if self._selected else 1,
        )
        icon_size = max(32, int(min(w, h) * 0.84) - 4)
        if self._icon_b64 and icon_size >= 16:
            self._icon_photo = self._load_photo(self._icon_b64, icon_size)
            if self._icon_photo:
                self.create_image(w / 2, h / 2, image=self._icon_photo)
                return
        label = self._text or "·"
        self.create_text(
            w / 2,
            h / 2,
            text=label,
            fill=FG,
            font=("Segoe UI Semibold", 10),
        )


class ClicxApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ClicX")
        self.configure(bg=BG)
        self.geometry("980x720")
        self.minsize(820, 620)
        self.resizable(True, True)

        self.ui_q: queue.SimpleQueue[tuple[str, Any]] = queue.SimpleQueue()
        self.controller = HostController(self.ui_q)
        self.ip_var = tk.StringVar(value=core.local_ip())
        self.port_var = tk.StringVar(value=str(core.PORT))
        self.status_var = tk.StringVar(value="Ready")
        self.clients_var = tk.StringVar(value="0 clients")
        self.url_var = tk.StringVar()
        self.qr_payload_var = tk.StringVar()
        self._qr_photo: Any = None
        self._usb_active = False
        self._running_ui = False
        self._view = "home"
        self._home_tab = "deck"
        self.deck_cfg: dict[str, Any] = deck.load_config()
        self._deck_page_idx = 0
        self._deck_slot_idx = 0
        self._deck_icon_preview_photo: Any = None
        self._deck_reordering = False
        self._reorder_from: int | None = None
        self._about_qr_photo: Any = None
        self._sidebar_visible = True

        self._build()
        self._refresh_url()
        self.after(80, self._poll_ui)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._start)

    def _font(self, size: int, *, bold: bool = False) -> tuple[str, int]:
        if bold:
            return ("Segoe UI Semibold", size)
        return ("Segoe UI", size)

    def _label(
        self,
        parent: tk.Misc,
        text: str = "",
        *,
        var: tk.StringVar | None = None,
        size: int = 13,
        color: str = FG,
        bold: bool = False,
        justify: str = "left",
        anchor: str | None = None,
        **pack,
    ) -> tk.Label:
        kw: dict[str, Any] = {
            "fg": color,
            "bg": parent.cget("bg"),
            "font": self._font(size, bold=bold),
            "justify": justify,
        }
        if anchor is not None:
            kw["anchor"] = anchor
        if var is not None:
            kw["textvariable"] = var
        else:
            kw["text"] = text
        width = pack.pop("width", None)
        if width is not None:
            kw["width"] = width
        lbl = tk.Label(parent, **kw)
        if pack:
            lbl.pack(**pack)
        return lbl

    def _btn(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        kind: str = "secondary",
        radius: int = 20,
        height: int = 42,
    ) -> RoundButton:
        return RoundButton(
            parent,
            text,
            command,
            kind=kind,
            radius=radius,
            height=height,
            bold=kind in ("primary", "link", "back"),
        )

    def _btn_slot(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        kind: str = "secondary",
        radius: int = 18,
        height: int = 42,
        padx: tuple[int, int] = (0, 8),
    ) -> RoundButton:
        """Equal-width slot so Canvas buttons expand correctly."""
        slot = tk.Frame(parent, bg=BG)
        slot.pack(side="left", fill="both", expand=True, padx=padx)
        btn = self._btn(slot, text, command, kind=kind, radius=radius, height=height)
        btn.pack(fill="both", expand=True)
        return btn

    def _build(self) -> None:
        self.shell = tk.Frame(self, bg=BG)
        self.shell.pack(fill="both", expand=True)

        self.home = tk.Frame(self.shell, bg=BG)
        self.home.pack(fill="both", expand=True)

        titlebar = tk.Frame(self.home, bg=BG, height=36)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        self._sidebar_toggle = self._btn(
            titlebar, "☰", self._toggle_sidebar, kind="back", radius=8, height=26
        )
        self._sidebar_toggle.pack(side="left", padx=(12, 0), pady=5)
        self._label(
            titlebar, "ClicX", size=13, bold=True, color=FG, side="left", padx=(8, 0)
        )

        self._home_body = tk.Frame(self.home, bg=BG)
        self._home_body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._home_body.columnconfigure(0, weight=0, minsize=208)
        self._home_body.columnconfigure(1, weight=1)
        self._home_body.rowconfigure(0, weight=1)

        self._side_wrap = RoundFrame(
            self._home_body, radius=18, fill=SURFACE, outline=BORDER, pad=10
        )
        self._side_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        side = self._side_wrap.inner

        self._nav_deck = self._make_sidebar_item(side, "▦   Slots", "deck")
        self._nav_conn = self._make_sidebar_item(side, "ⓘ   Conectar", "connection")

        tk.Frame(side, bg=SURFACE, height=8).pack(fill="x", expand=True)

        status = tk.Frame(side, bg=SURFACE)
        status.pack(fill="x", pady=(8, 0))
        self.status_dot = tk.Canvas(
            status, width=10, height=10, bg=SURFACE, highlightthickness=0
        )
        self.status_dot.pack(side="left", pady=2)
        self._draw_dot(DIM)
        self._label(
            status,
            var=self.status_var,
            size=11,
            bold=True,
            color=FG,
            side="left",
            padx=(6, 0),
        )
        self._label(
            side, var=self.clients_var, size=11, color=MUTED, anchor="w", pady=(2, 0)
        )
        self._label(
            side,
            f"Host  ·  v{core.VERSION}",
            size=10,
            color=DIM,
            anchor="w",
            pady=(8, 0),
        )

        self.admin_frame = RoundFrame(
            side, radius=12, fill=SURFACE_2, outline=BORDER, pad=10
        )
        self.admin_label = tk.Label(
            self.admin_frame.inner,
            text="",
            fg=MUTED,
            bg=SURFACE_2,
            font=self._font(10),
            justify="left",
            wraplength=160,
            anchor="w",
        )
        self.admin_label.pack(anchor="w")
        self.admin_btn = self._btn(
            self.admin_frame.inner,
            "Abrir como admin",
            self._relaunch_admin,
            kind="primary",
            radius=12,
            height=32,
        )
        self.admin_btn.pack(anchor="w", fill="x", pady=(8, 0))

        right = tk.Frame(self._home_body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.connection_panel = tk.Frame(right, bg=BG)
        self.connection_panel.grid(row=0, column=0, sticky="nsew")
        self.connection_panel.columnconfigure(0, weight=1)
        self.connection_panel.rowconfigure(0, weight=1)
        self._build_about_panel()

        self.deck_panel = tk.Frame(right, bg=BG)
        self.deck_panel.grid(row=0, column=0, sticky="nsew")
        self.deck_panel.rowconfigure(0, weight=1)
        self.deck_panel.columnconfigure(0, weight=1)
        self._build_deck_panel()

        # —— QR VIEW ——
        self.qr_view = tk.Frame(self.shell, bg=BG)

        qr_inner = tk.Frame(self.qr_view, bg=BG)
        qr_inner.pack(fill="both", expand=True, padx=28, pady=22)

        qr_nav = RoundFrame(qr_inner, radius=24, fill=SURFACE, outline=BORDER, pad=8)
        qr_nav.pack(fill="x")
        self._btn(
            qr_nav.inner,
            "←  Back",
            self._show_home_view,
            kind="back",
            radius=16,
            height=34,
        ).pack(side="left")
        self._label(
            qr_nav.inner, "Emparejar", size=14, bold=True, color=FG, side="left", padx=(12, 0)
        )

        qr_body = tk.Frame(qr_inner, bg=BG)
        qr_body.pack(fill="both", expand=True, pady=(18, 0))

        qr_left = tk.Frame(qr_body, bg=BG)
        qr_left.pack(side="left", fill="both", expand=True, padx=(4, 20))
        self._label(qr_left, "Escaneá para conectar.", size=24, bold=True, color=FG, anchor="w")
        self._label(
            qr_left,
            "Abrí ClicX en el teléfono y escaneá este código.\nMisma red — o usá USB.",
            size=13,
            color=MUTED,
            anchor="w",
            justify="left",
            pady=(10, 0),
        )
        self._label(
            qr_left,
            var=self.qr_payload_var,
            size=11,
            color=DIM,
            anchor="w",
            pady=(16, 0),
        )
        self._btn(
            qr_left, "Copiar enlace", self._copy_qr_payload, kind="secondary", radius=18
        ).pack(anchor="w", pady=(18, 0), fill="x")

        qr_right = RoundFrame(qr_body, radius=28, fill=SURFACE, outline=BORDER, pad=22)
        qr_right.pack(side="right")
        self.qr_image_label = tk.Label(qr_right.inner, bg=SURFACE, bd=0)
        self.qr_image_label.pack()

        self.port_var.trace_add("write", lambda *_: self._refresh_url())
        self._refresh_admin_banner()
        self._refresh_about_qr()
        self._switch_home_tab("deck")

    def _build_about_panel(self) -> None:
        scroll_host = tk.Frame(self.connection_panel, bg=BG)
        scroll_host.grid(row=0, column=0, sticky="nsew")
        scroll_host.rowconfigure(0, weight=1)
        scroll_host.columnconfigure(0, weight=1)

        canvas = tk.Canvas(scroll_host, bg=BG, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        about = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0, 0), window=about, anchor="nw")

        def _sync(_e: Any = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _width(event: Any) -> None:
            canvas.itemconfig(win, width=event.width)

        def _wheel(event: Any) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        about.bind("<Configure>", _sync)
        canvas.bind("<Configure>", _width)
        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
        about.columnconfigure(0, weight=1)
        about.configure(padx=28, pady=24)

        self._label(about, "Conectar", size=26, bold=True, color=FG, anchor="w", fill="x")
        self._label(
            about,
            "Usá el teléfono como trackpad y dock. Misma red, sin cuenta.",
            size=12,
            color=MUTED,
            anchor="w",
            pady=(4, 16),
        )

        open_card = RoundFrame(about, radius=16, fill=SURFACE, outline=BORDER, pad=16)
        open_card.pack(fill="x")
        card = open_card.inner
        self._label(
            card, "Abrir en otro dispositivo", size=14, bold=True, color=FG, anchor="w", fill="x"
        )

        pair = tk.Frame(card, bg=SURFACE)
        pair.pack(fill="x", pady=(14, 0))
        qr_hold = tk.Frame(pair, bg="#9CB080", width=124, height=124)
        qr_hold.pack(side="left", pady=4)
        qr_hold.pack_propagate(False)
        self.about_qr_label = tk.Label(qr_hold, bg="#9CB080", bd=0)
        self.about_qr_label.place(relx=0.5, rely=0.5, anchor="center")

        meta = tk.Frame(pair, bg=SURFACE)
        meta.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self._label(
            meta,
            "Escaneá o abrí esta dirección",
            size=11,
            bold=True,
            color=MUTED,
            anchor="w",
            fill="x",
        )
        self._label(
            meta,
            var=self.url_var,
            size=13,
            bold=True,
            color=FG,
            anchor="w",
            pady=(6, 10),
        )
        actions = tk.Frame(meta, bg=SURFACE)
        actions.pack(anchor="w")
        self._btn(
            actions, "Copiar URL", self._copy_url, kind="secondary", radius=10, height=32
        ).pack(side="left")
        self._btn(
            actions, "Abrir", self._open_connect_url, kind="secondary", radius=10, height=32
        ).pack(side="left", padx=(8, 0))

        self._label(
            card,
            "La PC y el teléfono tienen que estar en la misma red. USB sirve si no hay Wi‑Fi.",
            size=10,
            color=DIM,
            anchor="w",
            pady=(12, 0),
        )

        stats = tk.Frame(about, bg=BG)
        stats.pack(fill="x", pady=(16, 0))
        self.about_online_dot = tk.Canvas(
            stats, width=10, height=10, bg=BG, highlightthickness=0
        )
        self.about_online_dot.pack(side="left")
        self.about_online_var = tk.StringVar(value="Servidor offline")
        self.about_devices_var = tk.StringVar(value="0 dispositivos")
        self.about_pinned_var = tk.StringVar(value="0 fijados")
        self._label(
            stats,
            var=self.about_online_var,
            size=11,
            bold=True,
            color=FG,
            side="left",
            padx=(6, 16),
        )
        self._label(
            stats, var=self.about_devices_var, size=11, color=MUTED, side="left", padx=(0, 16)
        )
        self._label(stats, var=self.about_pinned_var, size=11, color=MUTED, side="left")

        host = RoundFrame(about, radius=16, fill=SURFACE, outline=BORDER, pad=14)
        host.pack(fill="x", pady=(16, 0))
        self._label(host.inner, "Host", size=13, bold=True, color=FG, anchor="w", fill="x")
        spec = tk.Frame(host.inner, bg=SURFACE)
        spec.pack(fill="x", pady=(10, 0))
        self._spec_row(spec, "IP", var=self.ip_var, action=("Copiar", self._copy_ip))
        tk.Frame(spec, bg=HAIR, height=1).pack(fill="x", pady=8)
        self._spec_row(spec, "Puerto", entry_var=self.port_var)

        row = tk.Frame(host.inner, bg=SURFACE)
        row.pack(fill="x", pady=(12, 0))
        self.start_btn = self._btn(
            row, "Start", self._start, kind="quiet", radius=12, height=34
        )
        self.start_btn.pack(side="left")
        self.stop_btn = self._btn(
            row, "Stop", self._stop, kind="danger", radius=12, height=34
        )
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.stop_btn.configure(state="disabled")
        self.usb_btn = self._btn(
            row, "USB", self._toggle_usb, kind="secondary", radius=12, height=34
        )
        self.usb_btn.pack(side="left", padx=(8, 0))
        self._btn(
            row, "Refresh", self._refresh_ip, kind="quiet", radius=12, height=34
        ).pack(side="left", padx=(8, 0))

        folders = RoundFrame(about, radius=16, fill=SURFACE, outline=BORDER, pad=14)
        folders.pack(fill="x", pady=(16, 0))
        self._label(folders.inner, "Carpetas de archivos", size=13, bold=True, color=FG, anchor="w", fill="x")
        spec2 = tk.Frame(folders.inner, bg=SURFACE)
        spec2.pack(fill="x", pady=(10, 0))
        from file_transfer import transfer_dir
        self._spec_row(
            spec2,
            "From Phone",
            var=tk.StringVar(value=str(transfer_dir("from_phone"))),
            action=("Abrir", lambda: self._open_folder(transfer_dir("from_phone"))),
        )
        tk.Frame(spec2, bg=HAIR, height=1).pack(fill="x", pady=8)
        self._spec_row(
            spec2,
            "From PC",
            var=tk.StringVar(value=str(transfer_dir("from_pc"))),
            action=("Abrir", lambda: self._open_folder(transfer_dir("from_pc"))),
        )

        self._activity_label = self._label(
            about, "Activity", size=11, color=MUTED, bold=True, anchor="w", pady=(16, 6)
        )
        log_wrap = RoundFrame(about, radius=16, fill=SURFACE, outline=BORDER, pad=6)
        log_wrap.pack(fill="x")
        self.log_box = tk.Text(
            log_wrap.inner,
            height=5,
            bg=SURFACE,
            fg=MUTED,
            insertbackground=FG,
            relief="flat",
            bd=0,
            font=("Consolas", 9),
            wrap="word",
            state="disabled",
            highlightthickness=0,
            padx=10,
            pady=8,
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_configure("dim", foreground=DIM)

    def _toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        if self._sidebar_visible:
            self._side_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
            self._home_body.columnconfigure(0, minsize=208)
        else:
            self._side_wrap.grid_remove()
            self._home_body.columnconfigure(0, minsize=0)

    def _make_sidebar_item(
        self, parent: tk.Misc, label: str, tab: str
    ) -> tuple[RoundFrame, tk.Label]:
        wrap = RoundFrame(parent, radius=6, fill=SURFACE, outline=SURFACE, pad=0)
        wrap.pack(fill="x", pady=2)
        lbl = tk.Label(
            wrap.inner,
            text=label,
            bg=SURFACE,
            fg=MUTED,
            font=self._font(13),
            anchor="w",
            padx=10,
            pady=5,
            cursor="hand2",
        )
        lbl.pack(fill="x")

        def pick(_e: Any = None) -> None:
            self._switch_home_tab(tab)

        def hover(_e: Any = None) -> None:
            if self._home_tab != tab:
                wrap.set_fill("#618764", "#618764")
                lbl.configure(bg="#618764")

        def leave(_e: Any = None) -> None:
            self._paint_sidebar()

        wrap.bind("<Button-1>", pick)
        lbl.bind("<Button-1>", pick)
        wrap.bind("<Enter>", hover)
        wrap.bind("<Leave>", leave)
        lbl.bind("<Enter>", hover)
        lbl.bind("<Leave>", leave)
        return wrap, lbl

    def _paint_sidebar(self) -> None:
        items = (
            (self._nav_deck, self._home_tab == "deck"),
            (self._nav_conn, self._home_tab == "connection"),
        )
        for (wrap, lbl), on in items:
            bg = BLUE if on else SURFACE
            fg = FG if on else MUTED
            wrap.set_fill(bg, bg)
            lbl.configure(bg=bg, fg=fg, font=self._font(13, bold=on))

    def _switch_home_tab(self, tab: str) -> None:
        self._home_tab = tab
        if tab == "connection":
            self.connection_panel.grid(row=0, column=0, sticky="nsew")
            self.deck_panel.grid_remove()
        else:
            self.connection_panel.grid_remove()
            self.deck_panel.grid(row=0, column=0, sticky="nsew")
            self._refresh_deck_grid()
        self._paint_sidebar()

    def _deck_pages(self) -> list[dict[str, Any]]:
        pages = self.deck_cfg.setdefault("pages", [])
        while len(pages) < 5:
            pages.append(
                {
                    "id": deck._new_id(),
                    "title": f"Página {len(pages) + 1}",
                    "buttons": [],
                }
            )
        return [p for p in pages if isinstance(p, dict)]

    def _deck_current_page(self) -> dict[str, Any]:
        pages = self._deck_pages()
        if not pages:
            self.deck_cfg = deck.default_config()
            pages = self._deck_pages()
        idx = max(0, min(len(pages) - 1, self._deck_page_idx))
        self._deck_page_idx = idx
        return pages[idx]

    def _slot_button(self, idx: int) -> dict[str, Any] | None:
        page = self._deck_current_page()
        buttons = page.get("buttons", [])
        if idx >= len(buttons) or not isinstance(buttons[idx], dict):
            return None
        btn = buttons[idx]
        action = btn.get("action") if isinstance(btn.get("action"), dict) else {}
        kind = str(action.get("kind", ""))
        if kind == "app":
            return btn if str(action.get("app", "")).strip() else None
        if kind == "shell":
            return btn if str(action.get("command", "")).strip() else None
        if kind == "hotkey":
            return btn if action.get("keys") else None
        if kind == "volume":
            return btn
        return None

    def _slot_is_empty(self, idx: int) -> bool:
        return self._slot_button(idx) is None

    def _deck_current_button(self, *, create: bool = True) -> dict[str, Any] | None:
        page = self._deck_current_page()
        buttons = page.setdefault("buttons", [])
        existing = self._slot_button(self._deck_slot_idx)
        if existing is not None or not create:
            return existing
        while len(buttons) <= self._deck_slot_idx:
            buttons.append({})
        btn = {
            "id": deck._new_id(),
            "label": "App",
            "icon": "apps-outline",
            "color": "#9CB080",
            "action": {"kind": "app", "app": ""},
        }
        buttons[self._deck_slot_idx] = btn
        return btn

    def _build_deck_panel(self) -> None:
        self.deck_panel.columnconfigure(0, weight=1)
        self.deck_panel.rowconfigure(0, weight=1)

        self._deck_content = tk.Frame(self.deck_panel, bg=BG)
        self._deck_content.pack(fill="both", expand=True)
        self.deck_panel.bind("<Configure>", self._layout_deck_center)

        stage = tk.Frame(self._deck_content, bg=BG)
        stage.pack(expand=True)

        wrap = RoundFrame(stage, radius=40, fill=PAGE, outline=BORDER, pad=32)
        wrap.pack()
        wrap.inner.columnconfigure(0, weight=1)

        self.deck_page_var = tk.IntVar(value=0)
        self.deck_page_title_var = tk.StringVar(value="Página")

        tile, gap = 80, 22
        self.deck_grid = tk.Frame(wrap.inner, bg=PAGE)
        self.deck_grid.grid(row=0, column=0)
        for col in range(4):
            self.deck_grid.columnconfigure(col, minsize=tile)
        for row in range(2):
            self.deck_grid.rowconfigure(row, minsize=tile)
        self._deck_slot_btns: list[DeckSlotTile] = []
        for row in range(2):
            for col in range(4):
                idx = row * 4 + col
                slot = tk.Frame(self.deck_grid, bg=PAGE, width=tile, height=tile)
                slot.grid(
                    row=row,
                    column=col,
                    padx=(0 if col == 0 else gap // 2, 0 if col == 3 else gap // 2),
                    pady=(0 if row == 0 else gap // 2, 0 if row == 1 else gap // 2),
                )
                slot.grid_propagate(False)
                slot.pack_propagate(False)
                b = DeckSlotTile(
                    slot,
                    lambda i=idx: self._on_slot_click(i),
                    height=tile,
                )
                b.pack(fill="both", expand=True)
                self._deck_slot_btns.append(b)

        self.deck_dots = tk.Frame(stage, bg=BG)
        self.deck_dots.pack(pady=(18, 0))
        self._deck_dot_canvases: list[tk.Canvas] = []

        footer = tk.Frame(self._deck_content, bg=BG)
        footer.pack(fill="x", side="bottom", pady=(0, 8), padx=12)
        self.deck_hint_var = tk.StringVar(value="")
        self._label(
            footer, var=self.deck_hint_var, size=12, color=MUTED, side="left"
        )
        self.deck_reorder_btn = self._btn(
            footer,
            "Reordenar",
            self._toggle_deck_reorder,
            kind="quiet",
            radius=20,
            height=36,
        )
        self.deck_reorder_btn.pack(side="right")

        scroll_host = tk.Frame(self._deck_content, bg=BG)
        scroll_host.rowconfigure(0, weight=1)
        scroll_host.columnconfigure(0, weight=1)

        self.deck_form_canvas = tk.Canvas(
            scroll_host, bg=PAGE, highlightthickness=0, bd=0
        )
        deck_scroll = tk.Scrollbar(
            scroll_host, orient="vertical", command=self.deck_form_canvas.yview
        )
        self.deck_form_canvas.configure(yscrollcommand=deck_scroll.set)
        self.deck_form_canvas.grid(row=0, column=0, sticky="nsew")
        deck_scroll.grid(row=0, column=1, sticky="ns")

        form_host = tk.Frame(self.deck_form_canvas, bg=DOKKE_SURFACE)
        self._deck_form_window = self.deck_form_canvas.create_window(
            (0, 0), window=form_host, anchor="nw"
        )

        def _sync_form_scroll(_event: Any = None) -> None:
            self.deck_form_canvas.configure(
                scrollregion=self.deck_form_canvas.bbox("all")
            )

        def _sync_form_width(event: Any) -> None:
            self.deck_form_canvas.itemconfig(self._deck_form_window, width=event.width)

        form_host.bind("<Configure>", _sync_form_scroll)
        self.deck_form_canvas.bind("<Configure>", _sync_form_width)

        def _deck_wheel(event: Any) -> None:
            self.deck_form_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        scroll_host.bind(
            "<Enter>",
            lambda _e: self.deck_form_canvas.bind_all("<MouseWheel>", _deck_wheel),
        )
        scroll_host.bind(
            "<Leave>", lambda _e: self.deck_form_canvas.unbind_all("<MouseWheel>")
        )

        form = RoundFrame(form_host, radius=16, fill=DOKKE_TILE, outline=DOKKE_BORDER, pad=14)
        form.pack(fill="x")

        self.deck_label_var = tk.StringVar()
        self.deck_icon_var = tk.StringVar()
        self.deck_color_var = tk.StringVar()
        self.deck_kind_var = tk.StringVar(value="app")
        self.deck_keys_var = tk.StringVar()
        self.deck_cwd_var = tk.StringVar()
        self.deck_app_var = tk.StringVar()
        self.deck_volume_var = tk.StringVar(value="mute")

        self._deck_form_row(form.inner, "Nombre", self.deck_label_var)

        self.deck_app_frame = tk.Frame(form.inner, bg=DOKKE_TILE)
        self.deck_icon_preview = tk.Label(
            self.deck_app_frame,
            bg=DOKKE_SURFACE,
            width=56,
            height=56,
            relief="flat",
            highlightthickness=1,
            highlightbackground=DOKKE_ACCENT,
        )
        self.deck_icon_preview.pack(pady=(4, 10))
        add_row = tk.Frame(self.deck_app_frame, bg=DOKKE_TILE)
        add_row.pack(fill="x")
        add_row.columnconfigure(0, weight=1)
        add_row.columnconfigure(1, weight=1)
        self._btn(
            add_row,
            "Agregar / Reemplazar",
            self._browse_deck_app,
            kind="primary",
            radius=16,
            height=40,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self._btn(
            add_row,
            "Quitar",
            self._remove_deck_slot,
            kind="danger",
            radius=16,
            height=40,
        ).grid(row=0, column=1, sticky="ew")
        self.deck_app_path_label = self._label(
            self.deck_app_frame,
            "Elegí un .exe o acceso directo",
            size=10,
            color=DIM,
            anchor="center",
        )
        self.deck_app_path_label.pack(fill="x", pady=(8, 0))
        self.deck_app_frame.pack(fill="x", pady=(6, 4))

        self.deck_advanced_toggle = self._btn(
            form.inner,
            "Opciones avanzadas ▾",
            self._toggle_deck_advanced,
            kind="quiet",
            radius=12,
            height=32,
        )
        self.deck_advanced_toggle.pack(fill="x", pady=(8, 0))

        self.deck_advanced_frame = tk.Frame(form.inner, bg=DOKKE_TILE)

        self._deck_form_row(self.deck_advanced_frame, "Ícono", self.deck_icon_var)
        self._deck_form_row(self.deck_advanced_frame, "Color", self.deck_color_var)

        kind_row = tk.Frame(self.deck_advanced_frame, bg=DOKKE_TILE)
        kind_row.pack(fill="x", pady=4)
        kind_row.columnconfigure(1, weight=1)
        self._label(kind_row, "Acción", size=11, color=MUTED).grid(
            row=0, column=0, sticky="nw", padx=(0, 10)
        )
        kind_opts = tk.Frame(kind_row, bg=DOKKE_TILE)
        kind_opts.grid(row=0, column=1, sticky="ew")
        for label, val in (
            ("App", "app"),
            ("Atajo", "hotkey"),
            ("Comando", "shell"),
            ("Volumen", "volume"),
        ):
            tk.Radiobutton(
                kind_opts,
                text=label,
                variable=self.deck_kind_var,
                value=val,
                command=self._deck_kind_changed,
                bg=DOKKE_TILE,
                fg=FG,
                selectcolor=DOKKE_SURFACE,
                activebackground=DOKKE_TILE,
                activeforeground=FG,
                font=self._font(10),
            ).pack(side="left", padx=(0, 10))

        self.deck_hotkey_frame = tk.Frame(self.deck_advanced_frame, bg=DOKKE_TILE)
        self._label(
            self.deck_hotkey_frame,
            "Teclas (coma)",
            size=11,
            color=MUTED,
            anchor="w",
        )
        tk.Entry(
            self.deck_hotkey_frame,
            textvariable=self.deck_keys_var,
            bg=DOKKE_SURFACE,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=self._font(11),
            highlightthickness=0,
        ).pack(fill="x", ipady=6, pady=(4, 0))

        self.deck_shell_frame = tk.Frame(self.deck_advanced_frame, bg=DOKKE_TILE)
        self._label(
            self.deck_shell_frame, "Comando (.bat)", size=11, color=MUTED, anchor="w"
        )
        self.deck_command_box = tk.Text(
            self.deck_shell_frame,
            height=3,
            bg=DOKKE_SURFACE,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Consolas", 10),
            highlightthickness=0,
            wrap="word",
        )
        self.deck_command_box.pack(fill="x", pady=(4, 6))
        self._deck_form_row(self.deck_shell_frame, "Carpeta", self.deck_cwd_var)

        self.deck_volume_frame = tk.Frame(self.deck_advanced_frame, bg=DOKKE_TILE)
        vol_row = tk.Frame(self.deck_volume_frame, bg=DOKKE_TILE)
        vol_row.pack(fill="x", pady=4)
        self._label(vol_row, "Volumen", size=11, color=MUTED, side="left")
        for label, val in (("Subir", "up"), ("Bajar", "down"), ("Mute", "mute")):
            tk.Radiobutton(
                vol_row,
                text=label,
                variable=self.deck_volume_var,
                value=val,
                bg=DOKKE_TILE,
                fg=FG,
                selectcolor=DOKKE_SURFACE,
                activebackground=DOKKE_TILE,
                activeforeground=FG,
                font=self._font(10),
            ).pack(side="left", padx=(8, 0))

        self._deck_advanced_open = False
        self._select_deck_slot(0)
        self._deck_kind_changed()
        self._refresh_page_dots()

    def _toggle_deck_advanced(self) -> None:
        self._deck_advanced_open = not self._deck_advanced_open
        if self._deck_advanced_open:
            self.deck_advanced_frame.pack(fill="x", pady=(8, 0))
            self.deck_advanced_toggle.configure(text="Opciones avanzadas ▴")
            self._deck_kind_changed()
        else:
            self.deck_advanced_frame.pack_forget()
            self.deck_advanced_toggle.configure(text="Opciones avanzadas ▾")

    def _layout_deck_center(self, event: Any = None) -> None:
        return

    def _set_deck_icon_preview(self, b64: str | None) -> None:
        if not b64 or not Image or not ImageTk:
            self._deck_icon_preview_photo = None
            self.deck_icon_preview.configure(image="", text="")
            return
        try:
            raw = base64.b64decode(b64)
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            img = img.resize((48, 48), Image.Resampling.LANCZOS)
            self._deck_icon_preview_photo = ImageTk.PhotoImage(img)
            self.deck_icon_preview.configure(image=self._deck_icon_preview_photo, text="")
        except Exception:  # noqa: BLE001
            self.deck_icon_preview.configure(image="", text="?")

    def _update_deck_app_path_label(self, path: str) -> None:
        if not path:
            self.deck_app_path_label.configure(text="Ninguna app seleccionada")
            return
        name = Path(path).name
        self.deck_app_path_label.configure(text=name if len(name) <= 42 else f"…{name[-40:]}")

    def _deck_form_row(
        self, parent: tk.Misc, label: str, var: tk.StringVar
    ) -> None:
        row = tk.Frame(parent, bg=parent.cget("bg"))
        row.pack(fill="x", pady=4)
        row.columnconfigure(1, weight=1)
        self._label(row, label, size=11, color=MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        tk.Entry(
            row,
            textvariable=var,
            bg=SURFACE,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=self._font(11),
            highlightthickness=0,
        ).grid(row=0, column=1, sticky="ew", ipady=5)

    def _deck_prev_page(self) -> None:
        pages = self._deck_pages()
        if not pages:
            return
        self._goto_deck_page((self._deck_page_idx - 1) % len(pages))

    def _deck_next_page(self) -> None:
        pages = self._deck_pages()
        if not pages:
            return
        self._goto_deck_page((self._deck_page_idx + 1) % len(pages))

    def _goto_deck_page(self, idx: int) -> None:
        pages = self._deck_pages()
        if not pages:
            return
        self._apply_deck_form()
        self._deck_page_idx = max(0, min(len(pages) - 1, idx))
        self._reorder_from = None
        self._refresh_deck_grid()
        self._select_deck_slot(0)

    def _refresh_page_dots(self) -> None:
        if not hasattr(self, "deck_dots"):
            return
        for child in self.deck_dots.winfo_children():
            child.destroy()
        self._deck_dot_canvases = []
        pages = self._deck_pages()
        for i in range(len(pages)):
            on = i == self._deck_page_idx
            c = tk.Canvas(
                self.deck_dots, width=11, height=11, bg=BG, highlightthickness=0, cursor="hand2"
            )
            fill = "#9CB080" if on else "#618764"
            c.create_oval(2, 2, 9, 9, fill=fill, outline="")
            c.bind("<Button-1>", lambda _e, n=i: self._goto_deck_page(n))
            c.pack(side="left", padx=3)
            self._deck_dot_canvases.append(c)

    def _toggle_deck_reorder(self) -> None:
        self._deck_reordering = not self._deck_reordering
        self._reorder_from = None
        if self._deck_reordering:
            self.deck_reorder_btn.configure(text="Listo", kind="primary")
            self.deck_hint_var.set("Tocá dos slots para intercambiarlos.")
        else:
            self.deck_reorder_btn.configure(text="Reordenar", kind="quiet")
            self.deck_hint_var.set("")
        self._refresh_deck_grid()

    def _swap_deck_slots(self, a: int, b: int) -> None:
        if a == b:
            return
        page = self._deck_current_page()
        buttons = page.setdefault("buttons", [])
        while len(buttons) <= max(a, b):
            buttons.append({})
        buttons[a], buttons[b] = buttons[b], buttons[a]
        deck.save_config(self.deck_cfg)

    def _on_slot_click(self, idx: int) -> None:
        self._deck_slot_idx = max(0, min(DECK_PAGE_SIZE - 1, idx))
        if self._deck_reordering:
            if self._reorder_from is None:
                self._reorder_from = idx
                self._refresh_deck_grid()
                return
            self._swap_deck_slots(self._reorder_from, idx)
            self._reorder_from = None
            self._refresh_deck_grid()
            return
        if self._slot_is_empty(idx):
            self._refresh_deck_grid()
            self._open_app_picker()
            return
        self._fill_deck_form()
        self._refresh_deck_grid()

    def _select_deck_slot(self, idx: int) -> None:
        self._deck_slot_idx = max(0, min(DECK_PAGE_SIZE - 1, idx))
        self._fill_deck_form()
        self._refresh_deck_grid()

    def _fill_deck_form(self) -> None:
        page = self._deck_current_page()
        self.deck_page_title_var.set(str(page.get("title", "Página")))
        btn = self._deck_current_button(create=False)
        if btn is None:
            self.deck_label_var.set("")
            self.deck_icon_var.set("apps-outline")
            self.deck_color_var.set("#9CB080")
            self.deck_kind_var.set("app")
            self.deck_keys_var.set("")
            self.deck_cwd_var.set("")
            self.deck_app_var.set("")
            self.deck_command_box.delete("1.0", "end")
            self.deck_volume_var.set("mute")
            self._set_deck_icon_preview(None)
            self._update_deck_app_path_label("")
            return
        self.deck_label_var.set(str(btn.get("label", "")))
        self.deck_icon_var.set(str(btn.get("icon", "ellipse-outline")))
        self.deck_color_var.set(str(btn.get("color", "#9CB080")))
        action = btn.get("action") if isinstance(btn.get("action"), dict) else {}
        kind = str(action.get("kind", "hotkey"))
        self.deck_kind_var.set(kind)
        keys = action.get("keys")
        if isinstance(keys, list):
            self.deck_keys_var.set(",".join(str(k) for k in keys))
        else:
            self.deck_keys_var.set("")
        self.deck_cwd_var.set(str(action.get("cwd", "")))
        app_path = str(action.get("app", ""))
        self.deck_app_var.set(app_path)
        self.deck_command_box.delete("1.0", "end")
        self.deck_command_box.insert("1.0", str(action.get("command", "")))
        self.deck_volume_var.set(str(action.get("action", "mute")))
        if kind == "app":
            attach_button_icon(btn)
            self._set_deck_icon_preview(str(btn.get("iconB64", "")) or None)
            self._update_deck_app_path_label(app_path)
        else:
            self._set_deck_icon_preview(None)
            self._update_deck_app_path_label("")
        self._deck_kind_changed()

    def _deck_kind_changed(self) -> None:
        kind = self.deck_kind_var.get()
        self.deck_hotkey_frame.pack_forget()
        self.deck_shell_frame.pack_forget()
        self.deck_volume_frame.pack_forget()
        if not self._deck_advanced_open:
            return
        if kind == "hotkey":
            self.deck_hotkey_frame.pack(fill="x", pady=4)
        elif kind == "shell":
            self.deck_shell_frame.pack(fill="x", pady=4)
        elif kind == "volume":
            self.deck_volume_frame.pack(fill="x", pady=4)

    def _apply_deck_form(self) -> None:
        page = self._deck_current_page()
        page["title"] = self.deck_page_title_var.get().strip() or "Página"
        btn = self._deck_current_button(create=False)
        if btn is None:
            return
        btn["label"] = self.deck_label_var.get().strip() or "Btn"
        btn["icon"] = self.deck_icon_var.get().strip() or "ellipse-outline"
        btn["color"] = self.deck_color_var.get().strip() or "#9CB080"
        kind = self.deck_kind_var.get()
        if kind == "app":
            app = self.deck_app_var.get().strip()
            btn["action"] = {"kind": "app", "app": app}
            if app and not self.deck_label_var.get().strip():
                btn["label"] = Path(app).stem.replace("_", " ").title()
            attach_button_icon(btn)
        elif kind == "hotkey":
            raw = self.deck_keys_var.get().strip()
            keys = [k.strip() for k in raw.replace("+", ",").split(",") if k.strip()]
            btn["action"] = {"kind": "hotkey", "keys": keys or ["enter"]}
        elif kind == "shell":
            cmd = self.deck_command_box.get("1.0", "end").strip()
            action: dict[str, Any] = {
                "kind": "shell",
                "command": cmd,
                "cwd": self.deck_cwd_var.get().strip(),
            }
            app = self.deck_app_var.get().strip()
            if app:
                action["app"] = app
            btn["action"] = action
        else:
            btn["action"] = {
                "kind": "volume",
                "action": self.deck_volume_var.get() or "mute",
            }

    def _refresh_deck_grid(self) -> None:
        page = self._deck_current_page()
        buttons = page.get("buttons", [])
        for i, slot_btn in enumerate(self._deck_slot_btns):
            label = f"{i + 1}"
            icon_b64: str | None = None
            empty = self._slot_is_empty(i)
            if i < len(buttons) and isinstance(buttons[i], dict) and not empty:
                btn = buttons[i]
                label = str(btn.get("label", label))[:8]
                attach_button_icon(btn)
                raw = btn.get("iconB64")
                if isinstance(raw, str) and raw:
                    icon_b64 = raw
                    label = ""
            selected = (
                i == self._reorder_from
                if self._deck_reordering
                else i == self._deck_slot_idx and not empty
            )
            slot_btn.configure(
                text=label,
                selected=selected,
                icon_b64=icon_b64,
                empty=empty,
            )
        self._refresh_page_dots()
        self._refresh_about_stats()

    def _pinned_keys(self) -> set[str]:
        keys: set[str] = set()
        for page in self._deck_pages():
            for btn in page.get("buttons", []):
                if not isinstance(btn, dict):
                    continue
                action = btn.get("action") if isinstance(btn.get("action"), dict) else {}
                app = str(action.get("app", "")).strip()
                if app:
                    keys.add(app.lower())
                    keys.add(Path(app).stem.lower())
                cmd = str(action.get("command", "")).strip()
                if "http" in cmd:
                    keys.add(cmd.lower())
                label = str(btn.get("label", "")).strip()
                if label:
                    keys.add(label.lower())
        return keys

    def _write_slot(self, idx: int, value: str, name: str, kind: str) -> None:
        page = self._deck_current_page()
        buttons = page.setdefault("buttons", [])
        while len(buttons) <= idx:
            buttons.append({})
        if kind == "url":
            buttons[idx] = {
                "id": deck._new_id(),
                "label": name,
                "icon": "globe-outline",
                "color": "#9CB080",
                "action": {"kind": "shell", "command": f'start "" "{value}"'},
            }
        else:
            btn = {
                "id": deck._new_id(),
                "label": name,
                "icon": "apps-outline",
                "color": "#9CB080",
                "action": {"kind": "app", "app": value},
            }
            attach_button_icon(btn)
            buttons[idx] = btn
        self._deck_slot_idx = idx

    def _pin_from_picker(self, value: str, name: str, kind: str = "app") -> None:
        self._write_slot(self._deck_slot_idx, value, name, kind)
        deck.save_config(self.deck_cfg)
        self._fill_deck_form()
        self._refresh_deck_grid()
        self._append_log(f"Fijada en el dock: {name}")

    def _open_app_picker(self) -> None:
        AppPicker(
            self,
            self._pin_from_picker,
            title="Agregar al dock",
            pinned=self._pinned_keys(),
        )

    def _browse_deck_app(self) -> None:
        self._open_app_picker()

    def _remove_deck_slot(self) -> None:
        page = self._deck_current_page()
        buttons = page.get("buttons", [])
        idx = self._deck_slot_idx
        if idx < len(buttons):
            buttons[idx] = {}
        deck.save_config(self.deck_cfg)
        self._fill_deck_form()
        self._refresh_deck_grid()
        self._append_log("Slot vacío")

    def _save_deck_slot(self) -> None:
        self._apply_deck_form()
        deck.save_config(self.deck_cfg)
        self._refresh_deck_grid()
        self._append_log("Deck guardado — sincronizado con el teléfono.")

    def _test_deck_slot(self) -> None:
        self._apply_deck_form()
        btn = self._deck_current_button(create=False)
        if not btn:
            return
        bid = str(btn.get("id", ""))
        if bid:
            deck.execute_button(bid)
            self._append_log(f"Deck test: {btn.get('label', bid)}")

    def _spec_row(
        self,
        parent: tk.Misc,
        label: str,
        *,
        var: tk.StringVar | None = None,
        action: tuple[str, Callable[[], None]] | None = None,
        entry_var: tk.StringVar | None = None,
    ) -> None:
        row = tk.Frame(parent, bg=SURFACE)
        row.pack(fill="x", pady=2)
        self._label(row, label, size=12, color=MUTED, side="left")
        right = tk.Frame(row, bg=SURFACE)
        right.pack(side="right")
        if entry_var is not None:
            shell = RoundFrame(right, radius=12, fill=SURFACE_2, outline=BORDER, pad=0)
            shell.pack(side="left")
            ent = tk.Entry(
                shell.inner,
                textvariable=entry_var,
                width=7,
                bg=SURFACE_2,
                fg=FG,
                insertbackground=FG,
                relief="flat",
                font=self._font(13),
                justify="right",
                highlightthickness=0,
                bd=0,
            )
            ent.pack(ipady=6, ipadx=10)
        elif var is not None:
            self._label(right, var=var, size=13, color=FG, bold=True, side="left")
        if action:
            name, cmd = action
            self._btn(right, name, cmd, kind="link", radius=12, height=28).pack(
                side="left", padx=(8, 0)
            )

    def _draw_dot(self, color: str) -> None:
        self.status_dot.delete("all")
        self.status_dot.create_oval(1, 1, 9, 9, fill=color, outline="")

    def _show_home_view(self) -> None:
        self._view = "home"
        self.qr_view.pack_forget()
        self.home.pack(fill="both", expand=True)

    def _show_qr_view(self) -> None:
        self._refresh_ip()
        payload = self._connect_payload()
        try:
            import qrcode
            from PIL import Image, ImageDraw, ImageTk
        except ImportError:
            messagebox.showerror(
                "Missing qrcode",
                'Install: pip install "qrcode[pil]" pillow',
            )
            return

        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#E8EDE4", back_color="#273338").convert("RGBA")
        w, h = img.size
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=20, fill=255)
        out = Image.new("RGBA", (w, h), (39, 51, 56, 255))
        out.paste(img, (0, 0))
        out.putalpha(mask)
        photo = ImageTk.PhotoImage(out)
        self._qr_photo = photo
        self.qr_image_label.configure(image=photo)
        self.qr_payload_var.set(payload)

        self._view = "qr"
        self.home.pack_forget()
        self.qr_view.pack(fill="both", expand=True)
        self._append_log(f"QR: {payload}")

    def _copy_qr_payload(self) -> None:
        text = self.qr_payload_var.get()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self._append_log("Link copied")

    def _refresh_admin_banner(self) -> None:
        if core.is_admin():
            self.admin_frame.pack_forget()
            return
        self.admin_label.configure(
            text="Sin admin: ventanas elevadas no responden."
        )
        self.admin_frame.pack(fill="x", anchor="sw", pady=(12, 0))

    def _relaunch_admin(self) -> None:
        if core.relaunch_as_admin():
            self.controller.stop()
            self.destroy()
            sys.exit(0)
        messagebox.showwarning(
            "UAC cancelled",
            "Windows did not elevate. Accept the UAC prompt or "
            "right‑click → Run as administrator.",
        )

    def _refresh_url(self) -> None:
        self.url_var.set(
            f"ws://{self.ip_var.get()}:{self.port_var.get().strip() or core.PORT}"
        )
        self._refresh_about_qr()

    def _connect_payload(self) -> str:
        host = self.ip_var.get().strip()
        port = self.port_var.get().strip() or str(core.PORT)
        return f"clicx://connect?host={host}&port={port}"

    def _toggle_usb(self) -> None:
        if self._usb_active:
            self._usb_off()
        else:
            self._usb_on()

    def _usb_on(self) -> None:
        try:
            port = int(self.port_var.get().strip() or core.PORT)
        except ValueError:
            messagebox.showerror("Invalid port", "Use a port between 1 and 65535.")
            return
        code, msg = run_adb(["devices"])
        if code != 0:
            self._append_log(f"USB: {msg}")
            messagebox.showerror("ADB", msg)
            return
        if "device" not in msg.replace("List of devices", ""):
            self._append_log("USB: no adb device")
            messagebox.showwarning(
                "No phone",
                "No adb device found. Enable USB debugging and reconnect the cable.",
            )
            return
        code, msg = run_adb(["reverse", f"tcp:{port}", f"tcp:{port}"])
        if code != 0:
            self._append_log(f"USB reverse failed: {msg}")
            messagebox.showerror("adb reverse", msg)
            return
        self._usb_active = True
        self.usb_btn.configure(text="USB On")
        self._append_log(f"USB on: adb reverse tcp:{port}")

    def _usb_off(self) -> None:
        try:
            port = int(self.port_var.get().strip() or core.PORT)
        except ValueError:
            port = core.PORT
        code, msg = run_adb(["reverse", "--remove", f"tcp:{port}"])
        self._usb_active = False
        self.usb_btn.configure(text="USB")
        if code != 0:
            self._append_log(f"USB remove: {msg}")
        else:
            self._append_log(f"USB off (tcp:{port})")

    def _refresh_ip(self) -> None:
        self.ip_var.set(core.local_ip())
        self._refresh_url()
        self._refresh_about_qr()
        self._refresh_about_stats()
        self._append_log(f"IP: {self.ip_var.get()}")

    def _copy_ip(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.ip_var.get())
        self._append_log("IP copied")

    def _copy_url(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.url_var.get())
        self._append_log("URL copied")

    def _open_connect_url(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            return
        http = url.replace("ws://", "http://", 1).replace("wss://", "https://", 1)
        try:
            webbrowser.open(http)
        except Exception:  # noqa: BLE001
            self._append_log("No se pudo abrir el navegador")

    def _open_folder(self, folder) -> None:
        try:
            from pathlib import Path
            Path(folder).mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
        except Exception:  # noqa: BLE001
            self._append_log("No se pudo abrir la carpeta")

    def _refresh_about_qr(self) -> None:
        if not hasattr(self, "about_qr_label"):
            return
        payload = self._connect_payload()
        try:
            import qrcode
            from PIL import Image as PilImage
            from PIL import ImageTk as PilImageTk
        except ImportError:
            self.about_qr_label.configure(text="QR", fg=DIM)
            return
        qr = qrcode.QRCode(version=1, box_size=4, border=1)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#273338", back_color="#9CB080").convert("RGBA")
        img = img.resize((112, 112), PilImage.Resampling.NEAREST)
        self._about_qr_photo = PilImageTk.PhotoImage(img)
        self.about_qr_label.configure(image=self._about_qr_photo, text="")

    def _refresh_about_stats(self) -> None:
        if not hasattr(self, "about_online_var"):
            return
        online = self.controller.is_running()
        self.about_online_var.set("Servidor online" if online else "Servidor offline")
        self.about_online_dot.delete("all")
        self.about_online_dot.create_oval(
            1, 1, 9, 9, fill=OK if online else ERR, outline=""
        )
        n = 0
        try:
            n = int(self.clients_var.get().split()[0])
        except (ValueError, IndexError):
            n = 0
        self.about_devices_var.set(f"{n} dispositivo{'s' if n != 1 else ''}")
        pinned = 0
        for page in self._deck_pages():
            for btn in page.get("buttons", []):
                if not isinstance(btn, dict):
                    continue
                action = btn.get("action") if isinstance(btn.get("action"), dict) else {}
                kind = str(action.get("kind", ""))
                if kind == "app" and str(action.get("app", "")).strip():
                    pinned += 1
                elif kind == "shell" and str(action.get("command", "")).strip():
                    pinned += 1
                elif kind == "hotkey" and action.get("keys"):
                    pinned += 1
                elif kind == "volume":
                    pinned += 1
        self.about_pinned_var.set(f"{pinned} fijado{'s' if pinned != 1 else ''}")

    def _set_running_ui(self, running: bool) -> None:
        self._running_ui = running
        if running:
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
        else:
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
        self._refresh_about_stats()

    def _start(self) -> None:
        if self.controller.is_running():
            return
        try:
            port = int(self.port_var.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid port", "Use a port between 1 and 65535.")
            return
        self._refresh_ip()
        self.controller.start(port)
        self._set_running_ui(True)

    def _stop(self) -> None:
        self.controller.stop()
        self._set_running_ui(False)

    def _append_log(self, msg: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{stamp}  ", "dim")
        self.log_box.insert("end", f"{msg}\n")
        self.log_box.see("end")
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 80:
            self.log_box.delete("1.0", "20.0")
        self.log_box.configure(state="disabled")

    def _poll_ui(self) -> None:
        try:
            while True:
                kind, payload = self.ui_q.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    text, sk = payload
                    self.status_var.set(text)
                    color = {"ok": OK, "err": ERR, "warn": WARN}.get(sk, DIM)
                    self._draw_dot(color)
                    self._refresh_about_stats()
                elif kind == "clients":
                    n = int(payload)
                    self.clients_var.set(f"{n} client{'s' if n != 1 else ''}")
                    self._refresh_about_stats()
        except queue.Empty:
            pass
        running = self.controller.is_running()
        if running != self._running_ui:
            self._set_running_ui(running)
        self.after(80, self._poll_ui)

    def _on_close(self) -> None:
        try:
            self.controller.stop()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


def run_gui() -> None:
    app = ClicxApp()
    app.mainloop()


if __name__ == "__main__":
    run_gui()
