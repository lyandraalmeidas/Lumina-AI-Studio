"""Motor do Lumina Studio: restauração clássica + IA, saída de vídeo com áudio."""
import os
import shutil
import subprocess
from dataclasses import dataclass

import cv2
import numpy as np

VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
FILTERS = ("original", "vivid", "warm", "cool", "noir", "vintage", "fade")
FILTER_TRANSFORMS = {
    "vivid": np.array(
        ((1.16, -0.08, -0.08, 0), (-0.08, 1.16, -0.08, 0),
         (-0.08, -0.08, 1.16, 0)), dtype=np.float32),
    "warm": np.array(
        ((0.90, 0, 0, 0), (0, 1.02, 0, 2), (0, 0, 1.08, 8)),
        dtype=np.float32),
    "cool": np.array(
        ((1.08, 0, 0, 8), (0, 1.02, 0, 2), (0, 0, 0.90, 0)),
        dtype=np.float32),
    "noir": np.array(
        ((0.114, 0.587, 0.299, 0), (0.114, 0.587, 0.299, 0),
         (0.114, 0.587, 0.299, 0)), dtype=np.float32),
    "vintage": np.array(
        ((0.131, 0.534, 0.272, 0), (0.168, 0.686, 0.349, 0),
         (0.189, 0.769, 0.393, 0)), dtype=np.float32),
    "fade": np.array(
        ((0.82, 0, 0, 24), (0, 0.82, 0, 24), (0, 0, 0.82, 24)),
        dtype=np.float32),
}


@dataclass
class Settings:
    denoise: int = 40        # 0-100, redução de ruído clássica
    color: bool = True       # correção automática de cor
    face: bool = True        # restauração de rostos (IA)
    upscale: bool = True     # ampliar até target_h
    use_ai: bool = True      # upscaling por IA (senão Lanczos)
    anime: bool = False      # modelo para anime e desenhos
    fast_cpu: bool = False   # acelera IA em CPU com possível perda de detalhes
    target_h: int = 2160
    sharpen: int = 30        # 0-100
    stab: bool = False       # estabilização de câmera (vídeo)
    interp: bool = False     # dobra o fps (vídeo)
    fast_video: bool = True
    filter_name: str = "original"


def out_size(w, h, target_h):
    """Tamanho de saída com proporção mantida e dimensões pares."""
    if h >= target_h:
        oh, ow = h, w
    else:
        oh = target_h
        ow = round(w * target_h / h)
    return ow - ow % 2, oh - oh % 2


# ------------------------------------------------------------ clássico
def denoise(img, amount, fast=False):
    if amount <= 0:
        return img
    a = amount / 100.0
    smooth = cv2.bilateralFilter(img, 3 if fast else 7, 20 + 60 * a, 3 if fast else 7)
    return cv2.addWeighted(img, 1 - 0.7 * a, smooth, 0.7 * a, 0)


def apply_filter(img, filter_name):
    if filter_name not in FILTERS:
        raise ValueError(f"Filtro não suportado: {filter_name}")
    if filter_name == "original":
        return img

    return cv2.transform(img, FILTER_TRANSFORMS[filter_name])


def color_fix(img):
    f = img.astype(np.float32)
    means = f.reshape(-1, 3).mean(axis=0) + 1e-3
    f *= means.mean() / means                      # balanço de branco (gray-world)
    bal = np.clip(f, 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(bal, cv2.COLOR_BGR2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[..., 0])
    fixed = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return cv2.addWeighted(img, 0.4, fixed, 0.6, 0)


def sharpen(img, amount):
    if amount <= 0:
        return img
    a = amount / 100.0 * 0.8
    blur = cv2.GaussianBlur(img, (0, 0), 1.5)
    return cv2.addWeighted(img, 1 + a, blur, -a, 0)


def shift(img, t):
    h, w = img.shape[:2]
    M = np.float32([[1, 0, t[0]], [0, 1, t[1]]])
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)


def trajectory_corrections(path, radius=20):
    """Estima o movimento da câmera e devolve a correção a aplicar em cada quadro."""
    cap = cv2.VideoCapture(path)
    x = y = 0.0
    traj, prev = [], None
    if not cap.isOpened():
        cap.release()
        raise ValueError("Não foi possível abrir o vídeo.")
    try:
        ok, f = cap.read()
        while ok:
            g = cv2.cvtColor(
                cv2.resize(f, None, fx=0.5, fy=0.5),
                cv2.COLOR_BGR2GRAY,
            ).astype(np.float32)
            if prev is not None:
                (dx, dy), _ = cv2.phaseCorrelate(prev, g)
                x += dx * 2
                y += dy * 2
            traj.append((x, y))
            prev = g
            ok, f = cap.read()
    finally:
        cap.release()
    if not traj:
        return None
    traj = np.array(traj)
    k = np.ones(2 * radius + 1) / (2 * radius + 1)
    smooth = np.stack([np.convolve(np.pad(traj[:, c], radius, mode="edge"), k, mode="valid")
                       for c in range(2)], axis=1)
    return smooth - traj


def interpolate(a, b):
    """Quadro intermediário com fluxo óptico calculado em resolução reduzida."""
    h, w = a.shape[:2]
    sm = 0.5 if w * h > 1280 * 720 else 1.0
    ga = cv2.cvtColor(cv2.resize(a, (int(w * sm), int(h * sm))), cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(cv2.resize(b, (int(w * sm), int(h * sm))), cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 4, 21, 3, 5, 1.1, 0)
    flow = cv2.resize(flow, (w, h)) / sm
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    fx, fy = flow[..., 0], flow[..., 1]
    wa = cv2.remap(a, gx - 0.5 * fx, gy - 0.5 * fy, cv2.INTER_LINEAR)
    wb = cv2.remap(b, gx + 0.5 * fx, gy + 0.5 * fy, cv2.INTER_LINEAR)
    return cv2.addWeighted(wa, 0.5, wb, 0.5, 0)


# ------------------------------------------------------------ pipeline
def restore(img, s, ai=None, t=None, progress=None, video=False):
    """Ordem fixa: ruído → filtro → cor → estabilização → IA → ampliação → nitidez."""
    f = denoise(img, s.denoise, fast=video and s.fast_video)
    f = apply_filter(f, s.filter_name)
    if s.color:
        f = color_fix(f)
    if t is not None:
        f = shift(f, t)
    if progress:
        progress(0.15, "Preparando imagem")
    if ai is not None and s.face and ai.can_face:
        if progress:
            progress(0.2, "Restaurando rostos")
        f = ai.restore_faces(f)
        if progress:
            progress(0.4, "Rostos restaurados")
    if s.upscale:
        h, w = f.shape[:2]
        ow, oh = out_size(w, h, s.target_h)
        if (ow, oh) != (w, h):
            if ai is not None and s.use_ai and ai.can_upscale:
                if progress:
                    progress(0.42, "Aplicando upscaling com IA")
                f = ai.upscale(
                    f, oh / h, fast_cpu=s.fast_cpu,
                    progress=(lambda p: progress(
                        0.42 + 0.48 * p, "Aplicando upscaling com IA",
                    )) if progress else None,
                )
            if f.shape[:2] != (oh, ow):
                f = cv2.resize(f, (ow, oh), interpolation=cv2.INTER_LANCZOS4)
            if progress:
                progress(0.92, "Finalizando resolução")
    if progress:
        progress(0.96, "Aplicando nitidez")
    f = sharpen(f, s.sharpen)
    if progress:
        progress(0.99, "Salvando resultado")
    return f


def make_preview(img, s, ai, center=None, pv=640, cs=256, video=False):
    """Processa um recorte central (ou escolhido) para a prévia rápida."""
    h, w = img.shape[:2]
    cs = min(cs, h, w)
    cx, cy = center if center else (w // 2, h // 2)
    x0 = int(np.clip(cx - cs // 2, 0, w - cs))
    y0 = int(np.clip(cy - cs // 2, 0, h - cs))
    crop = img[y0:y0 + cs, x0:x0 + cs].copy()
    after = restore(crop, s, ai, video=video)
    before = cv2.resize(crop, (pv, pv), interpolation=cv2.INTER_CUBIC)
    after = cv2.resize(after, (pv, pv), interpolation=cv2.INTER_AREA)
    return before, after, (x0, y0, cs)


# ------------------------------------------------------------ arquivos
def read_image(path):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Não foi possível ler a imagem.")
    return img


def write_image(path, img):
    ext = os.path.splitext(path)[1].lower() or ".png"
    params = [cv2.IMWRITE_JPEG_QUALITY, 97] if ext in (".jpg", ".jpeg") else []
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        raise ValueError("Falha ao codificar a imagem.")
    buf.tofile(path)


def read_first_frame(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXT:
        cap = cv2.VideoCapture(path)
        ok, f = cap.read()
        cap.release()
        if not ok:
            raise ValueError("Não foi possível abrir este vídeo.")
        return f, "video"
    if ext in IMAGE_EXT:
        return read_image(path), "image"
    raise ValueError("Formato não suportado. Use MP4, MOV, MKV, WEBM, JPG, PNG, WEBP etc.")


def find_ffmpeg():
    try:
        import imageio_ffmpeg
    except ImportError:
        return shutil.which("ffmpeg")
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (OSError, RuntimeError):
        return shutil.which("ffmpeg")


class VideoOut:
    """Grava quadros via FFmpeg (H.264 + áudio original); usa OpenCV se o FFmpeg faltar."""

    def __init__(self, dst, size, fps, src):
        self.w, self.h = size
        self.proc = None
        self.writer = None
        ff = find_ffmpeg()
        if ff:
            cmd = [ff, "-y", "-loglevel", "error",
                   "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{self.w}x{self.h}",
                   "-r", f"{fps:.4f}", "-i", "-",
                   "-i", src, "-map", "0:v:0", "-map", "1:a?",
                   "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "192k", "-shortest", dst]
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            self.writer = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"mp4v"), fps, (self.w, self.h))
            if not self.writer.isOpened():
                raise RuntimeError("Não foi possível criar o arquivo de vídeo.")

    def write(self, img):
        if self.proc:
            try:
                frame = np.ascontiguousarray(img)
                self.proc.stdin.write(memoryview(frame).cast("B"))
            except BrokenPipeError:
                raise RuntimeError("O FFmpeg encerrou inesperadamente.")
        else:
            self.writer.write(img)

    def close(self, abort=False):
        if self.proc:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            err = self.proc.stderr.read().decode("utf-8", "ignore")
            self.proc.wait()
            if self.proc.returncode and not abort:
                raise RuntimeError("FFmpeg falhou:\n" + err[-600:])
        elif self.writer:
            self.writer.release()


# ------------------------------------------------------------ processos
def process_image(src, dst, s, ai=None, progress=None):
    write_image(dst, restore(read_image(src), s, ai, progress=progress))
    if progress:
        progress(1.0, "Aprimoramento concluído")


def process_video(src, dst, s, ai, progress, cancel):
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        cap.release()
        raise ValueError("Não foi possível abrir o vídeo.")
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if w < 1 or h < 1:
        cap.release()
        raise ValueError("Não foi possível abrir o vídeo.")
    if not np.isfinite(fps) or fps <= 0:
        fps = 30.0

    ow, oh = out_size(w, h, s.target_h) if s.upscale else (w - w % 2, h - h % 2)
    out_fps = fps * 2 if s.interp else fps
    if s.stab:
        cap.release()
        corr = trajectory_corrections(src)
        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            cap.release()
            raise ValueError("Não foi possível abrir o vídeo.")
    else:
        corr = None
    out = None
    prev, i = None, 0
    try:
        out = VideoOut(dst, (ow, oh), out_fps, src)
        ok, f = cap.read()
        while ok and not cancel.is_set():
            t = corr[i] if corr is not None and i < len(corr) else None
            cur = restore(f, s, ai, t, video=True)[:oh, :ow]
            if s.interp and prev is not None:
                out.write(interpolate(prev, cur))
            out.write(cur)
            prev = cur
            i += 1
            if total > 0:
                progress(min(i / total, 1.0))
            ok, f = cap.read()
    except BaseException:
        if out is not None:
            out.close(abort=True)
        raise
    finally:
        cap.release()
    if out is not None:
        out.close(abort=cancel.is_set())


def load_ai(anime, log=print, progress=None, load_upscaler=True, load_face=True):
    import ai
    return ai.AIEngine(anime=anime, log=log, progress=progress,
                       load_upscaler=load_upscaler, load_face=load_face)