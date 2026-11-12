#!/usr/bin/env python3
import json
import itertools
import pathlib
import re
import sqlite3
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from seed import professor_assignments

CATALOG_PATH = ROOT / "data" / "program_catalog.json"
SEED_PATH = ROOT / "data" / "seed.json"
DB_PATH = ROOT / "db" / "minerva.sqlite3"

INSTRUCTOR_PATTERN = re.compile(r"^Dr\. [A-Z][a-z]+ Quenvar$")
ADVISOR_PATTERN = re.compile(r"^Dr\. [A-Z][a-z]+ Quenvar-Advising-[A-Z]+$")
SYNTHETIC_HALLS = {"Bluehaven Hall", "Maplelight Hall", "Northstar Hall"}


def fail(message):
    raise SystemExit(f"FAILED: {message}")


def main():
    catalog = json.loads(CATALOG_PATH.read_text())
    seed = json.loads(SEED_PATH.read_text())

    summaries = [str(program.get("summary", "")).strip() for program in catalog]
    if not summaries or any("Bolder-Kohn" not in summary for summary in summaries):
        fail("every program must have a Bolder-Kohn description")
    if len(summaries) != len(set(summaries)):
        fail("program descriptions must be unique")
    trigrams = []
    for summary in summaries:
        words = re.findall(r"[a-z0-9]+", summary.lower())
        trigrams.append(set(zip(words, words[1:], words[2:])))
    maximum_similarity = max(
        (
            len(left & right) / len(left | right)
            for left, right in itertools.combinations(trigrams, 2)
        ),
        default=0,
    )
    if maximum_similarity >= 0.6:
        fail(f"program descriptions remain too similar ({maximum_similarity:.1%})")

    catalog_summaries = {
        program["program_id"]: program["summary"] for program in catalog
    }
    seed_summaries = {
        program["program_id"]: program["summary"] for program in seed.get("programs", [])
    }
    if catalog_summaries != seed_summaries:
        fail("program descriptions differ between catalog and seed data")

    for advisor in seed.get("advisors", []):
        if not ADVISOR_PATTERN.fullmatch(advisor.get("name", "")):
            fail(f"non-synthetic adviser label: {advisor.get('name', '')}")
        hall = str(advisor.get("office", "")).rsplit(" ", 1)[0]
        if hall not in SYNTHETIC_HALLS:
            fail(f"unexpected adviser building: {advisor.get('office', '')}")

    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute("SELECT term, professor FROM courses").fetchall()
        invalid = sorted({name for _, name in rows if not INSTRUCTOR_PATTERN.fullmatch(name)})
        if invalid:
            fail(f"non-synthetic instructor labels: {invalid[:5]}")

        assignments = dict(connection.execute("SELECT crn, professor FROM courses"))
        if assignments != professor_assignments():
            fail("instructor assignments do not preserve source identities across courses/terms/components")

        db_summaries = dict(connection.execute("SELECT program_id, summary FROM programs"))
        if db_summaries != catalog_summaries:
            fail("active database program descriptions differ from the catalog")

        database_advisors = connection.execute(
            "SELECT name, office FROM advisors ORDER BY advisor_id"
        ).fetchall()
        if any(not ADVISOR_PATTERN.fullmatch(name) for name, _ in database_advisors):
            fail("active database contains a non-synthetic adviser label")

    terms = len({term for term, _ in rows})
    print(
        f"PASS: {len(catalog)} unique synthetic degree descriptions; "
        f"maximum description overlap {maximum_similarity:.1%}; "
        f"{len(rows)} synthetic instructor assignments across {terms} terms; "
        "source instructor relationships preserved; synthetic adviser buildings and labels."
    )


if __name__ == "__main__":
    main()
