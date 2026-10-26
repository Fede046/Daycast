import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import numpy as np
except ImportError:  # senza numpy (e quindi senza Timestral) questi test non hanno senso
    np = None

from daycast.db import UsageDB

LEVELS = (0.01, 0.05) + tuple(round(0.1 * i, 1) for i in range(1, 10)) + (0.95, 0.99)
LEVELS = tuple(sorted(set(LEVELS) | {0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85}))  # 21 livelli come Timestral

# lunedì 16 marzo 2026: due settimane prima, nessun cambio d'ora
FIRST = date(2026, 3, 2)
TODAY = date(2026, 3, 16)
NOW = datetime(2026, 3, 16, 8, 0)
CATS = [{"id": "c1", "name": "Lavoro", "slot": 1}]


def at(day: date, hour: int) -> float:
    return datetime(day.year, day.month, day.day, hour).timestamp()


class RepeatYesterday:
    """Modello finto: prevede che domani sia uguale a ieri (e l'intervallo è ±50%)."""

    levels = LEVELS

    def __call__(self, contexts, horizon):
        ctx = np.asarray(contexts, dtype=np.float32)
        period = 24 if horizon % 24 == 0 and ctx.shape[1] >= 24 else 1
        median = np.resize(ctx[:, -period:], (ctx.shape[0], horizon)) if period > 1 else np.repeat(ctx[:, -1:], horizon, axis=1)
        spread = np.linspace(0.5, 1.5, len(LEVELS))
        return median[:, :, None] * spread[None, None, :]


@unittest.skipIf(np is None, "serve numpy")
class ForecastTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "usage.db"
        self.db = UsageDB(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def add(self, name, start, end):
        sid = self.db.start_session(self.db.app_id(name, "app", None), start)
        self.db.extend_session(sid, end)

    def fill(self, days: int, switch_after: int):
        """Un'ora di VS Code al giorno: prima alle 15, poi (da `switch_after`) alle 9."""
        for i in range(days):
            d = FIRST + timedelta(days=i)
            hour = 15 if i < switch_after else 9
            self.add("Visual Studio Code", at(d, hour), at(d, hour + 1))

    def test_picks_timestral_when_it_does_better(self):
        from daycast import forecast

        self.fill(14, switch_after=5)  # abitudine cambiata: la media dei giorni passati sbaglia
        run, rows = forecast.compute(self.path, NOW, RepeatYesterday)
        self.assertEqual(run["backtest_days"], 7)
        self.assertEqual(run["mae_timestral"], 0.0)
        self.assertGreater(run["mae_base"], 0.0)
        self.assertEqual(run["chosen"], "timestral")
        # oggi è lunedì: si prevede fino a domenica
        targets = {r[0] for r in rows if r[0] >= TODAY.isoformat()}
        self.assertEqual(len(targets), 7)

        self.db.save_forecast_run(run, rows)
        from daycast.real_data import RealSource

        d = RealSource(self.path).dashboard(TODAY, NOW, CATS, {"Visual Studio Code": "c1"})
        self.assertEqual(d["forecast_model"], "timestral")
        self.assertAlmostEqual(d["hours"][9]["forecast_active"], 60)
        self.assertAlmostEqual(d["hours"][9]["forecast"]["c1"], 60)
        self.assertAlmostEqual(d["totals"]["all"]["p50"], 60)
        app = next(a for a in d["apps"] if a["name"] == "Visual Studio Code")
        self.assertGreater(app["probability"], 0.9)

    def test_keeps_base_when_timestral_is_worse(self):
        from daycast import forecast

        class Zero(RepeatYesterday):
            def __call__(self, contexts, horizon):
                return super().__call__(contexts, horizon) * 0

        self.fill(14, switch_after=0)
        run, rows = forecast.compute(self.path, NOW, Zero)
        self.assertEqual(run["chosen"], "base")
        self.db.save_forecast_run(run, rows)
        from daycast.real_data import RealSource

        d = RealSource(self.path).dashboard(TODAY, NOW, CATS, {})
        self.assertEqual(d["forecast_model"], "base")
        self.assertEqual(d["forecast_eval"]["chosen"], "base")

    def test_too_little_history_does_not_load_the_model(self):
        from daycast import forecast

        self.fill(4, switch_after=0)  # logger installato da soli 4 giorni

        def must_not_load():
            raise AssertionError("con pochi giorni il modello non va caricato")

        run, rows = forecast.compute(self.path, datetime(2026, 3, 6, 8, 0), must_not_load)
        self.assertEqual((run["chosen"], rows), ("base", []))

    def test_past_day_uses_only_its_own_forecast(self):
        from daycast import forecast
        from daycast.real_data import RealSource

        self.fill(14, switch_after=5)
        run, rows = forecast.compute(self.path, NOW, RepeatYesterday)
        self.db.save_forecast_run(run, rows)
        yesterday = TODAY - timedelta(days=1)
        d = RealSource(self.path).dashboard(yesterday, NOW, CATS, {})
        self.assertEqual(d["forecast_model"], "timestral")
        origins = {r[3] for r in rows if r[0] == yesterday.isoformat()}
        self.assertEqual(origins, {yesterday.isoformat()})


@unittest.skipIf(np is None, "serve numpy")
class RealTimestralTest(unittest.TestCase):
    """Con Timestral vero, se installato e col modello già scaricato."""

    def test_predictor_shapes(self):
        from daycast import forecast

        if not forecast.available() or not (forecast.MODEL_DIR / "model.safetensors").exists():
            self.skipTest("Timestral o il modello non sono disponibili")
        predictor = forecast.TimestralPredictor(forecast.MODEL_DIR)
        ctx = np.tile(np.r_[np.zeros(9), np.full(2, 40.0), np.zeros(13)], 14)[None, :]
        q = predictor(ctx, 24)
        self.assertEqual(q.shape, (1, 24, len(predictor.levels)))
        self.assertTrue((q >= 0).all())


if __name__ == "__main__":
    unittest.main()
