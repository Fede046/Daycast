import unittest

from timescreen.sites import OTHER_SITES, site_for, site_from_title, site_from_url, strip_browser_suffix


class StripSuffixTest(unittest.TestCase):
    def test_browsers(self):
        cases = {
            "Video divertente - YouTube - Google Chrome": "Video divertente - YouTube",
            "Video divertente - YouTube — Mozilla Firefox": "Video divertente - YouTube",
            "Video divertente - YouTube — Mozilla Firefox Private Browsing": "Video divertente - YouTube",
            "Video divertente - YouTube - Microsoft​ Edge": "Video divertente - YouTube",
            "Video divertente - YouTube and 3 more pages - Personale - Microsoft​ Edge": "Video divertente - YouTube",
            "Video divertente - YouTube - Brave": "Video divertente - YouTube",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(strip_browser_suffix(title), expected)


class SiteFromTitleTest(unittest.TestCase):
    def test_known_sites(self):
        cases = {
            "(3) Come fare la pasta - YouTube - Google Chrome": "YouTube",
            "r/italy - Google Chrome": "Reddit",
            "Che ne pensate? : r/italy - Google Chrome": "Reddit",
            "Reddit - Dive into anything - Microsoft​ Edge": "Reddit",
            "Home / X - Google Chrome": "X",
            "Netflix - Google Chrome": "Netflix",
            "Posta in arrivo (12) - mario@gmail.com - Gmail - Google Chrome": "Gmail",
            "Fede046/TimeScreen: previsioni - GitHub - Google Chrome": "GitHub",
            "Python (linguaggio) - Wikipedia - Google Chrome": "Wikipedia",
            "Budget 2026 - Fogli Google - Google Chrome": "Google Docs",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(site_from_title(title), expected)

    def test_search_page_is_not_the_site(self):
        # cercare "youtube" su Google non è usare YouTube
        self.assertEqual(site_from_title("youtube downloader - Cerca con Google - Google Chrome"), OTHER_SITES)

    def test_unknown_and_empty(self):
        self.assertEqual(site_from_title("Ricetta del tiramisù - Google Chrome"), OTHER_SITES)
        self.assertEqual(site_from_title(""), OTHER_SITES)
        self.assertEqual(site_from_title("Google Chrome"), OTHER_SITES)


class SiteFromUrlTest(unittest.TestCase):
    def test_any_site_gets_its_domain(self):
        cases = {
            "www.ansa.it/sito/notizie/politica/politica.shtml": "ansa.it",
            "https://www.unibo.it/it/studiare": "unibo.it",
            "virtuale.unibo.it/course/view.php?id=123": "unibo.it",  # i sottodomini vanno insieme
            "corsi.unibo.it/laurea/informatica": "unibo.it",
            "news.bbc.co.uk/sport": "bbc.co.uk",
            "localhost:8765/": "localhost",
            "file:///C:/Users/me/tesi.pdf": "File locali",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(site_from_url(url), expected)

    def test_known_sites_get_a_friendly_name(self):
        self.assertEqual(site_from_url("youtube.com/watch?v=abc"), "YouTube")
        self.assertEqual(site_from_url("mail.google.com/mail/u/0/#inbox"), "Gmail")
        self.assertEqual(site_from_url("www.google.com/search?q=meteo"), "Google")
        self.assertEqual(site_from_url("it.wikipedia.org/wiki/Bologna"), "Wikipedia")

    def test_not_a_web_address(self):
        for url in ("chrome://downloads", "edge://settings", "about:blank", "ciao come stai", ""):
            with self.subTest(url=url):
                self.assertIsNone(site_from_url(url))

    def test_title_is_the_fallback(self):
        # pagina interna o barra illeggibile: si guarda il titolo
        self.assertEqual(site_for("Video - YouTube - Google Chrome", None), "YouTube")
        self.assertEqual(site_for("Nuova scheda - Google Chrome", "chrome://newtab"), OTHER_SITES)
        # con l'indirizzo, il titolo non conta più
        self.assertEqual(site_for("Informatica - Laurea - Bologna - Google Chrome", "corsi.unibo.it/laurea"), "unibo.it")


if __name__ == "__main__":
    unittest.main()
