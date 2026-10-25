"""Finestra di TimeScreen.

Di default apre una finestra nativa con pywebview (usa WebView2, già presente
in Windows 11). Con `--browser`, o se pywebview non è installato, serve la UI
su http://127.0.0.1 e la apre nel browser: utile per lo sviluppo.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .mock_data import MockSource
from .real_data import RealSource
from .settings import Settings

UI_DIR = Path(__file__).parent / "ui"


class Api:
    """Metodi chiamabili dalla UI: window.pywebview.api.* oppure POST /api/<metodo>."""

    PUBLIC = (
        "get_dashboard",
        "get_settings",
        "add_category",
        "rename_category",
        "delete_category",
        "assign_app",
    )

    def __init__(self, settings: Settings | None = None, demo: bool = False):
        self._settings = settings or Settings()
        self._lock = threading.Lock()
        self._demo = demo
        self._real = RealSource()

    def _source(self):
        # si ricontrolla ogni volta: se il logger parte con la finestra aperta,
        # al primo aggiornamento compaiono i dati veri
        if not self._demo and self._real.has_data():
            return self._real
        return MockSource()

    def get_dashboard(self, day=None):
        parsed = date.fromisoformat(day) if day else None
        with self._lock:
            return self._source().dashboard(
                parsed,
                categories=self._settings.categories,
                assignments=self._settings.assignments,
            )

    def get_settings(self):
        with self._lock:
            return {**self._settings.to_dict(), "apps": self._source().known_apps()}

    def _change(self, fn, *args):
        with self._lock:
            try:
                fn(*args)
            except ValueError as err:
                return {"ok": False, "error": str(err)}
        return {"ok": True, **self.get_settings()}

    def add_category(self, name):
        return self._change(self._settings.add_category, name)

    def rename_category(self, cat_id, name):
        return self._change(self._settings.rename_category, cat_id, name)

    def delete_category(self, cat_id):
        return self._change(self._settings.delete_category, cat_id)

    def assign_app(self, app, cat_id=None):
        return self._change(self._settings.assign, app, cat_id)


def _make_handler(api: Api, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(UI_DIR), **kwargs)

        def end_headers(self):
            # niente cache: dopo un aggiornamento HTML e JS devono arrivare insieme
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _send_json(self, status: int, payload) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            # solo JSON e solo dal nostro host: blocca pagine esterne che
            # provassero a chiamare il server locale
            if self.headers.get("Host") not in allowed_hosts:
                return self.send_error(403)
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self.send_error(415)
            name = self.path.removeprefix("/api/")
            if name not in Api.PUBLIC:
                return self.send_error(404)
            try:
                length = int(self.headers.get("Content-Length", 0))
                args = json.loads(self.rfile.read(length) or b"[]")
                if not isinstance(args, list):
                    raise ValueError
                result = getattr(api, name)(*args)
            except (ValueError, TypeError):
                return self.send_error(400)
            self._send_json(200, result)

        def log_message(self, *args):
            pass

    return Handler


class _Server(ThreadingHTTPServer):
    # su Windows SO_REUSEADDR lascerebbe due istanze sulla stessa porta,
    # con la vecchia che risponde al posto della nuova
    allow_reuse_address = False


def run_browser(port: int, open_browser: bool = True, demo: bool = False) -> None:
    try:
        server = _Server(("127.0.0.1", port), _make_handler(Api(demo=demo), port))
    except OSError:
        raise SystemExit(f"La porta {port} è già in uso: TimeScreen è già aperto? Prova --port.")
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"TimeScreen su {url}  (Ctrl+C per uscire)")
    if open_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def run_window(demo: bool = False) -> None:
    import webview

    webview.create_window(
        "TimeScreen",
        str(UI_DIR / "index.html"),
        js_api=Api(demo=demo),
        width=1180,
        height=820,
        min_size=(720, 560),
    )
    webview.start()


def run_ui(browser: bool = False, port: int = 8765, open_browser: bool = True, demo: bool = False) -> None:
    if not browser:
        try:
            run_window(demo)
            return
        except ImportError:
            print("pywebview non installato: apro la UI nel browser.")
    run_browser(port, open_browser=open_browser, demo=demo)
