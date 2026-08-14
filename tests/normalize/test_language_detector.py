import unittest

from semantica.normalize.language_detector import (
    LANGDETECT_AVAILABLE,
    LanguageDetector,
)


class TestLanguageDetector(unittest.TestCase):
    def setUp(self):
        self.detector = LanguageDetector()

    @unittest.skipUnless(LANGDETECT_AVAILABLE, "langdetect is not installed")
    def test_detect_language(self):
        # English
        self.assertEqual(
            self.detector.detect("This is a simple English sentence."), "en"
        )
        # French
        self.assertEqual(
            self.detector.detect("Ceci est une phrase française simple."), "fr"
        )
        # German
        self.assertEqual(
            self.detector.detect("Dies ist ein einfacher deutscher Satz."), "de"
        )

    def test_detect_short_text(self):
        # Should return default for very short text
        self.assertEqual(self.detector.detect("Hi"), "en")

    @unittest.skipUnless(LANGDETECT_AVAILABLE, "langdetect is not installed")
    def test_detect_with_confidence(self):
        lang, conf = self.detector.detect_with_confidence(
            "This is definitely an English sentence."
        )
        self.assertEqual(lang, "en")
        self.assertGreater(conf, 0.5)

    def test_get_language_name(self):
        self.assertEqual(self.detector.get_language_name("en"), "English")
        self.assertEqual(self.detector.get_language_name("fr"), "French")
        self.assertEqual(self.detector.get_language_name("xx"), "XX")


if __name__ == "__main__":
    unittest.main()
