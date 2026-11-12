from decimal import Decimal, ROUND_HALF_UP


MONEY = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def split_annual_amount(amount, term_index):
    annual = money(amount)
    if term_index == 0:
        return (annual / Decimal("2")).quantize(MONEY, rounding=ROUND_HALF_UP)
    return annual - split_annual_amount(annual, 0)


# Bolder-Kohn University 2025-2026 demo annual fee tables, based on 30
# credits across Fall and Winter. Values are stored locally so the synthetic
# institution does not depend on external billing pages.
RESIDENCY_LABELS = {
    "quebec": "Quebec resident",
    "out_of_province": "Canadian out-of-province",
    "france": "France/Belgium francophone with CAQ",
    "international": "International",
}


DEGREE_FEE_PROFILES = {
    "BA": {
        "degree": "Bachelor of Arts",
        "faculty": "Bolder-Kohn Faculty of Arts and Letters",
        "annual": {
            "quebec": {
                "Tuition": "3026.70",
                "Society and other fees": "704.28",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU health and dental insurance": "345.00",
                "International health insurance": "0.00",
            },
            "out_of_province": {
                "Tuition": "12607.20",
                "Canada Award": "0.00",
                "Society and other fees": "704.28",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU health and dental insurance": "345.00",
                "International health insurance": "0.00",
            },
            "france": {
                "Tuition": "9447.00",
                "Society and other fees": "704.28",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU dental insurance": "150.00",
                "International health insurance": "1155.00",
            },
            "international": {
                "Tuition": "48999.90",
                "Society and other fees": "704.28",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU dental insurance": "150.00",
                "International health insurance": "1155.00",
            },
        },
    },
    "BSc": {
        "degree": "Bachelor of Science",
        "faculty": "Bolder-Kohn Faculty of Natural and Computational Sciences",
        "annual": {
            "quebec": {
                "Tuition": "3026.70",
                "Society and other fees": "673.20",
                "Student services, athletics and recreation": "737.30",
                "Registration, transcripts, diploma and general administrative charges": "405.79",
                "Copyright fee": "33.60",
                "Information technology charges": "288.00",
                "BKSU health and dental insurance": "345.00",
                "International health insurance": "0.00",
            },
            "out_of_province": {
                "Tuition": "12607.20",
                "Canada Award": "0.00",
                "Society and other fees": "652.68",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU health and dental insurance": "345.00",
                "International health insurance": "0.00",
            },
            "france": {
                "Tuition": "9447.00",
                "Society and other fees": "652.68",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU dental insurance": "150.00",
                "International health insurance": "1155.00",
            },
            "international": {
                "Tuition": "62898.90",
                "Society and other fees": "652.68",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU dental insurance": "150.00",
                "International health insurance": "1155.00",
            },
        },
    },
    "BEng": {
        "degree": "Bachelor of Engineering",
        "faculty": "Bolder-Kohn Faculty of Engineering and Design",
        "annual": {
            "quebec": {
                "Tuition": "3026.70",
                "Society and other fees": "1151.28",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU health and dental insurance": "345.00",
                "International health insurance": "0.00",
            },
            "out_of_province": {
                "Tuition": "14677.50",
                "Society and other fees": "1151.28",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU health and dental insurance": "345.00",
                "International health insurance": "0.00",
            },
            "france": {
                "Tuition": "9447.00",
                "Society and other fees": "1151.28",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU dental insurance": "150.00",
                "International health insurance": "1155.00",
            },
            "international": {
                "Tuition": "63889.80",
                "Society and other fees": "1151.28",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU dental insurance": "150.00",
                "International health insurance": "1155.00",
            },
        },
    },
    "BCom": {
        "degree": "Bachelor of Commerce",
        "faculty": "Bolder-Kohn School of Enterprise and Management",
        "annual": {
            "quebec": {
                "Tuition": "3026.70",
                "Society and other fees": "767.18",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU health and dental insurance": "345.00",
                "International health insurance": "0.00",
            },
            "out_of_province": {
                "Tuition": "14677.50",
                "Society and other fees": "767.18",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU health and dental insurance": "345.00",
                "International health insurance": "0.00",
            },
            "france": {
                "Tuition": "9447.00",
                "Society and other fees": "767.18",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU dental insurance": "150.00",
                "International health insurance": "1155.00",
            },
            "international": {
                "Tuition": "69599.40",
                "Society and other fees": "767.18",
                "Student services, athletics and recreation": "752.04",
                "Registration, transcripts, diploma and general administrative charges": "413.86",
                "Copyright fee": "34.20",
                "Information technology charges": "293.70",
                "BKSU dental insurance": "150.00",
                "International health insurance": "1155.00",
            },
        },
    },
}


MAJOR_FEE_MAP = {
    "Arts": {"degree_code": "BA"},
    "Science": {"degree_code": "BSc"},
    "Engineering": {"degree_code": "BEng"},
    "Management": {"degree_code": "BCom"},
}


def profile_for_faculty(faculty):
    return DEGREE_FEE_PROFILES[MAJOR_FEE_MAP[faculty]["degree_code"]]


def annual_lines_for_profile(profile, residency):
    return [
        {"description": description, "amount": money(amount)}
        for description, amount in profile["annual"][residency].items()
    ]


def total_for_profile(profile, residency):
    return sum((line["amount"] for line in annual_lines_for_profile(profile, residency)), Decimal("0.00"))


def term_lines_for_profile(profile, residency, term_index):
    return [
        {"description": line["description"], "amount": split_annual_amount(line["amount"], term_index)}
        for line in annual_lines_for_profile(profile, residency)
    ]


def term_total_for_profile(profile, residency, term_index):
    return sum((line["amount"] for line in term_lines_for_profile(profile, residency, term_index)), Decimal("0.00"))


def amount_due_catalog(interfaculty_options, science_majors):
    rows = []
    for faculty, options in interfaculty_options.items():
        profile = profile_for_faculty(faculty)
        majors = science_majors if faculty == "Science" else options
        for major in majors:
            row = {
                "faculty": faculty,
                "major": major,
                "degree": profile["degree"],
            }
            for residency in RESIDENCY_LABELS:
                row[residency] = total_for_profile(profile, residency)
            rows.append(row)
    return rows
