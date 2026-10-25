import unittest

from timescreen.sites import OTHER_SITES, site_from_title, strip_browser_suffix


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


if __name__ == "__main__":
    unittest.main()
