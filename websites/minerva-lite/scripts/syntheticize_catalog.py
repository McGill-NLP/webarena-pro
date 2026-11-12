#!/usr/bin/env python3
import json
import pathlib
import sqlite3
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.synthetic_catalog import sanitize_program
import seed as seed_module


PROGRAM_CATALOG_PATH = ROOT / "data" / "program_catalog.json"
SEED_PATH = ROOT / "data" / "seed.json"
DB_PATH = ROOT / "db" / "minerva.sqlite3"

SYNTHETIC_ADVISORS = {
    "9801001": {
        "name": "Dr. Maren Quenvar-Advising-SCI",
        "office": "Bluehaven Hall 3170",
    },
    "9801002": {
        "name": "Dr. Solen Quenvar-Advising-ARTS",
        "office": "Maplelight Hall 215",
    },
    "9801003": {
        "name": "Dr. Veyra Quenvar-Advising-IAS",
        "office": "Northstar Hall 401",
    },
}


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def update_json_sources():
    catalog = json.loads(PROGRAM_CATALOG_PATH.read_text())
    catalog = [sanitize_program(program) for program in catalog]
    write_json(PROGRAM_CATALOG_PATH, catalog)

    seed = json.loads(SEED_PATH.read_text())
    seed["programs"] = [sanitize_program(program) for program in seed.get("programs", [])]
    seed["metadata"]["notes"] = (
        "Program titles and course requirements are retained for local registration tasks. "
        "All institutional descriptions, faculty display names, instructor and adviser labels, "
        "locations, and links use synthetic Bolder-Kohn University data."
    )
    for advisor in seed.get("advisors", []):
        synthetic_advisor = SYNTHETIC_ADVISORS.get(str(advisor.get("advisor_id")))
        if synthetic_advisor:
            advisor.update(synthetic_advisor)
    write_json(SEED_PATH, seed)
    return catalog, seed


def update_database(catalog, seed):
    if not DB_PATH.exists():
        return
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        assignments = seed_module.professor_assignments()
        crns = {row[0] for row in con.execute("SELECT crn FROM courses")}
        unknown = crns - assignments.keys()
        if unknown:
            raise ValueError(f"Cannot recover instructor identities for unknown CRNs: {sorted(unknown)}")
        for program in catalog:
            con.execute(
                """
                UPDATE programs
                SET summary=?, requirement_sections_json=?
                WHERE program_id=?
                """,
                (
                    program["summary"],
                    json.dumps(program.get("requirement_sections", []), ensure_ascii=False),
                    program["program_id"],
                ),
            )
        for advisor in seed.get("advisors", []):
            con.execute(
                "UPDATE advisors SET name=?, office=? WHERE advisor_id=?",
                (advisor["name"], advisor["office"], advisor["advisor_id"]),
            )
        con.executemany(
            "UPDATE courses SET professor=? WHERE crn=?",
            [(assignments[crn], crn) for crn in sorted(crns)],
        )
        con.commit()


def main():
    catalog, seed = update_json_sources()
    update_database(catalog, seed)
    print(f"Syntheticized {len(catalog)} program descriptions and the active database.")


if __name__ == "__main__":
    main()
