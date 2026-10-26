"""Storico di utilizzo in SQLite: una riga per ogni periodo continuo d'uso di un'app o sito.

Si salvano solo nome, tipo ed eseguibile, mai i titoli delle finestre.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .paths import data_dir, env_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,          -- 'app' o 'sito'
    exe  TEXT                    -- ultimo eseguibile visto, utile per capire da dove arriva
);
CREATE TABLE IF NOT EXISTS sessions (
    id     INTEGER PRIMARY KEY,
    app_id INTEGER NOT NULL REFERENCES apps(id),
    start  REAL NOT NULL,        -- secondi Unix
    end    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_start ON sessions(start);

-- previsioni di Timestral, calcolate da un processo a parte (forecast.py)
CREATE TABLE IF NOT EXISTS forecasts (
    target_day TEXT NOT NULL,    -- AAAA-MM-GG del giorno previsto
    series     TEXT NOT NULL,    -- 'active' (uso del PC) oppure 'app:<nome>'
    freq       TEXT NOT NULL,    -- 'hour' (24 valori) oppure 'day' (totale del giorno)
    origin_day TEXT NOT NULL,    -- primo giorno senza dati usati: la previsione vede solo i giorni prima
    q          TEXT NOT NULL,    -- JSON {"p10": [...], "p50": [...], "p90": [...]}, più "prob" per 'day'
    PRIMARY KEY (target_day, series, freq)
);
-- un'esecuzione al giorno: quale modello ha vinto il confronto sugli ultimi giorni
CREATE TABLE IF NOT EXISTS forecast_runs (
    origin_day    TEXT PRIMARY KEY,
    created       REAL NOT NULL,
    model         TEXT,
    chosen        TEXT NOT NULL,  -- 'timestral' oppure 'base'
    mae_timestral REAL,           -- errore medio in minuti per ora sui giorni del confronto
    mae_base      REAL,
    backtest_days INTEGER,
    history_days  INTEGER,
    error         TEXT
);
"""


def default_path() -> Path:
    return env_path("DB") or data_dir() / "usage.db"


class UsageDB:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self._app_ids: dict[str, int] = {}

    def close(self) -> None:
        self.conn.close()

    # ---------- scrittura (logger) ----------

    def app_id(self, name: str, kind: str, exe: str | None) -> int:
        if name in self._app_ids:
            return self._app_ids[name]
        with self.conn:
            self.conn.execute(
                "INSERT INTO apps(name, kind, exe) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET exe = excluded.exe",
                (name, kind, exe),
            )
        row = self.conn.execute("SELECT id FROM apps WHERE name = ?", (name,)).fetchone()
        self._app_ids[name] = row[0]
        return row[0]

    def start_session(self, app_id: int, ts: float) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO sessions(app_id, start, end) VALUES (?, ?, ?)", (app_id, ts, ts)
            )
        return cur.lastrowid

    def extend_session(self, session_id: int, ts: float) -> None:
        with self.conn:
            self.conn.execute("UPDATE sessions SET end = ? WHERE id = ?", (ts, session_id))

    def drop_short_session(self, session_id: int, min_seconds: float) -> None:
        """Toglie un passaggio troppo breve (es. alt-tab di un attimo)."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM sessions WHERE id = ? AND end - start < ?", (session_id, min_seconds)
            )

    # ---------- lettura ----------

    def sessions_between(self, start: float, end: float) -> list[tuple[str, str, float, float]]:
        return self.conn.execute(
            "SELECT a.name, a.kind, s.start, s.end FROM sessions s JOIN apps a ON a.id = s.app_id "
            "WHERE s.end > ? AND s.start < ? ORDER BY s.start",
            (start, end),
        ).fetchall()

    # ---------- previsioni di Timestral ----------

    def save_forecast_run(self, run: dict, rows: list[tuple[str, str, str, str, dict]]) -> None:
        """Salva un'esecuzione e le sue previsioni (target_day, series, freq, origin_day, quantili)."""
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO forecasts(target_day, series, freq, origin_day, q) VALUES (?, ?, ?, ?, ?)",
                [(t, s, f, o, json.dumps(q)) for t, s, f, o, q in rows],
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO forecast_runs(origin_day, created, model, chosen, mae_timestral, mae_base,"
                " backtest_days, history_days, error) VALUES (:origin_day, :created, :model, :chosen,"
                " :mae_timestral, :mae_base, :backtest_days, :history_days, :error)",
                {"model": None, "mae_timestral": None, "mae_base": None, "backtest_days": None,
                 "history_days": None, "error": None, **run},
            )

    def forecast_run(self, origin: date) -> dict | None:
        cur = self.conn.execute("SELECT * FROM forecast_runs WHERE origin_day = ?", (origin.isoformat(),))
        row = cur.fetchone()
        return dict(zip([c[0] for c in cur.description], row)) if row else None

    def forecasts_for(self, days: list[date]) -> dict[tuple[str, str, str], tuple[str, dict]]:
        """{(target_day, series, freq): (origin_day, quantili)} per i giorni chiesti."""
        if not days:
            return {}
        marks = ",".join("?" * len(days))
        rows = self.conn.execute(
            f"SELECT target_day, series, freq, origin_day, q FROM forecasts WHERE target_day IN ({marks})",
            [d.isoformat() for d in days],
        ).fetchall()
        return {(t, s, f): (o, json.loads(q)) for t, s, f, o, q in rows}

    def first_day(self) -> date | None:
        """Il giorno del primo dato registrato: prima di allora il logger non c'era."""
        row = self.conn.execute("SELECT MIN(start) FROM sessions").fetchone()
        return date.fromtimestamp(row[0]) if row and row[0] else None

    def known_apps(self) -> list[dict]:
        rows = self.conn.execute("SELECT name, kind FROM apps ORDER BY name").fetchall()
        return [{"name": n, "kind": k} for n, k in rows]


def day_bounds(day: date) -> tuple[float, float]:
    start = datetime.combine(day, datetime.min.time())
    return start.timestamp(), (start + timedelta(days=1)).timestamp()


def _hour_edges(day: date) -> list[float]:
    # confini delle ore sull'orologio locale (il giorno del cambio d'ora ha un'ora in più o in meno)
    midnight = datetime.combine(day, datetime.min.time())
    return [(midnight + timedelta(hours=h)).timestamp() for h in range(25)]


def _spread(hours: list[float], edges: list[float], start: float, end: float) -> None:
    for h in range(24):
        overlap = min(end, edges[h + 1]) - max(start, edges[h])
        if overlap > 0:
            hours[h] += overlap / 60


def hourly_minutes(sessions, day: date) -> dict[str, list[float]]:
    """Minuti di ogni app in ciascuna delle 24 ore del giorno."""
    edges = _hour_edges(day)
    out: dict[str, list[float]] = {}
    for name, _kind, start, end in sessions:
        _spread(out.setdefault(name, [0.0] * 24), edges, start, end)
    return out


def active_minutes(sessions, day: date) -> list[float]:
    """Minuti di uso del PC per ora: i periodi sovrapposti contano una volta sola."""
    edges = _hour_edges(day)
    hours = [0.0] * 24
    merged: list[list[float]] = []
    for _name, _kind, start, end in sorted(sessions, key=lambda s: s[2]):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    for start, end in merged:
        _spread(hours, edges, start, end)
    return hours
