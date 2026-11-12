import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import seed


class SeedSnapshotTests(unittest.TestCase):
    def test_reset_restores_data_and_schema_without_changing_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "live.sqlite3"
            snapshot = Path(directory) / "seed.sqlite3"
            with sqlite3.connect(database) as db:
                db.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT UNIQUE)")
                db.execute("INSERT INTO records VALUES (1, 'expanded seed')")
            with patch.object(seed, "_snapshot_paths", return_value=(database, snapshot)):
                seed.create_seed_snapshot()
                original = snapshot.read_bytes()
                for _ in range(2):
                    with sqlite3.connect(database) as db:
                        db.execute("DELETE FROM records")
                        db.execute("CREATE TABLE episode_only (id INTEGER)")
                    self.assertTrue(seed.restore_seed_snapshot())
                    with sqlite3.connect(database) as db:
                        self.assertEqual(db.execute("SELECT * FROM records").fetchall(), [(1, "expanded seed")])
                        self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='episode_only'").fetchall(), [])
                    self.assertEqual(snapshot.read_bytes(), original)

    def test_missing_snapshot_keeps_live_data(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "live.sqlite3"
            database.write_bytes(b"unchanged")
            with patch.object(seed, "_snapshot_paths", return_value=(database, Path(directory) / "missing")):
                self.assertFalse(seed.restore_seed_snapshot())
            self.assertEqual(database.read_bytes(), b"unchanged")
