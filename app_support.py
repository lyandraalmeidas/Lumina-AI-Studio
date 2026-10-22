"""Persistent preferences, translations, and bundled-resource paths."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping


LANGUAGES = ("pt_BR", "en", "es")
THEMES = ("auto", "light", "dark")
DEFAULT_LANGUAGE = "pt_BR"
DEFAULT_THEME = "auto"


@dataclass(frozen=True)
class Preferences:
    theme: str = DEFAULT_THEME
    language: str = DEFAULT_LANGUAGE


def resource_path(relative_path: str | Path, base_dir: Path | None = None) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("O caminho do recurso deve permanecer dentro do pacote.")
    if base_dir is None:
        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    else:
        base_dir = Path(base_dir)
    return base_dir / relative


def preferences_path(
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    app_data = env.get("APPDATA")
    if app_data:
        root = Path(app_data)
    elif os.name == "nt":
        root = (Path.home() if home is None else home) / "AppData" / "Roaming"
    elif env.get("XDG_CONFIG_HOME"):
        root = Path(env["XDG_CONFIG_HOME"])
    else:
        root = (Path.home() if home is None else home) / ".config"
    return root / "LuminaStudio" / "preferences.json"


def load_preferences(path: Path | None = None) -> tuple[Preferences, str | None]:
    target = preferences_path() if path is None else path
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Preferences(), None
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return Preferences(), str(error)

    if not isinstance(payload, dict):
        return Preferences(), "O arquivo de preferências precisa conter um objeto JSON."
    theme = payload.get("theme", DEFAULT_THEME)
    language = payload.get("language", DEFAULT_LANGUAGE)
    if theme not in THEMES or language not in LANGUAGES:
        return Preferences(), "O arquivo contém uma aparência ou idioma não suportado."
    return Preferences(theme=theme, language=language), None


def save_preferences(preferences: Preferences, path: Path | None = None) -> None:
    target = preferences_path() if path is None else path
    if preferences.theme not in THEMES or preferences.language not in LANGUAGES:
        raise ValueError("A aparência ou o idioma selecionado não é suportado.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(asdict(preferences), temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
    except OSError:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Chave de tradução duplicada: {key}")
        result[key] = value
    return result


def load_catalogs(directory: Path | None = None) -> dict[str, dict[str, str]]:
    root = resource_path("locales") if directory is None else directory
    catalogs: dict[str, dict[str, str]] = {}
    for language in LANGUAGES:
        path = root / f"{language}.json"
        try:
            with path.open(encoding="utf-8") as source:
                catalog = json.load(source, object_pairs_hook=_unique_object)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise RuntimeError(
                f"Não foi possível carregar as traduções em '{path}': {error}"
            ) from error
        if not isinstance(catalog, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in catalog.items()
        ):
            raise ValueError(f"Catálogo de tradução inválido: {path}")
        catalogs[language] = catalog
    return catalogs


def resolve_theme(theme: str, system_theme: str = "light") -> str:
    if theme not in THEMES:
        raise ValueError(f"Aparência não suportada: {theme}")
    if system_theme not in ("light", "dark"):
        raise ValueError(f"Aparência do sistema não suportada: {system_theme}")
    return system_theme if theme == "auto" else theme


def system_theme() -> str:
    if sys.platform != "win32":
        return "light"
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        return "light"
    return "light" if value else "dark"


class Translator:
    def __init__(
        self,
        catalogs: Mapping[str, Mapping[str, str]],
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        if language not in LANGUAGES:
            raise ValueError(f"Idioma não suportado: {language}")
        self.catalogs = catalogs
        self.language = language

    def set_language(self, language: str) -> None:
        if language not in LANGUAGES:
            raise ValueError(f"Idioma não suportado: {language}")
        self.language = language

    def __call__(self, key: str, **values: object) -> str:
        text = self.catalogs.get(self.language, {}).get(key)
        if text is None:
            text = self.catalogs[DEFAULT_LANGUAGE].get(key)
        if text is None:
            raise KeyError(f"Chave de tradução não encontrada: {key}")
        return text.format(**values) if values else text


def format_number(value: float, language: str, decimals: int = 1) -> str:
    formatted = f"{value:,.{decimals}f}"
    if language == "en":
        return formatted
    if language not in ("pt_BR", "es"):
        raise ValueError(f"Idioma não suportado: {language}")
    return formatted.replace(",", "\0").replace(".", ",").replace("\0", ".")


def format_bytes(value: int | float, language: str) -> str:
    size = float(value)
    units = ("B", "KB", "MB", "GB")
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    return f"{format_number(size, language)} {units[unit_index]}"
