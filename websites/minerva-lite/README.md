# Minerva-lite: Bolder-Kohn University Course Registration System

A lightweight web application for course registration and student scheduling. This is a simplified implementation of a university course registration system that allows students to search for classes, manage their course schedule, and view their enrollment status.

## Features

### 0. **Authentication and Roles**

- Sign in is required for private Minerva-lite pages
- Student accounts open the registration, records, accounts, search, add/drop, and schedule workflows
- Advisor accounts open an advisor dashboard for student lookup, curriculum review, and registration support
- Users can change their password from the Student Records menu

### 1. **Registration Menu** (Home Page)

- Entry point for course registration workflow
- Overview of the four registration process steps
- Navigation hub to access other features

### 2. **Student Records Menu**

- Access records-related actions:
  - View unofficial transcript
  - Change primary curriculum
  - Change secondary curriculum
  - Apply for intrafaculty transfer
  - Apply for interfaculty transfer
- The unofficial transcript displays a print-style Bolder-Kohn University record for a second-year B.Sc. Computer Science student in the Phys,Earth,Math&Comp Sci group
- Primary curriculum changes are limited to majors in the current Bolder-Kohn faculty program group
- Secondary curriculum change requests allow minors from the listed Bolder-Kohn faculties
- Intrafaculty and interfaculty transfer forms capture desired majors or program groups
- Curriculum changes are submitted for advisor approval instead of being applied immediately

### 3. **Student Accounts Menu**

- Access account-related actions:
  - View itemized bill
  - View previous payments
  - Pay bill
  - Request refund
- Account pages use Bolder-Kohn University Student Accounts 2025-2026 fee tables stored in `billing_math.py`
- The itemized bill shows charges, posted payments, outstanding balances, and a faculty/major/residency rate catalog for future demo users
- Previous payments are displayed as separate payment entries with amount paid, amount due, details, term, due date, and payment method
- Pay bill requires complete debit or credit card details and accepts an allowlist of demo payment cards for any positive amount, including overpayments
- Refund requests support full and partial refund selections and block requests when the balance is at or below $0.00

### 4. **Search Class Schedule**

- Search courses by:
  - **Subject**: Filter by department/subject code (e.g., COMP, MATH)
  - **Course Number**: Search by course number or partial matches
  - **Course Title**: Search for keywords in course titles
  - **Campus**: Filter by campus location
- View detailed course information including:
  - Course code and title
  - Instructor and schedule details
  - Available seats and waitlist information
  - CRN (Course Registration Number)
  - Linked laboratory and conference sections with their own CRNs

### 5. **Add/Drop Courses**

- Add courses to your schedule by entering the CRN for each lecture, laboratory, or conference section
- Drop courses from your current registration
- View all currently enrolled courses
- Real-time seat availability updates
- Error handling for invalid operations:
  - Duplicate enrollment prevention
  - Closed course detection
  - Cross-term validation

### 6. **Student Schedule**

- View all currently registered courses for the selected term
- Display course details including:
  - Subject and course number
  - Course title
  - Section type
  - Meeting times and instructor information
- Drop courses from this view

### 7. **Weekly Schedule View**

- Visual calendar representation of your course schedule
- Grid-based weekly layout (Monday–Friday, 8:00 AM–6:00 PM)
- Color-coded course blocks showing:
  - Course code and title
  - Meeting time
  - Duration
- Easy identification of schedule conflicts

### 8. **Term Selection**

- Switch between available academic terms:
  - Summer 2026
  - Fall 2026
  - Winter 2027
- Session-based term management
- Ability to change term without losing application state

### 9. **Advisor Dashboard**

- Search students by name, student ID, faculty, major, minor, or major group
- View a selected student's current registrations, waitlist, transcript entries, and pending curriculum requests
- Update a student's major, minor, faculty, or major group
- Approve or reject pending curriculum requests
- Force-register a student into a course by CRN

## Usage Notes

- Term must be selected before accessing most features
- Student operations are performed for the signed-in student account
- The system prevents duplicate registrations and respects seat availability
- Some lecture sections have linked laboratory or conference sections that must be found in search and added by CRN

## Sign In

### Student Accounts

| Student | Login ID | Password | Faculty | Program |
|---------|----------|----------|---------|---------|
| Alice Chen | `260123456` | `mcgill123` | Bolder-Kohn Faculty of Natural and Computational Sciences | Computer Science Major (B.Sc.) |
| Noah Singh | `260223344` | `mcgill123` | Bolder-Kohn Faculty of Arts and Letters | Economics Major Concentration (B.A.) |
| Sofia Martinez | `260334455` | `mcgill123` | Bolder-Kohn Faculty of Integrated Arts and Sciences | Computer Science Major Concentration (B.A.) |
| Liam O'Brien | `260445566` | `mcgill123` | Bolder-Kohn Faculty of Natural and Computational Sciences | Biology Major (B.Sc.) |

### Advisor Accounts

| Advisor | Login ID | Password | Faculty | Department |
|---------|----------|----------|---------|------------|
| Dr. Maren Quenvar-Advising-SCI | `9801001` | `advisor123` | Bolder-Kohn Faculty of Natural and Computational Sciences | Computer Science |
| Dr. Solen Quenvar-Advising-ARTS | `9801002` | `advisor123` | Bolder-Kohn Faculty of Arts and Letters | Economics and Political Science |
| Dr. Veyra Quenvar-Advising-IAS | `9801003` | `advisor123` | Bolder-Kohn Faculty of Integrated Arts and Sciences | Interfaculty Programs |

## Accepted Payment Cards

Minerva-lite validates that all payment fields are present, then checks the card number against the demo allowlist. The password-manager cards below can be used with their saved cardholder, expiry, CVV, and billing postal code.

| Source | Cardholder | Brand | Card Number | Expiry | CVV |
|--------|------------|-------|-------------|--------|-----|
| Password Manager | Jane Smith | Visa | `4111111111111111` | `12/2027` | `123` |
| Password Manager | Jane Smith | Mastercard | `5500005555555559` | `08/2026` | `456` |
| Password Manager | Jane Smith | Amex | `371449635398431` | `03/2028` | `7890` |
| Password Manager | John Smith | Visa | `4532015112830366` | `05/2026` | `789` |
| Legacy demo | Any non-empty name | Demo card | `4000000000001000` | Any non-empty value | Any non-empty value |
| Legacy demo | Any non-empty name | Demo card | `5105105105105100` | Any non-empty value | Any non-empty value |
| Legacy demo | Any non-empty name | Demo card | `6011000990139424` | Any non-empty value | Any non-empty value |
| Legacy demo | Any non-empty name | Demo card | `3566002020360505` | Any non-empty value | Any non-empty value |

## Seed Data

Sample course data is seeded from `data/courses_seed.json` including:

- Computer Science (COMP) courses
- Math, statistics, biology, chemistry, physics, economics, psychology, English, history, political science, sociology, philosophy, geography, and anthropology courses
- Explicit term availability for Summer 2026, Fall 2026, and Winter 2027
- Linked laboratory and conference sections for selected courses
- Bolder-Kohn University Course Catalogue course titles and term-offered patterns, projected onto the 2026-2027 registration year
- Bolder-Kohn University-style meeting days and time slots for schedule search and weekly schedule testing

## Reset Functionality

Hit the `/reset` endpoint to clear the database and re-seed with initial data

## License

WebArena-Pro's original application code and contributions in this directory are
licensed under the [MIT License](LICENSE).

Dependencies, datasets, media, and other third-party components retain their
respective licenses and attribution requirements. They are not relicensed by
this application's MIT license.
