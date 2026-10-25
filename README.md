**English** · [Italiano](README.it.md)

# TimeScreen

Predicts how much you will use your PC today, hour by hour, and which apps and
sites (YouTube, Reddit, …) you will open, with an uncertainty range.

> Current status: the **logger** records apps and sites and the **interface**
> shows the real data, with a baseline forecast. The forecasting model
> ([Timestral](https://mistral.ai/news/timestral/)) will come later.
>
> The interface is in Italian for now.

## Installation (app)

1. Download `TimeScreen-<version>-win64.zip` from the
   [Releases](https://github.com/Fede046/TimeScreen/releases) page and extract
   it wherever you like (for example in `Documents`).
2. Open `TimeScreen\TimeScreen.exe`.

On first launch, recording starts in the background (icon next to the clock)
and the window with your data opens. Closing the window keeps recording; to
stop it: icon → **Esci** (Quit). To start it at every sign-in: icon →
**Avvia con Windows** (Start with Windows).

Python is not required. You need Windows 10/11 with WebView2 (already included
in Windows 11). Windows may show a SmartScreen warning because the exe is not
signed: *More info* → *Run anyway*.

Your data stays in `%LOCALAPPDATA%\TimeScreen`; to uninstall, quit from the
icon, turn off "Start with Windows" and delete the folder.

## Running from source

Requires Python 3.10+ on Windows.

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m timescreen
```

Same as the exe: it starts the logger if it is not already running and opens
the window (pywebview, using Windows' WebView2). `python -m timescreen ui`
opens only the window. To work on the UI in a browser:

```bash
python -m timescreen --browser
```

The interface uses the logger's data as soon as there is any; until then it
shows sample data. With `--demo` it always shows the sample data.

## Forecast

Until the model is in place, the forecast is a simple baseline: for each hour,
the average of the same weekdays recorded so far (with fewer than 3, it uses
weekdays or weekend days, then all days); the range goes from the 10th to the
90th percentile of those days. Each day is predicted only from the days before
it, so "was predicted" is a fair comparison. Forecasts start after the first
full day of data and improve as the weeks go by.

## Logger

Records in the background which app or site you are using. It is lightweight:
about 20 MB of RAM from source (about 45 MB in the exe) and practically zero CPU.

It runs as a background app with an icon in the notification area, next to the
clock (if you can't see it, it is among the hidden icons under the ^ arrow).
Click the icon for the menu: **Apri TimeScreen** (Open), **Metti in pausa** /
**Riprendi** (Pause / Resume), **Avvia con Windows** (Start with Windows),
**Esci** (Quit). Double-click opens TimeScreen. While paused the icon turns grey.

```bash
python -m timescreen log        # start the logger with the icon (--console to stay in the terminal)
python -m timescreen report     # today's summary (--date YYYY-MM-DD for another day)
python -m timescreen autostart  # start it at every Windows sign-in, without a console (--off to remove)
```

- Every 2 seconds it checks the foreground window; it writes to disk only when
  something changes, plus an update every 30 seconds.
- **Sites**: in browsers (Chrome, Edge, Firefox, Brave, Opera, Vivaldi…) it
  reads the active tab's address from the address bar (Windows UI Automation)
  and keeps the domain: every site gets its own entry (`ansa.it`,
  `unibo.it`…), with subdomains grouped together (`virtuale.unibo.it` →
  `unibo.it`). Well-known sites get a friendly name (YouTube, Gmail, Reddit…).
  The address bar is read again only when the tab changes; if it can't be
  read, the window title is used. Names and rules are in `timescreen/sites.py`.
- **Privacy**: only the app name or the site's domain and the times are saved,
  never full addresses or window titles. Everything stays in
  `%LOCALAPPDATA%\TimeScreen\usage.db`.
- **Idle time**: after 2 minutes without keyboard and mouse it stops counting,
  unless something keeps the screen on (a video, a film). Sleep and switches
  shorter than 3 seconds are not counted.

## Reading the charts

Several apps can be in use in the same hour (music while you work, Discord
while you play). With the **Tutte** (All) filter, the height of each bar is the
time you used the PC, so never more than 60 minutes in an hour, and each
category takes a share proportional to its use. The tooltip shows each
category's actual minutes and its percentage.

## Categories

You decide the categories, from the **Categorie** button: you can create them
(up to 8, as many as there are distinguishable colours), rename them, delete
them and assign each app or site. Until you assign them, apps stay
*Da classificare* (Unclassified). Your choices are saved in
`%LOCALAPPDATA%\TimeScreen\settings.json` (for testing you can point to another
file with the `TIMESCREEN_SETTINGS` variable).

## Project structure

| Path | What it does |
|---|---|
| `timescreen/cli.py` | commands: `start`, `ui`, `log`, `report`, `autostart` |
| `timescreen/app.py` | pywebview window, or local server with `--browser` |
| `timescreen/logger.py` | logger loop: foreground window, idle time, sleep |
| `timescreen/tray.py` | notification-area icon with the logger's menu |
| `timescreen/launcher.py` | relaunches TimeScreen (from source or the exe) and checks whether the logger is running |
| `timescreen/winapi.py` | Win32 calls via ctypes |
| `timescreen/sites.py` | from domain (or title) to site name |
| `timescreen/browser_url.py` | reads the address bar with UI Automation |
| `timescreen/db.py` | SQLite database and minutes per hour |
| `timescreen/settings.py` | user categories and app assignments |
| `timescreen/real_data.py` | dashboard from the logger's data, with the baseline forecast |
| `timescreen/mock_data.py` | sample data; its output format is the contract with the UI |
| `timescreen/ui/` | HTML/CSS/JS interface, no external libraries |
| `timescreen/assets/` | temporary logo icons (regenerate with `python tools/make_icons.py`) |
| `packaging/` | PyInstaller spec and build script |

## Tests

```bash
python -m unittest discover -s tests -t .
```

## Building the exe and the zip

```bash
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python packaging\build.py
```

This creates `dist\TimeScreen\TimeScreen.exe` and
`dist\TimeScreen-<version>-win64.zip` (PyInstaller, a folder rather than a
single exe: it starts faster and antivirus software complains less). The
version is in `timescreen/__init__.py`.

## Roadmap

1. ~~**Interface** with sample data~~
2. ~~Lightweight background **logger**, with site recognition~~
3. ~~**Connect the interface to the logger's real data**, with a baseline forecast~~
4. **Forecast** with Timestral, started only when needed (it doesn't stay in memory) ← next step
