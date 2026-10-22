import ast
import re
import tempfile
import unittest
from pathlib import Path
from string import Formatter

from app_support import (
    LANGUAGES,
    Preferences,
    Translator,
    format_bytes,
    format_number,
    load_catalogs,
    load_preferences,
    preferences_path,
    resolve_theme,
    resource_path,
    save_preferences,
)


ROOT = Path(__file__).resolve().parents[1]
KEY_PREFIX = re.compile(
    r"^(?:app|action|media|preview|preferences|theme|language|section|"
    r"option|model|output|status|hint|dialog|engine|stage)\."
)


class AppSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalogs = load_catalogs(ROOT / "locales")

    def test_locale_keys_match_and_are_used(self):
        key_sets = [set(catalog) for catalog in self.catalogs.values()]
        self.assertTrue(all(keys == key_sets[0] for keys in key_sets[1:]))

        source = (ROOT / "main.py").read_text(encoding="utf-8")
        constants = {
            node.value for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and KEY_PREFIX.match(node.value)
            and not node.value.endswith(".")
        }
        constants.update(f"theme.{theme}" for theme in ("auto", "light", "dark"))
        constants.update(f"language.{language}" for language in LANGUAGES)

        keys = key_sets[0]
        self.assertEqual(constants - keys, set(), "Missing translation keys")
        self.assertEqual(keys - constants, set(), "Unused translation keys")

    def test_translation_placeholders_match(self):
        for key in self.catalogs["pt_BR"]:
            placeholders = []
            for language in LANGUAGES:
                text = self.catalogs[language][key]
                placeholders.append({
                    field_name for _, field_name, _, _ in Formatter().parse(text)
                    if field_name
                })
            self.assertTrue(
                all(fields == placeholders[0] for fields in placeholders[1:]),
                f"Placeholder mismatch for {key}",
            )

    def test_duplicate_translation_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pt_BR.json").write_text(
                '{"app.title":"Lumina","app.title":"Duplicate"}', encoding="utf-8")
            for language in ("en", "es"):
                (root / f"{language}.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "duplicada"):
                load_catalogs(root)

    def test_missing_translation_falls_back_to_portuguese(self):
        catalogs = {language: dict(value) for language, value in self.catalogs.items()}
        del catalogs["en"]["app.subtitle"]
        translator = Translator(catalogs, "en")
        self.assertEqual(
            translator("app.subtitle"), self.catalogs["pt_BR"]["app.subtitle"])
        with self.assertRaises(KeyError):
            translator("missing.key")

    def test_preferences_round_trip_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "LuminaStudio" / "preferences.json"
            chosen = Preferences(theme="dark", language="es")
            save_preferences(chosen, path)
            self.assertEqual(load_preferences(path), (chosen, None))
            path.write_text("{broken", encoding="utf-8")
            restored, warning = load_preferences(path)
            self.assertEqual(restored, Preferences())
            self.assertIsNotNone(warning)

    def test_preferences_use_a_persistent_user_directory(self):
        result = preferences_path(
            environ={"APPDATA": r"C:\Users\user\AppData\Roaming"},
            home=Path("C:/home"),
        )
        self.assertEqual(
            result,
            Path(r"C:\Users\user\AppData\Roaming")
            / "LuminaStudio" / "preferences.json",
        )

    def test_resource_paths_are_bounded_and_app_relative(self):
        root = Path("C:/app")
        relative = Path("locales") / "en.json"
        self.assertEqual(resource_path(relative, root), root / relative)
        self.assertEqual(resource_path("locales"), ROOT / "locales")
        with self.assertRaises(ValueError):
            resource_path("../outside.txt", root)

    def test_theme_resolution(self):
        self.assertEqual(resolve_theme("auto", "dark"), "dark")
        self.assertEqual(resolve_theme("auto", "light"), "light")
        self.assertEqual(resolve_theme("light", "dark"), "light")
        with self.assertRaises(ValueError):
            resolve_theme("sepia")

    def test_number_and_byte_formatting_follow_the_selected_language(self):
        self.assertEqual(format_number(1234.5, "en"), "1,234.5")
        self.assertEqual(format_number(1234.5, "pt_BR"), "1.234,5")
        self.assertEqual(format_number(1234.5, "es"), "1.234,5")
        self.assertEqual(format_bytes(1536, "en"), "1.5 KB")
        self.assertEqual(format_bytes(1536, "pt_BR"), "1,5 KB")

    def test_application_icon_contains_windows_sizes(self):
        from PIL import Image

        with Image.open(ROOT / "assets" / "lumina.ico") as icon:
            self.assertIn((256, 256), icon.ico.sizes())
            self.assertIn((16, 16), icon.ico.sizes())


if __name__ == "__main__":
    unittest.main()
