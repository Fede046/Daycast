# TimeScreen

Prevede quanto userai il PC oggi, ora per ora, e quali app e siti (YouTube,
Reddit, …) aprirai, con un intervallo di incertezza.

> Stato attuale: il **logger** registra davvero app e siti; l'**interfaccia**
> mostra ancora dati di esempio. Il collegamento tra i due e il modello di
> previsione ([Timestral](https://mistral.ai/news/timestral/)) arriveranno dopo.

## Avvio

Serve Python 3.10+ su Windows.

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m timescreen
```

Si apre una finestra nativa (pywebview, usa WebView2 di Windows).
Per lavorare sulla UI dal browser:

```bash
python -m timescreen --browser
```

## Logger

Registra in background quale app o sito usi. È leggero: solo `ctypes` e
`sqlite3`, circa 20 MB di RAM e CPU praticamente a zero.

```bash
python -m timescreen log        # avvia il logger (Ctrl+C per fermarlo)
python -m timescreen report     # riepilogo di oggi (--date AAAA-MM-GG per un altro giorno)
python -m timescreen autostart  # lo avvia a ogni accesso a Windows, senza console (--off per toglierlo)
```

- Ogni 2 secondi guarda la finestra in primo piano; scrive su disco solo quando
  cambia qualcosa, più un aggiornamento ogni 30 secondi.
- **Siti**: nei browser (Chrome, Edge, Firefox, Brave, Opera, Vivaldi…) il sito
  si riconosce dal titolo della scheda attiva. Quelli non riconosciuti finiscono
  in *Altri siti web*; l'elenco è in `timescreen/sites.py`.
- **Privacy**: si salvano solo il nome dell'app o del sito e gli orari, mai i
  titoli delle finestre. Tutto resta in `%LOCALAPPDATA%\TimeScreen\usage.db`.
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
| `timescreen/cli.py` | comandi: `ui`, `log`, `report`, `autostart` |
| `timescreen/app.py` | finestra pywebview, o server locale con `--browser` |
| `timescreen/logger.py` | ciclo del logger: finestra attiva, inattività, sospensione |
| `timescreen/winapi.py` | chiamate Win32 via ctypes |
| `timescreen/sites.py` | dal titolo del browser al nome del sito |
| `timescreen/db.py` | database SQLite e minuti per ora |
| `timescreen/settings.py` | categorie dell'utente e assegnazione delle app |
| `timescreen/mock_data.py` | dati finti; il formato restituito è il contratto con la UI |
| `timescreen/ui/` | interfaccia in HTML/CSS/JS, senza librerie esterne |

## Test

```bash
python -m unittest discover -s tests -t .
```

## Piano

1. ~~**Interfaccia** con dati di esempio~~
2. ~~**Logger** leggero in background, con riconoscimento dei siti~~
3. **Collegare l'interfaccia ai dati veri** del logger ← prossimo passo
4. **Previsione** con Timestral, avviata solo quando serve (non resta in memoria)
