"""Query-execution coverage for DBIngestor and DataExporter.

Regression tests for #1015: ``sqlalchemy.text`` was imported function-locally inside
``DatabaseConnector.connect()`` and ``DatabaseConnector.test_connection()``, but called
in ``DataExporter.export_table_data()`` and ``DBIngestor.execute_query()``, which never
imported it. Both raised ``NameError``, re-wrapped by their ``except Exception`` handlers
into a ``ProcessingError`` reading "Failed to execute query: name 'text' is not defined"
-- a message that looks like a database problem rather than a missing import.

Nothing caught it because no test exercised either method; the only ``execute_query``
references under ``tests/`` are Mock stand-ins for the unrelated graph-store method of
the same name.

These tests run against a temporary SQLite database, so they need no external service.
"""

import os
import tempfile
import unittest

try:
    from sqlalchemy import create_engine, text

    SQLALCHEMY_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only where sqlalchemy is absent
    SQLALCHEMY_AVAILABLE = False

from semantica.ingest.db_ingestor import DataExporter, DBIngestor


@unittest.skipUnless(SQLALCHEMY_AVAILABLE, "sqlalchemy is required for these tests")
class TestDBIngestorQueryExecution(unittest.TestCase):
    """Both query paths must survive the call that needed sqlalchemy.text -- see #1015."""

    def setUp(self):
        # Register each cleanup as soon as the resource exists: tearDown is not
        # called when setUp raises partway through, but addCleanup callbacks are.
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.db_path = os.path.join(self._tmpdir.name, "test.db")
        self.connection_string = f"sqlite:///{self.db_path}"
        self.engine = create_engine(self.connection_string)
        self.addCleanup(self.engine.dispose)

        with self.engine.begin() as conn:
            conn.execute(text("CREATE TABLE widgets (id INTEGER, name TEXT)"))
            for row_id, name in [(1, "alpha"), (2, "beta"), (3, "gamma")]:
                conn.execute(
                    text("INSERT INTO widgets VALUES (:id, :name)"),
                    {"id": row_id, "name": name},
                )

    def test_execute_query_returns_rows(self):
        """DBIngestor.execute_query -- the text() call that raised NameError."""
        rows = DBIngestor().execute_query(
            self.connection_string,
            "SELECT id, name FROM widgets ORDER BY id",
        )
        self.assertEqual(
            rows,
            [
                {"id": 1, "name": "alpha"},
                {"id": 2, "name": "beta"},
                {"id": 3, "name": "gamma"},
            ],
        )

    def test_execute_query_binds_parameters(self):
        """The params argument is passed alongside text(), so cover it explicitly."""
        rows = DBIngestor().execute_query(
            self.connection_string,
            "SELECT name FROM widgets WHERE id = :wanted",
            wanted=2,
        )
        self.assertEqual(rows, [{"name": "beta"}])

    def test_export_table_data_with_limit(self):
        """Exercises the main text() call; the COUNT(*) branch is skipped when limit is set."""
        result = DataExporter().export_table_data(self.engine, "widgets", limit=2)

        self.assertEqual(result.table_name, "widgets")
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.row_count, 2)
        self.assertEqual([c["name"] for c in result.columns], ["id", "name"])

    def test_export_table_data_without_limit_counts_rows(self):
        """Covers the second text() call.

        ``export_table_data`` only issues its ``SELECT COUNT(*)`` when no ``limit`` is
        passed, so the test above never reaches that line. Without this case one of the
        three call sites the bug touched would stay untested.
        """
        result = DataExporter().export_table_data(self.engine, "widgets")

        self.assertEqual(len(result.rows), 3)
        self.assertEqual(result.row_count, 3)

    def test_export_table_data_honors_where_and_order(self):
        """The WHERE/ORDER BY clauses are interpolated before text() wraps the query."""
        result = DataExporter().export_table_data(
            self.engine,
            "widgets",
            where="id >= 2",
            order_by="id DESC",
        )

        self.assertEqual([r["name"] for r in result.rows], ["gamma", "beta"])
        self.assertEqual(result.row_count, 2)


if __name__ == "__main__":
    unittest.main()
