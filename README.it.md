[English](README.md) · **Italiano**

# TimeScreen

Prevede quanto userai il PC oggi, ora per ora, e quali app e siti (YouTube,
Reddit, …) aprirai, con un intervallo di incertezza.

> Stato attuale: il **logger** registra app e siti e l'**interfaccia** mostra i
> dati veri, con una previsione base. Il modello di previsione
> ([Timestral](https://mistral.ai/news/timestral/)) arriverà dopo.

## Installazione (app)

1. Scarica `TimeScreen-<versione>-win64.zip` dalla pagina delle
   [Release](https://github.com/Fede046/TimeScreen/releases) ed estrailo dove
   vuoi (ad esempio in `Documenti`).
2. Apri `TimeScreen\TimeScreen.exe`.

Al primo avvio parte la registrazione in background (icona vicino
all'orologio) e si apre la finestra con i dati. Chiudendo la finestra la
registrazione continua; per fermarla: icona → **Esci**.

Nella finestra, il pallino in alto mostra lo stato della registrazione
(attiva, in pausa, spenta). Cliccandolo, o con l'ingranaggio, si aprono le
**Impostazioni**:

- **Registrazione**: metti in pausa, riprendi, o avviala se è spenta.
- **Avvia TimeScreen con Windows**: la registrazione parte da sola a ogni
  accesso. Una volta attivo, TimeScreen compare anche in Impostazioni di
  Windows → App → Avvio e in Gestione attività → App di avvio; se lo spegni
  da lì, l'interruttore di TimeScreen si aggiorna.
- **Cartella dei dati**: apre `%LOCALAPPDATA%\TimeScreen`.

Le stesse voci (pausa, avvio con Windows) ci sono nel menu dell'icona.

Non serve Python. Serve Windows 10/11 con WebView2 (già presente in Windows 11).
Windows potrebbe mostrare un avviso SmartScreen perché l'exe non è firmato:
*Ulteriori informazioni* → *Esegui comunque*.

I dati restano in `%LOCALAPPDATA%\TimeScreen`; per disinstallare basta uscire
dall'icona, togliere "Avvia con Windows" e cancellare la cartella.

## Avvio da sorgente

Serve Python 3.10+ su Windows.

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m timescreen
```

Come l'exe: avvia il logger se non gira già e apre la finestra (pywebview,
usa WebView2 di Windows). `python -m timescreen ui` apre solo la finestra.
Per lavorare sulla UI dal browser:

```bash
python -m timescreen --browser
```

L'interfaccia usa i dati del logger appena ce ne sono; prima mostra dati di
esempio. Con `--demo` si vedono sempre quelli di esempio.

## Previsione

Finché non c'è il modello, la previsione è una base semplice: per ogni ora, la
media degli stessi giorni della settimana registrati (con meno di 3, si usano
i giorni feriali o del weekend, poi tutti); l'intervallo va dal 10° al 90°
percentile di quei giorni. Ogni giorno viene previsto solo con i giorni
precedenti, così "era previsto" è un confronto onesto. Le previsioni partono
dopo il primo giorno completo di dati e migliorano con il passare delle
settimane.

## Logger

Registra in background quale app o sito usi. È leggero: circa 20 MB di RAM da
sorgente (circa 45 MB nell'exe) e CPU praticamente a zero.

Gira come app in background con un'icona nell'area di notifica, vicino
all'orologio (se non la vedi, è tra le icone nascoste sotto la freccia ^).
Clic sull'icona per il menu: **Apri TimeScreen**, **Metti in pausa** /
**Riprendi**, **Avvia con Windows**, **Esci**. Doppio clic apre TimeScreen.
In pausa l'icona diventa grigia.

```bash
python -m timescreen log        # avvia il logger con l'icona (--console per restare nel terminale)
python -m timescreen report     # riepilogo di oggi (--date AAAA-MM-GG per un altro giorno)
python -m timescreen autostart  # lo avvia a ogni accesso a Windows, senza console (--off per toglierlo)
```

- Ogni 2 secondi guarda la finestra in primo piano; scrive su disco solo quando
  cambia qualcosa, più un aggiornamento ogni 30 secondi.
- **Siti**: nei browser (Chrome, Edge, Firefox, Brave, Opera, Vivaldi…) legge
  l'indirizzo della scheda attiva dalla barra (UI Automation di Windows) e ne
  tiene il dominio: ogni sito ha la sua voce (`ansa.it`, `unibo.it`…), con i
  sottodomini raggruppati (`virtuale.unibo.it` → `unibo.it`). I siti più noti
  hanno un nome leggibile (YouTube, Gmail, Reddit…). La barra si rilegge solo
  quando cambia la scheda; se non si riesce a leggerla si usa il titolo.
  Nomi e regole sono in `timescreen/sites.py`.
- **Privacy**: si salvano solo il nome dell'app o il dominio del sito e gli
  orari, mai indirizzi completi o titoli delle finestre. Tutto resta in
  `%LOCALAPPDATA%\TimeScreen\usage.db`.
- **Inattività**: dopo 2 minuti senza tastiera e mouse non conta più, a meno
  che qualcosa tenga acceso lo schermo (un video, un film). Sospensioni e
  passaggi più brevi di 3 secondi non vengono contati.

## Come leggere i grafici

Più app possono essere in uso nella stessa ora (musica mentre lavori, Discord
mentre giochi). Con il filtro **Tutte** l'altezza di ogni barra è il tempo in
cui hai usato il PC, quindi mai più di 60 minuti in un'ora, e ogni categoria ne
occupa una quota proporzionale al suo uso. Il tooltip mostra i minuti reali di
ogni categoria e la percentuale.

## Categorie

Le categorie le decidi tu, dal pulsante **Categorie**: puoi crearle (massimo 8,
tanti quanti i colori distinguibili), rinominarle, eliminarle e assegnare ogni
app o sito. Finché non le assegni, le app restano *Da classificare*.
Le scelte si salvano in `%LOCALAPPDATA%\TimeScreen\settings.json`
(per le prove si può usare un altro file con la variabile `TIMESCREEN_SETTINGS`).

## Struttura

| Percorso | Cosa fa |
|---|---|
| `timescreen/cli.py` | comandi: `start`, `ui`, `log`, `report`, `autostart` |
| `timescreen/app.py` | finestra pywebview, o server locale con `--browser` |
| `timescreen/logger.py` | ciclo del logger: finestra attiva, inattività, sospensione |
| `timescreen/tray.py` | icona nell'area di notifica con il menu del logger |
| `timescreen/launcher.py` | rilancia TimeScreen (da sorgente o dall'exe) e controlla se il logger gira |
| `timescreen/control.py` | pausa, ripresa e stato del logger in esecuzione, per l'interfaccia |
| `timescreen/winapi.py` | chiamate Win32 via ctypes |
| `timescreen/sites.py` | dal dominio (o dal titolo) al nome del sito |
| `timescreen/browser_url.py` | legge la barra degli indirizzi con UI Automation |
| `timescreen/db.py` | database SQLite e minuti per ora |
| `timescreen/settings.py` | categorie dell'utente e assegnazione delle app |
| `timescreen/real_data.py` | dashboard dai dati del logger, con la previsione base |
| `timescreen/mock_data.py` | dati di esempio; il formato restituito è il contratto con la UI |
| `timescreen/ui/` | interfaccia in HTML/CSS/JS, senza librerie esterne |
| `timescreen/assets/` | icone del logo provvisorio (rigenerabili con `python tools/make_icons.py`) |
| `packaging/` | spec di PyInstaller e script di build |

## Test

```bash
python -m unittest discover -s tests -t .
```

## Creare l'exe e lo zip

```bash
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python packaging\build.py
```

Crea `dist\TimeScreen\TimeScreen.exe` e `dist\TimeScreen-<versione>-win64.zip`
(PyInstaller, una cartella invece di un exe unico: si apre più in fretta e
gli antivirus si lamentano meno). La versione è in `timescreen/__init__.py`.

## Piano

1. ~~**Interfaccia** con dati di esempio~~
2. ~~**Logger** leggero in background, con riconoscimento dei siti~~
3. ~~**Collegare l'interfaccia ai dati veri** del logger, con una previsione base~~
4. **Previsione** con Timestral, avviata solo quando serve (non resta in memoria) ← prossimo passo
