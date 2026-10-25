import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from timescreen.db import UsageDB, active_minutes, day_bounds, hourly_minutes
from timescreen.logger import IDLE_AFTER, Logger

DAY = date(2026, 3, 10)  # un giorno senza cambio d'ora
T0 = datetime(2026, 3, 10, 9, 0).timestamp()

CODE = ("Visual Studio Code", "app", "code.exe")
YT = ("YouTube", "sito", "chrome.exe")


class FakeWorld:
    """Orologio, finestra in primo piano e inattività finti, comandati dal test."""

    def __init__(self):
        self.now = T0
        self.target = None
        self.idle_for = 0.0

    def clock(self):
        return self.now

    def sample(self):
        return self.target

    def idle(self):
        return self.idle_for


class LoggerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = UsageDB(Path(self.tmp.name) / "usage.db")
        self.w = FakeWorld()
        self.logger = Logger(self.db, clock=self.w.clock, sample=self.w.sample, idle=self.w.idle)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def run_for(self, seconds, step=2):
        end = self.w.now + seconds
        while self.w.now < end:
            self.logger.tick()
            self.w.now += step

    def sessions(self):
        return [(n, round(s - T0), round(e - T0)) for n, _k, s, e in self.db.sessions_between(*day_bounds(DAY))]

    def test_switching_apps_creates_sessions(self):
        self.w.target = CODE
        self.run_for(600)
        self.w.target = YT
        self.run_for(300)
        self.logger.stop()
        self.assertEqual(self.sessions(), [("Visual Studio Code", 0, 600), ("YouTube", 600, 900)])

    def test_quick_alt_tab_is_dropped(self):
        self.w.target = CODE
        self.run_for(60)
        self.w.target = YT
        self.run_for(2)
        self.w.target = CODE
        self.run_for(60)
        self.logger.stop()
        names = [s[0] for s in self.sessions()]
        self.assertNotIn("YouTube", names)

    def test_idle_ends_session_when_input_stopped(self):
        self.w.target = CODE
        self.run_for(300)
        # nessun input da 2 minuti e mezzo: il periodo finisce quando hai smesso di toccare il PC
        self.w.idle_for = IDLE_AFTER + 30
        self.run_for(10)
        self.assertEqual(self.sessions(), [("Visual Studio Code", 0, 300 - IDLE_AFTER - 30)])

    def test_sleep_gap_closes_at_last_check(self):
        self.w.target = CODE
        self.run_for(100)
        self.w.now += 3600  # il PC dorme un'ora
        self.run_for(20)
        self.logger.stop()
        first, second = self.sessions()
        self.assertEqual(first[2], 98)
        self.assertEqual(second[1], 100 + 3600)

    def test_crash_keeps_recent_progress(self):
        self.w.target = CODE
        self.run_for(95)
        # niente stop(): il periodo è stato aggiornato almeno ogni 30 secondi
        (_name, start, end), = self.sessions()
        self.assertGreaterEqual(end - start, 60)


class HourlyTest(unittest.TestCase):
    def test_session_split_across_hours(self):
        start = datetime(2026, 3, 10, 9, 40).timestamp()
        end = datetime(2026, 3, 10, 10, 20).timestamp()
        hours = hourly_minutes([("Code", "app", start, end)], DAY)["Code"]
        self.assertAlmostEqual(hours[9], 20)
        self.assertAlmostEqual(hours[10], 20)

    def test_overlaps_count_once_in_active_time(self):
        s = datetime(2026, 3, 10, 21, 0).timestamp()
        sessions = [
            ("Counter-Strike 2", "app", s, s + 40 * 60),
            ("Discord", "app", s + 20 * 60, s + 50 * 60),
        ]
        self.assertAlmostEqual(active_minutes(sessions, DAY)[21], 50)


if __name__ == "__main__":
    unittest.main()
