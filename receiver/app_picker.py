"""Dokke-style modal to pin apps or website links on the deck."""

from __future__ import annotations

import base64
import io
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Literal

from icon_extract import extract_icon_b64
from windows_apps import list_installed_apps, search_apps

if __import__("sys").platform == "win32":
    from PIL import Image, ImageTk
else:
    Image = None  # type: ignore[misc, assignment]
    ImageTk = None  # type: ignore[misc, assignment]

PickKind = Literal["app", "url"]

# Forest moss — #9CB080 #618764 #2B5748 #273338
CANVAS = "#273338"
PAGE = "#2B5748"
ROW = "#2B5748"
ROW_HOVER = "#618764"
FG = "#E8EDE4"
MUTED = "#9CB080"
DIVIDER = "#618764"
BLUE = "#618764"
BLUE_HOVER = "#9CB080"
INPUT_BG = "#273338"
INPUT_BORDER = "#9CB080"

WEBSITE_SUGGESTIONS: list[tuple[str, str]] = [
    ("GitHub", "https://github.com"),
    ("YouTube", "https://youtube.com"),
    ("WhatsApp", "https://web.whatsapp.com"),
    ("Pinterest", "https://pinterest.com"),
    ("Threads", "https://threads.net"),
    ("TikTok", "https://tiktok.com"),
    ("LinkedIn", "https://linkedin.com"),
    ("ChatGPT", "https://chatgpt.com"),
]


def _normalize_url(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    if "://" not in text:
        return f"https://{text}"
    return text


class AppPicker(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        on_select: Callable[[str, str, PickKind], None],
        *,
        title: str = "Agregar al dock",
        pinned: set[str] | None = None,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.configure(bg=CANVAS)
        self.geometry("480x620")
        self.minsize(420, 520)
        self._on_select = on_select
        self._pinned = {p.lower() for p in (pinned or set())}
        self._photos: list[object] = []
        self._tab = tk.StringVar(value="apps")
        self._search_var = tk.StringVar()
        self._url_var = tk.StringVar()

        self.transient(master.winfo_toplevel())
        self.grab_set()

        self._body = tk.Frame(self, bg=CANVAS)
        self._body.pack(fill="both", expand=True)

        self._build_chrome()
        tk.Frame(self._body, bg=DIVIDER, height=1).pack(fill="x")
        self._header = tk.Frame(self._body, bg=CANVAS)
        self._header.pack(fill="x", padx=16, pady=(16, 12))
        self._content = tk.Frame(self._body, bg=CANVAS)
        self._content.pack(fill="both", expand=True)

        self._tab.trace_add("write", lambda *_: self._switch_tab())
        self._search_var.trace_add("write", lambda *_: self._refresh_apps())
        self._switch_tab()

        self.bind("<Escape>", lambda _e: self.destroy())

    def _build_chrome(self) -> None:
        bar = tk.Frame(self._body, bg=CANVAS, padx=16, pady=16)
        bar.pack(fill="x")

        seg = tk.Frame(bar, bg="#2B5748", padx=3, pady=3)
        seg.pack(side="left", fill="x", expand=True)
        self._tab_apps_btn = tk.Label(
            seg,
            text="Apps",
            font=("Segoe UI Semibold", 10),
            padx=16,
            pady=6,
            cursor="hand2",
        )
        self._tab_apps_btn.pack(side="left", fill="x", expand=True)
        self._tab_web_btn = tk.Label(
            seg,
            text="Sitios web",
            font=("Segoe UI", 10),
            padx=16,
            pady=6,
            cursor="hand2",
        )
        self._tab_web_btn.pack(side="left", fill="x", expand=True)
        self._tab_apps_btn.bind("<Button-1>", lambda _e: self._tab.set("apps"))
        self._tab_web_btn.bind("<Button-1>", lambda _e: self._tab.set("websites"))

        close = tk.Label(
            bar,
            text="✕",
            fg=MUTED,
            bg="#2B5748",
            font=("Segoe UI", 11),
            width=2,
            cursor="hand2",
        )
        close.pack(side="right", padx=(10, 0), ipady=4)
        close.bind("<Button-1>", lambda _e: self.destroy())
        close.bind("<Enter>", lambda _e: close.configure(bg=ROW_HOVER))
        close.bind("<Leave>", lambda _e: close.configure(bg=ROW))

    def _paint_tabs(self) -> None:
        apps_on = self._tab.get() == "apps"
        on = {"bg": BLUE, "fg": FG, "font": ("Segoe UI Semibold", 10)}
        off = {"bg": ROW, "fg": MUTED, "font": ("Segoe UI", 10)}
        self._tab_apps_btn.configure(**(on if apps_on else off))
        self._tab_web_btn.configure(**(off if apps_on else on))

    def _build_header(self, icon: str, title: str) -> None:
        for w in self._header.winfo_children():
            w.destroy()
        row = tk.Frame(self._header, bg=CANVAS)
        row.pack(fill="x")
        badge = tk.Label(
            row,
            text=icon,
            fg=FG,
            bg=ROW,
            font=("Segoe UI", 16),
            width=3,
            height=1,
        )
        badge.pack(side="left")
        tk.Label(
            row,
            text=title,
            fg=FG,
            bg=CANVAS,
            font=("Segoe UI Semibold", 16),
            anchor="w",
        ).pack(side="left", padx=(12, 0))

    def _switch_tab(self) -> None:
        self._paint_tabs()
        for w in self._content.winfo_children():
            w.destroy()
        if self._tab.get() == "apps":
            self._build_header("▦", "Agregar apps al dock")
            self._build_apps_tab()
        else:
            self._build_header("🌐", "Agregar links al dock")
            self._build_websites_tab()

    def _build_apps_tab(self) -> None:
        tools = tk.Frame(self._content, bg=CANVAS)
        tools.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(
            tools,
            text="▼  Biblioteca",
            fg=FG,
            bg=CANVAS,
            font=("Segoe UI Semibold", 11),
        ).pack(side="left")

        search_wrap = tk.Frame(tools, bg=INPUT_BG, highlightthickness=1, highlightbackground=INPUT_BORDER)
        search_wrap.pack(side="right")
        tk.Label(search_wrap, text="🔍", bg=INPUT_BG, fg=MUTED).pack(side="left", padx=(8, 4))
        ent = tk.Entry(
            search_wrap,
            textvariable=self._search_var,
            bg=INPUT_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Segoe UI", 10),
            width=18,
            highlightthickness=0,
        )
        ent.pack(side="left", ipady=5, padx=(0, 8))
        ent.focus_set()

        list_wrap = tk.Frame(self._content, bg=CANVAS)
        list_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self._apps_canvas = tk.Canvas(list_wrap, bg=CANVAS, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=self._apps_canvas.yview)
        self._apps_inner = tk.Frame(self._apps_canvas, bg=CANVAS)
        self._apps_inner.bind(
            "<Configure>",
            lambda e: self._apps_canvas.configure(scrollregion=self._apps_canvas.bbox("all")),
        )
        self._apps_win = self._apps_canvas.create_window((0, 0), window=self._apps_inner, anchor="nw")
        self._apps_canvas.bind(
            "<Configure>",
            lambda e: self._apps_canvas.itemconfig(self._apps_win, width=e.width),
        )
        self._apps_canvas.configure(yscrollcommand=scroll.set)
        self._apps_canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._bind_wheel(self._apps_canvas)
        self._show_loading()
        threading.Thread(target=self._load_apps_worker, daemon=True).start()

    def _show_loading(self) -> None:
        for w in self._apps_inner.winfo_children():
            w.destroy()
        tk.Label(
            self._apps_inner,
            text="Cargando apps…",
            fg=MUTED,
            bg=CANVAS,
            font=("Segoe UI", 11),
            pady=32,
        ).pack()

    def _load_apps_worker(self) -> None:
        try:
            rows = list_installed_apps(refresh=True)
        except Exception:  # noqa: BLE001
            rows = []
        self.after(0, lambda: self._render_apps(rows))

    def _render_apps(self, rows: list[dict[str, str]]) -> None:
        if not self.winfo_exists() or not hasattr(self, "_apps_inner"):
            return
        if not self._apps_inner.winfo_exists():
            return
        for w in self._apps_inner.winfo_children():
            w.destroy()
        self._photos.clear()
        q = self._search_var.get().strip().lower()
        if q:
            rows = [a for a in rows if q in a["name"].lower()]
        rows = sorted(rows, key=lambda a: (self._is_pinned(a), a["name"].lower()))
        if not rows:
            tk.Label(
                self._apps_inner,
                text="Sin resultados",
                fg=MUTED,
                bg=CANVAS,
                font=("Segoe UI", 11),
                pady=24,
            ).pack()
            return
        for app in rows[:120]:
            self._add_app_row(app)

    def _refresh_apps(self) -> None:
        if not hasattr(self, "_apps_inner") or not self._apps_inner.winfo_exists():
            return
        if self._tab.get() != "apps":
            return
        rows = search_apps(self._search_var.get())
        self._render_apps(rows)

    def _add_app_row(self, app: dict[str, str]) -> None:
        row = tk.Frame(self._apps_inner, bg=ROW, padx=12, pady=10)
        row.pack(fill="x", pady=(0, 8))

        icon_frame = tk.Frame(row, bg="#ffffff", width=34, height=34)
        icon_frame.pack(side="left")
        icon_frame.pack_propagate(False)
        icon_lbl = tk.Label(
            icon_frame,
            text=app["name"][:1].upper(),
            fg="#333",
            bg="#ffffff",
            font=("Segoe UI Semibold", 12),
        )
        icon_lbl.place(relx=0.5, rely=0.5, anchor="center")
        self.after(0, lambda: self._load_row_icon(app, icon_lbl))

        text = tk.Frame(row, bg=ROW)
        text.pack(side="left", fill="x", expand=True, padx=(12, 8))
        tk.Label(
            text,
            text=app["name"],
            fg=FG,
            bg=ROW,
            font=("Segoe UI", 11),
            anchor="w",
        ).pack(anchor="w")
        path = app["path"]
        if len(path) > 48:
            path = "…" + path[-46:]
        tk.Label(
            text,
            text=path,
            fg=MUTED,
            bg=ROW,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(anchor="w")

        if self._is_pinned(app):
            tk.Label(
                row,
                text="✓",
                fg="#30D158",
                bg=ROW,
                font=("Segoe UI Semibold", 14),
            ).pack(side="right")
        else:
            add = tk.Label(
                row,
                text="Agregar",
                fg=FG,
                bg=BLUE,
                font=("Segoe UI Semibold", 9),
                padx=12,
                pady=6,
                cursor="hand2",
            )
            add.pack(side="right")

            def pick(_e=None) -> None:
                self._on_select(app["path"], app["name"], "app")
                self.destroy()

            add.bind("<Button-1>", pick)
            add.bind("<Enter>", lambda _e: add.configure(bg=BLUE_HOVER))
            add.bind("<Leave>", lambda _e: add.configure(bg=BLUE))
        row.bind("<Enter>", lambda _e, r=row: self._row_hover(r, True))
        row.bind("<Leave>", lambda _e, r=row: self._row_hover(r, False))

    def _is_pinned(self, app: dict[str, str]) -> bool:
        name = app.get("name", "").lower()
        path = app.get("path", "").lower()
        return name in self._pinned or path in self._pinned

    def _load_row_icon(self, app: dict[str, str], icon_lbl: tk.Label) -> None:
        if not icon_lbl.winfo_exists():
            return

        def work() -> None:
            b64 = extract_icon_b64(app["path"], size=256)

            def apply() -> None:
                if not icon_lbl.winfo_exists() or not b64 or not Image or not ImageTk:
                    return
                try:
                    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")
                    img = img.resize((32, 32), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self._photos.append(photo)
                    icon_lbl.configure(image=photo, text="")
                except Exception:  # noqa: BLE001
                    pass

            self.after(0, apply)

        threading.Thread(target=work, daemon=True).start()

    def _build_websites_tab(self) -> None:
        pad = tk.Frame(self._content, bg=CANVAS, padx=16)
        pad.pack(fill="both", expand=True)

        url_row = tk.Frame(
            pad,
            bg=INPUT_BG,
            highlightthickness=1,
            highlightbackground=INPUT_BORDER,
            padx=12,
            pady=10,
        )
        url_row.pack(fill="x", pady=(0, 12))
        tk.Label(url_row, text="🌐", bg=INPUT_BG, fg=MUTED).pack(side="left", padx=(0, 8))
        url_ent = tk.Entry(
            url_row,
            textvariable=self._url_var,
            bg=INPUT_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Segoe UI", 11),
            highlightthickness=0,
        )
        url_ent.pack(side="left", fill="x", expand=True, ipady=4)
        url_ent.insert(0, "https://")
        add_url = tk.Label(
            url_row,
            text="Agregar",
            fg=FG,
            bg=BLUE,
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=5,
            cursor="hand2",
        )
        add_url.pack(side="right", padx=(8, 0))

        def add_custom(_e=None) -> None:
            url = _normalize_url(self._url_var.get())
            if not url or url == "https://":
                return
            name = self._title_from_url(url)
            self._on_select(url, name, "url")
            self.destroy()

        add_url.bind("<Button-1>", add_custom)
        url_ent.bind("<Return>", add_custom)

        tk.Label(
            pad,
            text="Sugerencias",
            fg=FG,
            bg=CANVAS,
            font=("Segoe UI Semibold", 12),
            anchor="w",
        ).pack(anchor="w", pady=(4, 8))

        list_wrap = tk.Frame(pad, bg=CANVAS)
        list_wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(list_wrap, bg=CANVAS, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=CANVAS)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._bind_wheel(canvas)

        for name, url in WEBSITE_SUGGESTIONS:
            self._add_website_row(inner, name, url)

    def _add_website_row(self, parent: tk.Misc, name: str, url: str) -> None:
        row = tk.Frame(parent, bg=ROW, padx=12, pady=10)
        row.pack(fill="x", pady=(0, 8))

        plate = tk.Label(
            row,
            text=name[:1].upper(),
            fg="#333",
            bg="#ffffff",
            font=("Segoe UI Semibold", 12),
            width=2,
            height=1,
        )
        plate.pack(side="left")

        text = tk.Frame(row, bg=ROW)
        text.pack(side="left", fill="x", expand=True, padx=(12, 8))
        tk.Label(text, text=name, fg=FG, bg=ROW, font=("Segoe UI", 11), anchor="w").pack(
            anchor="w"
        )
        tk.Label(text, text=url, fg=MUTED, bg=ROW, font=("Segoe UI", 9), anchor="w").pack(
            anchor="w"
        )

        already = name.lower() in self._pinned or url.lower() in self._pinned
        if already:
            tk.Label(
                row,
                text="✓",
                fg="#30D158",
                bg=ROW,
                font=("Segoe UI Semibold", 14),
            ).pack(side="right")
        else:
            add = tk.Label(
                row,
                text="Agregar",
                fg=FG,
                bg=BLUE,
                font=("Segoe UI Semibold", 9),
                padx=12,
                pady=6,
                cursor="hand2",
            )
            add.pack(side="right")

            def pick(_e=None) -> None:
                self._on_select(url, name, "url")
                self.destroy()

            add.bind("<Button-1>", pick)
            add.bind("<Enter>", lambda _e: add.configure(bg=BLUE_HOVER))
            add.bind("<Leave>", lambda _e: add.configure(bg=BLUE))
        row.bind("<Enter>", lambda _e, r=row: self._row_hover(r, True))
        row.bind("<Leave>", lambda _e, r=row: self._row_hover(r, False))

    @staticmethod
    def _title_from_url(url: str) -> str:
        try:
            from urllib.parse import urlparse

            host = urlparse(url).hostname or ""
            host = host.removeprefix("www.")
            label = host.split(".")[0] if host else "Sitio"
            return label.replace("-", " ").replace("_", " ").title()
        except Exception:  # noqa: BLE001
            return "Sitio"

    @staticmethod
    def _row_hover(row: tk.Frame, on: bool) -> None:
        bg = ROW_HOVER if on else ROW
        row.configure(bg=bg)
        for child in row.winfo_children():
            if isinstance(child, tk.Frame):
                child.configure(bg=bg)
                for sub in child.winfo_children():
                    if isinstance(sub, tk.Label) and sub.cget("bg") not in (BLUE, BLUE_HOVER, "#ffffff"):
                        sub.configure(bg=bg)
            elif isinstance(child, tk.Label) and child.cget("bg") not in (BLUE, BLUE_HOVER):
                child.configure(bg=bg)

    def _bind_wheel(self, canvas: tk.Canvas) -> None:
        def on_wheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", on_wheel))
        canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
