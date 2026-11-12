import hashlib
import re


FACULTY_DISPLAY_NAMES = {
    "Arts": "Bolder-Kohn Faculty of Arts and Letters",
    "Arts & Science": "Bolder-Kohn Faculty of Integrated Arts and Sciences",
    "Business & Management": "Bolder-Kohn School of Enterprise and Management",
    "Engineering": "Bolder-Kohn Faculty of Engineering and Design",
    "Science": "Bolder-Kohn Faculty of Natural and Computational Sciences",
}


SYNTHETIC_GIVEN_NAMES = [
    "Aven",
    "Brial",
    "Caelis",
    "Darian",
    "Elowen",
    "Ferren",
    "Galen",
    "Hollis",
    "Ivara",
    "Joren",
    "Kaelin",
    "Liora",
    "Maren",
    "Neris",
    "Orin",
    "Perrin",
    "Quilla",
    "Riven",
    "Solen",
    "Tavian",
    "Ulric",
    "Veyra",
    "Wren",
    "Xavian",
    "Yara",
    "Zerin",
]


TEXT_REPLACEMENTS = (
    ("Bolder-Kohn Faculty of Management", FACULTY_DISPLAY_NAMES["Business & Management"]),
    ("Faculty of Management", FACULTY_DISPLAY_NAMES["Business & Management"]),
    ("Faculty of Engineering", FACULTY_DISPLAY_NAMES["Engineering"]),
    ("Faculty of Science", FACULTY_DISPLAY_NAMES["Science"]),
    ("Faculty of the Arts", FACULTY_DISPLAY_NAMES["Arts"]),
    ("Faculty of Arts", FACULTY_DISPLAY_NAMES["Arts"]),
    ("Downtown campus", "Bluehaven Campus"),
    ("Downtown Campus", "Bluehaven Campus"),
    ("West Campus", "Lakeshore Campus"),
)


def faculty_display_name(value):
    return FACULTY_DISPLAY_NAMES.get(str(value), str(value))


def sanitize_catalog_text(value):
    text = str(value or "")
    for original, replacement in TEXT_REPLACEMENTS:
        if original.startswith("Faculty of"):
            text = re.sub(rf"(?<!Bolder-Kohn ){re.escape(original)}", replacement, text)
        else:
            text = text.replace(original, replacement)
    text = re.sub(
        r"\b(?:[A-Z][A-Za-z'’-]+\s+){1,4}Building\b",
        "Bluehaven Academic Hall",
        text,
    )
    text = re.sub(
        r"\bProf\.\s+[A-Z][A-Za-z'’-]+(?:\s+[A-Z][A-Za-z'’-]+){1,3}",
        "the Bolder-Kohn program adviser",
        text,
    )
    text = re.sub(
        r"\bcontact\s+[A-Z][A-Za-z'’-]+\s+[A-Z][A-Za-z'’-]+,",
        "contact the Bolder-Kohn program adviser,",
        text,
    )
    text = re.sub(
        r"(Lakeshore Campus)\s+in\s+[A-Z][A-Za-zÀ-ÿ'’-]+(?:-[A-Z][A-Za-zÀ-ÿ'’-]+)+",
        r"\1 in Lakehurst",
        text,
    )
    return text


def synthetic_program_summary(program):
    title = str(program.get("title") or "Undergraduate Program").strip()
    program_type = str(program.get("program_type") or "undergraduate").strip().lower()
    program_article = "an" if program_type[:1] in "aeiou" else "a"
    focus = str(program.get("major_group") or title).strip()
    faculty = faculty_display_name(program.get("faculty", ""))
    degree = str(program.get("degree") or "undergraduate credential").strip()
    requirements = program.get("requirements") or []
    unique_codes = list(
        dict.fromkeys(
            str(requirement.get("code", "")).strip()
            for requirement in requirements
            if str(requirement.get("code", "")).strip()
        )
    )
    course_titles = list(
        dict.fromkeys(
            str(requirement.get("title", "")).strip()
            for requirement in requirements
            if str(requirement.get("title", "")).strip()
        )
    )
    subject_areas = list(
        dict.fromkeys(code.split()[0] for code in unique_codes if " " in code)
    )
    credit_values = [
        float(requirement["credits"])
        for requirement in requirements
        if isinstance(requirement.get("credits"), (int, float))
    ]
    option_count = len(unique_codes)
    listed_credits = sum(credit_values)
    digest = hashlib.sha256(str(program.get("program_id", title)).encode("utf-8")).digest()
    approaches = (
        "close reading, structured inquiry, and independent synthesis",
        "conceptual foundations, collaborative workshops, and applied analysis",
        "comparative study, evidence-led discussion, and reflective projects",
        "sequenced core work, flexible exploration, and integrative assignments",
        "method training, case-based learning, and student-directed investigation",
        "historical context, contemporary questions, and practical experimentation",
        "quantitative reasoning, interpretive work, and cross-field connections",
        "studio-style practice, critical feedback, and cumulative portfolio work",
        "theory building, source evaluation, and problem-centred seminars",
        "foundational breadth, focused electives, and a culminating inquiry",
        "systems thinking, collaborative design, and iterative evaluation",
        "disciplinary technique, ethical reflection, and public-facing communication",
    )
    outcomes = (
        "frame precise questions and communicate well-supported conclusions",
        "connect specialist knowledge with unfamiliar practical settings",
        "assemble an academic pathway that balances depth with useful breadth",
        "evaluate competing explanations and make careful, evidence-based choices",
        "translate foundational ideas into independent analytical work",
        "develop a flexible toolkit for advanced study and related professional work",
        "recognize relationships across methods, scales, and fields of inquiry",
        "turn complex source material into clear arguments and responsible decisions",
        "test ideas iteratively while documenting the reasoning behind each result",
        "build confidence moving between abstract models and concrete problems",
        "combine individual initiative with constructive team-based practice",
        "identify assumptions, examine consequences, and propose defensible responses",
    )
    openers = (
        "At Bolder-Kohn University, {title} offers {article} {program_type} route through {focus}.",
        "{title} is Bolder-Kohn University's {program_type} pathway for focused work in {focus}.",
        "Designed within {faculty}, {title} approaches {focus} as a connected field of study at Bolder-Kohn University.",
        "Bolder-Kohn University created {title} for students seeking {article} {program_type} plan centred on {focus}.",
        "Within the {degree} credential family, {title} gives Bolder-Kohn students a distinct way to investigate {focus}.",
        "The Bolder-Kohn catalog places {title} in {faculty} as a {program_type} exploration of {focus}.",
        "Students entering {title} follow a Bolder-Kohn {program_type} curriculum shaped around {focus}.",
        "{faculty} administers {title}, a Bolder-Kohn University plan devoted to sustained study of {focus}.",
        "As {article} {program_type} offering at Bolder-Kohn University, {title} brings several perspectives to {focus}.",
        "{title} maps a Bolder-Kohn University learning journey across the ideas and practices associated with {focus}.",
        "Bolder-Kohn University's {title} turns interest in {focus} into a deliberately sequenced {program_type} plan.",
        "Housed in {faculty}, {title} is a synthetic Bolder-Kohn curriculum for studying {focus} with purpose and range.",
    )
    method_sentences = (
        "The learning design combines {approach}, helping students {outcome}.",
        "Its academic rhythm moves among {approach}; the aim is to help learners {outcome}.",
        "Students work through {approach} in order to {outcome}.",
        "A mix of {approach} supports a central goal: to {outcome}.",
        "Rather than following a single mode of study, the plan uses {approach} so participants can {outcome}.",
        "The curriculum emphasizes {approach}, creating repeated opportunities to {outcome}.",
        "Across the plan, {approach} provides the groundwork needed to {outcome}.",
        "Its distinctive learning pattern pairs {approach} with the expectation that students will {outcome}.",
        "Through {approach}, learners are invited to {outcome}.",
        "The program's synthetic brief prioritizes {approach} and encourages students to {outcome}.",
        "Work in the plan alternates between {approach}, all directed toward the ability to {outcome}.",
        "Bolder-Kohn frames the experience around {approach}, enabling students to {outcome}.",
    )
    catalog_sentences = (
        "The requirement map lists {count} course choices ({credits:g} listed credits), with examples such as {examples}.",
        "Representative entries include {examples}; together, the local catalog records {count} options worth {credits:g} listed credits.",
        "Among its {count} catalog options are {examples}, illustrating the range available for planning.",
        "The current planning record spans {count} choices and highlights work such as {examples}; its listed entries total {credits:g} credits before substitutions.",
        "Students can orient their choices around requirement examples like {examples}, drawn from a {count}-course local map.",
        "A {count}-option requirement map connects offerings such as {examples} within the broader {degree} pathway.",
        "In Minerva-lite, the plan is represented by {count} course options, including {examples}, across {credits:g} listed credits.",
        "Coursework such as {examples} anchors a local selection map containing {count} distinct options.",
        "Its catalog footprint brings together {examples} and {count_minus_examples} additional choices for individualized sequencing.",
        "The plan's subject mix is visible in offerings such as {examples}; Minerva-lite records {count} available course choices.",
        "Examples from the requirement blocks—{examples}—show how the plan's {count} options can support different routes through the field.",
        "The local course map totals {credits:g} listed credits across {count} choices, ranging from {examples}.",
    )
    planning_sentences = (
        "Minerva-lite is the planning workspace for prerequisites, term sequence, and Bolder-Kohn advising requests.",
        "Learners use Minerva-lite to compare prerequisites and shape the plan with the Bolder-Kohn advising team.",
        "Term-by-term choices are reviewed in Minerva-lite, where advising requests can be attached to the proposed sequence.",
        "Minerva-lite keeps the pathway, prerequisite checks, and Bolder-Kohn guidance in one local workspace.",
        "Planning happens in Minerva-lite so course order and advising questions remain connected to the degree record.",
        "The Minerva-lite record helps students turn these options into a coherent sequence before consulting Bolder-Kohn advisers.",
        "Students document their intended route in Minerva-lite and use it as the basis for Bolder-Kohn advising conversations.",
        "Prerequisite review and term sequencing take place through Minerva-lite's local program-planning tools.",
        "Minerva-lite provides the working view used to organize selections and request guidance when alternatives overlap.",
        "The final route is assembled in Minerva-lite, with Bolder-Kohn advising available for substitutions and sequencing questions.",
        "Students revisit the Minerva-lite plan as their interests develop and use advising requests to resolve constraints.",
        "Minerva-lite turns the catalog outline into a term plan that can be reviewed with the Bolder-Kohn advising team.",
    )

    approach = approaches[digest[0] % len(approaches)]
    outcome = outcomes[digest[1] % len(outcomes)]
    if course_titles:
        start = digest[2] % len(course_titles)
        ordered_titles = course_titles[start:] + course_titles[:start]
        selected_titles = ordered_titles[:3]
        examples = ", ".join(selected_titles)
    elif subject_areas:
        examples = ", ".join(subject_areas[:3])
    else:
        examples = "individualized study, guided electives, and an integrative project"

    values = {
        "title": title,
        "program_type": program_type,
        "article": program_article,
        "focus": focus,
        "faculty": faculty,
        "degree": degree,
        "approach": approach,
        "outcome": outcome,
        "count": option_count,
        "credits": listed_credits,
        "examples": examples,
        "count_minus_examples": max(0, option_count - min(3, len(course_titles))),
    }
    sentences = [
        openers[digest[4] % len(openers)].format(**values),
        method_sentences[digest[5] % len(method_sentences)].format(**values),
        catalog_sentences[digest[6] % len(catalog_sentences)].format(**values),
        planning_sentences[digest[7] % len(planning_sentences)].format(**values),
    ]
    if digest[8] % 2:
        sentences[1], sentences[2] = sentences[2], sentences[1]
    return " ".join(sentences)


def sanitize_program(program):
    sanitized = dict(program)
    sanitized["summary"] = synthetic_program_summary(sanitized)
    sections = []
    for section in sanitized.get("requirement_sections", []):
        clean_section = dict(section)
        clean_section["heading"] = sanitize_catalog_text(section.get("heading", ""))
        clean_section["notes"] = [sanitize_catalog_text(note) for note in section.get("notes", [])]
        if section.get("course_groups"):
            clean_section["course_groups"] = [
                {
                    **group,
                    "note": sanitize_catalog_text(group.get("note", "")),
                }
                for group in section.get("course_groups", [])
            ]
        sections.append(clean_section)
    sanitized["requirement_sections"] = sections
    return sanitized


# These positions correspond to the 24 instructor identities in the original
# public seed (cc474a4e). Keep the order and size stable: section assignment uses
# the original seeded RNG, while display names contain no source-person names.
INSTRUCTOR_IDS = tuple(f"I{index:02}" for index in range(1, 25))


def synthetic_professor_name(instructor_id):
    """Give one source instructor the same unique label in every section/term."""
    index = INSTRUCTOR_IDS.index(instructor_id)
    return f"Dr. {SYNTHETIC_GIVEN_NAMES[index]} Quenvar"
