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
