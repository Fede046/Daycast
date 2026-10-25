import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from timescreen.db import UsageDB
from timescreen.real_data import RealSource

CATS = [{"id": "c1", "name": "Lavoro", "slot": 1}, {"id": "c2", "name": "Giochi", "slot": 4}]
ASSIGN = {"Visual Studio Code": "c1", "Counter-Strike 2": "c2"}

# martedì 3, 10, 17 e 24 marzo 2026: nessun cambio d'ora in mezzo
TUESDAYS = [date(2026, 3, 3) + timedelta(weeks=i) for i in range(4)]


def at(day: date, hour: int, minute: int = 0) -> float:
    return datetime(day.year, day.month, day.day, hour, minute).timestamp()


class RealDataTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "usage.db"
        self.db = UsageDB(self.path)
        self.source = RealSource(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def add(self, name, kind, start, end):
        sid = self.db.start_session(self.db.app_id(name, kind, None), start)
        self.db.extend_session(sid, end)

    def dash(self, day, now):
        return self.source.dashboard(day, now, CATS, ASSIGN)

    def test_empty_database_has_no_data(self):
        self.assertFalse(self.source.has_data())
        self.add("Visual Studio Code", "app", at(TUESDAYS[0], 9), at(TUESDAYS[0], 10))
        self.assertTrue(self.source.has_data())

    def test_forecast_is_average_of_same_weekday(self):
        # tre martedì: 60, 30 e 60 minuti di VS Code alle 9
        for day, minutes in zip(TUESDAYS[:3], (60, 30, 60)):
            self.add("Visual Studio Code", "app", at(day, 9), at(day, 9) + minutes * 60)
        d = self.dash(TUESDAYS[3], datetime(2026, 3, 24, 8, 0))
        self.assertEqual(d["history_days"], 3)
        self.assertAlmostEqual(d["hours"][9]["forecast"]["c1"], 50)
        self.assertAlmostEqual(d["hours"][9]["band"]["all"]["p10"], 36)
        app = next(a for a in d["apps"] if a["name"] == "Visual Studio Code")
        self.assertEqual(app["probability"], 1.0)

    def test_past_day_is_predicted_only_with_earlier_days(self):
        for day in TUESDAYS:
            self.add("Visual Studio Code", "app", at(day, 9), at(day, 10))
        # dal punto di vista del 25 marzo, il 10 marzo ha alle spalle solo il 3 marzo
        # (più i giorni feriali vuoti di quella settimana): i martedì dopo non contano
        d = self.dash(TUESDAYS[1], datetime(2026, 3, 25, 12, 0))
        later = self.dash(TUESDAYS[1], datetime(2026, 3, 11, 12, 0))
        self.assertEqual(d["hours"][9]["forecast"], later["hours"][9]["forecast"])
        self.assertEqual(d["hours"][9]["actual"]["c1"], 60)

    def test_overlapping_apps_count_once_in_active_time(self):
        day = TUESDAYS[0]
        self.add("Counter-Strike 2", "app", at(day, 21), at(day, 21, 40))
        self.add("Discord", "app", at(day, 21, 20), at(day, 21, 50))
        d = self.dash(day, datetime(2026, 3, 4, 12, 0))
        hour = d["hours"][21]
        self.assertAlmostEqual(hour["actual_active"], 50)
        self.assertAlmostEqual(hour["actual"]["c2"], 40)
        self.assertAlmostEqual(hour["actual"]["none"], 30)  # Discord non è classificato
        self.assertIn("none", [c["id"] for c in d["categories"]])

    def test_today_is_partial_and_future_has_no_actual(self):
        day = TUESDAYS[0]
        self.add("Visual Studio Code", "app", at(day, 9), at(day, 10, 15))
        d = self.dash(day, datetime(2026, 3, 3, 10, 15))
        self.assertEqual(d["relation"], "today")
        self.assertAlmostEqual(d["hours"][10]["actual"]["c1"], 15)  # l'ora in corso, parziale
        self.assertIsNone(d["hours"][11]["actual"])
        self.assertAlmostEqual(d["totals"]["all"]["actual"], 75)
        self.assertEqual(d["history_days"], 0)
        today = next(w for w in d["week"] if w["is_today"])
        self.assertTrue(today["partial"])
        future = self.dash(day + timedelta(days=1), datetime(2026, 3, 3, 10, 15))
        self.assertIsNone(future["hours"][9]["actual"])
        self.assertEqual(future["totals"]["all"]["actual"], 0)


if __name__ == "__main__":
    unittest.main()
