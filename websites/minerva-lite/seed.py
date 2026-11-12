import hashlib
import json
import os
import pathlib
import random
import sqlite3

from werkzeug.security import generate_password_hash

from common.seed_utils import init_db, load_json
from common.synthetic_catalog import INSTRUCTOR_IDS, synthetic_professor_name


ROOT = pathlib.Path(__file__).parent
DB_PATH = ROOT / "db" / "minerva.sqlite3"
SCHEMA = ROOT / "schema.sql"
SEED_JSON = ROOT / "data" / "seed.json"
PROGRAM_CATALOG_JSON = ROOT / "data" / "program_catalog.json"
SEED = int(os.environ.get("APP_SEED", 42))
random.seed(SEED)


seed = load_json(SEED_JSON)
program_catalog = load_json(PROGRAM_CATALOG_JSON)

TERMS = ["Summer 2026", "Fall 2026", "Winter 2027"]
TERM_PREFIX = {"Summer 2026": "3", "Fall 2026": "1", "Winter 2027": "2"}
MEETING_PATTERNS = [
    ("MWF", "08:35-09:25"),
    ("MWF", "09:35-10:25"),
    ("MWF", "10:35-11:25"),
    ("TR", "10:05-11:25"),
    ("TR", "11:35-12:55"),
    ("MW", "14:35-15:55"),
    ("TR", "14:35-15:55"),
    ("MW", "16:05-17:25"),
]

COMPONENT_SECTIONS = {
    ("COMP", "202"): [("Laboratory", "F", "13:35-15:25"), ("Laboratory", "R", "14:35-16:25")],
    ("COMP", "206"): [("Laboratory", "M", "15:35-17:25"), ("Conference", "F", "10:35-11:25")],
    ("COMP", "250"): [("Conference", "M", "13:35-14:25"), ("Conference", "W", "13:35-14:25")],
    ("MATH", "140"): [("Conference", "T", "15:35-16:25"), ("Conference", "R", "15:35-16:25")],
    ("BIOL", "111"): [("Laboratory", "T", "13:35-16:25"), ("Laboratory", "R", "13:35-16:25")],
    ("BIOL", "200"): [("Laboratory", "M", "14:35-17:25")],
    ("CHEM", "110"): [("Laboratory", "M", "13:35-16:25"), ("Laboratory", "W", "13:35-16:25")],
    ("CHEM", "212"): [("Laboratory", "T", "14:35-17:25")],
    ("PHYS", "101"): [("Laboratory", "W", "14:35-17:25"), ("Conference", "F", "12:35-13:25")],
    ("ECON", "208"): [("Conference", "T", "16:05-16:55"), ("Conference", "R", "16:05-16:55")],
}

SECTION_STATUS_OVERRIDES = {
    ("Fall 2026", "COMP", "421"): "full_waitlist_open",
    ("Fall 2026", "COMP", "206"): "full_waitlist_open",
    ("Fall 2026", "MATH", "203"): "full_waitlist_full",
    ("Winter 2027", "COMP", "250"): "full_no_waitlist",
    ("Winter 2027", "MATH", "204"): "full_no_waitlist",
}


def _course_code(subject, number):
    return f"{subject} {number}"


def _stable_rng(*parts):
    key = "::".join(str(part) for part in parts)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return random.Random(SEED + int.from_bytes(digest[:8], "big"))


def _components_for_course(course):
    return COMPONENT_SECTIONS.get((course["subject"], course["number"]), [])


def _section_status(course, term, course_idx):
    override = SECTION_STATUS_OVERRIDES.get((term, course["subject"], course["number"]))
    if override:
        return override
    rng = _stable_rng(term, course["subject"], course["number"], course_idx)
    p = rng.random()
    if p < 0.10:
        return "full_waitlist_open"
    if p < 0.16:
        return "full_waitlist_full"
    if p < 0.22:
        return "full_no_waitlist"
    if p < 0.36:
        return "nearly_full"
    return "open"


def _section_availability(course, term, seats_total, course_idx):
    status = _section_status(course, term, course_idx)
    rng = _stable_rng("availability", term, course["subject"], course["number"], course_idx)
    if status == "full_waitlist_open":
        waitlist_total = rng.choice([10, 15, 20, 25, 30])
        return seats_total, waitlist_total, rng.randint(1, waitlist_total - 1)
    if status == "full_waitlist_full":
        waitlist_total = rng.choice([5, 10, 15, 20])
        return seats_total, waitlist_total, waitlist_total
    if status == "full_no_waitlist":
        return seats_total, 0, 0
    if status == "nearly_full":
        seats_left = rng.randint(1, min(5, max(1, seats_total // 12)))
        return seats_total - seats_left, rng.choice([0, 5, 10, 15]), 0
    return int(seats_total * rng.uniform(0.35, 0.76)), rng.choice([0, 5, 10, 15, 20]), 0


def _catalog_requirement_courses():
    seen = {
        _course_code(course["subject"], course["number"])
        for course in seed["courses"]
    }
    additions = []
    for program in program_catalog:
        for req in program.get("requirements", []):
            code = str(req.get("code", "")).strip()
            parts = code.split()
            if len(parts) < 2 or not parts[1][:3].isdigit():
                continue
            subject = parts[0].upper()
            number = "".join(ch for ch in parts[1] if ch.isdigit())[:3]
            if len(number) != 3:
                continue
            normalized_code = _course_code(subject, number)
            if normalized_code in seen:
                continue
            title = str(req.get("title", "")).strip().rstrip(".")
            if not title:
                continue
            seen.add(normalized_code)
            additions.append(
                {
                    "code": normalized_code,
                    "subject": subject,
                    "number": number,
                    "title": title,
                    "credits": float(req.get("credits") or 3),
                }
            )
    return additions


def _forced_terms_by_code():
    forced = {}
    for user in seed["users"]:
        for term, codes in user.get("registrations", {}).items():
            mapped_term = "Fall 2026" if "Fall" in term else "Winter 2027" if "Winter" in term else term
            for code in codes:
                forced.setdefault(code, set()).add(mapped_term)
        for term, codes in user.get("waitlist", {}).items():
            mapped_term = "Fall 2026" if "Fall" in term else "Winter 2027" if "Winter" in term else term
            for code in codes:
                forced.setdefault(code, set()).add(mapped_term)
    return forced


def _terms_for_course(course, idx):
    code = _course_code(course["subject"], course["number"])
    forced = _forced_terms_by_code().get(code, set())
    level = int("".join(ch for ch in course["number"] if ch.isdigit())[:3] or 0)
    if level < 250:
        available = set(TERMS)
    else:
        rng = _stable_rng("terms", code, idx)
        available = {term for term in TERMS if rng.random() < 0.58}
        if not available:
            available = {TERMS[idx % len(TERMS)]}
        if rng.random() < 0.22:
            available.add(TERMS[(idx + 1) % len(TERMS)])
    available.update(forced)
    return [term for term in TERMS if term in available]


def _professor_for_course(course, term, idx):
    # Preserve the original seed's instructor assignment, anonymizing the chosen
    # identity rather than inventing a new person for each course/component.
    rng = _stable_rng("professor", course["subject"], course["number"], term, idx)
    return synthetic_professor_name(INSTRUCTOR_IDS[rng.randrange(len(INSTRUCTOR_IDS))])


def professor_assignments():
    """Expected CRN-to-instructor mapping for seeding and in-place migration."""
    assignments = {}
    course_idx = 0
    for course in _courses():
        for term in course["terms"]:
            course_idx += 1
            crn = f"{TERM_PREFIX[term]}{course['crn']}"
            professor = _professor_for_course(course, term, course_idx)
            assignments[crn] = professor
            for component_idx, _ in enumerate(_components_for_course(course), start=1):
                assignments[f"{crn}{component_idx}"] = professor
    return assignments


def _courses():
    courses = []
    all_courses = list(seed["courses"]) + _catalog_requirement_courses()
    for idx, course in enumerate(all_courses, start=1):
        days, time = MEETING_PATTERNS[idx % len(MEETING_PATTERNS)]
        merged = dict(course)
        merged.setdefault("crn", str(20000 + idx))
        merged.setdefault("days", days)
        merged.setdefault("time", time)
        merged.setdefault("campus", "Downtown")
        merged.setdefault("seats_total", 70 + (idx % 9) * 10)
        merged["terms"] = _terms_for_course(merged, idx)
        courses.append(merged)
    return courses


def expected_course_count():
    return len({(c["subject"], c["number"]) for c in _courses()})


def expected_section_count():
    total = 0
    for course in _courses():
        total += len(course["terms"]) * (1 + len(_components_for_course(course)))
    return total


def _insert_accounts_and_profiles(con):
    advisor_account_ids = {}
    for advisor in seed["advisors"]:
        cur = con.execute(
            "INSERT INTO accounts(login_id,password_hash,name,role) VALUES(?,?,?,?)",
            (
                advisor["login_id"],
                generate_password_hash(advisor["password"]),
                advisor["name"],
                "advisor",
            ),
        )
        account_id = cur.lastrowid
        advisor_account_ids[advisor["advisor_id"]] = account_id
        con.execute(
            """
            INSERT INTO advisors(advisor_id,account_id,name,faculty,department,office)
            VALUES(?,?,?,?,?,?)
            """,
            (
                advisor["advisor_id"],
                account_id,
                advisor["name"],
                advisor["faculty"],
                advisor["department"],
                advisor["office"],
            ),
        )

    student_ids = {}
    for user in seed["users"]:
        cur = con.execute(
            "INSERT INTO accounts(login_id,password_hash,name,role) VALUES(?,?,?,?)",
            (
                user["login_id"],
                generate_password_hash(user["password"]),
                user["name"],
                "student",
            ),
        )
        account_id = cur.lastrowid
        student_id = int(user["student_id"])
        student_ids[user["student_id"]] = student_id
        con.execute(
            """
            INSERT INTO students(id,account_id,name,faculty,major,minor,major_group,advisor_id,bills_paid,current_balance)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (
                student_id,
                account_id,
                user["name"],
                user["faculty"],
                user["major"],
                user.get("minor", ""),
                user["major_group"],
                user.get("advisor_id"),
                int(user.get("bills_paid", 0)),
                float(user.get("current_balance", 0)),
            ),
        )
        for bill in user.get("bills", []):
            con.execute(
                """
                INSERT INTO bills(student_id,term,label,amount,is_paid,method,confirmation)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    student_id,
                    bill["term"],
                    bill["label"],
                    float(bill["amount"]),
                    1 if bill.get("is_paid") else 0,
                    "Seeded payment" if bill.get("is_paid") else "",
                    f"MIN-SEED-{student_id}-{len(user.get('bills', []))}",
                ),
            )
        for entry in user.get("classes_taken", []):
            con.execute(
                """
                INSERT INTO transcript_entries(student_id,course_code,term,grade,credits)
                VALUES(?,?,?,?,?)
                """,
                (
                    student_id,
                    entry["code"],
                    entry["term"],
                    entry["grade"],
                    float(entry.get("credits", 3)),
                ),
            )
    return student_ids


def _insert_programs(con):
    for program in program_catalog:
        con.execute(
            """
            INSERT INTO programs(program_id,slug,title,faculty,major_group,program_type,degree,summary,requirements_json,requirement_sections_json,verified_on,official_url)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                program["program_id"],
                program.get("slug", ""),
                program["title"],
                program["faculty"],
                program["major_group"],
                program.get("program_type", ""),
                program.get("degree", ""),
                program.get("summary", ""),
                json.dumps(program.get("requirements", [])),
                json.dumps(program.get("requirement_sections", [])),
                program.get("verified_on", ""),
                program.get("official_url", ""),
            ),
        )


def _insert_courses(con):
    code_to_primary_crn = {}
    course_idx = 0
    for course in _courses():
        for term in course["terms"]:
            course_idx += 1
            base_crn = str(course["crn"])
            crn = f"{TERM_PREFIX[term]}{base_crn}"
            professor = _professor_for_course(course, term, course_idx)
            seats_total = int(course.get("seats_total", 100))
            seats_taken, waitlist_total, waitlist_taken = _section_availability(
                course,
                term,
                seats_total,
                course_idx,
            )
            con.execute(
                """
                INSERT INTO courses(crn,subject,number,title,professor,section_type,parent_crn,credits,days,time,campus,term,seats_total,seats_taken,waitlist_total,waitlist_taken)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    crn,
                    course["subject"],
                    course["number"],
                    course["title"],
                    professor,
                    "Lecture",
                    None,
                    float(course["credits"]),
                    course.get("days", ""),
                    course.get("time", ""),
                    course.get("campus", "Downtown"),
                    term,
                    seats_total,
                    seats_taken,
                    waitlist_total,
                    waitlist_taken,
                ),
            )
            code_to_primary_crn.setdefault((term, _course_code(course["subject"], course["number"])), crn)
            for component_idx, (section_type, component_days, component_time) in enumerate(_components_for_course(course), start=1):
                component_crn = f"{crn}{component_idx}"
                component_total = min(seats_total, 35 if section_type == "Laboratory" else 45)
                component_taken = min(seats_taken, int(component_total * (0.42 + component_idx * 0.12)))
                con.execute(
                    """
                    INSERT INTO courses(crn,subject,number,title,professor,section_type,parent_crn,credits,days,time,campus,term,seats_total,seats_taken,waitlist_total,waitlist_taken)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        component_crn,
                        course["subject"],
                        course["number"],
                        course["title"],
                        professor,
                        section_type,
                        crn,
                        0.0,
                        component_days,
                        component_time,
                        course.get("campus", "Downtown"),
                        term,
                        component_total,
                        component_taken,
                        0,
                        0,
                    ),
                )
    return code_to_primary_crn


def _insert_seeded_enrolments(con, code_to_primary_crn):
    for user in seed["users"]:
        student_id = int(user["student_id"])
        for term, codes in user.get("registrations", {}).items():
            mapped_term = "Fall 2026" if "Fall" in term else "Winter 2027" if "Winter" in term else term
            for code in codes:
                crn = code_to_primary_crn.get((mapped_term, code))
                if crn:
                    con.execute("INSERT OR IGNORE INTO registrations(student_id,crn) VALUES(?,?)", (student_id, crn))
        for term, codes in user.get("waitlist", {}).items():
            mapped_term = "Fall 2026" if "Fall" in term else "Winter 2027" if "Winter" in term else term
            for code in codes:
                crn = code_to_primary_crn.get((mapped_term, code))
                if crn:
                    position = con.execute(
                        "SELECT COALESCE(MAX(position), 0) + 1 FROM waitlists WHERE crn=?",
                        (crn,),
                    ).fetchone()[0]
                    con.execute(
                        "INSERT OR IGNORE INTO waitlists(student_id,crn,position) VALUES(?,?,?)",
                        (student_id, crn, position),
                    )
                    con.execute(
                        "UPDATE courses SET waitlist_taken = MAX(waitlist_taken, ?) WHERE crn=?",
                        (position, crn),
                    )


def seed_database():
    init_db(DB_PATH, SCHEMA)
    with sqlite3.connect(DB_PATH) as con:
        _insert_accounts_and_profiles(con)
        _insert_programs(con)
        code_to_primary_crn = _insert_courses(con)
        _insert_seeded_enrolments(con, code_to_primary_crn)
        con.commit()


if __name__ == "__main__":
    seed_database()
    print("Minerva-lite seeded.")
