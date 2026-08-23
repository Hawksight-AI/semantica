"""Construction coverage for the parse module's public parser classes.

Regression tests for #1014: ``ExcelParser.__init__`` called ``get_progress_tracker()``
without importing it, so every instantiation raised ``NameError``. The class was
covered by an import-only test, which passes regardless of whether ``__init__``
works, so nothing caught it. #530 was the same bug in ``SimilarityCalculator``.

These tests deliberately do **not** patch ``get_logger``/``get_progress_tracker``.
``tests/parse/test_parse_comprehensive.py`` patches both into every parse module
that exposes them, which would mock away the exact interaction under test here and
let the regression back in silently.
"""

import unittest

import semantica.parse as parse_module
from semantica.parse.excel_parser import ExcelParser


def _exported_parser_classes():
    """Public parser classes, taken from the package's own ``__all__``.

    Driven off ``__all__`` rather than a hand-written list so a parser added later
    is covered without anyone remembering to update this file.
    """
    return [
        (name, getattr(parse_module, name))
        for name in parse_module.__all__
        if name.endswith("Parser")
    ]


class TestExcelParserConstruction(unittest.TestCase):
    """ExcelParser must be constructible -- see #1014."""

    def test_excel_parser_constructs(self):
        parser = ExcelParser()
        self.assertIsNotNone(parser)

    def test_excel_parser_wires_progress_tracker(self):
        """The missing import was for the tracker, so assert it is actually set.

        A bare construction check would pass against a version that dropped the
        tracker call entirely; this pins the attribute the import exists to provide.
        """
        parser = ExcelParser()
        self.assertIsNotNone(parser.progress_tracker)


class TestExportedParsersConstruct(unittest.TestCase):
    """Every parser the package exports must survive ``__init__``."""

    def test_all_exported_parsers_construct(self):
        classes = _exported_parser_classes()
        self.assertGreater(len(classes), 0, "no exported parser classes found")

        for name, cls in classes:
            with self.subTest(parser=name):
                try:
                    self.assertIsNotNone(cls())
                except ImportError as exc:
                    # Parsers backed by an optional dependency raise a deliberate,
                    # actionable ImportError when it is absent (e.g. DoclingParser
                    # without `docling`). That is correct behavior, not a defect.
                    self.assertIn(
                        "install",
                        str(exc).lower(),
                        f"{name} raised ImportError without install guidance: {exc}",
                    )


if __name__ == "__main__":
    unittest.main()
