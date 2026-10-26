"""Logger in background: ogni pochi secondi guarda quale app o sito stai usando.

Pensato per restare leggero: solo ctypes e sqlite3, un controllo ogni 2
secondi e una scrittura su disco solo quando cambia qualcosa (più un
aggiornamento ogni 30 secondi, così un arresto improvviso perde poco).
"""

from __future__ import annotations

import logging
import os
import time
from logging.handlers import RotatingFileHandler

from . import browser_url, sites, winapi
from .db import UsageDB

INTERVAL = 2.0  # secondi tra un controllo e l'altro
FLUSH_EVERY = 30.0  # ogni quanto aggiornare la fine del periodo in corso
IDLE_AFTER = 120.0  # senza tastiera/mouse per tanto, non stai usando il PC...
MIN_SESSION = 3.0  # passaggi più brevi (alt-tab veloci) non si salvano
SLEEP_GAP = 60.0  # un buco così lungo tra due controlli vuol dire sospensione

# finestre di sistema che non sono "uso" di un'app
IGNORED_EXES = {
    "lockapp.exe",
    "searchhost.exe",
    "searchapp.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "textinputhost.exe",
}
FRAME_HOST = "applicationframehost.exe"

log = logging.getLogger("daycast.logger")


def current_target() -> tuple[str, str, str] | None:
    """(nome, tipo, eseguibile) di quello che è in primo piano, o None."""
    hwnd = winapi.foreground_window()
    if not hwnd:
        return None
    pid = winapi.window_pid(hwnd)
    path = winapi.process_path(pid)
    if not path:
        return None
    exe = os.path.basename(path).lower()
    if exe == FRAME_HOST:
        child = winapi.uwp_child_pid(hwnd, pid)
        path = winapi.process_path(child) if child else None
        if not path:
            return None
        exe = os.path.basename(path).lower()
    if exe in IGNORED_EXES:
        return None
    title = winapi.window_title(hwnd)
    if exe == "explorer.exe" and not title:
        return None  # desktop o barra delle applicazioni
    if exe in sites.BROWSERS:
        return _browser_site(hwnd, title), "sito", exe
    return winapi.app_display_name(path), "app", exe


# (finestra, titolo) -> sito: la barra degli indirizzi si rilegge solo quando
# cambia la scheda o la pagina, non a ogni controllo
_site_cache: dict[tuple[int, str], str] = {}


def _browser_site(hwnd: int, title: str) -> str:
    key = (hwnd, title)
    if key not in _site_cache:
        if len(_site_cache) > 256:
            _site_cache.clear()
        _site_cache[key] = sites.site_for(title, browser_url.address_bar(hwnd))
    return _site_cache[key]


def idle_seconds() -> float:
    # ...a meno che qualcosa tenga acceso lo schermo: video, film, giochi col pad
    if winapi.display_required():
        return 0.0
    return winapi.idle_seconds()


class Logger:
    def __init__(self, db: UsageDB, clock=time.time, sample=current_target, idle=idle_seconds):
        self.db = db
        self.clock = clock
        self.sample = sample
        self.idle = idle
        self.current = None  # ((nome, tipo), id sessione, inizio)
        self.last_tick: float | None = None
        self.last_flush = 0.0

    def tick(self) -> None:
        now = self.clock()
        if self.current and self.last_tick is not None and now - self.last_tick > SLEEP_GAP:
            self._close(self.last_tick)  # il PC era sospeso: il periodo finisce all'ultimo controllo

        idle = self.idle()
        target = self.sample() if idle < IDLE_AFTER else None

        if self.current and (target is None or target[:2] != self.current[0]):
            # andando via, il periodo finisce quando hai smesso di usare tastiera e mouse
            end = now - idle if target is None else now
            self._close(max(end, self.current[2]))

        if target and not self.current:
            app_id = self.db.app_id(*target)
            self.current = (target[:2], self.db.start_session(app_id, now), now)
            self.last_flush = now
        elif self.current and now - self.last_flush >= FLUSH_EVERY:
            self.db.extend_session(self.current[1], now)
            self.last_flush = now

        self.last_tick = now

    def _close(self, ts: float) -> None:
        _key, session_id, _start = self.current
        self.db.extend_session(session_id, ts)
        self.db.drop_short_session(session_id, MIN_SESSION)
        self.current = None

    def stop(self) -> None:
        if self.current:
            self._close(self.clock())

    def run(self, interval: float = INTERVAL) -> None:
        try:
            while True:
                try:
                    self.tick()
                except Exception:
                    # un errore su una finestra strana non deve fermare il logger
                    log.exception("controllo fallito")
                time.sleep(interval)
        finally:
            self.stop()


def _setup_logging(db: UsageDB) -> None:
    handler = RotatingFileHandler(db.path.with_name("logger.log"), maxBytes=200_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def run(interval: float = INTERVAL, tray: bool = True) -> None:
    """Avvia il logger: di default con l'icona nell'area di notifica, altrimenti in console."""
    from .launcher import logger_mutex_name

    mutex = winapi.single_instance(logger_mutex_name())
    if mutex is None:
        if tray:
            from .tray import message_box, text

            message_box(text("already"))
        print("Daycast is already recording.")
        return
    db = UsageDB()
    _setup_logging(db)
    log.info("avviato, database %s", db.path)
    browser_url.warm_up()
    try:
        if tray:
            from .tray import TrayApp

            TrayApp(Logger(db), interval).run()
        else:
            print(f"Logger attivo, salvo in {db.path}  (Ctrl+C per fermare)")
            Logger(db).run(interval)
    except KeyboardInterrupt:
        pass
    finally:
        log.info("fermato")
        db.close()
