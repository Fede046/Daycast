# TimeScreen

Prevede quanto userai il PC oggi, ora per ora, e quali app e siti (YouTube,
Reddit, …) aprirai, con un intervallo di incertezza.

> Stato attuale: **solo interfaccia, con dati di esempio**. Il logger delle
> finestre e il modello di previsione ([Timestral](https://mistral.ai/news/timestral/))
> arriveranno dopo.

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
| `timescreen/app.py` | finestra pywebview, o server locale con `--browser` |
| `timescreen/settings.py` | categorie dell'utente e assegnazione delle app |
| `timescreen/mock_data.py` | dati finti; il formato restituito è il contratto con la UI |
| `timescreen/ui/` | interfaccia in HTML/CSS/JS, senza librerie esterne |

## Piano

1. **Interfaccia** con dati finti ← siamo qui
2. **Logger** leggero in background: finestra attiva + titolo ogni 2–3 s,
   solo `ctypes` e `sqlite3`, scrive solo quando qualcosa cambia
3. **Siti** riconosciuti dal titolo della finestra del browser, raggruppati in categorie
4. **Previsione** con Timestral, avviata solo quando serve (non resta in memoria)
