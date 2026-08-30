import unittest

from semantica.normalize.language_detector import (
    LANGDETECT_AVAILABLE,
    UNKNOWN_LANGUAGE,
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

    def test_detect_short_text_returns_unknown(self):
        # Undetected input must not masquerade as a detected language
        self.assertEqual(self.detector.detect("Hi"), UNKNOWN_LANGUAGE)

    def test_configured_default_language_restores_assumption(self):
        detector = LanguageDetector(default_language="en")
        self.assertEqual(detector.detect("Hi"), "en")

    @unittest.skipUnless(LANGDETECT_AVAILABLE, "langdetect is not installed")
    def test_detect_with_confidence(self):
        lang, conf = self.detector.detect_with_confidence(
            "This is definitely an English sentence."
        )
        self.assertEqual(lang, "en")
        self.assertGreater(conf, 0.5)

    def test_default_min_text_length_preserved(self):
        # Backward compatibility: default threshold stays at 10
        self.assertEqual(self.detector.min_text_length, 10)
        self.assertEqual(self.detector.detect("Short txt"), UNKNOWN_LANGUAGE)

    def test_short_text_fallback_has_zero_confidence(self):
        # Fallback must be distinguishable from a genuine detection
        lang, conf = self.detector.detect_with_confidence("Hi")
        self.assertEqual((lang, conf), (UNKNOWN_LANGUAGE, 0.0))
        self.assertEqual(
            self.detector.detect_multiple("Hi"), [(UNKNOWN_LANGUAGE, 0.0)]
        )

    @unittest.skipUnless(LANGDETECT_AVAILABLE, "langdetect is not installed")
    def test_short_non_latin_text_with_configured_threshold(self):
        # 9 stripped chars: below the default threshold, falls back to unknown
        text = "你好，这是中文文本"
        self.assertEqual(self.detector.detect(text), UNKNOWN_LANGUAGE)

        # A configured threshold lets short CJK text reach the detector
        detector = LanguageDetector(min_text_length=5)
        self.assertTrue(detector.detect(text).startswith("zh"))

        lang, conf = detector.detect_with_confidence(text)
        self.assertTrue(lang.startswith("zh"))
        self.assertGreater(conf, 0.5)

        languages = detector.detect_multiple(text)
        self.assertTrue(languages[0][0].startswith("zh"))

    @unittest.skipUnless(LANGDETECT_AVAILABLE, "langdetect is not installed")
    def test_min_text_length_per_call_override(self):
        text = "你好，这是中文文本"
        self.assertEqual(self.detector.detect(text), UNKNOWN_LANGUAGE)
        self.assertTrue(
            self.detector.detect(text, min_text_length=5).startswith("zh")
        )

    def test_min_text_length_still_guards_empty_text(self):
        detector = LanguageDetector(min_text_length=0)
        self.assertEqual(detector.detect(""), UNKNOWN_LANGUAGE)
        self.assertEqual(
            detector.detect_with_confidence(""), (UNKNOWN_LANGUAGE, 0.0)
        )

    def test_invalid_min_text_length_degrades_to_fallback(self):
        # Invalid values must not raise TypeError during the length check
        for invalid in (None, "abc", object()):
            detector = LanguageDetector(min_text_length=invalid)
            self.assertEqual(detector.min_text_length, 10)
            self.assertEqual(detector.detect("Hi"), UNKNOWN_LANGUAGE)

        # Invalid per-call override falls back to the instance value
        detector = LanguageDetector(min_text_length=3)
        self.assertEqual(
            detector.detect("Hi", min_text_length=None), UNKNOWN_LANGUAGE
        )

        # Numeric-ish values are coerced; negatives clamp to zero
        self.assertEqual(LanguageDetector(min_text_length="5").min_text_length, 5)
        self.assertEqual(LanguageDetector(min_text_length=-1).min_text_length, 0)
        self.assertEqual(LanguageDetector(min_text_length=2.9).min_text_length, 2)

    def test_detect_language_wrapper_does_not_mutate_global_config(self):
        from semantica.normalize.config import normalize_config
        from semantica.normalize.methods import detect_language

        original = dict(normalize_config.get_method_config("language"))
        normalize_config.set_method_config("language", default_language="en")
        try:
            detect_language("Hi", min_text_length=1)
            self.assertNotIn(
                "min_text_length",
                normalize_config.get_method_config("language"),
            )
        finally:
            normalize_config.set_method_config("language", **original)

    def test_get_language_name(self):
        self.assertEqual(self.detector.get_language_name("en"), "English")
        self.assertEqual(self.detector.get_language_name("fr"), "French")
        self.assertEqual(
            self.detector.get_language_name(UNKNOWN_LANGUAGE), "Unknown"
        )
        self.assertEqual(self.detector.get_language_name("xx"), "XX")


if __name__ == "__main__":
    unittest.main()
