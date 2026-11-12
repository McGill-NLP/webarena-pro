DROP TABLE IF EXISTS curriculum_requests;
DROP TABLE IF EXISTS waitlists;
DROP TABLE IF EXISTS registrations;
DROP TABLE IF EXISTS transcript_entries;
DROP TABLE IF EXISTS bills;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS advisors;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS programs;
DROP TABLE IF EXISTS courses;

CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login_id TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('student', 'advisor'))
);

CREATE TABLE advisors (
    advisor_id TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    faculty TEXT NOT NULL,
    department TEXT NOT NULL,
    office TEXT NOT NULL,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
);

CREATE TABLE students (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    faculty TEXT NOT NULL,
    major TEXT NOT NULL,
    minor TEXT,
    major_group TEXT NOT NULL,
    advisor_id TEXT,
    bills_paid INTEGER NOT NULL DEFAULT 0,
    current_balance REAL NOT NULL DEFAULT 0,
    residency TEXT NOT NULL DEFAULT 'out_of_province',
    FOREIGN KEY(account_id) REFERENCES accounts(id),
    FOREIGN KEY(advisor_id) REFERENCES advisors(advisor_id)
);

CREATE TABLE programs (
    program_id TEXT PRIMARY KEY,
    slug TEXT,
    title TEXT NOT NULL,
    faculty TEXT NOT NULL,
    major_group TEXT NOT NULL,
    program_type TEXT,
    degree TEXT,
    summary TEXT,
    requirements_json TEXT NOT NULL DEFAULT '[]',
    requirement_sections_json TEXT NOT NULL DEFAULT '[]',
    verified_on TEXT,
    official_url TEXT
);

CREATE TABLE courses (
    crn TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    number TEXT NOT NULL,
    title TEXT NOT NULL,
    professor TEXT NOT NULL,
    section_type TEXT NOT NULL DEFAULT 'Lecture',
    parent_crn TEXT,
    credits REAL NOT NULL,
    days TEXT,
    time TEXT,
    campus TEXT NOT NULL,
    term TEXT NOT NULL,
    seats_total INTEGER NOT NULL,
    seats_taken INTEGER NOT NULL DEFAULT 0,
    waitlist_total INTEGER NOT NULL DEFAULT 0,
    waitlist_taken INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(parent_crn) REFERENCES courses(crn)
);

CREATE TABLE registrations (
    student_id INTEGER NOT NULL,
    crn TEXT NOT NULL,
    PRIMARY KEY (student_id, crn),
    FOREIGN KEY(student_id) REFERENCES students(id),
    FOREIGN KEY(crn) REFERENCES courses(crn)
);

CREATE TABLE waitlists (
    student_id INTEGER NOT NULL,
    crn TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (student_id, crn),
    FOREIGN KEY(student_id) REFERENCES students(id),
    FOREIGN KEY(crn) REFERENCES courses(crn)
);

CREATE TABLE transcript_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_code TEXT NOT NULL,
    term TEXT NOT NULL,
    grade TEXT NOT NULL,
    credits REAL NOT NULL,
    FOREIGN KEY(student_id) REFERENCES students(id)
);

CREATE TABLE bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    term TEXT NOT NULL,
    label TEXT NOT NULL,
    amount REAL NOT NULL,
    is_paid INTEGER NOT NULL DEFAULT 0,
    method TEXT,
    confirmation TEXT,
    FOREIGN KEY(student_id) REFERENCES students(id)
);

CREATE TABLE curriculum_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    request_type TEXT NOT NULL,
    requested_value TEXT NOT NULL,
    requested_faculty TEXT,
    requested_major_group TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    decided_at TEXT,
    decided_by TEXT,
    FOREIGN KEY(student_id) REFERENCES students(id)
);
