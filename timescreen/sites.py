"""Riconosce il sito dal titolo della finestra del browser.

Il titolo completo non viene mai salvato: da qui esce solo il nome del sito
(es. "YouTube") oppure "Altri siti web".
"""

from __future__ import annotations

import re

# eseguibile -> nome del browser
BROWSERS = {
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave",
    "opera.exe": "Opera",
    "opera_gx.exe": "Opera GX",
    "vivaldi.exe": "Vivaldi",
    "arc.exe": "Arc",
    "zen.exe": "Zen",
}

OTHER_SITES = "Altri siti web"

# la parte finale che i browser aggiungono al titolo; Edge con più schede
# aggiunge anche "and 3 more pages - <profilo>"
_BROWSER_SUFFIX = re.compile(
    r"((\s+and \d+ more pages?|\s+e altre \d+ pagine)(\s[-—–]\s[^-—–]+)?)?"
    r"\s[-—–]\s(Google Chrome|Mozilla Firefox[^-—–]*|Firefox|Microsoft​?\s?Edge|Brave|Opera( GX)?|Vivaldi|Arc|Zen Browser)$",
    re.IGNORECASE,
)
# i separatori tra le parti del titolo: "Video - YouTube", "Home / X", "Post : r/italy"
_SEPARATORS = re.compile(r"\s[-—–|·•/:]\s")

# (nome del sito, parti di titolo che lo identificano, espressione regolare in più)
SITES = [
    ("YouTube", {"youtube", "youtube music"}, None),
    ("Reddit", {"reddit", "reddit - dive into anything"}, r"(^|\s)r/\w+"),
    ("Netflix", {"netflix"}, None),
    ("Prime Video", {"prime video", "amazon prime video"}, None),
    ("Disney+", {"disney+"}, None),
    ("Twitch", {"twitch"}, None),
    ("Instagram", {"instagram"}, r"\bInstagram\b"),
    ("TikTok", {"tiktok"}, None),
    ("Facebook", {"facebook"}, None),
    ("X", {"x", "twitter"}, None),
    ("LinkedIn", {"linkedin"}, None),
    ("WhatsApp Web", {"whatsapp"}, None),
    ("Telegram Web", {"telegram", "telegram web"}, None),
    ("Gmail", {"gmail"}, r"\bGmail\b"),
    ("Outlook", {"outlook", "posta - outlook", "mail - outlook"}, None),
    ("GitHub", {"github"}, None),
    ("Stack Overflow", {"stack overflow"}, None),
    ("ChatGPT", {"chatgpt"}, None),
    ("Claude", {"claude"}, None),
    ("Wikipedia", set(), r"\bWikipedia\b"),
    ("Google Docs", {"google docs", "documenti google", "google sheets", "fogli google", "google slides", "presentazioni google"}, None),
    ("Spotify", {"spotify", "spotify - web player"}, None),
    ("Amazon", {"amazon.it", "amazon.com", "amazon"}, None),
]

_COMPILED = [(name, tokens, re.compile(rx, re.IGNORECASE) if rx else None) for name, tokens, rx in SITES]


def strip_browser_suffix(title: str) -> str:
    return _BROWSER_SUFFIX.sub("", title.strip())


def site_from_title(title: str) -> str:
    """Il sito della scheda attiva, o OTHER_SITES se non è tra quelli noti."""
    clean = strip_browser_suffix(title)
    if not clean:
        return OTHER_SITES
    # il contatore di notifiche "(3) Titolo" non fa parte del nome
    clean = re.sub(r"^\(\d+\+?\)\s*", "", clean)
    parts = {p.strip().casefold() for p in _SEPARATORS.split(clean)}
    parts.add(clean.casefold())
    for name, tokens, rx in _COMPILED:
        if parts & tokens or (rx and rx.search(clean)):
            return name
    return OTHER_SITES


# ---------- dal dominio (barra degli indirizzi) ----------

# nomi leggibili per i siti più comuni; si cerca prima l'host intero
# (mail.google.com), poi il dominio principale (google.com)
DOMAIN_NAMES = {
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "music.youtube.com": "YouTube Music",
    "reddit.com": "Reddit",
    "netflix.com": "Netflix",
    "primevideo.com": "Prime Video",
    "disneyplus.com": "Disney+",
    "twitch.tv": "Twitch",
    "instagram.com": "Instagram",
    "tiktok.com": "TikTok",
    "facebook.com": "Facebook",
    "x.com": "X",
    "twitter.com": "X",
    "linkedin.com": "LinkedIn",
    "web.whatsapp.com": "WhatsApp Web",
    "web.telegram.org": "Telegram Web",
    "mail.google.com": "Gmail",
    "docs.google.com": "Google Docs",
    "drive.google.com": "Google Drive",
    "calendar.google.com": "Google Calendar",
    "meet.google.com": "Google Meet",
    "google.com": "Google",
    "google.it": "Google",
    "outlook.live.com": "Outlook",
    "outlook.office.com": "Outlook",
    "github.com": "GitHub",
    "stackoverflow.com": "Stack Overflow",
    "chatgpt.com": "ChatGPT",
    "chat.openai.com": "ChatGPT",
    "claude.ai": "Claude",
    "wikipedia.org": "Wikipedia",
    "open.spotify.com": "Spotify",
    "amazon.it": "Amazon",
    "amazon.com": "Amazon",
}

# domini di secondo livello usati come suffisso (bbc.co.uk -> bbc.co.uk, non co.uk)
_SECOND_LEVEL = {"co", "com", "ac", "gov", "org", "edu", "net", "gv", "or", "ne"}
_INTERNAL = re.compile(r"^(chrome|edge|brave|opera|vivaldi|about|moz-extension|chrome-extension|view-source):", re.I)
_HOST = re.compile(r"^(?:https?://)?(?:[^@/\s]+@)?([a-z0-9.-]+\.[a-z]{2,}|localhost|\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?(?:[/?#]|$)", re.I)


def registrable_domain(host: str) -> str:
    """Il dominio "principale": virtuale.unibo.it -> unibo.it, news.bbc.co.uk -> bbc.co.uk."""
    labels = host.lower().strip(".").split(".")
    if labels[-1].isdigit() or len(labels) <= 2:
        return ".".join(labels)
    if len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def site_from_url(url: str) -> str | None:
    """Il nome del sito dall'indirizzo, o None se non è un indirizzo web
    (pagina interna del browser, testo che si sta scrivendo nella barra...)."""
    url = url.strip()
    if not url or _INTERNAL.match(url):
        return None
    if url.lower().startswith("file:"):
        return "File locali"
    m = _HOST.match(url)
    if not m:
        return None
    host = m.group(1).lower()
    if host.startswith("www."):
        host = host[4:]
    domain = registrable_domain(host)
    return DOMAIN_NAMES.get(host) or DOMAIN_NAMES.get(domain) or domain


def site_for(title: str, url: str | None) -> str:
    """Il sito della scheda attiva: dall'indirizzo se c'è, altrimenti dal titolo."""
    if url:
        name = site_from_url(url)
        if name:
            return name
    return site_from_title(title)
