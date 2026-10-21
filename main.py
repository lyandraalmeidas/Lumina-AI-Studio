"""Lumina Studio — interface gráfica (uso pessoal, sem créditos ou limites)."""
import os
import queue
import tempfile
import threading
import tkinter as tk
import traceback
from tkinter import ttk, filedialog, messagebox

import cv2
from PIL import Image, ImageTk

import engine
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


class App(BaseTk):
    def __init__(self):
        super().__init__()
        self.title("Lumina Studio")
        self.geometry("1360x860")
        self.minsize(1080, 700)

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

        self._build()
        self.btn_prev.config(state="disabled")
        self.btn_go.config(state="disabled")
        self.after(80, self._poll)

    # ----------------------------------------------------------- layout
    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#171b24")
        style.configure("Card.TFrame", background="#202633")
        style.configure("TLabel", background="#171b24", foreground="#e7eaf0")
        style.configure("Muted.TLabel", background="#171b24", foreground="#aab3c2")
        style.configure("Card.TLabel", background="#202633", foreground="#e7eaf0")
        style.configure("Title.TLabel", background="#171b24", foreground="#f4f6fa",
                        font=("Segoe UI Semibold", 19))
        style.configure("Section.TLabelframe", background="#202633",
                        foreground="#f4f6fa", bordercolor="#343d4d")
        style.configure("Section.TLabelframe.Label", background="#202633",
                        foreground="#b8c7ff", font=("Segoe UI Semibold", 10))
        style.configure("Section.TCheckbutton", background="#202633",
                        foreground="#e7eaf0")
        style.map("Section.TCheckbutton",
                  background=[("active", "#202633")],
                  foreground=[("disabled", "#778092")])
        style.configure("Primary.TButton", background="#667cf4", foreground="white",
                        padding=(12, 9), font=("Segoe UI Semibold", 10))
        style.map("Primary.TButton", background=[("active", "#7b8eff"),
                                                ("disabled", "#454c5a")])
        style.configure("Secondary.TButton", padding=(10, 8))
        style.configure("Horizontal.TProgressbar", troughcolor="#303746",
                        background="#7488ff", bordercolor="#303746", lightcolor="#7488ff",
                        darkcolor="#7488ff")
        self.configure(background="#171b24")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(22, 16, 22, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="Lumina Studio", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        ttk.Label(header, text="Restaure e aprimore fotos e vídeos",
                  style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.btn_open = ttk.Button(header, text="＋  Abrir foto ou vídeo",
                                   command=self.open_dialog, style="Secondary.TButton")
        self.btn_open.grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))

        self.lbl_file = ttk.Label(self, text="Nenhum arquivo selecionado — abra ou arraste uma mídia",
                                  style="Muted.TLabel", padding=(22, 0, 22, 12))
        self.lbl_file.grid(row=1, column=0, sticky="ew")

        main = ttk.Panedwindow(self, orient="horizontal")
        main.grid(row=2, column=0, sticky="nsew", padx=18, pady=(0, 12))

        preview_card = ttk.Frame(main, style="Card.TFrame", padding=16)
        main.add(preview_card, weight=4)
        preview_card.grid_columnconfigure(0, weight=1)
        preview_card.grid_rowconfigure(1, weight=1)
        ttk.Label(preview_card, text="PRÉVIA", style="Card.TLabel",
                  font=("Segoe UI Semibold", 10)).grid(row=0, column=0, sticky="w", pady=(0, 10))
        stage = ttk.Frame(preview_card, style="Card.TFrame")
        stage.grid(row=1, column=0, sticky="nsew")
        stage.grid_columnconfigure(0, weight=1)
        stage.grid_rowconfigure(0, weight=1)
        self.view = tk.Canvas(stage, width=PV, height=PV, bg="#10141c",
                              highlightthickness=1, highlightbackground="#343d4d")
        self.view.grid(row=0, column=0)
        self._empty_preview = self.view.create_text(
            PV // 2, PV // 2, fill="#9ba6b8",
            text="Sua prévia aparecerá aqui\n\nAbra uma imagem ou vídeo para começar",
            justify="center", font=("Segoe UI", 12))
        self.view.bind("<ButtonPress-1>", self._on_split)
        self.view.bind("<B1-Motion>", self._on_split)
        for b in ("<Button-2>", "<Button-3>"):
            self.view.bind(b, self._on_pick)
        self.view.bind("<Control-Button-1>", self._on_pick)
        self.view.bind("<Configure>", self._on_view_resize)
        if DND_FILES:
            self.view.drop_target_register(DND_FILES)
            self.view.dnd_bind("<<Drop>>", lambda e: self.load_path(self.tk.splitlist(e.data)[0]))
        ttk.Label(preview_card,
                  text="Arraste a linha vertical para comparar. Clique com o botão direito para escolher uma área.",
                  style="Card.TLabel", wraplength=650).grid(row=2, column=0, sticky="w", pady=(10, 0))

        settings_shell = ttk.Frame(main, style="Card.TFrame", padding=10, width=360)
        main.add(settings_shell, weight=2)
        settings_shell.grid_columnconfigure(0, weight=1)
        settings_shell.grid_rowconfigure(0, weight=1)
        settings_shell.grid_rowconfigure(1, weight=0)
        settings_canvas = tk.Canvas(settings_shell, background="#202633",
                                    highlightthickness=0, width=330)
        self.settings_canvas = settings_canvas
        settings_scroll = ttk.Scrollbar(settings_shell, orient="vertical",
                                        command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        settings_canvas.grid(row=0, column=0, sticky="nsew")
        settings_scroll.grid(row=0, column=1, sticky="ns")
        right = ttk.Frame(settings_canvas, style="Card.TFrame", padding=(4, 2, 10, 8))
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

        ia = ttk.LabelFrame(right, text="Inteligência artificial", style="Section.TLabelframe",
                            padding=12)
        ia.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Checkbutton(ia, text="Restaurar rostos", variable=self.v_face,
                        command=self._hint, style="Section.TCheckbutton").pack(anchor="w", pady=3)
        ttk.Checkbutton(ia, text="Upscaling com IA", variable=self.v_ai,
                        command=self._hint, style="Section.TCheckbutton").pack(anchor="w", pady=3)
        ttk.Checkbutton(
            ia, text="Acelerar IA em CPU (pode reduzir detalhes)",
            variable=self.v_fast_cpu, style="Section.TCheckbutton",
        ).pack(anchor="w", pady=3)
        ttk.Label(ia, text="Perfil do modelo", style="Card.TLabel").pack(anchor="w", pady=(8, 2))
        self.cmb_model = ttk.Combobox(
            ia, textvariable=self.v_model, state="readonly",
            values=["Fotos e vídeos reais", "Anime e desenhos"])
        self.cmb_model.pack(fill="x")
        self.lbl_ai = ttk.Label(ia, text="Os modelos são baixados na primeira utilização.",
                                style="Muted.TLabel", wraplength=285)
        self.lbl_ai.pack(anchor="w", pady=(7, 0))

        aj = ttk.LabelFrame(right, text="Ajustes de imagem", style="Section.TLabelframe",
                            padding=12)
        aj.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self._add_scale(aj, "Redução de ruído", self.v_denoise, 0)
        ttk.Checkbutton(aj, text="Correção automática de cor", variable=self.v_color,
                        style="Section.TCheckbutton").grid(row=2, column=0, sticky="w", pady=(8, 2))
        self._add_scale(aj, "Nitidez", self.v_sharp, 3)

        out = ttk.LabelFrame(right, text="Resolução e vídeo", style="Section.TLabelframe",
                             padding=12)
        out.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Checkbutton(out, text="Ampliar resolução", variable=self.v_up,
                        command=self._hint, style="Section.TCheckbutton").pack(anchor="w", pady=3)
        ttk.Label(out, text="Altura de saída", style="Card.TLabel").pack(anchor="w", pady=(7, 2))
        self.cmb_target = ttk.Combobox(out, textvariable=self.v_target, state="readonly",
                                       values=list(TARGETS))
        self.cmb_target.pack(fill="x")
        ttk.Separator(out).pack(fill="x", pady=8)
        self.chk_stab = ttk.Checkbutton(out, text="Estabilizar câmera (vídeo)", variable=self.v_stab,
                                        style="Section.TCheckbutton")
        self.chk_stab.pack(anchor="w", pady=3)
        self.chk_interp = ttk.Checkbutton(out, text="Interpolar para 60 fps (vídeo)",
                                          variable=self.v_interp, style="Section.TCheckbutton")
        self.chk_interp.pack(anchor="w", pady=3)

        self.lbl_hint = ttk.Label(right, text="", style="Muted.TLabel",
                                  wraplength=290, justify="left")
        self.lbl_hint.grid(row=3, column=0, sticky="w", pady=(0, 8))

        actions = ttk.Frame(settings_shell, style="Card.TFrame", padding=(4, 10, 4, 2))
        actions.grid(row=1, column=0, columnspan=2, sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        ttk.Separator(actions).grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.btn_prev = ttk.Button(actions, text="Atualizar prévia",
                                   command=self.preview, style="Secondary.TButton")
        self.btn_prev.grid(row=1, column=0, sticky="ew", pady=3)
        self.btn_go = ttk.Button(actions, text="Processar e salvar",
                                 command=self.start, style="Primary.TButton")
        self.btn_go.grid(row=2, column=0, sticky="ew", pady=3)
        self.btn_cancel = ttk.Button(actions, text="Cancelar processamento",
                                      command=self.cancel.set, state="disabled")
        self.btn_cancel.grid(row=3, column=0, sticky="ew", pady=(3, 2))
        self.btn_cancel.grid_remove()

        footer = ttk.Frame(self, padding=(22, 8, 22, 14))
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.status = ttk.Label(footer, text="Pronto para começar", style="Muted.TLabel")
        self.status.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.pb = ttk.Progressbar(footer, maximum=100, mode="determinate")
        self.pb.grid(row=1, column=0, sticky="ew")
        self.status_detail = ttk.Label(footer, text="", style="Muted.TLabel")
        self.status_detail.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self._hint()

    def _add_scale(self, parent, label, variable, row):
        parent.grid_columnconfigure(0, weight=1)
        ttk.Label(parent, text=label, style="Card.TLabel").grid(
            row=row, column=0, sticky="w")
        value = ttk.Label(parent, text=f"{int(variable.get())}%", style="Card.TLabel")
        value.grid(row=row, column=1, sticky="e")
        ttk.Scale(parent, from_=0, to=100, variable=variable).grid(
            row=row + 1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        variable.trace_add("write", lambda *_: value.config(text=f"{int(variable.get())}%"))

    def _settings_wheel(self, event):
        widget = event.widget
        while widget is not None and widget is not self.settings_canvas:
            widget = getattr(widget, "master", None)
        if widget is self.settings_canvas:
            self.settings_canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"

    def _hint(self):
        msgs = []
        if self.kind == "video" and (self.v_ai.get() or self.v_face.get()):
            msgs.append("Vídeo com IA é muito lento sem placa NVIDIA (CUDA). "
                        "Para testar rápido, desative a IA.")
        if not DND_FILES:
            msgs.append("Para abrir um arquivo, use o botão Abrir foto ou vídeo.")
        self.lbl_hint.config(text=" ".join(msgs))
        self.chk_stab.config(state="normal" if self.kind == "video" else "disabled")
        self.chk_interp.config(state="normal" if self.kind == "video" else "disabled")
        self.cmb_model.config(
            state="readonly" if self.v_ai.get() and self.v_up.get() else "disabled")
        self.cmb_target.config(state="readonly" if self.v_up.get() else "disabled")
        if self.kind:
            self.lbl_ai.config(
                text="Os modelos selecionados são baixados na primeira utilização. "
                     "Sem internet, os ajustes clássicos continuam disponíveis.")

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
            anime=self.v_model.get().startswith("Anime"),
            fast_cpu=self.v_fast_cpu.get(),
            target_h=TARGETS[self.v_target.get()],
            sharpen=int(self.v_sharp.get()),
            stab=video and self.v_stab.get(),
            interp=video and self.v_interp.get(),
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
        path = filedialog.askopenfilename(filetypes=[("Foto ou vídeo", exts), ("Todos", "*.*")])
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            frame, kind = engine.read_first_frame(path)
        except Exception as e:
            messagebox.showerror("Arquivo inválido", str(e))
            return
        self.src, self.kind, self.first = path, kind, frame
        self.btn_prev.config(state="normal")
        self.btn_go.config(state="normal")
        self.center = None
        self.prev = None
        self.box = None
        h, w = frame.shape[:2]
        self.lbl_file.config(text=f"{os.path.basename(path)} — {w}×{h} — "
                                  f"{'vídeo' if kind == 'video' else 'imagem'}")
        self._hint()
        self.view.delete("all")
        self.view.create_text(self.view.winfo_width() // 2, self.view.winfo_height() // 2,
                              fill="#9ba6b8",
                              text="Preparando prévia…", justify="center",
                              font=("Segoe UI", 12))
        self.preview()

    # ----------------------------------------------------------- prévia
    def preview(self):
        if self.busy or self.first is None:
            return
        s = self.settings()
        self.preview_id += 1
        preview_id = self.preview_id
        frame = self.first.copy()
        center = self.center
        self.status.config(text="Gerando prévia…")
        self.status_detail.config(text="A prévia básica é rápida; a IA pode levar mais tempo.")
        self._busy(True)
        threading.Thread(
            target=self._preview_job,
            args=(s, preview_id, frame, center),
            daemon=True,
        ).start()

    def _preview_job(self, s, preview_id, frame, center):
        succeeded = False
        try:
            before, after, box = engine.make_preview(frame, s, None, center, PV)
            self.q.put(("preview", (preview_id, before, after, box)))
            succeeded = True
        except Exception as e:
            traceback.print_exc()
            self.q.put(("err", str(e)))
        finally:
            self.q.put(("idle", None))
        if succeeded and (s.face or (s.use_ai and s.upscale)):
            threading.Thread(
                target=self._ai_preview_job,
                args=(s, preview_id, frame, center),
                daemon=True,
            ).start()

    def _ai_preview_job(self, s, preview_id, frame, center):
        try:
            self.q.put(("log", "Prévia básica pronta; carregando modelos de IA…"))
            ai = self._get_ai(s)
            if ai and ((s.face and ai.can_face)
                       or (s.use_ai and s.upscale and ai.can_upscale)):
                before, after, box = engine.make_preview(frame, s, ai, center, PV)
                self.q.put(("preview", (preview_id, before, after, box)))
        except Exception as e:
            traceback.print_exc()
            self.q.put(("log", f"Prévia básica mantida; falha ao aplicar IA: {e}"))
        finally:
            self.q.put(("stage_done", None))

    def _on_split(self, e):
        if not self._display_rect:
            return
        display_x, size = self._display_rect[0], self._display_rect[2]
        self.split = min(max((e.x - display_x) / size, 0.0), 1.0)
        self._compose()

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
            messagebox.showinfo("Lumina Studio", "Abra um arquivo primeiro.")
            return
        s = self.settings()
        base, ext = os.path.splitext(os.path.basename(self.src))
        if self.kind == "video":
            dst = filedialog.asksaveasfilename(initialfile=f"{base}_lumina.mp4",
                                               defaultextension=".mp4",
                                               filetypes=[("MP4", "*.mp4")])
        else:
            ext = ext.lower() if ext.lower() in IMAGE_EXT else ".png"
            dst = filedialog.asksaveasfilename(initialfile=f"{base}_lumina{ext}",
                                               defaultextension=ext,
                                               filetypes=[("Imagem", "*" + ext)])
        if not dst:
            return
        if os.path.normcase(os.path.abspath(dst)) == os.path.normcase(os.path.abspath(self.src)):
            messagebox.showerror(
                "Destino inválido",
                "Escolha um arquivo de saída diferente do arquivo original.",
            )
            return
        self.cancel.clear()
        self._busy(True, cancellable=self.kind == "video")
        threading.Thread(target=self._job, args=(s, dst), daemon=True).start()

    def _job(self, s, dst):
        try:
            if self.kind == "image" and (s.face or (s.use_ai and s.upscale)):
                self.q.put(("stage", "Salvando imagem editada…"))
                engine.process_image(self.src, dst, s, None)
                self.q.put(("log", "Imagem salva; carregando IA para aprimoramento…"))
                ai = self._get_ai(s)
                if ai and ((s.face and ai.can_face)
                           or (s.use_ai and s.upscale and ai.can_upscale)):
                    self.q.put(("stage", "Aplicando aprimoramento de IA…"))
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
                        if os.path.exists(ai_dst):
                            os.remove(ai_dst)
                        traceback.print_exc()
                        self.q.put(("log", f"IA falhou; imagem editada mantida. Erro: {e}"))
            elif self.kind == "image":
                self.q.put(("stage", "Processando e salvando imagem…"))
                engine.process_image(self.src, dst, s, None)
            else:
                self.q.put(("stage", "Carregando modelos de IA…"
                            if s.face or (s.use_ai and s.upscale) else "Preparando vídeo…"))
                ai = self._get_ai(s)
                self.q.put(("stage", "Processando vídeo…"))
                engine.process_video(self.src, dst, s, ai,
                                     progress=lambda p: self.q.put(("prog", p)),
                                     cancel=self.cancel)
            self.q.put(("done", (dst, self.cancel.is_set())))
        except Exception as e:
            traceback.print_exc()
            self.q.put(("err", str(e)))
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
                self.ai_key = ai_key
                self.q.put(("stage", "Preparando modelos de IA…"))
                try:
                    self.ai = engine.load_ai(
                        s.anime,
                        log=lambda m: self.q.put(("log", m)),
                        progress=lambda name, done, total: self.q.put(
                            ("download", (name, done, total))),
                        load_upscaler=load_upscaler,
                        load_face=load_face,
                    )
                except Exception as e:
                    self.q.put(("log", f"IA indisponível; usando processamento clássico. Erro: {e}"))
                    return None
                summary = self.ai.summary()
                self.q.put(("log", summary))
                if not self.ai.can_upscale and not self.ai.can_face:
                    self.q.put(("log", f"{summary} — usando processamento clássico."))
        return self.ai

    # ----------------------------------------------------------- fila da interface
    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.status.config(text=val)
                    self.status_detail.config(text="")
                elif kind == "stage":
                    self.status.config(text=val)
                    self.status_detail.config(text="O aplicativo está trabalhando; você pode acompanhar o progresso acima.")
                    self.pb.stop()
                    self.pb.configure(mode="indeterminate")
                    self.pb.start(12)
                elif kind == "stage_done":
                    if not self.busy:
                        self.pb.stop()
                        self.pb.configure(mode="determinate")
                        self.pb["value"] = 0
                        self.status_detail.config(text="")
                elif kind == "download":
                    name, done, total = val
                    if total > 0:
                        self.pb.stop()
                        self.pb.configure(mode="determinate")
                        self.pb["value"] = min(done / total * 100, 100)
                        percent = min(done / total * 100, 100)
                        self.status.config(text=f"Baixando modelo: {name}")
                        self.status_detail.config(
                            text=f"{percent:.0f}%  ·  {self._format_bytes(done)} de {self._format_bytes(total)}")
                    else:
                        self.pb.configure(mode="indeterminate")
                        self.pb.start(12)
                        self.status.config(text=f"Baixando modelo: {name}")
                        self.status_detail.config(text=f"{self._format_bytes(done)} recebidos")
                elif kind == "prog":
                    self.pb.stop()
                    self.pb.configure(mode="determinate")
                    self.pb["value"] = val * 100
                    self.status.config(text=f"Processando vídeo… {val * 100:.0f}%")
                    self.status_detail.config(text="Não feche o aplicativo até o processamento terminar.")
                elif kind == "image_prog":
                    progress, stage = val
                    self.pb.stop()
                    self.pb.configure(mode="determinate")
                    self.pb["value"] = progress * 100
                    self.status.config(text=f"{stage}… {progress * 100:.0f}%")
                    self.status_detail.config(
                        text="Acompanhe o andamento do aprimoramento na barra abaixo.")
                elif kind == "preview":
                    preview_id, before, after, box = val
                    if preview_id == self.preview_id:
                        self.prev = (before, after)
                        self.box = box
                        self._compose()
                        self.status.config(text="Prévia atualizada")
                elif kind == "done":
                    dst, cancelled = val
                    msg = ("Interrompido. A parte já processada foi salva em:"
                           if cancelled else "Concluído! Arquivo salvo em:")
                    self.status.config(text="Pronto")
                    self.status_detail.config(text=f"Arquivo salvo em: {dst}")
                    self._busy(False)
                    messagebox.showinfo("Lumina Studio", f"{msg}\n{dst}")
                elif kind == "err":
                    self.status.config(text="Não foi possível concluir")
                    self.status_detail.config(text="Confira a mensagem de erro para saber como continuar.")
                    self._busy(False)
                    messagebox.showerror("Lumina Studio", val)
                elif kind == "idle":
                    self._busy(False)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    @staticmethod
    def _format_bytes(value):
        size = float(value)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}"
            size /= 1024


if __name__ == "__main__":
    App().mainloop()