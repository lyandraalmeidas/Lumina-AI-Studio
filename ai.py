"""Modelos de IA: Real-ESRGAN (upscaling) e GFPGAN (restauração de rostos)."""
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "models")

WEIGHTS = {
    "x4plus": ("RealESRGAN_x4plus.pth",
               "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"),
    "anime": ("RealESRGAN_x4plus_anime_6B.pth",
              "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth"),
    "gfpgan": ("GFPGANv1.4.pth",
               "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth"),
}
DOWNLOAD_TIMEOUT = 30


def _patch_torchvision():
    """Compatibilidade: basicsr antigo importa um módulo removido em torchvision recente."""
    try:
        import torchvision.transforms.functional_tensor  # noqa: F401
    except ImportError:
        import torchvision.transforms.functional as F
        sys.modules["torchvision.transforms.functional_tensor"] = F


def _weight(key, log, progress=None):
    name, url = WEIGHTS[key]
    os.makedirs(MODELS, exist_ok=True)
    path = os.path.join(MODELS, name)
    if not os.path.exists(path):
        log(f"Baixando modelo {name} (só na primeira vez)…")
        tmp = path + ".part"
        try:
            with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
                try:
                    total = int(response.headers.get("Content-Length", 0))
                except (TypeError, ValueError):
                    total = 0
                downloaded = 0
                with open(tmp, "wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress(name, downloaded, total)
            os.replace(tmp, path)
            if progress:
                progress(name, downloaded, total or downloaded)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
    return path


class AIEngine:
    def __init__(self, anime=False, log=print, progress=None,
                 load_upscaler=True, load_face=True):
        self.errors = []
        self.can_upscale = False
        self.can_face = False
        self.log = log
        self.progress = progress
        try:
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception as e:
            self.device = "cpu"
            self.errors.append(f"PyTorch indisponível ({e})")
            return
        self.half = self.device == "cuda"
        self.tile = 512 if self.device == "cuda" else 0   # tiles economizam VRAM na GPU
        self.upsampler = None
        self.restorer = None

        if load_upscaler:
            try:
                self._load_upscaler(anime)
            except Exception as e:
                self.errors.append(f"upscaling IA: {e}")
        if load_face:
            try:
                self._load_face()
            except Exception as e:
                self.errors.append(f"rostos IA: {e}")

    def _load_upscaler(self, anime):
        _patch_torchvision()
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
        if anime:
            net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=6, num_grow_ch=32, scale=4)
            key = "anime"
        else:
            net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
            key = "x4plus"
        self.upsampler = RealESRGANer(
            scale=4, model_path=_weight(key, self.log, self.progress), model=net,
            tile=self.tile, tile_pad=10, pre_pad=0, half=self.half, device=self.device)
        self.can_upscale = True

    def _load_face(self):
        _patch_torchvision()
        from gfpgan import GFPGANer
        self.restorer = GFPGANer(
            model_path=_weight("gfpgan", self.log, self.progress), upscale=1, arch="clean",
            channel_multiplier=2, bg_upsampler=None, device=self.device)
        self.can_face = True

    def upscale(self, img, scale):
        out, _ = self.upsampler.enhance(img, outscale=scale)
        return out

    def restore_faces(self, img):
        _, _, out = self.restorer.enhance(img, has_aligned=False,
                                          only_center_face=False, paste_back=True)
        return out if out is not None else img

    def summary(self):
        parts = ["IA " + ("GPU (CUDA)" if self.device == "cuda" else "CPU")]
        parts.append("upscaling OK" if self.can_upscale else "upscaling OFF")
        parts.append("rostos OK" if self.can_face else "rostos OFF")
        if self.errors:
            parts.append("avisos: " + "; ".join(self.errors))
        return " · ".join(parts)