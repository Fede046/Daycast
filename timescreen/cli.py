"""Comandi da riga di comando.

    python -m timescreen               avvia il logger (se non gira già) e apre la finestra
    python -m timescreen ui            solo la finestra
    python -m timescreen --browser     interfaccia nel browser
    python -m timescreen --demo        interfaccia con i dati di esempio
    python -m timescreen log           avvia il logger con l'icona vicino all'orologio (--console per restare nel terminale)
    python -m timescreen report        riepilogo di quello che il logger ha registrato
    python -m timescreen autostart     avvia il logger all'accesso a Windows (--off per toglierlo)
    python -m timescreen forecast      calcola la previsione di oggi con Timestral (lo avvia l'interfaccia)
"""

from __future__ import annotations

import argparse
from datetime import date


def _fmt(minutes: float) -> str:
    m = round(minutes)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def report(day: date) -> None:
    from .db import UsageDB, active_minutes, day_bounds, default_path, hourly_minutes

    if not default_path().exists():
        print("Nessun dato: avvia prima il logger con  python -m timescreen log")
        return
    db = UsageDB()
    try:
        sessions = db.sessions_between(*day_bounds(day))
    finally:
        db.close()
    if not sessions:
        print(f"Nessun utilizzo registrato il {day:%d/%m/%Y}.")
        return

    per_app = hourly_minutes(sessions, day)
    kinds = {name: kind for name, kind, *_ in sessions}
    active = active_minutes(sessions, day)
    print(f"Utilizzo del {day:%d/%m/%Y}: {_fmt(sum(active))}\n")
    for name, hours in sorted(per_app.items(), key=lambda kv: -sum(kv[1])):
        print(f"  {_fmt(sum(hours)):>8}  {name}" + ("  (sito)" if kinds[name] == "sito" else ""))
    print("\n  Ora per ora:")
    for h, minutes in enumerate(active):
        if minutes >= 0.5:
            print(f"  {h:02d}:00  {'█' * round(minutes / 2):<30} {_fmt(minutes)}")


def autostart(off: bool) -> None:
    from . import autostart as auto

    if off:
        print("Avvio automatico tolto." if auto.disable() else "L'avvio automatico non era attivo.")
        return
    cmd = auto.enable()
    print(f"Il logger partirà a ogni accesso a Windows:\n  {cmd}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="timescreen", description="Previsione dell'uso del PC.")
    parser.add_argument("command", nargs="?", default="start", choices=["start", "ui", "log", "report", "autostart", "forecast"])
    parser.add_argument("--browser", action="store_true", help="ui: apri nel browser")
    parser.add_argument("--port", type=int, default=8765, help="ui: porta del server locale")
    parser.add_argument("--no-open", action="store_true", help="ui: non aprire il browser")
    parser.add_argument("--demo", action="store_true", help="ui: usa i dati di esempio anche se ci sono quelli veri")
    parser.add_argument("--interval", type=float, default=None, help="log: secondi tra i controlli")
    parser.add_argument("--console", action="store_true", help="log: resta in console invece dell'icona vicino all'orologio")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="report: giorno AAAA-MM-GG")
    parser.add_argument("--off", action="store_true", help="autostart: disattiva")
    args = parser.parse_args(argv)

    if args.command == "log":
        from . import logger

        logger.run(args.interval or logger.INTERVAL, tray=not args.console)
    elif args.command == "report":
        report(args.date or date.today())
    elif args.command == "autostart":
        autostart(args.off)
    elif args.command == "forecast":
        from . import forecast

        forecast.run()
    else:
        from .app import run_ui

        if args.command == "start" and not args.browser:
            # il doppio clic sull'exe: registrazione in background più la finestra dei dati
            from .launcher import logger_running, spawn

            if not logger_running():
                spawn("log")
        run_ui(browser=args.browser, port=args.port, open_browser=not args.no_open, demo=args.demo)
