import json
import pathlib
from datetime import date
import re

import requests
from bs4 import BeautifulSoup

from common.synthetic_catalog import sanitize_program


ROOT = pathlib.Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "data" / "seed.json"
OUTPUT_PATH = ROOT / "data" / "program_catalog.json"


def _clean(text):
    return " ".join((text or "").replace("\xa0", " ").split())


def _extract_summary(tab):
    if not tab:
        return ""
    paragraphs = []
    capture = False
    for node in tab.find_all(["p", "h2", "h3"], recursive=False):
        text = _clean(node.get_text(" ", strip=True))
        if not text:
            continue
        if node.name in {"h2", "h3"} and "program description" in text.lower():
            capture = True
            continue
        if node.name in {"h2", "h3"} and "degree requirements" in text.lower():
            break
        if capture and node.name == "p":
            paragraphs.append(text)
    return " ".join(paragraphs)


def _extract_courses(table):
    rows = []
    for tr in table.find_all("tr"):
        classes = tr.get("class") or []
        if "bubbledrawer" in classes:
            continue
        cells = tr.find_all("td")
        if len(cells) != 3:
            continue
        code = _clean(cells[0].get_text(" ", strip=True))
        title = _clean(cells[1].get_text(" ", strip=True)).rstrip(".")
        title = re.sub(r"\s+\d+$", "", title).rstrip(".")
        credits = _clean(cells[2].get_text(" ", strip=True))
        if not code or code.lower() == "course":
            continue
        try:
            credit_value = float(credits)
        except ValueError:
            credit_value = None
        rows.append(
            {
                "code": code,
                "title": title,
                "credits": credit_value,
            }
        )
    return rows


def _extract_requirement_sections(tab):
    if not tab:
        return []
    sections = []
    current = None
    pending_note = None
    for child in tab.children:
        if not getattr(child, "name", None):
            continue
        if child.name == "h2":
            if current:
                sections.append(current)
            current = {"heading": _clean(child.get_text(" ", strip=True)), "notes": [], "courses": [], "course_groups": []}
            pending_note = None
        elif child.name == "p" and current:
            text = _clean(child.get_text(" ", strip=True))
            if text:
                current["notes"].append(text)
                pending_note = text
        elif child.name == "div" and "courselist-wrapper" in (child.get("class") or []) and current:
            table = child.find("table", class_="sc_courselist")
            if table:
                courses = _extract_courses(table)
                current["courses"].extend(courses)
                current["course_groups"].append({"note": pending_note or "", "courses": courses})
                pending_note = None
    if current:
        sections.append(current)
    return sections


def build_catalog():
    seed_data = json.loads(SEED_PATH.read_text())
    programs = seed_data.get("programs", [])
    session = requests.Session()
    built = []
    for index, program in enumerate(programs, start=1):
        response = session.get(program["official_url"], timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        tabs = soup.select("div.tab_content")
        summary = _extract_summary(tabs[1] if len(tabs) > 1 else None)
        sections = _extract_requirement_sections(tabs[2] if len(tabs) > 2 else None)
        flattened = []
        for section in sections:
            flattened.extend(section["courses"])
        merged = dict(program)
        merged["summary"] = summary or program.get("summary", "")
        merged["requirements"] = flattened or program.get("requirements", [])
        merged["requirement_sections"] = sections
        merged["verified_on"] = date.today().isoformat()
        built.append(sanitize_program(merged))
        if index % 25 == 0:
            print(f"Fetched {index}/{len(programs)} programmes")
    OUTPUT_PATH.write_text(json.dumps(built, indent=2))
    return built


if __name__ == "__main__":
    build_catalog()
