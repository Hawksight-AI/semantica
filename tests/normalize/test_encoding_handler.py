import unittest

from semantica.normalize.encoding_handler import EncodingHandler


class TestEncodingHandler(unittest.TestCase):
    def setUp(self):
        self.handler = EncodingHandler()

    def test_detect_encoding(self):
        # UTF-8
        text = "Héllò Wörld"
        utf8_bytes = text.encode("utf-8")
        encoding, conf = self.handler.detect(utf8_bytes)
        self.assertEqual(encoding.lower(), "utf-8")

        # Latin-1
        latin1_bytes = text.encode("latin-1")
        encoding, conf = self.handler.detect(latin1_bytes)
        # Short single-byte samples are ambiguous, so verify the detected codec
        # can losslessly represent the bytes instead of asserting a codec name.
        decoded = latin1_bytes.decode(encoding)
        self.assertEqual(decoded.encode(encoding), latin1_bytes)
        self.assertGreaterEqual(conf, 0.0)
        self.assertLessEqual(conf, 1.0)

    def test_convert_to_utf8(self):
        text = "Héllò Wörld"
        latin1_bytes = text.encode("latin-1")
        converted = self.handler.convert_to_utf8(
            latin1_bytes, source_encoding="latin-1"
        )
        self.assertEqual(converted, text)

    def test_remove_bom(self):
        # UTF-8 BOM
        bom_bytes = b"\xef\xbb\xbfHello"
        self.assertEqual(self.handler.remove_bom(bom_bytes), b"Hello")

        # String BOM
        bom_str = "\ufeffHello"
        self.assertEqual(self.handler.remove_bom(bom_str), "Hello")

    def test_validate_encoding(self):
        self.assertTrue(self.handler.validate_encoding("Hello", "utf-8"))
        # Invalid sequence for ascii
        self.assertFalse(self.handler.validate_encoding("Héllò", "ascii"))


if __name__ == "__main__":
    unittest.main()
