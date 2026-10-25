import os
import tempfile
import unittest
import winreg
from pathlib import Path
from unittest import mock

from timescreen import autostart, control

TEST_ROOT = r"Software\TimeScreenTest"


def _delete_tree(path: str) -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_tree(f"{path}\\{child}")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass


class AutostartTest(unittest.TestCase):
    """Usa chiavi di registro di prova: le vere voci di avvio non vengono toccate."""

    def setUp(self):
        self.run_key = TEST_ROOT + r"\Run"
        self.approved_key = TEST_ROOT + r"\StartupApproved\Run"
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.run_key).Close()
        patches = [
            mock.patch.object(autostart, "RUN_KEY", self.run_key),
            mock.patch.object(autostart, "APPROVED_KEY", self.approved_key),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(_delete_tree, TEST_ROOT)

    def set_windows_flag(self, first_byte: int):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.approved_key) as key:
            winreg.SetValueEx(key, autostart.VALUE_NAME, 0, winreg.REG_BINARY, bytes([first_byte]) + b"\x00" * 11)

    def test_enable_and_disable(self):
        self.assertFalse(autostart.is_enabled())
        autostart.enable()
        self.assertTrue(autostart.is_enabled())
        self.assertIn("timescreen", autostart.current().lower())
        self.assertTrue(autostart.disable())
        self.assertFalse(autostart.is_enabled())

    def test_turned_off_in_windows_settings(self):
        autostart.enable()
        self.set_windows_flag(0x03)  # come fa Windows quando la spegni da Impostazioni → App → Avvio
        self.assertFalse(autostart.is_enabled())
        # riattivarla da TimeScreen la riaccende anche per Windows
        autostart.enable()
        self.assertTrue(autostart.is_enabled())

    def test_old_value_name_is_replaced(self):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.run_key) as key:
            winreg.SetValueEx(key, "TimeScreen Logger", 0, winreg.REG_SZ, "vecchio comando")
        self.assertTrue(autostart.is_enabled())
        autostart.enable()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.run_key) as key:
            names = {winreg.EnumValue(key, i)[0] for i in range(winreg.QueryInfoKey(key)[1])}
        self.assertEqual(names, {autostart.VALUE_NAME})


class ControlTest(unittest.TestCase):
    """Pausa e stato chiesti alla finestra nascosta del logger, come fa l'interfaccia."""

    @classmethod
    def setUpClass(cls):
        from timescreen.db import UsageDB
        from timescreen.logger import Logger
        from timescreen.tray import TrayApp

        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict(os.environ, {"TIMESCREEN_DB": str(Path(cls.tmp.name) / "usage.db")})
        cls.env.start()
        cls.db = UsageDB()
        # la finestra nasce senza icona: l'icona compare solo con run()
        cls.app = TrayApp(Logger(cls.db, sample=lambda: None, idle=lambda: 0.0), interval=60)

    @classmethod
    def tearDownClass(cls):
        from timescreen.tray import user32

        user32.DestroyWindow(cls.app.hwnd)
        cls.db.close()
        cls.env.stop()
        cls.tmp.cleanup()

    def test_pause_and_resume(self):
        self.assertEqual(control.status(), "running")
        self.assertEqual(control.set_paused(True), "paused")
        self.assertTrue(self.app.paused)
        self.assertEqual(control.status(), "paused")
        self.assertEqual(control.set_paused(False), "running")
        self.assertFalse(self.app.paused)

    def test_other_database_sees_no_logger(self):
        with mock.patch.dict(os.environ, {"TIMESCREEN_DB": str(Path(self.tmp.name) / "altro.db")}):
            self.assertEqual(control.status(), "stopped")


if __name__ == "__main__":
    unittest.main()
