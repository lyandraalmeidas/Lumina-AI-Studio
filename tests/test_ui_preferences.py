import unittest
from unittest.mock import patch

from app_support import LANGUAGES, THEMES, Preferences, load_catalogs
import engine
from main import App


class InterfacePreferenceTests(unittest.TestCase):
    @patch("main.save_preferences")
    @patch("main.load_preferences", return_value=(Preferences(), None))
    def test_language_and_theme_changes_preserve_editing_state(
        self, _load_preferences, save_preferences_mock
    ):
        app = App()
        app.withdraw()
        try:
            app.v_denoise.set(73)
            app.v_sharp.set(61)
            app.v_face.set(False)
            app.v_color.set(False)
            app.cmb_filter.current(engine.FILTERS.index("vintage"))
            app.split = 0.27

            app.cmb_theme.current(THEMES.index("dark"))
            app._on_theme_selected()
            app.cmb_theme.current(THEMES.index("light"))
            app._on_theme_selected()
            self.assertEqual(app.preferences.theme, "light")
            self.assertEqual(app.theme, "light")
            self.assertEqual(app.v_denoise.get(), 73)
            self.assertEqual(app.v_sharp.get(), 61)
            self.assertFalse(app.v_face.get())
            self.assertFalse(app.v_color.get())
            self.assertEqual(
                app.cmb_filter.current(), engine.FILTERS.index("vintage"))
            self.assertEqual(app.split, 0.27)

            catalogs = load_catalogs()
            for index, language in enumerate(LANGUAGES):
                app.cmb_language.current(index)
                app._on_language_selected()
                self.assertEqual(app.lbl_preview.cget("text"),
                                 catalogs[language]["preview.title"])
                self.assertEqual(app.lbl_title.cget("text"),
                                 catalogs[language]["app.title"])

            self.assertEqual(app.v_denoise.get(), 73)
            self.assertEqual(app.v_sharp.get(), 61)
            self.assertFalse(app.v_face.get())
            self.assertFalse(app.v_color.get())
            self.assertEqual(
                app.cmb_filter.current(), engine.FILTERS.index("vintage"))
            self.assertEqual(app.split, 0.27)
            self.assertEqual(save_preferences_mock.call_count, len(LANGUAGES) + 2)
        finally:
            app._destroy_app()

    @patch("main.engine.make_preview", return_value=(None, None, None))
    @patch.object(App, "_get_ai")
    def test_video_preview_does_not_load_ai_models(
        self, get_ai_mock, _make_preview_mock
    ):
        app = App()
        app.withdraw()
        try:
            app._preview_job(engine.Settings(), 1, object(), None, True)
            get_ai_mock.assert_not_called()
            self.assertEqual(app.q.get_nowait()[0], "preview")
            self.assertEqual(app.q.get_nowait()[0], "idle")
        finally:
            app._destroy_app()

    @patch("main.system_theme", return_value="dark")
    @patch("main.save_preferences")
    @patch("main.load_preferences", return_value=(Preferences(theme="auto"), None))
    def test_automatic_theme_tracks_system_changes(
        self, _load_preferences, _save_preferences, system_theme_mock
    ):
        app = App()
        app.withdraw()
        try:
            self.assertEqual(app.theme, "dark")
            if app._auto_theme_job is not None:
                app.after_cancel(app._auto_theme_job)
            system_theme_mock.return_value = "light"
            app._schedule_auto_theme_check()
            self.assertEqual(app.theme, "light")
        finally:
            app._destroy_app()


if __name__ == "__main__":
    unittest.main()
