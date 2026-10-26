"""Icona nell'area di notifica (vicino all'orologio) per il logger.

Tutto con ctypes, senza librerie in più: una finestra nascosta riceve i clic
sull'icona e un timer di Windows fa girare il logger ogni pochi secondi, nello
stesso thread. Clic destro (o sinistro) apre il menu; doppio clic apre Daycast.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from pathlib import Path

from . import autostart, control
from .launcher import spawn
from .logger import Logger
from .paths import APP_NAME
from .settings import current_language

log = logging.getLogger("daycast.logger")

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

ASSETS = Path(__file__).resolve().parent / "assets"

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_NULL = 0x0000
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
WM_TRAY = WM_APP + 1

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x10
SM_CXSMICON = 49
MF_STRING, MF_GRAYED, MF_CHECKED, MF_SEPARATOR = 0x0, 0x1, 0x8, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80
MB_ICONINFORMATION = 0x40
TIMER_ID = 1

ID_OPEN, ID_PAUSE, ID_AUTOSTART, ID_QUIT = 101, 102, 104, 103


class GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.SetMenuDefaultItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

CLASS_NAME = control.CLASS_NAME


# testi del menu e del suggerimento; la lingua si legge dalle impostazioni a ogni uso
TEXT = {
    "en": {
        "recording": "Recording", "paused": "Paused", "open": "Open Daycast", "pause": "Pause",
        "resume": "Resume", "autostart": "Start with Windows", "quit": "Quit",
        "already": "Daycast is already recording: you'll find its icon next to the clock.",
    },
    "it": {
        "recording": "Registrazione attiva", "paused": "In pausa", "open": "Apri Daycast", "pause": "Metti in pausa",
        "resume": "Riprendi", "autostart": "Avvia con Windows", "quit": "Esci",
        "already": "Daycast sta già registrando: trovi l'icona vicino all'orologio.",
    },
}


def text(key: str) -> str:
    return TEXT.get(current_language(), TEXT["en"])[key]


def message_box(message: str) -> None:
    user32.MessageBoxW(None, message, APP_NAME, MB_ICONINFORMATION)


def _load_icon(name: str) -> int:
    size = user32.GetSystemMetrics(SM_CXSMICON)  # segue la scala del monitor
    return user32.LoadImageW(None, str(ASSETS / name), IMAGE_ICON, size, size, LR_LOADFROMFILE)


class TrayApp:
    def __init__(self, logger: Logger, interval: float):
        self.logger = logger
        self.interval_ms = int(interval * 1000)
        self.paused = False
        self.icons = {False: _load_icon("icon.ico"), True: _load_icon("icon-paused.ico")}
        self._proc = WNDPROC(self._wndproc)  # tenuto in vita: Windows lo richiama
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName=CLASS_NAME)
        user32.RegisterClassW(ctypes.byref(wc))
        # finestra normale ma mai mostrata: così riceve anche gli avvisi di
        # spegnimento e di riavvio di Esplora risorse, che le finestre "solo messaggi" non ricevono
        # il titolo permette all'interfaccia di trovare proprio questo logger (vedi control.py)
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, control.window_title(), 0, 0, 0, 0, 0, None, None, hinst, None)

    # ---------- icona ----------

    def _icon_data(self) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.icons[self.paused]
        nid.szTip = f"{APP_NAME}: {text('paused' if self.paused else 'recording')}"
        return nid

    def _show_icon(self, action: int = NIM_ADD) -> bool:
        return bool(shell32.Shell_NotifyIconW(action, ctypes.byref(self._icon_data())))

    # ---------- azioni ----------

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        if paused:
            self.logger.stop()  # chiude il periodo in corso
        log.info("pausa" if paused else "ripresa")
        self._show_icon(NIM_MODIFY)

    def open_ui(self) -> None:
        spawn("ui")

    def toggle_autostart(self) -> None:
        if autostart.is_enabled():
            autostart.disable()
            log.info("avvio con Windows disattivato")
        else:
            autostart.enable()
            log.info("avvio con Windows attivato")

    def quit(self) -> None:
        user32.DestroyWindow(self.hwnd)

    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        status = text("paused" if self.paused else "recording")
        user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 0, f"{APP_NAME} · {status}")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_OPEN, text("open"))
        user32.AppendMenuW(menu, MF_STRING, ID_PAUSE, text("resume" if self.paused else "pause"))
        checked = MF_CHECKED if autostart.is_enabled() else 0
        user32.AppendMenuW(menu, MF_STRING | checked, ID_AUTOSTART, text("autostart"))
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_QUIT, text("quit"))
        user32.SetMenuDefaultItem(menu, ID_OPEN, 0)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        # senza questo il menu non si chiude cliccando altrove (comportamento noto di Windows)
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        if cmd:
            self._command(cmd)

    def _command(self, cmd: int) -> None:
        if cmd == ID_OPEN:
            self.open_ui()
        elif cmd == ID_PAUSE:
            self.set_paused(not self.paused)
        elif cmd == ID_AUTOSTART:
            self.toggle_autostart()
        elif cmd == ID_QUIT:
            self.quit()

    # ---------- messaggi di Windows ----------

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TIMER:
                if not self.paused:
                    self.logger.tick()
                return 0
            if msg == WM_TRAY:
                event = lparam & 0xFFFF
                if event in (WM_RBUTTONUP, WM_LBUTTONUP):
                    self._menu()
                elif event == WM_LBUTTONDBLCLK:
                    self.open_ui()
                return 0
            if msg == WM_COMMAND:
                self._command(wparam & 0xFFFF)
                return 0
            if msg == control.WM_CONTROL:
                # dall'interfaccia: pausa, ripresa o solo una domanda sullo stato
                if wparam == control.CMD_PAUSE and not self.paused:
                    self.set_paused(True)
                elif wparam == control.CMD_RESUME and self.paused:
                    self.set_paused(False)
                return 1 if self.paused else 0
            if msg == self._taskbar_created:
                self._show_icon()  # Esplora risorse riavviato: l'icona va rimessa
                return 0
            if msg == WM_QUERYENDSESSION:
                return 1
            if msg == WM_ENDSESSION and wparam:
                self.logger.stop()  # spegnimento o disconnessione
                return 0
            if msg in (WM_CLOSE,):
                self.quit()
                return 0
            if msg == WM_DESTROY:
                user32.KillTimer(hwnd, TIMER_ID)
                self.logger.stop()
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._icon_data()))
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            log.exception("errore nella gestione di un messaggio")
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self) -> None:
        if not self._show_icon():
            log.warning("impossibile aggiungere l'icona nell'area di notifica")
        log.info("icona nell'area di notifica attiva")
        self.logger.tick()
        user32.SetTimer(self.hwnd, TIMER_ID, self.interval_ms, None)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        for icon in self.icons.values():
            if icon:
                user32.DestroyIcon(icon)
