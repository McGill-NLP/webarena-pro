"""Run with: python -m unittest discover -s tests -v (from minerva-lite)."""

import hashlib
import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import seed
from common.synthetic_catalog import INSTRUCTOR_IDS, synthetic_professor_name
from scripts import syntheticize_catalog


class InstructorIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.clean_db = pathlib.Path(cls.directory.name) / "clean.sqlite3"
        with patch.object(seed, "DB_PATH", cls.clean_db), patch.object(seed, "SEED", 42):
            seed.seed_database()

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def connect(self):
        connection = sqlite3.connect(self.clean_db)
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        return connection

    def test_original_instructor_relationship_partition_is_preserved(self):
        # Independently recorded from cc474a4e's checked-in SQLite database:
        # sort CRNs within each source instructor group, then sort the groups.
        # Comparing the partition preserves all relationships without retaining
        # source-person names or making the test depend on the new name generator.
        groups = {}
        for crn, professor in self.connect().execute("SELECT crn, professor FROM courses"):
            groups.setdefault(professor, []).append(crn)
        partition = sorted(sorted(crns) for crns in groups.values())
        digest = hashlib.sha256(json.dumps(partition, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(sum(map(len, partition)), 5857)
        self.assertEqual(len(partition), 24)
        self.assertEqual(digest, "c460b820ba709870b4a34d5c1bb5e9ec1f09372d3203a97cf144b0f8f53940d2")

    def test_all_identities_have_unique_stable_synthetic_labels(self):
        names = [synthetic_professor_name(identity) for identity in INSTRUCTOR_IDS]
        self.assertEqual(len(set(names)), 24)
        self.assertEqual(names[0], "Dr. Aven Quenvar")
        self.assertEqual(names[3], "Dr. Darian Quenvar")
        with self.assertRaises(ValueError):
            synthetic_professor_name("COMP421LEC")

    def test_components_retain_the_lecture_instructor(self):
        con = self.connect()
        self.assertGreater(con.execute("SELECT count(*) FROM courses WHERE parent_crn IS NOT NULL").fetchone()[0], 0)
        self.assertEqual(con.execute("""
            SELECT c.crn FROM courses c JOIN courses p ON c.parent_crn=p.crn
            WHERE c.professor != p.professor
        """).fetchall(), [])

    def test_shipped_database_matches_clean_seed_assignments(self):
        with sqlite3.connect(ROOT / "db" / "minerva.sqlite3") as shipped:
            actual = dict(shipped.execute("SELECT crn, professor FROM courses"))
        self.assertEqual(actual, dict(self.connect().execute("SELECT crn, professor FROM courses")))
        self.assertEqual(actual, seed.professor_assignments())

    def test_migration_repairs_course_specific_names_and_is_idempotent(self):
        path = pathlib.Path(self.directory.name) / "migration.sqlite3"
        shutil.copyfile(self.clean_db, path)
        # The existing program migration normalizes JSON Unicode escaping.
        # Establish that baseline separately from the instructor repair.
        with patch.object(syntheticize_catalog, "DB_PATH", path):
            syntheticize_catalog.update_database(seed.program_catalog, seed.seed)
        with sqlite3.connect(path) as con:
            before = list(con.iterdump())
            con.execute("UPDATE courses SET professor='Dr. Course Quenvar-' || crn")
        with patch.object(syntheticize_catalog, "DB_PATH", path):
            for _ in range(2):
                syntheticize_catalog.update_database(seed.program_catalog, seed.seed)
                with sqlite3.connect(path) as con:
                    self.assertEqual(list(con.iterdump()), before)

    def test_migration_refuses_to_guess_unknown_course_identity(self):
        path = pathlib.Path(self.directory.name) / "unknown.sqlite3"
        shutil.copyfile(self.clean_db, path)
        with sqlite3.connect(path) as con:
            con.execute("UPDATE courses SET crn='unknown' WHERE crn='120043'")
        with patch.object(syntheticize_catalog, "DB_PATH", path):
            with self.assertRaisesRegex(ValueError, "unknown CRNs"):
                syntheticize_catalog.update_database(seed.program_catalog, seed.seed)

    def test_professor_tasks_have_visible_suitable_candidates(self):
        con = self.connect()
        courses = {row["crn"]: dict(row) for row in con.execute("SELECT * FROM courses")}
        waitlist = con.execute("SELECT crn FROM waitlists WHERE student_id=260123456").fetchall()
        self.assertEqual([row[0] for row in waitlist], ["120043"])
        original = courses["120043"]
        self.assertEqual(original["professor"], "Dr. Darian Quenvar")

        def conflicts(left, right):
            return (set(left["days"]) & set(right["days"])
                    and left["time"].split("-")[0] < right["time"].split("-")[1]
                    and right["time"].split("-")[0] < left["time"].split("-")[1])

        for term, expected, instructor in [
            ("Fall 2026", "121518", original["professor"]),  # Task 138
            ("Winter 2027", "222178", original["professor"]),  # Task 142
            ("Fall 2026", "120046", "Dr. Aven Quenvar"),  # Tasks 143/144
        ]:
            registered = [dict(row) for row in con.execute("""
                SELECT c.* FROM registrations r JOIN courses c USING(crn)
                WHERE r.student_id=260123456 AND c.term=?
            """, (term,))]
            candidates = [c for c in courses.values() if c["term"] == term
                          and c["subject"] == "COMP" and c["professor"] == instructor
                          and c["seats_taken"] < c["seats_total"]
                          and not any(conflicts(c, current) for current in registered)]
            if term == "Winter 2027":
                existing_days = set("".join(c["days"] for c in registered))
                fewest_new_days = min(len(set(c["days"]) - existing_days) for c in candidates)
                candidates = [c for c in candidates if len(set(c["days"]) - existing_days) == fewest_new_days]
            self.assertEqual([c["crn"] for c in candidates], [expected])


if __name__ == "__main__":
    unittest.main()
