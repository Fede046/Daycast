"""Dati finti per provare l'interfaccia prima che logger e modello esistano.

La forma del dizionario restituito da `dashboard()` è il contratto tra il
backend e la UI: quando arriverà il modello vero dovrà produrre la stessa
struttura.

Più app possono essere in uso nella stessa ora (musica mentre lavori, Discord
mentre giochi), quindi la somma dei minuti delle app può superare 60. Per
questo, oltre ai minuti per categoria, ogni ora ha `*_active`: i minuti in cui
il PC è stato usato davvero, che non superano mai 60.
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta

NONE_ID = "none"
NONE_CATEGORY = {"id": NONE_ID, "name": "Da classificare", "slot": None}

# (nome, tipo, picchi feriali, picchi weekend)
# ogni picco è (ora centrale, ampiezza in ore, minuti al picco)
APPS = [
    ("Visual Studio Code", "app", [(10.5, 1.6, 34), (15.5, 1.8, 32)], [(16, 1.2, 10)]),
    ("Microsoft Word", "app", [(11.5, 1.0, 12), (17, 1.0, 9)], []),
    ("YouTube", "sito", [(13.2, 0.6, 12), (21.5, 1.4, 24)], [(11, 1.5, 16), (21, 2.0, 24)]),
    ("Netflix", "sito", [(22.8, 0.8, 18)], [(22, 1.2, 26)]),
    ("Reddit", "sito", [(8.5, 0.5, 9), (13, 0.6, 10), (20, 1.2, 8)], [(10.5, 1.4, 13), (19, 1.5, 9)]),
    ("Instagram", "sito", [(19.5, 1.0, 6)], [(15, 2.0, 7)]),
    ("Counter-Strike 2", "app", [(22, 0.9, 16)], [(16.5, 1.6, 30), (22.5, 1.0, 22)]),
    # Discord e Spotify girano spesso insieme ad altro: qui nascono le sovrapposizioni
    ("Discord", "app", [(21.5, 1.6, 18)], [(17, 3.0, 20)]),
    ("WhatsApp", "app", [(9, 3.0, 3), (18.5, 2.0, 4)], [(12, 4.0, 4)]),
    ("Esplora file", "app", [(11, 3.0, 3), (16, 2.0, 3)], [(15, 3.0, 2)]),
    ("Spotify", "app", [(10.5, 2.0, 22), (15.5, 2.0, 20)], [(14, 3.0, 12)]),
]

WEEKDAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def known_apps() -> list[dict]:
    """App e siti visti finora (poi arriveranno dal database del logger)."""
    return [{"name": name, "kind": kind} for name, kind, *_ in APPS]


# riporta i picchi sopra a una giornata plausibile (circa 6-7 ore)
PROFILE_SCALE = 0.62


def _profile(peaks, hour: int) -> float:
    centre = hour + 0.5
    m = PROFILE_SCALE * sum(m * math.exp(-((centre - c) ** 2) / (2 * w * w)) for c, w, m in peaks)
    return m if m >= 1 else 0.0  # niente code di pochi secondi a notte fonda


def _union(minutes) -> float:
    """Minuti coperti da almeno una delle app, supponendo usi indipendenti."""
    free = 1.0
    for m in minutes:
        free *= 1 - min(m, 60) / 60
    return 60 * (1 - free)


def _hourly_forecast(day: date) -> dict[str, list[float]]:
    """Minuti previsti (mediana) per app, ora per ora."""
    weekend = day.weekday() >= 5
    # piccola variazione stabile per giorno, così ogni giorno è un po' diverso
    rng = random.Random(day.toordinal())
    out = {}
    for name, _kind, weekday_peaks, weekend_peaks in APPS:
        peaks = weekend_peaks if weekend else weekday_peaks
        scale = rng.uniform(0.8, 1.2)
        out[name] = [min(60.0, _profile(peaks, h) * scale) for h in range(24)]
    return out


def _hourly_actual(day: date, forecast: dict[str, list[float]]) -> dict[str, list[float]]:
    rng = random.Random(day.toordinal() * 7919)
    return {
        name: [min(60.0, v * rng.lognormvariate(0, 0.35)) for v in series]
        for name, series in forecast.items()
    }


def _band(p50: float, low: float, high: float, cap: float | None = None) -> dict:
    p90 = p50 * high
    if cap is not None:
        p90 = min(p90, cap)
    return {"p10": round(p50 * low, 1), "p50": round(p50, 1), "p90": round(p90, 1)}


def _known_hours(day: date, now: datetime) -> int:
    if day < now.date():
        return 24
    if day == now.date():
        return now.hour  # l'ora in corso non è ancora completa
    return 0


class _Grouping:
    """Raggruppa le app nelle categorie scelte dall'utente."""

    def __init__(self, categories: list[dict], assignments: dict[str, str]):
        ids = {c["id"] for c in categories}
        self.app_cat = {
            name: assignments.get(name) if assignments.get(name) in ids else NONE_ID
            for name, *_ in APPS
        }
        self.categories = list(categories)
        if NONE_ID in self.app_cat.values():
            self.categories.append(NONE_CATEGORY)
        self.ids = [c["id"] for c in self.categories]

    def hour(self, per_app: dict[str, list[float]], h: int) -> tuple[dict[str, float], float]:
        """(minuti per categoria, minuti di uso del PC) in un'ora."""
        by_cat = {
            cid: round(_union(v[h] for name, v in per_app.items() if self.app_cat[name] == cid), 1)
            for cid in self.ids
        }
        active = round(_union(v[h] for v in per_app.values()), 1)
        return by_cat, active


def _day_summary(day: date, now: datetime, grouping: _Grouping) -> dict:
    forecast = _hourly_forecast(day)
    known = _known_hours(day, now)
    actual = _hourly_actual(day, forecast) if known else None
    fc = dict.fromkeys(grouping.ids, 0.0)
    ac = dict.fromkeys(grouping.ids, 0.0)
    fc_active = ac_active = 0.0
    for h in range(24):
        cats, active = grouping.hour(forecast, h)
        fc_active += active
        for k, v in cats.items():
            fc[k] += v
        if actual and h < known:
            cats, active = grouping.hour(actual, h)
            ac_active += active
            for k, v in cats.items():
                ac[k] += v
    return {
        "date": day.isoformat(),
        "label": f"{WEEKDAYS[day.weekday()][:3]} {day.day}",
        "is_today": day == now.date(),
        "forecast": {k: round(v, 1) for k, v in fc.items()},
        "forecast_active": round(fc_active, 1),
        # per oggi è l'uso fino a ora, il resto della giornata è previsione
        "actual": {k: round(v, 1) for k, v in ac.items()} if actual else None,
        "actual_active": round(ac_active, 1) if actual else None,
        "partial": 0 < known < 24,
        "total": _band(fc_active, 0.8, 1.18),
    }


def dashboard(
    day: date | None = None,
    now: datetime | None = None,
    categories: list[dict] | None = None,
    assignments: dict[str, str] | None = None,
) -> dict:
    now = now or datetime.now()
    today = now.date()
    day = day or today
    grouping = _Grouping(categories or [], assignments or {})

    forecast = _hourly_forecast(day)
    actual_full = _hourly_actual(day, forecast)
    known_hours = _known_hours(day, now)

    hours = []
    for h in range(24):
        fc, fc_active = grouping.hour(forecast, h)
        if h < known_hours:
            ac, ac_active = grouping.hour(actual_full, h)
        else:
            ac, ac_active = None, None
        hours.append({
            "hour": h,
            "forecast": fc,
            "forecast_active": fc_active,
            "actual": ac,
            "actual_active": ac_active,
            "band": {
                "all": _band(fc_active, 0.6, 1.35, cap=60),
                **{k: _band(v, 0.5, 1.5, cap=60) for k, v in fc.items()},
            },
        })

    totals = {}
    for cid in grouping.ids:
        p50 = sum(hh["forecast"][cid] for hh in hours)
        done = sum(hh["actual"][cid] for hh in hours if hh["actual"])
        totals[cid] = {**_band(p50, 0.7, 1.3), "actual": round(done, 1)}
    p50_all = sum(hh["forecast_active"] for hh in hours)
    done_all = sum(hh["actual_active"] for hh in hours if hh["actual"])
    totals["all"] = {**_band(p50_all, 0.82, 1.15), "actual": round(done_all, 1)}

    apps = []
    for name, kind, *_ in APPS:
        p50 = sum(forecast[name])
        done = sum(actual_full[name][:known_hours])
        if p50 < 2:
            continue
        apps.append({
            "name": name,
            "kind": kind,
            "category": grouping.app_cat[name],
            **_band(p50, 0.45, 1.6),
            "actual": round(done, 1),
            "probability": round(1 - math.exp(-p50 / 12), 2),
        })
    apps.sort(key=lambda a: a["p50"], reverse=True)

    monday = day - timedelta(days=day.weekday())
    week = [_day_summary(monday + timedelta(days=i), now, grouping) for i in range(7)]

    return {
        "date": day.isoformat(),
        "weekday": WEEKDAYS[day.weekday()],
        "relation": "past" if day < today else "today" if day == today else "future",
        "now_hour": now.hour if day == today else None,
        "categories": grouping.categories,
        "hours": hours,
        "totals": totals,
        "apps": apps,
        "week": week,
        "mock": True,
    }


class MockSource:
    """Stessa interfaccia di real_data.RealSource, con i dati finti."""

    name = "mock"

    def known_apps(self) -> list[dict]:
        return known_apps()

    def dashboard(self, day=None, now=None, categories=None, assignments=None) -> dict:
        return dashboard(day, now, categories, assignments)
