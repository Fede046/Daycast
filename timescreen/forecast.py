"""Previsione con Timestral, in un processo a parte (`python -m timescreen forecast`).

L'interfaccia lo avvia quando manca la previsione di oggi. Qui, e solo qui, si
caricano PyTorch e il modello (Timestral-5M, incluso nell'app):

- si prevedono ora per ora oggi e i giorni restanti della settimana, per l'uso
  del PC e per ogni app o sito usato abbastanza, più i totali di ogni giorno;
- si rifanno le previsioni degli ultimi giorni, ognuna vedendo solo i giorni
  precedenti, e si confrontano con la previsione base (backtest): l'interfaccia
  mostra il modello che ha sbagliato meno;
- tutto finisce nel database; l'interfaccia legge solo i numeri salvati.
"""

from __future__ import annotations

import ctypes
import importlib.util
import logging
import time
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .db import UsageDB, active_minutes, day_bounds, default_path, hourly_minutes

MODEL_NAME = "Timestral-5M"
MODEL_REPO = f"mistralai/{MODEL_NAME}"
MODEL_DIR = Path(__file__).resolve().parent / "models" / MODEL_NAME
MODEL_FILES = ["config.json", "model.safetensors", "LICENSE"]

HISTORY_DAYS = 56  # contesto massimo dato al modello (8 settimane)
MIN_HISTORY_DAYS = 7  # con meno giorni completi Timestral non viene neanche provato
BACKTEST_DAYS = 7  # giorni recenti su cui si confrontano i due modelli
MIN_BACKTEST_DAYS = 3  # sotto questo numero il confronto non basta e resta la previsione base
MIN_APP_MINUTES = 10.0  # app usate meno di così nello storico: nessuna previsione
BELOW_NORMAL_PRIORITY_CLASS = 0x4000

log = logging.getLogger("timescreen.forecast")


def available() -> bool:
    """True se PyTorch e Timestral sono installati (senza importarli: pesano)."""
    return importlib.util.find_spec("torch") is not None and importlib.util.find_spec("timestral") is not None


def ensure_model() -> Path:
    """La cartella del modello: inclusa nell'app, oppure scaricata una volta da Hugging Face."""
    if (MODEL_DIR / "model.safetensors").exists():
        return MODEL_DIR
    from huggingface_hub import snapshot_download

    log.info("scarico %s in %s", MODEL_REPO, MODEL_DIR)
    snapshot_download(MODEL_REPO, local_dir=MODEL_DIR, allow_patterns=MODEL_FILES)
    return MODEL_DIR


class TimestralPredictor:
    """predict(contesti (serie, tempo), orizzonte) -> quantili (serie, orizzonte, livelli)."""

    def __init__(self, model_dir: Path, threads: int = 2):
        import torch
        from timestral import TimestralForecaster

        torch.set_num_threads(threads)  # gentile con il resto del PC
        self.forecaster = TimestralForecaster.from_pretrained(str(model_dir))
        self.levels = tuple(self.forecaster.quantile_levels)

    def __call__(self, contexts, horizon: int):
        import numpy as np

        fc = self.forecaster.forecast(np.asarray(contexts, dtype=np.float32), prediction_length=horizon)
        return fc.quantiles.numpy().reshape(len(contexts), horizon, -1)


def _level_index(levels, value: float) -> int:
    return min(range(len(levels)), key=lambda i: abs(levels[i] - value))


def _prob_at_least(quantiles, levels, threshold: float = 1.0) -> float:
    """Probabilità che il valore superi la soglia, letta dai quantili previsti."""
    for level, q in zip(levels, quantiles):
        if q >= threshold:
            return round(1.0 - level, 2)
    return 0.0


def compute(path: Path, now: datetime, make_predictor) -> tuple[dict, list]:
    """Calcola previsioni e confronto. `make_predictor()` si chiama solo se serve davvero."""
    import numpy as np

    from .real_data import _Builder

    today = now.date()
    run = {"origin_day": today.isoformat(), "created": time.time(), "model": MODEL_NAME, "chosen": "base"}

    db = UsageDB(path)
    try:
        first = db.first_day()
        if first is None:
            return {**run, "history_days": 0}, []
        start = max(first, today - timedelta(days=HISTORY_DAYS + BACKTEST_DAYS))
        # solo giorni completi: oggi è ancora in corso
        sessions = db.sessions_between(day_bounds(start)[0], day_bounds(today)[0])
    finally:
        db.close()

    days = [start + timedelta(days=i) for i in range((today - start).days)]
    run["history_days"] = min(len(days), HISTORY_DAYS)
    if len(days) < MIN_HISTORY_DAYS:
        return run, []

    by_day: dict[date, list] = {}
    for s in sessions:
        d, last = date.fromtimestamp(s[2]), date.fromtimestamp(s[3])
        while d <= last:
            by_day.setdefault(d, []).append(s)
            d += timedelta(days=1)
    per_app = [hourly_minutes(by_day.get(d, []), d) for d in days]
    active = [active_minutes(by_day.get(d, []), d) for d in days]

    totals: dict[str, float] = {}
    for day_apps in per_app:
        for name, hours in day_apps.items():
            totals[name] = totals.get(name, 0.0) + sum(hours)
    apps = sorted(n for n, t in totals.items() if t >= MIN_APP_MINUTES)
    names = ["active"] + [f"app:{n}" for n in apps]

    hourly = np.array(
        [np.concatenate(active)] + [np.concatenate([d.get(n, [0.0] * 24) for d in per_app]) for n in apps],
        dtype=np.float32,
    )
    daily = hourly.reshape(len(names), len(days), 24).sum(axis=2)

    predictor = make_predictor()
    levels = predictor.levels
    i10, i50, i90 = (_level_index(levels, v) for v in (0.1, 0.5, 0.9))

    def quantiles(series_q, cap=None):
        out = {}
        for key, idx in (("p10", i10), ("p50", i50), ("p90", i90)):
            values = series_q[:, idx]
            if cap is not None:
                values = np.minimum(values, cap)
            out[key] = [round(float(v), 1) for v in values]
        return out

    # giorni del confronto: i più recenti, purché abbiano abbastanza storia prima
    backtest = [d for d in days[-BACKTEST_DAYS:] if days.index(d) >= MIN_HISTORY_DAYS]
    origins = backtest + [today]

    rows, errors = [], {}
    for origin in origins:
        idx = days.index(origin) if origin in days else len(days)
        ctx0 = max(0, idx - HISTORY_DAYS)
        horizon_days = 1 if origin != today else 7 - today.weekday()  # fino a domenica
        hq = predictor(hourly[:, ctx0 * 24: idx * 24], horizon_days * 24)
        dq = predictor(daily[:, ctx0:idx], horizon_days)
        for k in range(horizon_days):
            target = (origin + timedelta(days=k)).isoformat()
            for s, name in enumerate(names):
                rows.append((target, name, "hour", origin.isoformat(), quantiles(hq[s, k * 24:(k + 1) * 24], cap=60.0)))
                day_q = quantiles(dq[s, k:k + 1], cap=24 * 60.0)
                day_q["prob"] = _prob_at_least(dq[s, k], levels)
                rows.append((target, name, "day", origin.isoformat(), day_q))
        if origin != today:
            truth = np.array(active[idx])
            errors[origin] = float(np.abs(np.minimum(hq[0, :24, i50], 60) - truth).mean())

    # stessi giorni con la previsione base, calcolata come la fa l'interfaccia
    if errors:
        builder = _Builder(path, now, today, [], {}, use_stored=False)
        base_errors = []
        for origin in errors:
            idx = days.index(origin)
            base = np.array([h["active"] for h in builder.forecast(origin)["hours"]])
            base_errors.append(float(np.abs(base - np.array(active[idx])).mean()))
        run["mae_timestral"] = round(float(np.mean(list(errors.values()))), 2)
        run["mae_base"] = round(float(np.mean(base_errors)), 2)
        run["backtest_days"] = len(errors)
        if len(errors) >= MIN_BACKTEST_DAYS and run["mae_timestral"] < run["mae_base"]:
            run["chosen"] = "timestral"
    return run, rows


def needs_run(today: date | None = None) -> bool:
    """Va calcolata la previsione di oggi? (dati veri presenti, nessuna esecuzione oggi)"""
    from .launcher import forecast_running
    from .real_data import RealSource

    if not available() or forecast_running() or not RealSource().has_data():
        return False
    db = UsageDB()
    try:
        return db.forecast_run(today or date.today()) is None
    finally:
        db.close()


def run() -> None:
    from . import winapi
    from .launcher import forecast_mutex_name

    mutex = winapi.single_instance(forecast_mutex_name())
    if mutex is None:
        return  # già in corso
    path = default_path()
    handler = RotatingFileHandler(path.with_name("forecast.log"), maxBytes=200_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    # in secondo piano: se stai giocando o lavorando, la precedenza è tua
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass(ctypes.c_void_p(kernel32.GetCurrentProcess()), BELOW_NORMAL_PRIORITY_CLASS)

    now = datetime.now()
    t0 = time.perf_counter()
    try:
        result, rows = compute(path, now, lambda: TimestralPredictor(ensure_model()))
    except Exception as err:  # la previsione base resta comunque disponibile
        log.exception("previsione non riuscita")
        result = {"origin_day": now.date().isoformat(), "created": time.time(), "model": MODEL_NAME,
                  "chosen": "base", "error": repr(err)[:500]}
        rows = []
    db = UsageDB(path)
    try:
        db.save_forecast_run(result, rows)
    finally:
        db.close()
    log.info(
        "fatto in %.1f s: %d previsioni, scelta %s (errore medio Timestral %s, base %s, su %s giorni)",
        time.perf_counter() - t0, len(rows), result["chosen"], result.get("mae_timestral"),
        result.get("mae_base"), result.get("backtest_days"),
    )
