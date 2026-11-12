from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import json, os, sqlite3, pathlib, re
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
import seed
from billing_math import (
    RESIDENCY_LABELS,
    amount_due_catalog,
    money,
    profile_for_faculty,
    term_lines_for_profile,
    term_total_for_profile,
)
from common.synthetic_catalog import FACULTY_DISPLAY_NAMES, faculty_display_name


APP = Flask(__name__)
APP.secret_key = "dev-minerva-lite"  # session for term selection
ROOT = pathlib.Path(__file__).parent
DB_PATH = ROOT / "db" / "minerva.sqlite3"
PROGRAM_CATALOG_PATH = ROOT / "data" / "program_catalog.json"
TERMS = ["Summer 2026", "Fall 2026", "Winter 2027"]
DEFAULT_TERM = "Fall 2026"

ACCEPTED_PAYMENT_CARDS = {
    # Cards seeded in websites/password-manager/backend/seed.py.
    "4111111111111111",
    "5500005555555559",
    "371449635398431",
    "4532015112830366",
    "4000000000001000",
    "5105105105105100",
    "6011000990139424",
    "3566002020360505",
}

DEFAULT_CURRICULUM = {
    "faculty": FACULTY_DISPLAY_NAMES["Science"],
    "degree": "Bachelor of Science",
    "degree_short": "B Sc",
    "program_group": "Phys,Earth,Math&Comp Sci",
    "primary_major": "Computer Science",
    "secondary_program": "",
}

PHYS_EARTH_MATH_COMP_SCI_MAJORS = [
    "Atmospheric Sciences",
    "Atmospheric Science and Physics",
    "Chemistry",
    "Computer Science",
    "Geology",
    "Earth System Science",
    "Environment",
    "Geography",
    "Mathematics",
    "Mathematics and Computer Science",
    "Statistics",
    "Statistics and Computer Science",
    "Physics",
    "Physics and Computer Science",
    "Physics and Geophysics",
    "Software Engineering",
]

SCIENCE_MINOR_OPTIONS = [
    "Anatomy and Cell Biology",
    "Atmospheric Science",
    "Biochemistry",
    "Biology",
    "Biotechnology",
    "Chemistry",
    "Cognitive Science",
    "Computer Science",
    "Earth System Science",
    "Environment",
    "Field Study",
    "Geochemistry",
    "Geographical Information Systems & Remote Sensing",
    "Geography",
    "Interdisciplinary Life Sciences",
    "Mathematics",
    "Microbiology and Immunology",
    "Natural History",
    "Neuroscience",
    "Pharmacology",
    "Physics",
    "Physiology",
    "Psychology",
    "Statistics",
]

ARTS_MINOR_OPTIONS = [
    "African Studies",
    "Anthropology",
    "Arabic Language",
    "Art History",
    "Canadian Studies",
    "Classics",
    "Communication Studies",
    "East Asian Cultural Studies",
    "East Asian Language and Literature",
    "Economics",
    "English",
    "French Language and Literature",
    "Gender, Sexuality, Feminist, and Social Justice Studies",
    "German Studies",
    "Hispanic Studies",
    "History",
    "Indigenous Studies",
    "International Development Studies",
    "Italian Studies",
    "Jewish Studies",
    "Linguistics",
    "Philosophy",
    "Political Science",
    "Religious Studies",
    "Sociology",
    "World Cinemas",
]

MINOR_OPTIONS = [
    {"faculty": "Science", "name": name} for name in SCIENCE_MINOR_OPTIONS
] + [
    {"faculty": "Arts", "name": name} for name in ARTS_MINOR_OPTIONS
]

INTERFACULTY_OPTIONS = {
    "Arts": [
        "Anthropology",
        "Economics",
        "English",
        "History",
        "International Development Studies",
        "Linguistics",
        "Philosophy",
        "Political Science",
        "Psychology",
        "Sociology",
    ],
    "Science": [
        "Biological, Biomedical & Life Sciences Group",
        "Bio-Physical-Computational Sciences Group",
        "Neuroscience Group",
        "Physical, Earth, Math & Computer Science Group",
    ],
    "Engineering": [
        "Bioengineering",
        "Chemical Engineering",
        "Civil Engineering",
        "Computer Engineering",
        "Electrical Engineering",
        "Materials Engineering",
        "Mechanical Engineering",
        "Mining Engineering",
        "Software Engineering",
    ],
    "Management": [
        "Accounting",
        "Business Analytics",
        "Economics",
        "Finance",
        "Information Technology Management",
        "International Management",
        "Managing for Sustainability",
        "Marketing",
        "Mathematics and Statistics for Management",
        "Organizational Behaviour and Human Resources",
        "Retail Management",
        "Strategic Management",
    ],
}

TRANSCRIPT_TERMS = [
    {
        "term": "Fall 2024",
        "year": "Year 1",
        "courses": [
            ("COMP", "202", "001", "Foundations of Programming", "3", "A-", "3", "A-"),
            ("MATH", "133", "001", "Linear Algebra and Geometry", "3", "B+", "3", "B+"),
            ("MATH", "140", "001", "Calculus 1", "3", "A-", "3", "A-"),
            ("PHYS", "131", "001", "Mechanics and Waves", "4", "B+", "4", "B+"),
        ],
        "term_gpa": "3.54",
        "cum_gpa": "3.54",
        "term_total": "13.00",
        "cum_total": "13.00",
        "points": "46.00",
        "total_credits": "37.00",
    },
    {
        "term": "Winter 2025",
        "year": "Year 1",
        "courses": [
            ("COMP", "250", "001", "Introduction to Computer Science", "3", "A-", "3", "A-"),
            ("MATH", "141", "001", "Calculus 2", "4", "B+", "4", "B+"),
            ("MATH", "240", "001", "Discrete Structures", "3", "A", "3", "A"),
            ("PHYS", "142", "001", "Electromagnetism & Optics", "4", "B", "4", "B"),
        ],
        "term_gpa": "3.46",
        "cum_gpa": "3.50",
        "term_total": "14.00",
        "cum_total": "27.00",
        "points": "93.70",
        "total_credits": "51.00",
    },
    {
        "term": "Fall 2025",
        "year": "Year 2",
        "courses": [
            ("COMP", "206", "001", "Introduction to Software Systems", "3", "A-", "3", "A-"),
            ("COMP", "251", "001", "Algorithms and Data Structures", "3", "B+", "3", "B+"),
            ("MATH", "222", "001", "Calculus 3", "3", "B+", "3", "B+"),
            ("MATH", "323", "002", "Probability", "3", "A-", "3", "A-"),
            ("ECON", "208", "001", "Microeconomic Analysis and Applications", "3", "A", "3", "A"),
        ],
        "term_gpa": "3.63",
        "cum_gpa": "3.55",
        "term_total": "15.00",
        "cum_total": "42.00",
        "points": "148.20",
        "total_credits": "66.00",
    },
    {
        "term": "Winter 2026",
        "year": "Year 2",
        "courses": [
            ("COMP", "273", "001", "Introduction to Computer Systems", "3", "A-", "3", "A-"),
            ("COMP", "302", "001", "Programming Languages and Paradigms", "3", "B+", "3", "B+"),
            ("COMP", "303", "001", "Software Design", "3", "A-", "3", "A-"),
            ("MATH", "223", "001", "Linear Algebra", "3", "B+", "3", "B+"),
            ("PSYC", "100", "001", "Introduction to Psychology", "3", "A", "3", "A"),
        ],
        "term_gpa": "3.63",
        "cum_gpa": "3.57",
        "term_total": "15.00",
        "cum_total": "57.00",
        "points": "202.70",
        "total_credits": "81.00",
    },
]

STEP_DESTINATIONS = {
    "home": {"endpoint": "registration_menu", "label": "Registration Menu"},
    "student_records_menu": {"endpoint": "student_records_menu", "label": "Student Records Menu"},
    "student_accounts_menu": {"endpoint": "student_accounts_menu", "label": "Student Accounts Menu"},
    "search": {"endpoint": "search", "label": "Search Class Schedule"},
    "add_drop": {"endpoint": "add_drop", "label": "Add or Drop Course Sections"},
    "schedule": {"endpoint": "schedule", "label": "Student Schedule"},
    "schedule_week": {"endpoint": "schedule_week", "label": "Weekly Schedule View"},
    "view_unofficial_transcript": {"endpoint": "view_unofficial_transcript", "label": "View Unofficial Transcript"},
    "change_primary_curriculum": {"endpoint": "change_primary_curriculum", "label": "Change Primary Curriculum"},
    "change_secondary_curriculum": {"endpoint": "change_secondary_curriculum", "label": "Change Secondary Curriculum"},
    "apply_intrafaculty_transfer": {"endpoint": "apply_intrafaculty_transfer", "label": "Apply for Intrafaculty Transfer"},
    "apply_interfaculty_transfer": {"endpoint": "apply_interfaculty_transfer", "label": "Apply for Interfaculty Transfer"},
    "view_itemized_bill": {"endpoint": "view_itemized_bill", "label": "View Itemized Bill"},
    "view_previous_payments": {"endpoint": "view_previous_payments", "label": "View Previous Payments"},
    "pay_bill": {"endpoint": "pay_bill", "label": "Pay Bill"},
    "request_refund": {"endpoint": "request_refund", "label": "Request Refund"},
}

STEP_KEYS_BY_ENDPOINT = {
    "registration_menu": "home",
    "student_records_menu": "student_records_menu",
    "student_accounts_menu": "student_accounts_menu",
    "search": "search",
    "add_drop": "add_drop",
    "schedule": "schedule",
    "schedule_week": "schedule_week",
    "view_unofficial_transcript": "view_unofficial_transcript",
    "change_primary_curriculum": "change_primary_curriculum",
    "change_secondary_curriculum": "change_secondary_curriculum",
    "apply_intrafaculty_transfer": "apply_intrafaculty_transfer",
    "apply_interfaculty_transfer": "apply_interfaculty_transfer",
    "view_itemized_bill": "view_itemized_bill",
    "view_previous_payments": "view_previous_payments",
    "pay_bill": "pay_bill",
    "request_refund": "request_refund",
}

STUDENT_RECORDS_ITEMS = [
    {
        "title": "View Unofficial Transcript",
        "description": "Review an unofficial copy of your academic record for the selected term.",
        "url": "/student-records/unofficial-transcript",
        "data_test": "records-menu-unofficial-transcript",
    },
    {
        "title": "Change Primary Curriculum",
        "description": "Request an update to your primary faculty, program, major, or concentration.",
        "url": "/student-records/change-primary-curriculum",
        "data_test": "records-menu-primary-curriculum",
    },
    {
        "title": "Change Secondary Curriculum",
        "description": "Request an update to a secondary program, minor, option, or concentration.",
        "url": "/student-records/change-secondary-curriculum",
        "data_test": "records-menu-secondary-curriculum",
    },
    {
        "title": "Apply for Intrafaculty Transfer",
        "description": "Start a transfer request between programs within your current faculty.",
        "url": "/student-records/apply-intrafaculty-transfer",
        "data_test": "records-menu-intrafaculty-transfer",
    },
    {
        "title": "Apply for Interfaculty Transfer",
        "description": "Start a transfer request from your current faculty to another faculty.",
        "url": "/student-records/apply-interfaculty-transfer",
        "data_test": "records-menu-interfaculty-transfer",
    },
    {
        "title": "Change Password",
        "description": "Update the password used with your student ID sign-in.",
        "url": "/change-password",
        "data_test": "records-menu-change-password",
    },
]

STUDENT_ACCOUNTS_ITEMS = [
    {
        "title": "View Itemized Bill",
        "description": "Review tuition, fees, credits, and term charges in an itemized statement.",
        "url": "/student-accounts/itemized-bill",
        "data_test": "accounts-menu-itemized-bill",
    },
    {
        "title": "View Previous Payments",
        "description": "Review payments and account credits posted to your student account.",
        "url": "/student-accounts/previous-payments",
        "data_test": "accounts-menu-previous-payments",
    },
    {
        "title": "Pay Bill",
        "description": "Open the payment workflow for outstanding balances.",
        "url": "/student-accounts/pay-bill",
        "data_test": "accounts-menu-pay-bill",
    },
    {
        "title": "Request Refund",
        "description": "Submit a full or partial refund request from your student account.",
        "url": "/student-accounts/request-refund",
        "data_test": "accounts-menu-request-refund",
    },
]


def get_current_term():
    if session.get("term") not in TERMS:
        session["term"] = DEFAULT_TERM
    return session["term"]


def require_term(step_key):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            get_current_term()
            session["term_confirmed"] = True
            return func(*args, **kwargs)
        return wrapper
    return decorator


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("account_id"):
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return func(*args, **kwargs)
    return wrapper


def role_required(role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            account = get_current_account()
            if not account:
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            if account["role"] != role:
                target = "advisor_dashboard" if account["role"] == "advisor" else "registration_menu"
                return redirect(url_for(target, msg="You do not have access to that page."))
            return func(*args, **kwargs)
        return wrapper
    return decorator

def _db_section_count():
    if not DB_PATH.exists():
        return 0
    try:
        rows = q("SELECT COUNT(*) AS count FROM courses")
        return int(rows[0]["count"]) if rows else 0
    except sqlite3.Error:
        return 0


def _db_has_course_components():
    if not DB_PATH.exists():
        return False
    try:
        columns = {row["name"] for row in q("PRAGMA table_info(courses)")}
        tables = {row["name"] for row in q("SELECT name FROM sqlite_master WHERE type='table'")}
        return {"section_type", "parent_crn", "professor"}.issubset(columns) and {
            "accounts",
            "advisors",
            "programs",
            "bills",
            "transcript_entries",
            "curriculum_requests",
        }.issubset(tables)
    except sqlite3.Error:
        return False


def ensure_seeded():
    if not _db_has_course_components() or _db_section_count() < seed.expected_section_count():
        seed.seed_database()


def q(sql, *params):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


ensure_seeded()


def execute(sql, *params):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(sql, params)
        con.commit()


def q1(sql, *params):
    rows = q(sql, *params)
    return rows[0] if rows else None


def get_current_account():
    account_id = session.get("account_id")
    if not account_id:
        return None
    return q1(
        """
        SELECT a.*, s.id AS student_id, s.faculty, s.major, s.minor, s.major_group,
               s.advisor_id, s.bills_paid, s.current_balance, adv.department, adv.office
        FROM accounts a
        LEFT JOIN students s ON s.account_id = a.id
        LEFT JOIN advisors adv ON adv.account_id = a.id
        WHERE a.id=?
        """,
        account_id,
    )


def current_student_id():
    account = get_current_account()
    if account and account["role"] == "student":
        return account["student_id"]
    return 260123456


def account_display_name(account):
    if not account:
        return ""
    parts = str(account["name"]).split()
    return f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) > 1 else account["name"]


def load_program_catalog():
    return json.loads(PROGRAM_CATALOG_PATH.read_text()) if PROGRAM_CATALOG_PATH.exists() else []


def decode_program(program):
    decoded = dict(program)
    decoded["requirements"] = json.loads(program.get("requirements_json") or "[]")
    decoded["requirement_sections"] = json.loads(program.get("requirement_sections_json") or "[]")
    decoded["requirement_sections"] = normalize_requirement_sections(decoded)
    return decoded


COMPUTER_SCIENCE_MAJOR_CONCENTRATION_GROUPS = [
    ("18 credits selected as follows:", []),
    ("3 credits from each of the groups A, B, C, and D:", []),
    ("Group A:", ["MATH 222", "MATH 323", "MATH 324"]),
    ("Group B:", ["MATH 223", "MATH 318", "MATH 340"]),
    ("Group C:", ["COMP 330", "COMP 350", "COMP 360"]),
    ("Group D:", ["COMP 302", "COMP 303"]),
    ("An additional 3 credits may be selected from Group A or B.", []),
    (
        "The remaining complementary credits must be selected from COMP 230 Logic and Computability. and COMP courses at the 300 level or above (except COMP 396 Undergraduate Research Project. ).",
        [],
    ),
]


COURSE_GROUP_OVERRIDES = {
    "arts-programs-computer-science-computer-science-major-concentration-ba": {
        "Complementary Courses": COMPUTER_SCIENCE_MAJOR_CONCENTRATION_GROUPS
    },
    "arts-science-programs-computer-science-computer-science-major-concentration-ba": {
        "Complementary Courses": COMPUTER_SCIENCE_MAJOR_CONCENTRATION_GROUPS
    },
    "science-programs-computer-science-computer-science-artificial-intelligence-major-bsc": {
        "Complementary Courses": [
            ("6 credits selected from:", ["COMP 330", "COMP 350", "COMP 360"]),
            ("3 credits selected from:", ["COMP 310", "COMP 421"]),
            ("3 or 4 credits selected from:", ["COMP 451", "COMP 551"]),
            ("3 credits selected from:", ["COMP 345", "COMP 370", "COMP 417", "COMP 445"]),
            (
                "3 or 4 credits selected from:",
                [
                    "COMP 511",
                    "COMP 514",
                    "COMP 545",
                    "COMP 549",
                    "COMP 550",
                    "COMP 558",
                    "COMP 562",
                    "COMP 565",
                    "COMP 579",
                    "COMP 585",
                    "ECSE 552",
                    "ECSE 557",
                ],
            ),
            (
                "6 credits of COMP courses at the 300 level or above (except COMP 396 Undergraduate Research Project. ).",
                [],
            ),
        ]
    }
}


def _section_override(program_id, heading):
    overrides = COURSE_GROUP_OVERRIDES.get(program_id, {})
    normalized_heading = re.sub(r"\s*\([^)]*\)\s*$", "", heading or "").strip()
    return overrides.get(normalized_heading)


def _is_selector_note(note):
    text = (note or "").lower()
    return "selected from" in text or "selected from the following" in text


def _minimum_option_count(note):
    if not _is_selector_note(note):
        return 0
    match = re.search(r"\d+", note or "")
    if not match:
        return 2
    credits = int(match.group(0))
    if credits <= 0:
        return 0
    if credits <= 4:
        return 2
    return max(2, credits // 3 + 1)


def _infer_legacy_course_groups(section):
    notes = section.get("notes", [])
    courses = section.get("courses", [])
    if not notes or not courses:
        return []
    groups = []
    course_index = 0
    selector_notes = [_is_selector_note(note) for note in notes]
    for index, note in enumerate(notes):
        group_courses = []
        if selector_notes[index] and course_index < len(courses):
            later_minimum = sum(
                _minimum_option_count(later_note)
                for later_note, is_selector in zip(notes[index + 1 :], selector_notes[index + 1 :])
                if is_selector
            )
            remaining_courses = len(courses) - course_index
            take = max(_minimum_option_count(note), remaining_courses - later_minimum)
            if any(selector_notes[index + 1 :]):
                take = min(take, max(0, remaining_courses - later_minimum))
            else:
                take = remaining_courses
            group_courses = courses[course_index : course_index + take]
            course_index += len(group_courses)
        groups.append({"note": note, "courses": group_courses})
    if course_index < len(courses):
        groups.append({"note": "", "courses": courses[course_index:]})
    return [group for group in groups if group["note"] or group["courses"]]


def normalize_requirement_sections(program):
    sections = []
    for section in program["requirement_sections"]:
        normalized = dict(section)
        normalized["display_groups"] = []
        override = _section_override(program["program_id"], section.get("heading", ""))
        if override:
            courses_by_code = {course.get("code"): course for course in section.get("courses", [])}
            used_codes = set()
            for note, codes in override:
                grouped_courses = [courses_by_code[code] for code in codes if code in courses_by_code]
                used_codes.update(course.get("code") for course in grouped_courses)
                normalized["display_groups"].append({"note": note, "courses": grouped_courses})
            remaining = [course for course in section.get("courses", []) if course.get("code") not in used_codes]
            if remaining:
                normalized["display_groups"].append({"note": "Additional courses:", "courses": remaining})
        elif section.get("course_groups"):
            normalized["display_groups"] = [
                {"note": group.get("note", ""), "courses": group.get("courses", [])}
                for group in section.get("course_groups", [])
                if group.get("note") or group.get("courses")
            ]
        elif len(section.get("notes", [])) > 1 and section.get("courses"):
            normalized["display_groups"] = _infer_legacy_course_groups(section)
        sections.append(normalized)
    return sections


def group_programs(programs):
    grouped = {}
    for program in programs:
        grouped.setdefault(program["faculty"], {}).setdefault(program["major_group"], []).append(program)
    return grouped


def program_matches_query(program, query):
    query = query.lower().strip()
    haystack = " ".join(
        str(program.get(field, ""))
        for field in ("title", "faculty", "major_group", "program_type", "degree")
    ).lower()
    return query in haystack


def submit_curriculum_request(request_type, requested_value, requested_faculty=None, requested_major_group=None):
    execute(
        """
        INSERT INTO curriculum_requests(student_id,request_type,requested_value,requested_faculty,requested_major_group)
        VALUES(?,?,?,?,?)
        """,
        current_student_id(),
        request_type,
        requested_value,
        requested_faculty,
        requested_major_group,
    )


def get_curriculum():
    account = get_current_account()
    if account and account["role"] == "student":
        degree = "Bachelor of Science" if account["faculty"] == "Science" else "Bachelor of Arts"
        degree_short = "B Sc" if account["faculty"] == "Science" else "B A"
        return {
            "faculty": faculty_display_name(account["faculty"]),
            "degree": degree,
            "degree_short": degree_short,
            "program_group": account["major_group"],
            "primary_major": account["major"],
            "secondary_program": account.get("minor") or "",
        }
    curriculum = dict(DEFAULT_CURRICULUM)
    saved = session.get("curriculum")
    if isinstance(saved, dict):
        curriculum.update({key: saved.get(key, value) for key, value in curriculum.items()})
    if curriculum["primary_major"] not in PHYS_EARTH_MATH_COMP_SCI_MAJORS:
        curriculum["primary_major"] = DEFAULT_CURRICULUM["primary_major"]
    return curriculum


def save_curriculum(**updates):
    curriculum = get_curriculum()
    curriculum.update(updates)
    session["curriculum"] = curriculum
    return curriculum


def minor_value(option):
    return f"{option['faculty']}|{option['name']}"


def find_minor(value):
    for option in MINOR_OPTIONS:
        if minor_value(option) == value:
            return option
    return None


def transcript_program_lines(curriculum):
    lines = [
        f"{curriculum['degree_short']} {curriculum['program_group']}",
        "Full-time",
        f"Major {curriculum['primary_major']}",
    ]
    if curriculum.get("secondary_program"):
        lines.append(f"Minor {curriculum['secondary_program']}")
    return lines


def transcript_terms_for_student(student_id):
    rows = q(
        """
        SELECT * FROM transcript_entries
        WHERE student_id=?
        ORDER BY term, course_code
        """,
        student_id,
    )
    if not rows:
        return TRANSCRIPT_TERMS
    by_term = {}
    for row in rows:
        code_parts = row["course_code"].split(" ", 1)
        subject = code_parts[0]
        number = code_parts[1] if len(code_parts) > 1 else ""
        by_term.setdefault(row["term"], []).append(
            (subject, number, "001", row["course_code"], str(row["credits"]), row["grade"], str(row["credits"]), row["grade"])
        )
    terms = []
    cumulative = 0.0
    for idx, (term, courses) in enumerate(by_term.items(), start=1):
        term_credits = sum(float(course[4]) for course in courses)
        cumulative += term_credits
        terms.append(
            {
                "term": term,
                "year": f"Year {idx}",
                "courses": courses,
                "term_gpa": "3.50",
                "cum_gpa": "3.50",
                "term_total": f"{term_credits:.2f}",
                "cum_total": f"{cumulative:.2f}",
                "points": f"{term_credits * 3.5:.2f}",
                "total_credits": f"{cumulative + 24:.2f}",
            }
        )
    return terms


def current_student_profile():
    account = get_current_account()
    if account and account["role"] == "student":
        return {
            "name": account["name"],
            "display_name": account_display_name(account),
            "student_id": str(account["student_id"]),
            "permanent_code": f"{str(account['student_id'])[-4:]}BKULITE",
            "advisor": q1("SELECT name FROM advisors WHERE advisor_id=?", account["advisor_id"])["name"],
            "residency": "out_of_province",
            "faculty": account["faculty"],
            "major": account["major"],
            "degree": get_curriculum()["degree"],
        }
    curriculum = get_curriculum()
    return {
        "name": "Maya Chen",
        "display_name": "Chen, Maya",
        "student_id": "260123456",
        "permanent_code": "CHEN04060400",
        "advisor": "Dr. Maren Quenvar-Advising-SCI",
        "residency": "out_of_province",
        "faculty": "Science",
        "major": curriculum["primary_major"],
        "degree": curriculum["degree"],
    }


def current_billing_profile():
    student = current_student_profile()
    return profile_for_faculty(student["faculty"] if student["faculty"] in INTERFACULTY_OPTIONS else "Science")


def posted_payments():
    student_id = current_student_id()
    db_payments = [
        {
            "amount": str(row["amount"]),
            "term": row["term"],
            "description": row["label"],
            "due_by": due_date_for_term(row["term"]),
            "method": row.get("method") or "Seeded payment",
            "confirmation": row.get("confirmation") or f"MIN-SEED-{row['id']}",
        }
        for row in q("SELECT * FROM bills WHERE student_id=? AND is_paid=1 ORDER BY id", student_id)
    ]
    payments = session.get("payments")
    if isinstance(payments, list):
        return db_payments + payments
    if db_payments:
        return db_payments
    return db_payments + [
        {
            "amount": "2250.00",
            "term": "Fall 2026",
            "description": "Online bill payment",
            "due_by": "August 31, 2026",
            "method": "Interac debit ending in 1842",
            "confirmation": "MIN-20260815-1042",
        }
    ]


def save_posted_payments(payments):
    session["payments"] = payments


def payments_total(payments=None):
    payments = posted_payments() if payments is None else payments
    return sum((money(payment["amount"]) for payment in payments), money("0.00"))


def due_date_for_term(term):
    return {
        "Summer 2026": "May 29, 2026",
        "Fall 2026": "August 31, 2026",
        "Winter 2027": "January 29, 2027",
    }.get(term, "August 31, 2026")


def term_index_for(term):
    return 1 if term == "Winter 2027" else 0


def account_summary():
    account = get_current_account()
    if account and account["role"] == "student":
        payments = posted_payments()
        paid = payments_total(payments)
        session_paid = payments_total(session.get("payments", [])) if isinstance(session.get("payments"), list) else money("0")
        balance = money(str(account["current_balance"])) - session_paid
        return {
            "term": get_current_term(),
            "term_index": term_index_for(get_current_term()),
            "full_payment_due_by": due_date_for_term(get_current_term()),
            "charges": money(paid + balance),
            "paid": paid,
            "balance": balance,
        }
    term = get_current_term()
    term_index = term_index_for(term)
    profile = current_billing_profile()
    residency = current_student_profile()["residency"]
    charges = term_total_for_profile(profile, residency, term_index)
    paid = payments_total()
    return {
        "term": term,
        "term_index": term_index,
        "full_payment_due_by": due_date_for_term(term),
        "charges": charges,
        "paid": paid,
        "balance": money(charges - paid),
    }


def format_money(value):
    value = money(value)
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


APP.jinja_env.filters["money"] = format_money
APP.jinja_env.filters["faculty_name"] = faculty_display_name


def normalize_digits(value):
    return "".join(ch for ch in value if ch.isdigit())


def has_all_card_details(form):
    return all(
        form.get(field, "").strip()
        for field in ("card_number", "card_name", "expiry", "security_code", "postal_code")
    )


@APP.before_request
def require_login_for_private_pages():
    public_endpoints = {"login", "status", "general", "reset", "static", "eval_state"}
    if request.endpoint in public_endpoints:
        return None
    if not session.get("account_id"):
        return redirect(url_for("login", next=request.full_path.rstrip("?")))
    return None


@APP.get("/status")
def status():
    return jsonify({"service": "minerva-lite", "ok": True})


@APP.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_id = request.form.get("login_id", "").strip()
        password = request.form.get("password", "")
        account = q1("SELECT * FROM accounts WHERE login_id=?", login_id)
        if not account or not check_password_hash(account["password_hash"], password):
            return render_template("login.html", msg="Invalid student ID or password.", next_url=request.form.get("next", ""))
        session.clear()
        session["account_id"] = account["id"]
        session["term"] = DEFAULT_TERM
        session["term_confirmed"] = True
        next_url = request.form.get("next", "").strip()
        if next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect(url_for("advisor_dashboard" if account["role"] == "advisor" else "registration_menu"))
    return render_template("login.html", next_url=request.args.get("next", ""))


@APP.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@APP.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    account = get_current_account()
    msg = ""
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not check_password_hash(account["password_hash"], current_password):
            msg = "Current password is incorrect."
        elif len(new_password) < 8:
            msg = "New password must be at least 8 characters."
        elif new_password != confirm_password:
            msg = "New passwords do not match."
        else:
            execute("UPDATE accounts SET password_hash=? WHERE id=?", generate_password_hash(new_password), account["id"])
            target = "advisor_dashboard" if account["role"] == "advisor" else "registration_menu"
            return redirect(url_for(target, msg="Password updated."))
    return render_template("change_password.html", msg=msg)


@APP.get("/")
def registration_menu():
    account = get_current_account()
    if account and account["role"] == "advisor":
        return redirect(url_for("advisor_dashboard"))
    msg = request.args.get("msg", "")
    return render_template("registration_menu.html", msg=msg)


@APP.get("/general")
def general():
    search_query = request.args.get("q", "").strip()
    selected_program_id = request.args.get("program", "").strip()
    rows = q("SELECT * FROM programs ORDER BY faculty, major_group, title")
    programs = [decode_program(row) for row in rows]
    search_results = [program for program in programs if program_matches_query(program, search_query)] if search_query else []
    selected_program = next((program for program in programs if program["program_id"] == selected_program_id), None)
    if selected_program is None:
        selected_program = (search_results or programs or [None])[0]
    return render_template(
        "general.html",
        grouped_programs=group_programs(programs),
        search_query=search_query,
        search_results=search_results,
        show_search_results=bool(search_query and not selected_program_id),
        selected_program=selected_program,
    )


@APP.get("/student-records")
@role_required("student")
@require_term("student_records_menu")
def student_records_menu():
    return render_template(
        "menu_page.html",
        page_title="Student Records Menu",
        items=STUDENT_RECORDS_ITEMS,
    )


@APP.get("/student-accounts")
@role_required("student")
@require_term("student_accounts_menu")
def student_accounts_menu():
    return render_template(
        "menu_page.html",
        page_title="Student Accounts Menu",
        items=STUDENT_ACCOUNTS_ITEMS,
    )


@APP.get("/student-records/unofficial-transcript")
@role_required("student")
@require_term("view_unofficial_transcript")
def view_unofficial_transcript():
    curriculum = get_curriculum()
    return render_template(
        "transcript.html",
        curriculum=curriculum,
        program_lines=transcript_program_lines(curriculum),
        transcript_terms=transcript_terms_for_student(current_student_id()),
    )


@APP.route("/student-records/change-primary-curriculum", methods=["GET", "POST"])
@role_required("student")
@require_term("change_primary_curriculum")
def change_primary_curriculum():
    msg = ""
    if request.method == "POST":
        major = request.form.get("primary_major", "").strip()
        if major in PHYS_EARTH_MATH_COMP_SCI_MAJORS:
            submit_curriculum_request("primary_major", major, "Science", get_curriculum()["program_group"])
            msg = f"Primary major change request submitted for advisor approval: {major}."
        else:
            msg = "Select a major from the Phys,Earth,Math&Comp Sci group."
    return render_template(
        "curriculum_form.html",
        page_title="Change Primary Curriculum",
        mode="primary",
        curriculum=get_curriculum(),
        major_options=PHYS_EARTH_MATH_COMP_SCI_MAJORS,
        minor_options=MINOR_OPTIONS,
        msg=msg,
    )


@APP.route("/student-records/change-secondary-curriculum", methods=["GET", "POST"])
@role_required("student")
@require_term("change_secondary_curriculum")
def change_secondary_curriculum():
    msg = ""
    if request.method == "POST":
        action = request.form.get("secondary_action", "set").strip()
        if action == "clear":
            submit_curriculum_request("secondary_minor", "")
            msg = "Secondary program removal request submitted for advisor approval."
        else:
            selected = find_minor(request.form.get("secondary_program", "").strip())
            if selected:
                submit_curriculum_request("secondary_minor", selected["name"], selected["faculty"], "")
                msg = f"Secondary minor change request submitted for advisor approval: {selected['name']}."
            else:
                msg = "Select a minor from one of the listed Bolder-Kohn faculties."
    return render_template(
        "curriculum_form.html",
        page_title="Change Secondary Curriculum",
        mode="secondary",
        curriculum=get_curriculum(),
        major_options=PHYS_EARTH_MATH_COMP_SCI_MAJORS,
        minor_options=MINOR_OPTIONS,
        minor_value=minor_value,
        msg=msg,
    )


@APP.route("/student-records/apply-intrafaculty-transfer", methods=["GET", "POST"])
@role_required("student")
@require_term("apply_intrafaculty_transfer")
def apply_intrafaculty_transfer():
    msg = ""
    if request.method == "POST":
        desired_major = request.form.get("desired_major", "").strip()
        desired_minor_option = find_minor(request.form.get("desired_minor", "").strip())
        if desired_major not in PHYS_EARTH_MATH_COMP_SCI_MAJORS:
            msg = "Select a desired major from your current Bolder-Kohn program group."
        else:
            requested = desired_major
            if desired_minor_option:
                requested = f"{desired_major}; minor {desired_minor_option['name']}"
            submit_curriculum_request(
                "intrafaculty_transfer",
                requested,
                "Science",
                get_curriculum()["program_group"],
            )
            msg = "Intrafaculty transfer request submitted for advisor approval."
    return render_template(
        "transfer_form.html",
        page_title="Apply for Intrafaculty Transfer",
        transfer_type="intra",
        curriculum=get_curriculum(),
        major_options=PHYS_EARTH_MATH_COMP_SCI_MAJORS,
        minor_options=MINOR_OPTIONS,
        minor_value=minor_value,
        msg=msg,
    )


@APP.route("/student-records/apply-interfaculty-transfer", methods=["GET", "POST"])
@role_required("student")
@require_term("apply_interfaculty_transfer")
def apply_interfaculty_transfer():
    msg = ""
    selected_faculty = request.form.get("desired_faculty", "Arts").strip() if request.method == "POST" else "Arts"
    if selected_faculty not in INTERFACULTY_OPTIONS:
        selected_faculty = "Arts"
    if request.method == "POST":
        desired_program = request.form.get("desired_program", "").strip()
        allowed = INTERFACULTY_OPTIONS[selected_faculty]
        if desired_program not in allowed:
            msg = "Select a major or program group within the desired faculty."
        else:
            submit_curriculum_request("interfaculty_transfer", desired_program, selected_faculty, desired_program)
            msg = (
                "Interfaculty transfer request submitted for advisor approval: "
                f"{faculty_display_name(selected_faculty)}: {desired_program}."
            )
    return render_template(
        "transfer_form.html",
        page_title="Apply for Interfaculty Transfer",
        transfer_type="inter",
        curriculum=get_curriculum(),
        interfaculty_options=INTERFACULTY_OPTIONS,
        selected_faculty=selected_faculty,
        msg=msg,
    )


@APP.get("/student-accounts/itemized-bill")
@role_required("student")
@require_term("view_itemized_bill")
def view_itemized_bill():
    term = get_current_term()
    student = current_student_profile()
    profile = current_billing_profile()
    residency = student["residency"]
    term_index = term_index_for(term)
    lines = term_lines_for_profile(profile, residency, term_index)
    summary = account_summary()
    return render_template(
        "itemized_bill.html",
        student=student,
        residency_label=RESIDENCY_LABELS[residency],
        lines=lines,
        payments=posted_payments(),
        summary=summary,
        amount_catalog=amount_due_catalog(INTERFACULTY_OPTIONS, PHYS_EARTH_MATH_COMP_SCI_MAJORS),
        residency_labels=RESIDENCY_LABELS,
    )


@APP.get("/student-accounts/previous-payments")
@role_required("student")
@require_term("view_previous_payments")
def view_previous_payments():
    return render_template(
        "previous_payments.html",
        payments=posted_payments(),
        summary=account_summary(),
    )


@APP.route("/student-accounts/pay-bill", methods=["GET", "POST"])
@role_required("student")
@require_term("pay_bill")
def pay_bill():
    msg = ""
    if request.method == "POST":
        amount_raw = request.form.get("amount", "").strip()
        try:
            amount = money(amount_raw)
        except Exception:
            amount = money("0.00")
        if amount <= 0:
            msg = "Enter a payment amount greater than $0.00."
        elif not has_all_card_details(request.form):
            msg = "Enter all payment card details."
        else:
            method_type = request.form.get("method_type", "Credit Card").strip() or "Credit Card"
            card_number = normalize_digits(request.form.get("card_number", ""))
            if card_number not in ACCEPTED_PAYMENT_CARDS:
                msg = "Card declined."
            else:
                last_four = card_number[-4:]
                payments = posted_payments()
                payments.append(
                    {
                        "amount": str(amount),
                        "term": get_current_term(),
                        "description": "Student account payment",
                        "due_by": due_date_for_term(get_current_term()),
                        "method": f"{method_type} ending in {last_four}",
                        "confirmation": f"MIN-{len(payments) + 1:06d}",
                    }
                )
                save_posted_payments(payments)
                return redirect(url_for("pay_bill", step="confirmation", msg="Payment accepted."))
    return render_template(
        "pay_bill.html",
        step=request.args.get("step", "review"),
        msg=request.args.get("msg", msg),
        summary=account_summary(),
        student=current_student_profile(),
    )


@APP.route("/student-accounts/request-refund", methods=["GET", "POST"])
@role_required("student")
@require_term("request_refund")
def request_refund():
    summary = account_summary()
    msg = ""
    if request.method == "POST":
        if summary["balance"] <= 0:
            msg = "You cannot request a refund if your balance is at or below $0.00."
        else:
            refund_type = request.form.get("refund_type", "full").strip()
            try:
                amount = summary["balance"] if refund_type == "full" else money(request.form.get("amount", "0"))
            except Exception:
                amount = money("0.00")
            if amount <= 0:
                msg = "Enter a partial refund amount greater than $0.00."
            elif amount > summary["balance"]:
                msg = "Partial refund amount cannot exceed the current account balance."
            else:
                msg = f"Refund request submitted for {format_money(amount)}."
    return render_template("request_refund.html", summary=summary, msg=msg)


@APP.get("/search")
@role_required("student")
@require_term("search")
def search():
    subject = request.args.get("subject", "").strip().upper()
    number = request.args.get("number", "").strip()
    title = request.args.get("title", "").strip()
    campus = request.args.get("campus", "").strip()
    term = get_current_term()
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        page = 1
    per_page = 30

    sql = "FROM courses WHERE parent_crn IS NULL"
    args = []
    if term:
        sql += " AND term = ?"
        args.append(term)
    if subject:
        sql += " AND subject = ?"
        args.append(subject)
    if number:
        sql += " AND number LIKE ?"
        args.append(f"%{number}%")
    if title:
        sql += " AND lower(title) LIKE ?"
        args.append(f"%{title.lower()}%")
    if campus:
        sql += " AND campus = ?"
        args.append(campus)
    total = q(f"SELECT COUNT(*) AS count {sql}", *args)[0]["count"]
    offset = (page - 1) * per_page
    results = q(
        f"SELECT * {sql} ORDER BY subject, number, crn LIMIT ? OFFSET ?",
        *args,
        per_page,
        offset,
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        return redirect(url_for("search", subject=subject, number=number, title=title, campus=campus, page=total_pages))
    components_by_parent = {}
    if results:
        parent_crns = [c["crn"] for c in results]
        placeholders = ",".join("?" for _ in parent_crns)
        component_rows = q(
            f"""
            SELECT * FROM courses
            WHERE parent_crn IN ({placeholders})
            ORDER BY parent_crn, section_type, crn
            """,
            *parent_crns,
        )
        for component in component_rows:
            components_by_parent.setdefault(component["parent_crn"], []).append(component)
    return render_template(
        "search.html",
        results=results,
        components_by_parent=components_by_parent,
        page=page,
        total_pages=total_pages,
        total_results=total,
        per_page=per_page,
    )


@APP.post("/add")
@role_required("student")
def add_course():
    crn = request.form.get("crn", "").strip()
    if not crn:
        return redirect(url_for("add_drop", msg="Enter a CRN."))
    # Check if exists
    rows = q("SELECT * FROM courses WHERE crn=?", crn)
    if not rows:
        return redirect(url_for("add_drop", msg="Invalid CRN."))
    course = rows[0]
    # Ensure CRN belongs to the currently selected term
    current_term = get_current_term()
    if course.get("term") != current_term:
        return redirect(url_for("add_drop", msg=f"CRN not in {current_term} term."))
    # Check if already registered or waitlisted
    student_id = current_student_id()
    reg = q("SELECT * FROM registrations WHERE student_id=? AND crn=?", student_id, crn)
    if reg:
        return redirect(url_for("add_drop", msg="Already registered."))
    wl = q("SELECT * FROM waitlists WHERE student_id=? AND crn=?", student_id, crn)
    if wl:
        return redirect(url_for("add_drop", msg="Already on waitlist."))
    # If seats available, register directly
    if course["seats_taken"] < course["seats_total"]:
        execute("INSERT INTO registrations(student_id,crn) VALUES(?,?)", student_id, crn)
        execute(
            "UPDATE courses SET seats_taken = seats_taken + 1 WHERE crn=?",
            crn,
        )
        return redirect(url_for("schedule", msg="Added CRN %s" % crn))
    # Section full — try waitlist
    if course["waitlist_total"] > 0 and course["waitlist_taken"] < course["waitlist_total"]:
        position = course["waitlist_taken"] + 1
        execute("INSERT INTO waitlists(student_id,crn,position) VALUES(?,?,?)", student_id, crn, position)
        execute(
            "UPDATE courses SET waitlist_taken = waitlist_taken + 1 WHERE crn=?",
            crn,
        )
        return redirect(url_for("add_drop", msg="Section full. Added to waitlist for CRN %s (position %d)." % (crn, position)))
    # Section full and no waitlist spots
    return redirect(url_for("add_drop", msg="Section full and waitlist is full."))


@APP.post("/drop")
@role_required("student")
def drop_course():
    crn = request.form.get("crn", "").strip()
    student_id = current_student_id()
    reg = q("SELECT * FROM registrations WHERE student_id=? AND crn=?", student_id, crn)
    if not reg:
        return redirect(url_for("schedule", msg="Not registered."))
    execute("DELETE FROM registrations WHERE student_id=? AND crn=?", student_id, crn)
    execute(
        "UPDATE courses SET seats_taken = CASE WHEN seats_taken>0 THEN seats_taken-1 ELSE 0 END WHERE crn=?",
        crn,
    )
    return redirect(url_for("schedule", msg="Dropped CRN %s" % crn))


@APP.post("/drop-waitlist")
@role_required("student")
def drop_waitlist():
    crn = request.form.get("crn", "").strip()
    student_id = current_student_id()
    wl = q("SELECT * FROM waitlists WHERE student_id=? AND crn=?", student_id, crn)
    if not wl:
        return redirect(url_for("add_drop", msg="Not on waitlist."))
    execute("DELETE FROM waitlists WHERE student_id=? AND crn=?", student_id, crn)
    execute(
        "UPDATE courses SET waitlist_taken = CASE WHEN waitlist_taken>0 THEN waitlist_taken-1 ELSE 0 END WHERE crn=?",
        crn,
    )
    return redirect(url_for("add_drop", msg="Removed from waitlist for CRN %s" % crn))


@APP.get("/add-drop")
@role_required("student")
@require_term("add_drop")
def add_drop():
    msg = request.args.get("msg", "")
    current_term = get_current_term()
    student_id = current_student_id()
    regs = q(
        "SELECT c.* FROM registrations r JOIN courses c ON r.crn=c.crn WHERE r.student_id=? AND c.term=? ORDER BY c.subject, c.number, COALESCE(c.parent_crn, c.crn), c.parent_crn IS NOT NULL, c.section_type, c.crn",
        student_id,
        current_term,
    )
    waitlisted = q(
        "SELECT c.*, w.position FROM waitlists w JOIN courses c ON w.crn=c.crn WHERE w.student_id=? AND c.term=? ORDER BY c.subject, c.number, COALESCE(c.parent_crn, c.crn), c.parent_crn IS NOT NULL, c.section_type, c.crn",
        student_id,
        current_term,
    )
    return render_template("add_drop.html", regs=regs, waitlisted=waitlisted, msg=msg)


@APP.get("/schedule")
@role_required("student")
@require_term("schedule")
def schedule():
    msg = request.args.get("msg", "")
    current_term = get_current_term()
    student_id = current_student_id()
    regs = q(
        "SELECT c.* FROM registrations r JOIN courses c ON r.crn=c.crn WHERE r.student_id=? AND c.term=? ORDER BY c.subject, c.number, COALESCE(c.parent_crn, c.crn), c.parent_crn IS NOT NULL, c.section_type, c.crn",
        student_id,
        current_term,
    )
    waitlisted = q(
        "SELECT c.*, w.position FROM waitlists w JOIN courses c ON w.crn=c.crn WHERE w.student_id=? AND c.term=? ORDER BY c.subject, c.number, COALESCE(c.parent_crn, c.crn), c.parent_crn IS NOT NULL, c.section_type, c.crn",
        student_id,
        current_term,
    )
    return render_template("schedule.html", regs=regs, waitlisted=waitlisted, msg=msg)


def _parse_time_range(range_str):
    try:
        s, e = [t.strip() for t in range_str.split("-")]
        sh, sm = [int(x) for x in s.split(":")]
        eh, em = [int(x) for x in e.split(":")]
        return sh * 60 + sm, eh * 60 + em
    except Exception:
        return None, None


@APP.get("/schedule-week")
@role_required("student")
@require_term("schedule_week")
def schedule_week():
    # Build weekly event blocks for registered sections
    current_term = get_current_term()
    regs = q(
        "SELECT c.* FROM registrations r JOIN courses c ON r.crn=c.crn WHERE r.student_id=? AND c.term=?",
        current_student_id(),
        current_term,
    )
    start_day_min = 8 * 60  # 08:00 grid start
    end_day_min = 18 * 60   # 18:00 grid end
    span = end_day_min - start_day_min
    grid_px = 800  # matches CSS .grid-body height
    day_map = {"M": 1, "T": 2, "W": 3, "R": 4, "F": 5}

    events = []
    for c in regs:
        smin, emin = _parse_time_range(c.get("time") or "")
        if smin is None:
            continue
        duration = max(emin - smin, 30)
        # pixel-perfect placement using the same 800px grid height
        top_px = max(int(round((smin - start_day_min) / span * grid_px)), 0)
        height_px = max(int(round(duration / span * grid_px)), 2)
        for ch in (c.get("days") or ""):  # e.g., "MWF" or "TR"
            if ch in day_map:
                events.append({
                    "day_col": day_map[ch],
                    "title": f"{c['subject']} {c['number']} {c['section_type']}",
                    "subtitle": c["title"],
                    "professor": c["professor"],
                    "time": c["time"],
                    "top_px": top_px,
                    "height_px": height_px,
                    "crn": c["crn"],
                })

    # Time labels every hour for the left rail
    time_labels = []
    for h in range(8, 18):
        time_labels.append(f"{h:02d}:00")

    return render_template(
        "schedule_week.html",
        events=events,
        time_labels=time_labels,
    )


@APP.get("/accounts")
@role_required("student")
@require_term("accounts")
def accounts():
    return redirect(url_for("student_accounts_menu"))


@APP.get("/advisor")
@role_required("advisor")
def advisor_dashboard():
    msg = request.args.get("msg", "")
    student_query = request.args.get("q", "").strip()
    students = q(
        """
        SELECT s.id AS student_id, s.name, s.major, s.minor, s.faculty, s.major_group,
               s.current_balance
        FROM students s
        ORDER BY s.name
        """
    )
    if student_query:
        needle = student_query.lower()
        students = [
            student
            for student in students
            if needle
            in " ".join(
                str(student.get(field, ""))
                for field in ("name", "student_id", "major", "minor", "faculty", "major_group")
            ).lower()
        ]
    selected_id = request.args.get("student", str(students[0]["student_id"]) if students else "").strip()
    selected_student = q1(
        """
        SELECT s.id AS student_id, s.name, s.major, s.minor, s.faculty, s.major_group,
               s.current_balance, a.login_id
        FROM students s
        JOIN accounts a ON a.id=s.account_id
        WHERE s.id=?
        """,
        selected_id,
    )
    registered = []
    waitlist = []
    transcript_entries = []
    curriculum_requests = []
    if selected_student:
        registered = q(
            """
            SELECT c.*, c.subject || ' ' || c.number AS course_code
            FROM registrations r
            JOIN courses c ON c.crn=r.crn
            WHERE r.student_id=? AND c.term=?
            ORDER BY c.subject, c.number
            """,
            selected_student["student_id"],
            get_current_term(),
        )
        waitlist = q(
            """
            SELECT c.*, c.subject || ' ' || c.number AS course_code,
                   w.position AS waitlist_position
            FROM waitlists w
            JOIN courses c ON c.crn=w.crn
            WHERE w.student_id=? AND c.term=?
            ORDER BY w.position, c.subject, c.number
            """,
            selected_student["student_id"],
            get_current_term(),
        )
        transcript_entries = q(
            """
            SELECT course_code, course_code AS title, term, grade
            FROM transcript_entries
            WHERE student_id=?
            ORDER BY term, course_code
            """,
            selected_student["student_id"],
        )
        curriculum_requests = q(
            """
            SELECT *
            FROM curriculum_requests
            WHERE student_id=? AND status='pending'
            ORDER BY created_at
            """,
            selected_student["student_id"],
        )
    programs = [
        decode_program(row)
        for row in q(
            """
            SELECT *
            FROM programs
            WHERE program_type IN ('Major','Major Concentration','Honours','Joint')
            ORDER BY faculty, major_group, title
            """
        )
    ]
    return render_template(
        "advisor.html",
        msg=msg,
        students=students,
        student_query=student_query,
        selected_student=selected_student,
        registered=registered,
        waitlist=waitlist,
        transcript_entries=transcript_entries,
        curriculum_requests=curriculum_requests,
        programs=programs,
    )


@APP.post("/advisor/update-major")
@role_required("advisor")
def advisor_update_major():
    student_id = request.form.get("student_id", "").strip()
    major = request.form.get("major", "").strip()
    minor = request.form.get("minor", "").strip()
    faculty = request.form.get("faculty", "").strip() or "Science"
    major_group = request.form.get("major_group", "").strip() or major
    if not student_id or not major:
        return redirect(url_for("advisor_dashboard", msg="Select a student and major."))
    execute(
        "UPDATE students SET major=?, minor=?, faculty=?, major_group=? WHERE id=?",
        major,
        minor,
        faculty,
        major_group,
        student_id,
    )
    return redirect(url_for("advisor_dashboard", student=student_id, msg="Student curriculum updated."))


@APP.post("/advisor/curriculum-request")
@role_required("advisor")
def advisor_curriculum_request():
    request_id = request.form.get("request_id", "").strip()
    action = request.form.get("action", "").strip()
    row = q1("SELECT * FROM curriculum_requests WHERE id=?", request_id)
    if not row:
        return redirect(url_for("advisor_dashboard", msg="Request not found."))
    if action == "approve":
        if row["request_type"] == "primary_major":
            execute("UPDATE students SET major=?, faculty=COALESCE(?, faculty), major_group=COALESCE(?, major_group) WHERE id=?", row["requested_value"], row["requested_faculty"], row["requested_major_group"], row["student_id"])
        elif row["request_type"] == "secondary_minor":
            execute("UPDATE students SET minor=? WHERE id=?", row["requested_value"], row["student_id"])
        elif row["request_type"] in {"intrafaculty_transfer", "interfaculty_transfer"}:
            execute("UPDATE students SET major=?, faculty=COALESCE(?, faculty), major_group=COALESCE(?, major_group) WHERE id=?", row["requested_value"], row["requested_faculty"], row["requested_major_group"], row["student_id"])
        execute("UPDATE curriculum_requests SET status='approved', decided_at=CURRENT_TIMESTAMP, decided_by=? WHERE id=?", get_current_account()["login_id"], request_id)
        msg = "Curriculum request approved."
    else:
        execute("UPDATE curriculum_requests SET status='rejected', decided_at=CURRENT_TIMESTAMP, decided_by=? WHERE id=?", get_current_account()["login_id"], request_id)
        msg = "Curriculum request rejected."
    return redirect(url_for("advisor_dashboard", student=row["student_id"], msg=msg))


@APP.post("/advisor/force-register")
@role_required("advisor")
def advisor_force_register():
    student_id = request.form.get("student_id", "").strip()
    crn = request.form.get("crn", "").strip()
    course = q1("SELECT * FROM courses WHERE crn=?", crn)
    if not student_id or not course:
        return redirect(url_for("advisor_dashboard", student=student_id, msg="Course or student not found."))
    execute("DELETE FROM waitlists WHERE student_id=? AND crn=?", student_id, crn)
    execute("INSERT OR IGNORE INTO registrations(student_id,crn) VALUES(?,?)", student_id, crn)
    execute("UPDATE courses SET seats_taken = seats_taken + 1, waitlist_taken = CASE WHEN waitlist_taken>0 THEN waitlist_taken-1 ELSE 0 END WHERE crn=?", crn)
    return redirect(url_for("advisor_dashboard", student=student_id, msg=f"Moved CRN {crn} into registered courses."))


@APP.post("/set-term")
def set_term():
    term = request.form.get("term", "").strip().title()
    if term not in TERMS:
        return redirect(url_for("registration_menu", msg="Invalid term."))
    session["term"] = term
    session["term_confirmed"] = True
    return_to = request.form.get("return_to", "").strip()
    next_key = request.form.get("next", "").strip()
    if next_key in STEP_DESTINATIONS:
        endpoint = STEP_DESTINATIONS[next_key]["endpoint"]
        return redirect(url_for(endpoint))
    if return_to.startswith("/") and not return_to.startswith("//"):
        return redirect(return_to)
    # Redirect back to the referrer if possible
    ref = request.headers.get("Referer")
    return redirect(ref or url_for("registration_menu", msg=f"Term set to {term}"))


@APP.get("/select-term")
def select_term():
    next_key = request.args.get("next", "search").strip()
    destination = STEP_DESTINATIONS.get(next_key, STEP_DESTINATIONS["search"])
    if request.args.get("reset"):
        session["term_confirmed"] = False
    return render_template(
        "select_term.html",
        next_key=next_key,
        destination_label=destination["label"],
    )


@APP.context_processor
def inject_term():
    current_step_key = STEP_KEYS_BY_ENDPOINT.get(request.endpoint, "")
    if request.endpoint == "select_term":
        current_step_key = request.args.get("next", current_step_key or "search")
    full_path = request.full_path
    current_return_path = full_path[:-1] if full_path.endswith("?") else full_path
    return {
        "current_term": get_current_term(),
        "terms": TERMS,
        "term_confirmed": True,
        "current_step_key": current_step_key,
        "current_return_path": current_return_path,
        "current_account": get_current_account(),
    }


@APP.get("/reset")
def reset():
    if DB_PATH.exists():
        DB_PATH.unlink()
    seed.seed_database()
    return jsonify({"reset": True})


# ------------------------------------------------------------------------------
# Read-only evaluation API
# ------------------------------------------------------------------------------
# Exposes backend state as JSON so the WebArena-Pro evaluator can grade tasks
# deterministically. Strictly read-only and gated by a secret token
# (WP_EVAL_TOKEN) the agent under test never sees, so it cannot be used to read
# answers. Disabled (403) when WP_EVAL_TOKEN is unset. Account password hashes
# are never returned.

EVAL_STATE_TABLES = [
    "students", "advisors", "programs", "courses", "registrations",
    "waitlists", "transcript_entries", "bills", "curriculum_requests",
]


def _eval_authorized():
    token = os.environ.get("WP_EVAL_TOKEN")
    return bool(token) and request.headers.get("X-Eval-Token") == token


@APP.get("/api/eval/state")
def eval_state():
    """Return relevant backend tables as JSON (read-only, token-gated)."""
    if not _eval_authorized():
        return jsonify({"error": "forbidden"}), 403
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    out = {}
    try:
        # accounts without the password_hash column
        try:
            out["accounts"] = [
                dict(r) for r in con.execute(
                    "SELECT id, login_id, name, role FROM accounts"
                ).fetchall()
            ]
        except sqlite3.Error:
            out["accounts"] = []
        for table in EVAL_STATE_TABLES:
            try:
                out[table] = [dict(r) for r in con.execute(f"SELECT * FROM {table}").fetchall()]
            except sqlite3.Error:
                out[table] = []
    finally:
        con.close()
    return jsonify(out)


if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=8000)
