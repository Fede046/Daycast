"""Dashboard costruita dai dati veri del logger, con lo stesso formato di mock_data.

Finché non arriva il modello (Timestral), la previsione è una base semplice:
per ogni ora, la media degli stessi giorni della settimana nello storico;
l'intervallo va dal 10° al 90° percentile di quei giorni. Ogni giorno viene
previsto solo con i giorni precedenti, così "era previsto" è onesto.

Nota: nel formato la chiave si chiama "p50" ma qui contiene la media, che
per "quanti minuti mi aspetto" è più utile della mediana (con pochi giorni
la mediana di un'app usata un giorno sì e uno no vale zero).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .db import UsageDB, active_minutes, day_bounds, default_path, hourly_minutes
from .mock_data import NONE_CATEGORY, NONE_ID, WEEKDAYS

HISTORY_DAYS = 56  # quanto storico guardare (8 settimane)
MIN_SIMILAR = 3  # giorni simili necessari prima di restringere allo stesso giorno della settimana


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _band(values: list[float], cap: float | None = None) -> dict:
    p90 = _quantile(values, 0.9)
    if cap is not None:
        p90 = min(p90, cap)
    return {"p10": round(_quantile(values, 0.1), 1), "p50": round(_mean(values), 1), "p90": round(p90, 1)}


@dataclass
class _DayStats:
    apps: dict[str, list[float]]  # minuti per app, ora per ora
    cats: dict[str, list[float]]  # minuti per categoria (sovrapposizioni contate una volta)
    active: list[float]  # minuti di uso del PC


class RealSource:
    name = "real"

    def __init__(self, path: Path | None = None):
        self.path = path or default_path()

    def has_data(self) -> bool:
        if not self.path.exists():
            return False
        try:
            # sola lettura: non deve creare il database se non c'è
            conn = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
            try:
                return conn.execute("SELECT 1 FROM sessions LIMIT 1").fetchone() is not None
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    def known_apps(self) -> list[dict]:
        db = UsageDB(self.path)
        try:
            return db.known_apps()
        finally:
            db.close()

    def dashboard(self, day: date | None = None, now: datetime | None = None,
                  categories: list[dict] | None = None, assignments: dict[str, str] | None = None) -> dict:
        now = now or datetime.now()
        return _Builder(self.path, now, day or now.date(), categories or [], assignments or {}).build()


def _union(minutes) -> float:
    """Minuti coperti da almeno una delle app (stima, come se gli usi fossero indipendenti)."""
    free = 1.0
    for m in minutes:
        free *= 1 - min(max(m, 0.0), 60.0) / 60
    return 60 * (1 - free)


class _Builder:
    def __init__(self, path, now, day, categories, assignments, use_stored: bool = True):
        self.now = now
        self.today = now.date()
        self.day = day
        monday = day - timedelta(days=day.weekday())
        self.week_days = [monday + timedelta(days=i) for i in range(7)]
        self.range_start = min(monday, day) - timedelta(days=HISTORY_DAYS)
        range_end = max(self.week_days[-1], day) + timedelta(days=1)

        db = UsageDB(path)
        try:
            sessions = db.sessions_between(day_bounds(self.range_start)[0], day_bounds(range_end)[0])
            self.first_day = db.first_day()
            # previsioni di Timestral salvate da forecast.py, se oggi ha vinto il confronto
            self.run = db.forecast_run(self.today) if use_stored else None
            wanted = sorted(set(self.week_days) | {day})
            self.stored = db.forecasts_for(wanted) if self.run and self.run["chosen"] == "timestral" else {}
        finally:
            db.close()

        self.kinds = {name: kind for name, kind, *_ in sessions}
        ids = {c["id"] for c in categories}
        self.app_cat = {name: assignments.get(name) if assignments.get(name) in ids else NONE_ID for name in self.kinds}
        self.categories = list(categories)
        if NONE_ID in self.app_cat.values():
            self.categories.append(NONE_CATEGORY)
        self.ids = [c["id"] for c in self.categories]

        # un periodo a cavallo della mezzanotte appartiene a entrambi i giorni
        self.by_day: dict[date, list] = {}
        for s in sessions:
            d = date.fromtimestamp(s[2])
            last = date.fromtimestamp(s[3])
            while d <= last:
                self.by_day.setdefault(d, []).append(s)
                d += timedelta(days=1)
        self._stats: dict[date, _DayStats] = {}
        self._forecasts: dict[date, dict] = {}

    # ---------- statistiche di un giorno ----------

    def stats(self, d: date) -> _DayStats:
        if d not in self._stats:
            ss = self.by_day.get(d, [])
            self._stats[d] = _DayStats(
                apps=hourly_minutes(ss, d),
                cats={cid: active_minutes([s for s in ss if self.app_cat[s[0]] == cid], d) for cid in self.ids},
                active=active_minutes(ss, d),
            )
        return self._stats[d]

    def history(self, d: date) -> list[date]:
        """I giorni completi prima di d da usare per prevederlo, i più simili possibile."""
        if not self.first_day:
            return []
        start = max(self.first_day, self.range_start)
        end = min(d, self.today)  # oggi non è completo
        days = [start + timedelta(days=i) for i in range((end - start).days)]
        same = [x for x in days if x.weekday() == d.weekday()]
        if len(same) >= MIN_SIMILAR:
            return same
        weekend = d.weekday() >= 5
        similar = [x for x in days if (x.weekday() >= 5) == weekend]
        return similar if len(similar) >= MIN_SIMILAR else days

    # ---------- previsione di Timestral (salvata) ----------

    def stored_forecast(self, d: date) -> dict | None:
        key = d.isoformat()
        hour = self.stored.get((key, "active", "hour"))
        day = self.stored.get((key, "active", "day"))
        if not hour or not day:
            return None
        if d < self.today and hour[0] != key:
            return None  # per un giorno passato vale solo la previsione fatta senza vederlo
        qa, qd = hour[1], day[1]
        apps_h = {n: self.stored.get((key, f"app:{n}", "hour")) for n in self.kinds}
        members = {cid: [apps_h[n][1] for n in self.kinds if self.app_cat[n] == cid and apps_h[n]] for cid in self.ids}

        hours = []
        for h in range(24):
            cats, band = {}, {"all": {"p10": qa["p10"][h], "p50": qa["p50"][h], "p90": qa["p90"][h]}}
            for cid in self.ids:
                vals = {k: round(_union(m[k][h] for m in members[cid]), 1) for k in ("p10", "p50", "p90")}
                cats[cid] = vals["p50"]
                band[cid] = vals
            hours.append({"cats": cats, "active": qa["p50"][h], "band": band})

        p10, p50, p90 = qd["p10"][0], qd["p50"][0], qd["p90"][0]
        totals = {"all": {"p10": p10, "p50": p50, "p90": p90}}
        lo, hi = (p10 / p50, p90 / p50) if p50 > 0 else (1.0, 1.0)
        for cid in self.ids:
            c50 = sum(h["cats"][cid] for h in hours)
            totals[cid] = {"p10": round(c50 * lo, 1), "p50": round(c50, 1), "p90": round(c50 * hi, 1)}

        apps = {}
        for name in self.kinds:
            row = self.stored.get((key, f"app:{name}", "day"))
            if row:
                q = row[1]
                apps[name] = {"p10": q["p10"][0], "p50": q["p50"][0], "p90": q["p90"][0], "probability": q["prob"]}
            else:
                apps[name] = {"p10": 0.0, "p50": 0.0, "p90": 0.0, "probability": 0.0}
        return {"hours": hours, "totals": totals, "apps": apps, "n": len(self.history(d)), "model": "timestral"}

    # ---------- previsione base ----------

    def forecast(self, d: date) -> dict:
        if d in self._forecasts:
            return self._forecasts[d]
        stored = self.stored_forecast(d) if self.stored else None
        if stored:
            self._forecasts[d] = stored
            return stored
        hist = [self.stats(x) for x in self.history(d)]
        hours = []
        for h in range(24):
            hours.append({
                "cats": {cid: _mean([s.cats[cid][h] for s in hist]) for cid in self.ids},
                "active": _mean([s.active[h] for s in hist]),
                "band": {
                    "all": _band([s.active[h] for s in hist], cap=60),
                    **{cid: _band([s.cats[cid][h] for s in hist], cap=60) for cid in self.ids},
                },
            })
        totals = {cid: _band([sum(s.cats[cid]) for s in hist]) for cid in self.ids}
        totals["all"] = _band([sum(s.active) for s in hist])
        apps = {}
        for name in self.kinds:
            daily = [sum(s.apps.get(name, ())) for s in hist]
            apps[name] = {**_band(daily), "probability": round(_mean([1.0 if m >= 1 else 0.0 for m in daily]), 2)}
        result = {"hours": hours, "totals": totals, "apps": apps, "n": len(hist), "model": "base"}
        self._forecasts[d] = result
        return result

    # ---------- assemblaggio ----------

    def known_hours(self, d: date) -> int:
        if d < self.today:
            return 24
        if d == self.today:
            return self.now.hour + 1  # anche l'ora in corso, parziale
        return 0

    def week_entry(self, d: date) -> dict:
        fc = self.forecast(d)
        known = self.known_hours(d)
        st = self.stats(d) if known else None
        return {
            "date": d.isoformat(),
            "label": f"{WEEKDAYS[d.weekday()][:3]} {d.day}",
            "is_today": d == self.today,
            "forecast": {cid: round(sum(h["cats"][cid] for h in fc["hours"]), 1) for cid in self.ids},
            "forecast_active": round(sum(h["active"] for h in fc["hours"]), 1),
            "actual": {cid: round(sum(st.cats[cid][:known]), 1) for cid in self.ids} if st else None,
            "actual_active": round(sum(st.active[:known]), 1) if st else None,
            "partial": 0 < known < 24,
            "total": fc["totals"]["all"],
        }

    def build(self) -> dict:
        d = self.day
        fc = self.forecast(d)
        known = self.known_hours(d)
        st = self.stats(d) if known else None

        hours = []
        for h, fh in enumerate(fc["hours"]):
            is_known = st is not None and h < known
            hours.append({
                "hour": h,
                "forecast": {cid: round(v, 1) for cid, v in fh["cats"].items()},
                "forecast_active": round(fh["active"], 1),
                "actual": {cid: round(st.cats[cid][h], 1) for cid in self.ids} if is_known else None,
                "actual_active": round(st.active[h], 1) if is_known else None,
                "band": fh["band"],
            })

        totals = {}
        for cid in [*self.ids, "all"]:
            done = 0.0
            if st:
                series = st.active if cid == "all" else st.cats[cid]
                done = sum(series[:known])
            totals[cid] = {**fc["totals"][cid], "actual": round(done, 1)}

        apps = []
        for name, kind in self.kinds.items():
            f = fc["apps"][name]
            done = sum(st.apps.get(name, [0.0] * 24)[:known]) if st else 0.0
            if f["p50"] < 1 and done < 0.5:
                continue
            apps.append({"name": name, "kind": kind, "category": self.app_cat[name], **f, "actual": round(done, 1)})
        apps.sort(key=lambda a: (a["p50"], a["actual"]), reverse=True)

        return {
            "date": d.isoformat(),
            "weekday": WEEKDAYS[d.weekday()],
            "relation": "past" if d < self.today else "today" if d == self.today else "future",
            "now_hour": self.now.hour if d == self.today else None,
            "categories": self.categories,
            "hours": hours,
            "totals": totals,
            "apps": apps,
            "week": [self.week_entry(x) for x in self.week_days],
            "mock": False,
            "history_days": fc["n"],
            "forecast_model": fc["model"],
            "forecast_eval": {k: self.run[k] for k in ("chosen", "mae_timestral", "mae_base", "backtest_days")}
            if self.run else None,
            "first_day": self.first_day.isoformat() if self.first_day else None,
        }
