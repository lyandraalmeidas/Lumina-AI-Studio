"""Lumina Studio — interface gráfica (uso pessoal, sem créditos ou limites)."""
import ctypes
import os
import queue
import tempfile
import threading
import tkinter as tk
import traceback
from dataclasses import replace
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import cv2
from PIL import Image, ImageTk

import engine
from app_support import (
    LANGUAGES,
    THEMES,
    Preferences,
    Translator,
    format_bytes,
    load_catalogs,
    load_preferences,
    resolve_theme,
    resource_path,
    save_preferences,
    system_theme,
)
from engine import Settings, VIDEO_EXT, IMAGE_EXT

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    BaseTk = TkinterDnD.Tk
except ImportError:
    BaseTk = tk.Tk
    DND_FILES = None

PV = 520  # tamanho da prévia em pixels
TARGETS = {"1080p (Full HD)": 1080, "1440p (2K)": 1440,
           "2160p (4K)": 2160, "4320p (8K)": 4320}
UI_ICONS = {
    "preferences.title": "⚙",
    "section.ai": "✦",
    "section.adjustments": "◉",
    "section.output": "▣",
    "action.open": "＋",
    "action.refresh_preview": "◉",
    "action.process": "✧",
    "action.cancel": "×",
    "option.face": "◉",
    "option.upscale_ai": "↗",
    "option.fast_cpu": "◇",
    "option.color": "◐",
    "option.upscale": "↗",
    "option.stabilize": "⌖",
    "option.interpolate": "⧖",
    "option.fast_video": "≋",
}


class App(BaseTk):
    def __init__(self):
        self.startup_warnings = []
        if os.name == "nt":
            try:
                set_app_user_model_id = (
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID)
                set_app_user_model_id.argtypes = [ctypes.c_wchar_p]
                set_app_user_model_id.restype = ctypes.c_long
                result = set_app_user_model_id("LuminaStudio.Desktop")
                if result != 0:
                    self.startup_warnings.append(
                        f"AppUserModelID HRESULT 0x{result & 0xFFFFFFFF:08X}")
            except (AttributeError, OSError) as error:
                self.startup_warnings.append(str(error))
        super().__init__()
        self.catalogs = load_catalogs()
        preferences, preference_warning = load_preferences()
        self.preferences = preferences
        self.translator = Translator(self.catalogs, preferences.language)
        self.theme = resolve_theme(preferences.theme, system_theme())
        self._localized_widgets = []
        self._status_state = None
        self._detail_state = None
        self._auto_theme_job = None
        if preference_warning:
            self.startup_warnings.append(preference_warning)

        self.title(self.t("app.title"))
        if os.name == "nt":
            icon_path = resource_path(Path("assets") / "lumina.ico")
            try:
                self.iconbitmap(str(icon_path))
            except tk.TclError as error:
                self.startup_warnings.append(
                    self.t("dialog.resource_error", path=icon_path) + f" ({error})")
        self.geometry("1280x820")
        self.minsize(940, 680)

        self.src = None
        self.kind = None
        self.first = None
        self.center = None
        self.box = None
        self.prev = None
        self.split = 0.5
        self.preview_id = 0
        self._display_rect = None
        self.busy = False
        self.ai = None
        self.ai_key = None
        self.ai_lock = threading.Lock()
        self.cancel = threading.Event()
        self.q = queue.Queue()
        self._photo = None
        self._load_generation = 0
        self._close_when_idle = False

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind_all("<Control-o>", lambda _event: self.open_dialog())
        self.bind_all("<Control-O>", lambda _event: self.open_dialog())
        self.bind_all("<Control-Return>", lambda _event: self.start())
        self.btn_prev.config(state="disabled")
        self.btn_go.config(state="disabled")
        if self.startup_warnings:
            self._set_detail("status.startup_warning", error="; ".join(self.startup_warnings))
        self.after(80, self._poll)
        self._schedule_auto_theme_check()

    # ----------------------------------------------------------- layout
    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        self.configure(background="#101827")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(24, 18, 24, 14))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        self.lbl_title = self._label(header, "app.title", "Title.TLabel")
        self.lbl_title.grid(row=0, column=0, sticky="w")
        self.lbl_subtitle = self._label(header, "app.subtitle", "Muted.TLabel")
        self.lbl_subtitle.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.studio_badge = tk.Label(
            header, text="LUMINA AI LAB • STUDIO MODE",
            bg="#1b2030", fg="#d5c7ff", bd=0, font=("Segoe UI", 8, "bold"),
            padx=10, pady=4)
        self.studio_badge.grid(row=0, column=1, sticky="ne", padx=(12, 0))
        self.btn_open = self._button(
            header, "action.open", self.open_dialog, "Secondary.TButton")
        self.btn_open.grid(row=1, column=1, sticky="e", padx=(12, 0), pady=(6, 0))
        self.accent_bar = tk.Canvas(
            header, height=4, highlightthickness=0, bd=0)
        self.accent_bar.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        self.accent_bar.bind("<Configure>", self._draw_accent)

        self.lbl_file = self._label(self, "media.none", "Muted.TLabel", padding=(24, 0, 24, 14))
        self.lbl_file.grid(row=1, column=0, sticky="ew")

        main = ttk.Panedwindow(self, orient="horizontal", style="Main.TPanedwindow")
        main.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 12))

        preview_card = ttk.Frame(main, style="Card.TFrame", padding=18)
        main.add(preview_card, weight=4)
        preview_card.grid_columnconfigure(0, weight=1)
        preview_card.grid_rowconfigure(1, weight=1)
        self.lbl_preview = self._label(
            preview_card, "preview.title", "Section.TLabel")
        self.lbl_preview.grid(row=0, column=0, sticky="w", pady=(0, 12))
        stage = ttk.Frame(preview_card, style="Card.TFrame")
        stage.grid(row=1, column=0, sticky="nsew")
        stage.grid_columnconfigure(0, weight=1)
        stage.grid_rowconfigure(0, weight=1)
        self.view = tk.Canvas(
            stage, width=PV, height=PV, bg="#101827",
            highlightthickness=1, highlightbackground="#34465A",
            takefocus=True,
        )
        self.view.grid(row=0, column=0, sticky="nsew")
        self._empty_preview = self.view.create_text(
            PV // 2, PV // 2, fill="#9ba6b8",
            text=self.t("preview.empty"), justify="center",
            font=("Segoe UI", 12), width=PV - 36)
        self.view.bind("<ButtonPress-1>", self._on_split)
        self.view.bind("<B1-Motion>", self._on_split)
        for b in ("<Button-2>", "<Button-3>"):
            self.view.bind(b, self._on_pick)
        self.view.bind("<Control-Button-1>", self._on_pick)
        self.view.bind("<Configure>", self._on_view_resize)
        if DND_FILES:
            self.view.drop_target_register(DND_FILES)
            self.view.dnd_bind("<<Drop>>", lambda e: self.load_path(self.tk.splitlist(e.data)[0]))
        self.lbl_preview_help = self._label(
            preview_card, "preview.help", "Muted.TLabel", wraplength=660)
        self.lbl_preview_help.grid(row=2, column=0, sticky="w", pady=(12, 0))

        settings_shell = ttk.Frame(main, style="Card.TFrame", padding=12, width=380)
        main.add(settings_shell, weight=2)
        settings_shell.grid_columnconfigure(0, weight=1)
        settings_shell.grid_rowconfigure(0, weight=1)
        settings_shell.grid_rowconfigure(1, weight=0)
        settings_canvas = tk.Canvas(
            settings_shell, background="#1B2A3A", highlightthickness=0, width=350)
        self.settings_canvas = settings_canvas
        settings_scroll = ttk.Scrollbar(settings_shell, orient="vertical",
                                        command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        settings_canvas.grid(row=0, column=0, sticky="nsew")
        settings_scroll.grid(row=0, column=1, sticky="ns")
        right = ttk.Frame(settings_canvas, style="Card.TFrame", padding=(5, 4, 12, 10))
        settings_window = settings_canvas.create_window((0, 0), window=right, anchor="nw")
        right.bind("<Configure>", lambda e: settings_canvas.configure(
            scrollregion=(0, 0, e.width, e.height)))
        settings_canvas.bind("<Configure>", lambda e: settings_canvas.itemconfigure(
            settings_window, width=e.width))
        self.bind("<MouseWheel>", self._settings_wheel)
        right.grid_columnconfigure(0, weight=1)

        self.v_denoise = tk.DoubleVar(value=40)
        self.v_sharp = tk.DoubleVar(value=30)
        self.v_color = tk.BooleanVar(value=True)
        self.v_face = tk.BooleanVar(value=True)
        self.v_ai = tk.BooleanVar(value=True)
        self.v_fast_cpu = tk.BooleanVar(value=True)
        self.v_model = tk.StringVar(value="Fotos e vídeos reais")
        self.v_up = tk.BooleanVar(value=True)
        self.v_target = tk.StringVar(value="2160p (4K)")
        self.v_stab = tk.BooleanVar(value=False)
        self.v_interp = tk.BooleanVar(value=False)
        self.v_fast_video = tk.BooleanVar(value=True)

        preferences = self._section(right, "preferences.title")
        preferences.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.lbl_appearance = self._label(preferences, "preferences.appearance", "Card.TLabel")
        self.lbl_appearance.pack(anchor="w")
        self.cmb_theme = ttk.Combobox(
            preferences, state="readonly",
            values=[self.t(f"theme.{theme}") for theme in THEMES], takefocus=True)
        self.cmb_theme.current(THEMES.index(self.preferences.theme))
        self.cmb_theme.pack(fill="x", pady=(4, 2))
        self._label(
            preferences, "preferences.appearance_help", "Muted.TLabel",
            wraplength=300,
        ).pack(anchor="w", pady=(0, 9))
        self.lbl_language = self._label(preferences, "preferences.language", "Card.TLabel")
        self.lbl_language.pack(anchor="w")
        self.cmb_language = ttk.Combobox(
            preferences, state="readonly",
            values=[self.t(f"language.{language}") for language in LANGUAGES],
            takefocus=True)
        self.cmb_language.current(LANGUAGES.index(self.preferences.language))
        self.cmb_language.pack(fill="x", pady=(4, 2))
        self._label(
            preferences, "preferences.language_help", "Muted.TLabel",
            wraplength=300,
        ).pack(anchor="w")
        self.cmb_theme.bind("<<ComboboxSelected>>", self._on_theme_selected)
        self.cmb_language.bind("<<ComboboxSelected>>", self._on_language_selected)

        ia = self._section(right, "section.ai")
        ia.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ia.grid_configure(row=1)
        self._checkbutton(ia, "option.face", self.v_face, self._hint).pack(anchor="w", pady=3)
        self._checkbutton(ia, "option.upscale_ai", self.v_ai, self._hint).pack(anchor="w", pady=3)
        self._checkbutton(ia, "option.fast_cpu", self.v_fast_cpu).pack(anchor="w", pady=3)
        self._label(ia, "model.label", "Card.TLabel").pack(anchor="w", pady=(8, 2))
        self.cmb_model = ttk.Combobox(
            ia, textvariable=self.v_model, state="readonly",
            values=[self.t("model.photo"), self.t("model.anime")], takefocus=True)
        self.cmb_model.pack(fill="x")
        self.cmb_model.current(0)
        self.lbl_ai = self._label(ia, "model.help", "Muted.TLabel", wraplength=300)
        self.lbl_ai.pack(anchor="w", pady=(7, 0))

        aj = self._section(right, "section.adjustments")
        aj.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self._label(aj, "option.filter", "Card.TLabel").grid(
            row=0, column=0, sticky="w")
        self.cmb_filter = ttk.Combobox(
            aj, state="readonly",
            values=[self.t(f"filter.{name}") for name in engine.FILTERS],
            takefocus=True)
        self.cmb_filter.grid(row=1, column=0, sticky="ew", pady=(3, 8))
        self.cmb_filter.current(0)
        self.cmb_filter.bind("<<ComboboxSelected>>", self._on_filter_selected)
        self._add_scale(aj, "option.denoise", self.v_denoise, 2)
        self._checkbutton(aj, "option.color", self.v_color).grid(
            row=4, column=0, sticky="w", pady=(8, 2))
        self._add_scale(aj, "option.sharpness", self.v_sharp, 5)

        out = self._section(right, "section.output")
        out.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self._checkbutton(out, "option.upscale", self.v_up, self._hint).pack(anchor="w", pady=3)
        self._label(out, "output.height", "Card.TLabel").pack(anchor="w", pady=(7, 2))
        self.cmb_target = ttk.Combobox(out, textvariable=self.v_target, state="readonly",
                                       values=list(TARGETS), takefocus=True)
        self.cmb_target.pack(fill="x")
        self.cmb_target.current(2)
        ttk.Separator(out).pack(fill="x", pady=8)
        self.chk_stab = self._checkbutton(out, "option.stabilize", self.v_stab)
        self.chk_stab.pack(anchor="w", pady=3)
        self.chk_interp = self._checkbutton(out, "option.interpolate", self.v_interp)
        self.chk_interp.pack(anchor="w", pady=3)
        self.chk_fast_video = self._checkbutton(
            out, "option.fast_video", self.v_fast_video)
        self.chk_fast_video.pack(anchor="w", pady=3)

        self.lbl_hint = ttk.Label(
            right, text="", style="Muted.TLabel", wraplength=300, justify="left")
        self.lbl_hint.grid(row=4, column=0, sticky="w", pady=(0, 8))

        actions = ttk.Frame(settings_shell, style="Card.TFrame", padding=(4, 10, 4, 2))
        actions.grid(row=1, column=0, columnspan=2, sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        ttk.Separator(actions).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.btn_prev = self._button(
            actions, "action.refresh_preview", self.preview, "Secondary.TButton")
        self.btn_prev.grid(row=1, column=0, sticky="ew", pady=3)
        self.btn_go = self._button(
            actions, "action.process", self.start, "Primary.TButton")
        self.btn_go.grid(row=2, column=0, sticky="ew", pady=3)
        self.btn_cancel = self._button(
            actions, "action.cancel", self.cancel.set, "Secondary.TButton", state="disabled")
        self.btn_cancel.grid(row=3, column=0, sticky="ew", pady=(3, 2))
        self.btn_cancel.grid_remove()

        footer = ttk.Frame(self, padding=(24, 8, 24, 16))
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.status = ttk.Label(footer, style="Status.TLabel")
        self.status.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.pb = ttk.Progressbar(footer, maximum=100, mode="determinate")
        self.pb.grid(row=1, column=0, sticky="ew")
        self.status_detail = ttk.Label(footer, style="RootMuted.TLabel", wraplength=1100)
        self.status_detail.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self._set_status("status.ready")
        self._set_detail("status.ready_detail")
        self._apply_theme(self.theme)
        self._hint()

    def _label(self, parent, key, style, **options):
        widget = ttk.Label(parent, style=style, **options)
        self._localized_widgets.append((widget, key, "text"))
        widget.configure(text=self.t(key))
        return widget

    def _localized_text(self, key):
        icon = UI_ICONS.get(key)
        return f"{icon}  {self.t(key)}" if icon else self.t(key)

    def _button(self, parent, key, command, style, **options):
        widget = ttk.Button(parent, command=command, style=style, **options)
        self._localized_widgets.append((widget, key, "text"))
        widget.configure(text=self._localized_text(key))
        return widget

    def _section(self, parent, key):
        widget = ttk.LabelFrame(
            parent, style="Section.TLabelframe", padding=14, takefocus=False)
        self._localized_widgets.append((widget, key, "text"))
        widget.configure(text=self._localized_text(key))
        return widget

    def _checkbutton(self, parent, key, variable, command=None):
        widget = ttk.Checkbutton(
            parent, variable=variable, command=command,
            style="Section.TCheckbutton", takefocus=True)
        self._localized_widgets.append((widget, key, "text"))
        widget.configure(text=self._localized_text(key))
        return widget

    def _add_scale(self, parent, label_key, variable, row):
        parent.grid_columnconfigure(0, weight=1)
        label = self._label(parent, label_key, "Card.TLabel")
        label.grid(row=row, column=0, sticky="w")
        value = ttk.Label(parent, text=f"{int(variable.get())}%", style="Card.TLabel")
        if label_key == "option.denoise":
            self.denoise_value = value
        else:
            self.sharpness_value = value
        value.grid(row=row, column=1, sticky="e")
        ttk.Scale(parent, from_=0, to=100, variable=variable, takefocus=True).grid(
            row=row + 1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        variable.trace_add(
            "write", lambda *_: value.config(text=f"{int(variable.get())}%"))

    def t(self, key, **values):
        return self.translator(key, **values)

    def _apply_theme(self, theme):
        self.theme = theme
        palettes = {
            "dark": {
                "background": "#0D1117", "surface": "#131B29",
                "surface_raised": "#1B2434", "border": "#2E3A4F",
                "text": "#EEF2FF", "muted": "#A7AFBF",
                "blue": "#7C6AF1", "orange": "#C778FF",
                "amber": "#A58BFF", "gold": "#F3C98B",
                "preview": "#0F1726", "disabled": "#58657A",
                "lavender": "#B9A9FF",
            },
            "light": {
                "background": "#F3F0ED", "surface": "#F7F4F1",
                "surface_raised": "#FFFFFF", "border": "#D8D0C8",
                "text": "#1C2430", "muted": "#5D6977",
                "blue": "#7B6FE5", "orange": "#B49BFF",
                "amber": "#C7B7FF", "gold": "#B98852",
                "preview": "#EFEAE3", "disabled": "#8F9AAF",
                "lavender": "#7B6FE5",
            },
        }
        self.colors = palettes[theme]
        c = self.colors
        style = ttk.Style(self)
        style.configure(".", font=("Segoe UI", 10), foreground=c["text"])
        style.configure("TFrame", background=c["background"])
        style.configure("Card.TFrame", background=c["surface"])
        style.configure("TLabel", background=c["background"], foreground=c["text"])
        style.configure("Card.TLabel", background=c["surface"], foreground=c["text"])
        style.configure("Muted.TLabel", background=c["surface"], foreground=c["muted"])
        style.configure(
            "RootMuted.TLabel", background=c["background"], foreground=c["muted"])
        style.configure(
            "Status.TLabel", background=c["background"], foreground=c["text"],
            font=("Segoe UI Semibold", 10))
        style.configure(
            "Title.TLabel", background=c["background"], foreground=c["text"],
            font=("Segoe UI Semibold", 22))
        style.configure(
            "Section.TLabel", background=c["surface"], foreground=c["gold"],
            font=("Segoe UI Semibold", 10))
        style.configure(
            "Section.TLabelframe", background=c["surface"], foreground=c["text"],
            bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"],
            relief="flat", borderwidth=1)
        style.configure(
            "Section.TLabelframe.Label", background=c["surface"], foreground=c["blue"],
            font=("Segoe UI Semibold", 10))
        style.configure(
            "Section.TCheckbutton", background=c["surface"], foreground=c["text"],
            padding=(5, 7), focuscolor=c["lavender"],
            font=("Segoe UI", 10))
        style.map(
            "Section.TCheckbutton",
            background=[("active", c["surface_raised"])],
            foreground=[("disabled", c["disabled"])])
        style.configure(
            "Primary.TButton", background=c["orange"], foreground="#FFFFFF",
            padding=(16, 11), bordercolor=c["orange"], borderwidth=0,
            font=("Segoe UI Semibold", 10), focuscolor=c["lavender"])
        style.map(
            "Primary.TButton",
            background=[("active", c["amber"]), ("pressed", c["amber"]),
                        ("disabled", c["disabled"])],
            foreground=[("disabled", "#FFFFFF")])
        style.configure(
            "Secondary.TButton", background=c["surface_raised"], foreground=c["text"],
            padding=(13, 9), bordercolor=c["border"], focuscolor=c["lavender"])
        style.map(
            "Secondary.TButton",
            background=[("active", c["blue"]), ("pressed", c["blue"]),
                        ("disabled", c["surface"])],
            foreground=[("active", "#FFFFFF"), ("disabled", c["disabled"])])
        style.configure(
            "TCombobox", fieldbackground=c["surface_raised"], background=c["surface_raised"],
            foreground=c["text"], arrowcolor=c["blue"], bordercolor=c["border"],
            lightcolor=c["border"], darkcolor=c["border"], padding=5,
            focuscolor=c["gold"])
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", c["surface_raised"])],
            foreground=[("readonly", c["text"])],
            selectbackground=[("readonly", c["blue"])],
            selectforeground=[("readonly", "#FFFFFF")])
        style.configure(
            "TScale", background=c["surface"], troughcolor=c["border"],
            sliderthickness=14, focuscolor=c["gold"])
        style.configure(
            "TScrollbar", background=c["surface_raised"], troughcolor=c["surface"],
            arrowcolor=c["muted"], bordercolor=c["surface"], lightcolor=c["surface"],
            darkcolor=c["surface"])
        style.configure(
            "Horizontal.TProgressbar", troughcolor=c["border"], background=c["amber"],
            bordercolor=c["border"], lightcolor=c["amber"], darkcolor=c["amber"])
        style.configure("TSeparator", background=c["border"])
        style.configure("Main.TPanedwindow", background=c["background"])
        self.configure(background=c["background"])
        if hasattr(self, "accent_bar"):
            self.accent_bar.configure(background=c["background"])
            self._draw_accent()
        if hasattr(self, "view"):
            self.view.configure(
                background=c["preview"], highlightbackground=c["border"])
            self.view.itemconfigure(self._empty_preview, fill=c["muted"])
        if hasattr(self, "settings_canvas"):
            self.settings_canvas.configure(background=c["surface"])
        if hasattr(self, "studio_badge"):
            self.studio_badge.configure(bg=c["surface_raised"], fg=c["lavender"])
        self._refresh_locale_widgets()

    def _draw_accent(self, _event=None):
        if not hasattr(self, "accent_bar") or not hasattr(self, "colors"):
            return
        width = self.accent_bar.winfo_width()
        if width < 2:
            return
        start = tuple(int(self.colors["blue"][index:index + 2], 16)
                      for index in (1, 3, 5))
        middle = tuple(int(self.colors["lavender"][index:index + 2], 16)
                       for index in (1, 3, 5))
        end = tuple(int(self.colors["gold"][index:index + 2], 16)
                    for index in (1, 3, 5))
        self.accent_bar.delete("gradient")
        segments = min(width, 240)
        for position in range(segments):
            ratio = position / max(segments - 1, 1)
            left, right, progress = (
                (start, middle, ratio * 2)
                if ratio <= 0.5 else (middle, end, (ratio - 0.5) * 2)
            )
            color = "#" + "".join(
                f"{round(a + (b - a) * progress):02x}"
                for a, b in zip(left, right)
            )
            x0 = position * width / segments
            x1 = (position + 1) * width / segments
            self.accent_bar.create_rectangle(
                x0, 0, x1 + 1, 4, fill=color, outline=color, tags="gradient")

    def _refresh_locale_widgets(self):
        for widget, key, option in self._localized_widgets:
            text = self._localized_text(key) if option == "text" else self.t(key)
            widget.configure(**{option: text})
        self.title(self.t("app.title"))
        if hasattr(self, "cmb_theme"):
            theme_index = self.cmb_theme.current()
            language_index = self.cmb_language.current()
            model_index = self.cmb_model.current()
            filter_index = self.cmb_filter.current()
            self.cmb_theme.configure(
                values=[self.t(f"theme.{theme}") for theme in THEMES])
            self.cmb_language.configure(
                values=[self.t(f"language.{language}") for language in LANGUAGES])
            self.cmb_model.configure(
                values=[self.t("model.photo"), self.t("model.anime")])
            self.cmb_filter.configure(
                values=[self.t(f"filter.{name}") for name in engine.FILTERS])
            if theme_index >= 0:
                self.cmb_theme.current(theme_index)
            if language_index >= 0:
                self.cmb_language.current(language_index)
            if model_index >= 0:
                self.cmb_model.current(model_index)
            if filter_index >= 0:
                self.cmb_filter.current(filter_index)
        if getattr(self, "src", None) and self.first is not None:
            height, width = self.first.shape[:2]
            self.lbl_file.configure(text=self.t(
                "media.detail", name=os.path.basename(self.src),
                width=width, height=height,
                kind=self.t("media.kind.video" if self.kind == "video"
                            else "media.kind.image")))
        elif hasattr(self, "lbl_file"):
            self.lbl_file.configure(text=self.t("media.none"))
        self._refresh_scale_values()
        if self._status_state:
            key, values, text = self._status_state
            self.status.configure(text=self.t(key, **values) if key else text)
        if self._detail_state:
            key, values, text = self._detail_state
            self.status_detail.configure(text=self.t(key, **values) if key else text)
        if hasattr(self, "v_face"):
            self._hint()

    def _refresh_scale_values(self):
        if not hasattr(self, "v_denoise"):
            return
        for variable, label in (
            (self.v_denoise, "denoise_value"),
            (self.v_sharp, "sharpness_value"),
        ):
            value_widget = getattr(self, label, None)
            if value_widget is not None:
                value_widget.configure(text=f"{int(variable.get())}%")

    def _set_status(self, key=None, text=None, **values):
        self._status_state = (key, values, text)
        self.status.configure(text=self.t(key, **values) if key else text)

    def _set_detail(self, key=None, text=None, **values):
        self._detail_state = (key, values, text)
        self.status_detail.configure(text=self.t(key, **values) if key else text)

    def _on_theme_selected(self, _event=None):
        theme = THEMES[self.cmb_theme.current()]
        self.preferences = replace(self.preferences, theme=theme)
        self._apply_theme(resolve_theme(
            theme, system_theme() if theme == "auto" else "light"))
        self._save_preferences()
        if self._auto_theme_job is not None:
            self.after_cancel(self._auto_theme_job)
            self._auto_theme_job = None
        self._schedule_auto_theme_check()

    def _on_language_selected(self, _event=None):
        language = LANGUAGES[self.cmb_language.current()]
        self.preferences = replace(self.preferences, language=language)
        self.translator.set_language(language)
        self._refresh_locale_widgets()
        self._save_preferences()

    def _save_preferences(self):
        try:
            save_preferences(self.preferences)
        except OSError as error:
            messagebox.showerror(
                self.t("dialog.error_title"),
                self.t("dialog.preferences_error", error=error),
                parent=self,
            )

    def _schedule_auto_theme_check(self):
        self._auto_theme_job = None
        if self.preferences.theme != "auto":
            return
        current_theme = resolve_theme("auto", system_theme())
        if current_theme != self.theme:
            self._apply_theme(current_theme)
        self._auto_theme_job = self.after(5000, self._schedule_auto_theme_check)

    def _on_close(self):
        if self.busy:
            if not messagebox.askyesno(
                self.t("dialog.error_title"),
                self.t("dialog.close_busy"),
                parent=self,
            ):
                return
            self._close_when_idle = True
            self.cancel.set()
            self._set_status("status.closing_when_idle")
            self._set_detail("status.closing_detail")
            return
        self._destroy_app()

    def _destroy_app(self):
        if self._auto_theme_job is not None:
            self.after_cancel(self._auto_theme_job)
        self.destroy()

    def _localize_engine_error(self, error):
        engine_errors = {
            "Não foi possível ler a imagem.": "engine.error_read_image",
            "Falha ao codificar a imagem.": "engine.error_encode_image",
            "Não foi possível criar o arquivo de vídeo.": "engine.error_create_video",
            "Não foi possível abrir o vídeo.": "engine.error_open_video",
            "O FFmpeg encerrou inesperadamente.": "engine.error_ffmpeg",
            "Formato não suportado. Use MP4, MOV, MKV, WEBM, JPG, PNG, WEBP etc.": (
                "engine.error_unsupported"),
        }
        message = str(error)
        key = engine_errors.get(message)
        return self.t(key) if key else message

    def _settings_wheel(self, event):
        widget = event.widget
        while widget is not None and widget is not self.settings_canvas:
            widget = getattr(widget, "master", None)
        if widget is self.settings_canvas:
            self.settings_canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"

    def _hint(self):
        msgs = []
        if self.src is None:
            msgs.append(self.t("hint.no_file"))
        if self.kind == "video" and (self.v_ai.get() or self.v_face.get()):
            msgs.append(self.t("hint.video_ai"))
        if not DND_FILES:
            msgs.append(self.t("hint.no_drag_drop"))
        self.lbl_hint.config(text=" ".join(msgs))
        self.chk_stab.config(state="normal" if self.kind == "video" else "disabled")
        self.chk_interp.config(state="normal" if self.kind == "video" else "disabled")
        self.chk_fast_video.config(state="normal" if self.kind == "video" else "disabled")
        self.cmb_model.config(
            state="readonly" if self.v_ai.get() and self.v_up.get() else "disabled")
        self.cmb_target.config(state="readonly" if self.v_up.get() else "disabled")
        if self.kind:
            self.lbl_ai.config(text=self.t("model.help"))

    def _on_view_resize(self, event):
        if self.prev is None:
            self.view.coords(self._empty_preview, event.width // 2, event.height // 2)
        else:
            self._compose()

    def settings(self):
        video = self.kind == "video"
        return Settings(
            denoise=int(self.v_denoise.get()),
            color=self.v_color.get(),
            face=self.v_face.get(),
            upscale=self.v_up.get(),
            use_ai=self.v_ai.get(),
            anime=self.cmb_model.current() == 1,
            fast_cpu=self.v_fast_cpu.get(),
            target_h=TARGETS[self.v_target.get()],
            sharpen=int(self.v_sharp.get()),
            stab=video and self.v_stab.get(),
            interp=video and self.v_interp.get(),
            fast_video=self.v_fast_video.get(),
            filter_name=engine.FILTERS[self.cmb_filter.current()],
        )

    def _busy(self, on, cancellable=False):
        self.busy = on
        st = "disabled" if on else "normal"
        for b in (self.btn_open, self.btn_go, self.btn_prev):
            b.config(state=st)
        if on and cancellable:
            self.btn_cancel.config(state="normal")
            self.btn_cancel.grid()
        else:
            self.btn_cancel.config(state="disabled")
            self.btn_cancel.grid_remove()
        if on:
            self.pb.stop()
            self.pb.configure(mode="indeterminate")
            self.pb.start(12)
        else:
            self.pb.stop()
            self.pb.configure(mode="determinate")
            self.pb["value"] = 0

    # ----------------------------------------------------------- arquivo
    def open_dialog(self):
        exts = " ".join("*" + e for e in sorted(VIDEO_EXT | IMAGE_EXT))
        path = filedialog.askopenfilename(
            parent=self,
            title=self.t("dialog.open_file_title"),
            filetypes=[
                (self.t("dialog.image_filter") + " / " + self.t("dialog.video_filter"), exts),
                (self.t("dialog.all_files"), "*.*"),
            ],
        )
        if path:
            self.load_path(path)

    def load_path(self, path):
        if self.busy:
            return
        self._load_generation += 1
        generation = self._load_generation
        self._busy(True)
        self._set_status("status.loading_media")
        self._set_detail("status.loading_media_detail")
        threading.Thread(
            target=self._load_path_job,
            args=(path, generation),
            daemon=True,
        ).start()

    def _load_path_job(self, path, generation):
        try:
            frame, kind = engine.read_first_frame(path)
        except Exception as error:
            self.q.put(("load_error", (generation, error)))
            return
        self.q.put(("loaded", (generation, path, frame, kind)))

    def _set_loaded_media(self, path, frame, kind):
        self.src, self.kind, self.first = path, kind, frame
        self.btn_prev.config(state="normal")
        self.btn_go.config(state="normal")
        self.center = None
        self.prev = None
        self.box = None
        h, w = frame.shape[:2]
        self.lbl_file.config(text=self.t(
            "media.detail", name=os.path.basename(path), width=w, height=h,
            kind=self.t("media.kind.video" if kind == "video" else "media.kind.image"),
        ))
        self._hint()
        self.view.delete("all")
        self.view.create_text(self.view.winfo_width() // 2, self.view.winfo_height() // 2,
                              fill=self.colors["muted"],
                              text=self.t("status.preview"), justify="center",
                              font=("Segoe UI", 12), width=PV - 36)
        self.preview()

    # ----------------------------------------------------------- prévia
    def preview(self):
        if self.busy or self.first is None:
            return
        s = self.settings()
        self.preview_id += 1
        preview_id = self.preview_id
        frame = self.first
        center = self.center
        video = self.kind == "video"
        self._set_status("status.preview")
        self._set_detail(
            "status.preview_video_detail" if video else "status.preview_detail")
        self._busy(True)
        threading.Thread(
            target=self._preview_job,
            args=(s, preview_id, frame, center, video),
            daemon=True,
        ).start()

    def _preview_job(self, s, preview_id, frame, center, video):
        try:
            before, after, box = engine.make_preview(
                frame, s, None, center, PV, video=video)
            self.q.put(("preview", (preview_id, before, after, box)))
        except Exception as e:
            traceback.print_exc()
            self.q.put(("err", str(e)))
            self.q.put(("idle", None))
            return
        if not video and (s.face or (s.use_ai and s.upscale)):
            threading.Thread(
                target=self._ai_preview_job,
                args=(s, preview_id, frame, center),
                daemon=True,
            ).start()
        else:
            self.q.put(("idle", None))

    def _ai_preview_job(self, s, preview_id, frame, center):
        try:
            self.q.put(("log_key", ("status.preview_basic_ready", {})))
            ai = self._get_ai(s)
            if ai and ((s.face and ai.can_face)
                       or (s.use_ai and s.upscale and ai.can_upscale)):
                before, after, box = engine.make_preview(frame, s, ai, center, PV)
                self.q.put(("preview", (preview_id, before, after, box)))
        except Exception as e:
            traceback.print_exc()
            self.q.put(("log_key", ("status.preview_ai_failed", {
                "error": self._localize_engine_error(e),
            })))
        finally:
            self.q.put(("stage_done", None))
            self.q.put(("idle", None))

    def _on_split(self, e):
        if not self._display_rect:
            return
        display_x, size = self._display_rect[0], self._display_rect[2]
        self.split = min(max((e.x - display_x) / size, 0.0), 1.0)
        self._compose()

    def _on_filter_selected(self, _event=None):
        self.preview()

    def _on_pick(self, e):
        if not self.box or self.busy:
            return
        if not self._display_rect:
            return
        x0, y0, cs = self.box
        display_x, display_y, size = self._display_rect
        width, height = self.first.shape[1], self.first.shape[0]
        cx = x0 + (e.x - display_x) / size * cs
        cy = y0 + (e.y - display_y) / size * cs
        self.center = (min(max(int(cx), 0), width - 1),
                       min(max(int(cy), 0), height - 1))
        self.preview()

    def _compose(self):
        if self.prev is None:
            return
        before, after = self.prev
        width, height = self.view.winfo_width(), self.view.winfo_height()
        size = min(PV, width, height)
        if size < 2:
            return
        display_x, display_y = (width - size) // 2, (height - size) // 2
        self._display_rect = (display_x, display_y, size)
        before = cv2.resize(before, (size, size), interpolation=cv2.INTER_AREA)
        after = cv2.resize(after, (size, size), interpolation=cv2.INTER_AREA)
        x = int(self.split * size)
        out = before.copy()
        out[:, x:] = after[:, x:]
        cv2.line(out, (min(x, size - 1), 0), (min(x, size - 1), size - 1),
                 (255, 255, 255), 2)
        self._photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB)))
        self.view.delete("all")
        self.view.create_image(display_x, display_y, anchor="nw", image=self._photo)

    # ----------------------------------------------------------- processar
    def start(self):
        if self.busy:
            return
        if self.src is None:
            messagebox.showinfo(
                self.t("dialog.error_title"), self.t("dialog.open_first"), parent=self)
            return
        s = self.settings()
        base, ext = os.path.splitext(os.path.basename(self.src))
        if self.kind == "video":
            dst = filedialog.asksaveasfilename(
                parent=self, title=self.t("dialog.save_video_title"),
                initialfile=f"{base}_lumina.mp4", defaultextension=".mp4",
                filetypes=[(self.t("dialog.video_filter"), "*.mp4")])
        else:
            ext = ext.lower() if ext.lower() in IMAGE_EXT else ".png"
            dst = filedialog.asksaveasfilename(
                parent=self, title=self.t("dialog.save_image_title"),
                initialfile=f"{base}_lumina{ext}", defaultextension=ext,
                filetypes=[(self.t("dialog.image_filter"), "*" + ext)])
        if not dst:
            return
        if os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(self.src)):
            messagebox.showerror(
                self.t("dialog.invalid_destination_title"),
                self.t("dialog.invalid_destination"),
                parent=self,
            )
            return
        self.cancel.clear()
        self._busy(True, cancellable=self.kind == "video")
        threading.Thread(target=self._job, args=(s, dst), daemon=True).start()

    def _job(self, s, dst):
        try:
            if self.kind == "image" and (s.face or (s.use_ai and s.upscale)):
                self.q.put(("stage", ("status.image_saved", {})))
                engine.process_image(self.src, dst, s, None)
                ai = self._get_ai(s)
                if ai and ((s.face and ai.can_face)
                           or (s.use_ai and s.upscale and ai.can_upscale)):
                    self.q.put(("stage", ("status.ai_enhancement", {})))
                    folder = os.path.dirname(os.path.abspath(dst))
                    ext = os.path.splitext(dst)[1]
                    fd, ai_dst = tempfile.mkstemp(prefix=".lumina_ai_", suffix=ext, dir=folder)
                    os.close(fd)
                    try:
                        engine.process_image(
                            self.src, ai_dst, s, ai,
                            progress=lambda p, stage: self.q.put(
                                ("image_prog", (p, stage))),
                        )
                        os.replace(ai_dst, dst)
                    except Exception as e:
                        try:
                            os.remove(ai_dst)
                        except FileNotFoundError:
                            pass
                        traceback.print_exc()
                        self.q.put(("log_key", ("status.ai_fallback", {
                            "error": self._localize_engine_error(e),
                        })))
            elif self.kind == "image":
                self.q.put(("stage", ("status.processing_image", {})))
                engine.process_image(self.src, dst, s, None)
            else:
                stage_key = ("status.loading_models"
                             if s.face or (s.use_ai and s.upscale)
                             else "status.preparing_video")
                self.q.put(("stage", (stage_key, {})))
                ai = self._get_ai(s)
                self.q.put(("stage", ("status.processing_video", {})))
                engine.process_video(self.src, dst, s, ai,
                                     progress=lambda p: self.q.put(("prog", p)),
                                     cancel=self.cancel)
            self.q.put(("done", (dst, self.cancel.is_set())))
        except Exception as e:
            traceback.print_exc()
            self.q.put(("err", self._localize_engine_error(e)))
        finally:
            self.q.put(("idle", None))

    def _get_ai(self, s):
        load_upscaler = s.use_ai and s.upscale
        load_face = s.face
        if not (load_upscaler or load_face):
            return None
        ai_key = (s.anime, load_upscaler, load_face)
        with self.ai_lock:
            if self.ai_key != ai_key:
                self.ai = None
                self.q.put(("stage", ("status.preparing_ai", {})))
                try:
                    self.ai = engine.load_ai(
                        s.anime,
                        log=lambda _message: self.q.put(
                            ("log_key", ("status.downloading_models", {}))),
                        progress=lambda name, done, total: self.q.put(
                            ("download", (name, done, total))),
                        load_upscaler=load_upscaler,
                        load_face=load_face,
                    )
                except Exception as e:
                    self.ai_key = None
                    self.q.put(("log_key", ("status.ai_unavailable", {
                        "error": self._localize_engine_error(e),
                    })))
                    return None
                self.ai_key = ai_key
                self.q.put(("log_key", ("status.ai_summary", {
                    "device": self.t("status.device.gpu" if self.ai.device == "cuda"
                                     else "status.device.cpu"),
                    "upscaling": self.t("status.feature.available"
                                        if self.ai.can_upscale
                                        else "status.feature.unavailable"),
                    "faces": self.t("status.feature.available"
                                    if self.ai.can_face
                                    else "status.feature.unavailable"),
                })))
                if not self.ai.can_upscale and not self.ai.can_face:
                    self.q.put(("log_key", ("status.classic_fallback", {})))
                for warning in self.ai.errors:
                    self.q.put(("log_key", ("status.ai_warning", {"error": warning})))
        return self.ai

    # ----------------------------------------------------------- fila da interface
    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self._set_status(text=val)
                    self._set_detail(text="")
                elif kind == "log_key":
                    key, values = val
                    self._set_status(key, **values)
                    self._set_detail(text="")
                elif kind == "stage":
                    key, values = val
                    self._set_status(key, **values)
                    self._set_detail("status.stage_detail")
                    self.pb.stop()
                    self.pb.configure(mode="indeterminate")
                    self.pb.start(12)
                elif kind == "stage_done":
                    if not self.busy:
                        self.pb.stop()
                        self.pb.configure(mode="determinate")
                        self.pb["value"] = 0
                        self._set_detail(text="")
                elif kind == "download":
                    name, done, total = val
                    if total > 0:
                        self.pb.stop()
                        self.pb.configure(mode="determinate")
                        self.pb["value"] = min(done / total * 100, 100)
                        percent = min(done / total * 100, 100)
                        self._set_status("status.download", name=name)
                        self._set_detail(
                            "status.download_detail", percent=f"{percent:.0f}",
                            done=self._format_bytes(done), total=self._format_bytes(total))
                    else:
                        self.pb.configure(mode="indeterminate")
                        self.pb.start(12)
                        self._set_status("status.download", name=name)
                        self._set_detail(
                            "status.received", size=self._format_bytes(done))
                elif kind == "prog":
                    self.pb.stop()
                    self.pb.configure(mode="determinate")
                    self.pb["value"] = val * 100
                    self._set_status("status.video_progress", percent=f"{val * 100:.0f}")
                    self._set_detail("status.video_detail")
                elif kind == "image_prog":
                    progress, stage = val
                    self.pb.stop()
                    self.pb.configure(mode="determinate")
                    self.pb["value"] = progress * 100
                    self._set_status(
                        "status.image_progress", stage=self._translate_stage(stage),
                        percent=f"{progress * 100:.0f}")
                    self._set_detail("status.image_detail")
                elif kind == "preview":
                    preview_id, before, after, box = val
                    if preview_id == self.preview_id:
                        self.prev = (before, after)
                        self.box = box
                        self._compose()
                        self._set_status("status.preview_updated")
                elif kind == "loaded":
                    generation, path, frame, media_kind = val
                    if generation == self._load_generation:
                        self._busy(False)
                        if self._close_when_idle:
                            self._destroy_app()
                            return
                        self._set_loaded_media(path, frame, media_kind)
                elif kind == "load_error":
                    generation, error = val
                    if generation == self._load_generation:
                        self._busy(False)
                        self._set_status("status.processing_error")
                        self._set_detail("status.processing_error_detail")
                        messagebox.showerror(
                            self.t("dialog.invalid_file_title"),
                            self._localize_engine_error(error),
                            parent=self,
                        )
                        if self._close_when_idle:
                            self._destroy_app()
                            return
                elif kind == "done":
                    dst, cancelled = val
                    self._set_status(
                        "status.processing_cancelled" if cancelled
                        else "status.processing_complete")
                    self._set_detail(
                        "status.partial_saved_to" if cancelled else "status.saved_to",
                        path=dst)
                    self._busy(False)
                    messagebox.showinfo(
                        self.t("dialog.error_title"),
                        self.t("dialog.processing_cancelled" if cancelled
                               else "dialog.processing_complete", path=dst),
                        parent=self,
                    )
                elif kind == "err":
                    self._set_status("status.processing_error")
                    self._set_detail("status.processing_error_detail")
                    self._busy(False)
                    messagebox.showerror(
                        self.t("dialog.error_title"), val, parent=self)
                elif kind == "idle":
                    self._busy(False)
                    if self._close_when_idle:
                        self._destroy_app()
                        return
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _translate_stage(self, stage):
        stage_keys = {
            "Preparando imagem": "stage.prepare_image",
            "Restaurando rostos": "stage.restore_faces",
            "Rostos restaurados": "stage.faces_restored",
            "Aplicando upscaling com IA": "stage.upscale",
            "Finalizando resolução": "stage.finalize_resolution",
            "Aplicando nitidez": "stage.sharpen",
            "Salvando resultado": "stage.save_result",
            "Aprimoramento concluído": "stage.complete",
        }
        key = stage_keys.get(stage)
        return self.t(key) if key else stage

    def _format_bytes(self, value):
        return format_bytes(value, self.preferences.language)


def main():
    try:
        app = App()
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Lumina AI Studio",
            "Falha ao carregar os recursos ou preferências do aplicativo.\n\n"
            f"{error}",
            parent=root,
        )
        root.destroy()
        raise
    app.mainloop()


if __name__ == "__main__":
    main()