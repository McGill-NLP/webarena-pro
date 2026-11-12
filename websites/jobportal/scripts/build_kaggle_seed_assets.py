#!/usr/bin/env python3
"""Build a compact, reproducible JobPortal seed pack from two Kaggle archives."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import random
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


SOURCE_JOB_TYPES = (
    "Full-time",
    "Contract",
    "Part-time",
    "Temporary",
    "Internship",
    "Volunteer",
    "Other",
)

CATEGORY_RULES = {
    "INFORMATION-TECHNOLOGY": (
        "software", "developer", "programmer", "information technology", "data scientist",
        "data engineer", "machine learning", "artificial intelligence", "cybersecurity",
        "network", "database", "cloud", "devops", "systems administrator", "technical support",
    ),
    "ENGINEERING": (
        "engineer", "engineering", "mechanical", "electrical", "chemical", "manufacturing",
        "quality assurance", "quality control", "robotics", "technician",
    ),
    "ACCOUNTANT": (
        "accountant", "accounting", "audit", "auditor", "bookkeeping", "tax", "payroll", "cpa",
    ),
    "ADVOCATE": (
        "attorney", "lawyer", "legal", "counsel", "paralegal", "litigation", "compliance officer",
    ),
    "AGRICULTURE": (
        "agriculture", "agricultural", "agronomy", "farm", "farming", "crop", "livestock",
    ),
    "APPAREL": (
        "apparel", "fashion", "textile", "garment", "footwear", "merchandiser",
    ),
    "ARTS": (
        "artist", "arts", "museum", "music", "theater", "theatre", "gallery", "curator",
    ),
    "AUTOMOBILE": (
        "automotive", "automobile", "vehicle", "mechanic", "dealership", "collision repair",
    ),
    "AVIATION": (
        "aviation", "airline", "aircraft", "aerospace", "flight", "pilot", "airport",
    ),
    "BANKING": (
        "bank", "banking", "teller", "credit", "loan", "mortgage", "lending",
    ),
    "BPO": (
        "call center", "contact center", "customer support", "customer service representative",
        "service desk", "outsourcing",
    ),
    "BUSINESS-DEVELOPMENT": (
        "business development", "partnership", "strategy", "operations manager", "program manager",
        "project manager", "product manager", "general manager", "entrepreneurship",
    ),
    "CHEF": (
        "chef", "cook", "culinary", "restaurant", "kitchen", "food service", "catering",
    ),
    "CONSTRUCTION": (
        "construction", "civil", "architect", "carpenter", "estimator", "site superintendent",
        "building materials", "real estate development",
    ),
    "CONSULTANT": (
        "consultant", "consulting", "advisor", "advisory", "implementation specialist",
    ),
    "DESIGNER": (
        "designer", "design", "user experience", "user interface", "graphic", "creative director",
        "interior design",
    ),
    "DIGITAL-MEDIA": (
        "digital media", "marketing", "content", "social media", "seo", "communications",
        "journalist", "copywriter", "advertising", "ecommerce",
    ),
    "FINANCE": (
        "finance", "financial", "investment", "treasury", "economist", "wealth management",
        "portfolio", "securities",
    ),
    "FITNESS": (
        "fitness", "trainer", "athletic", "sport", "wellness", "coach", "recreation",
    ),
    "HEALTHCARE": (
        "health", "medical", "nurse", "physician", "clinical", "pharmacy", "patient", "dental",
        "therapist", "hospital",
    ),
    "HR": (
        "human resources", "recruiter", "recruiting", "talent acquisition", "people operations",
        "employee relations", "compensation benefits",
    ),
    "PUBLIC-RELATIONS": (
        "public relations", "media relations", "community relations", "communications manager",
        "event coordinator", "public affairs",
    ),
    "SALES": (
        "sales", "account executive", "business development representative", "retail", "revenue",
        "store manager", "salesforce",
    ),
    "TEACHER": (
        "teacher", "education", "instructor", "professor", "academic", "school", "tutor", "curriculum",
    ),
}

CATEGORY_DISPLAY = {
    "INFORMATION-TECHNOLOGY": "Information Technology",
    "BUSINESS-DEVELOPMENT": "Business Development",
    "DIGITAL-MEDIA": "Digital Media",
    "PUBLIC-RELATIONS": "Public Relations",
    "BPO": "BPO",
    "HR": "HR",
    **{
        name: name.title()
        for name in CATEGORY_RULES
        if name not in {
            "INFORMATION-TECHNOLOGY",
            "BUSINESS-DEVELOPMENT",
            "DIGITAL-MEDIA",
            "PUBLIC-RELATIONS",
            "BPO",
            "HR",
        }
    },
}
PORTAL_CATEGORY_FLOOR = 100
CURATED_PORTAL_CATEGORY_COUNTS = {
    "Data & AI": 17,
    "Design": 14,
    "Marketing": 14,
    "Operations": 14,
    "Product": 14,
}
PORTAL_CATEGORY_ENRICHMENT_SOURCES = {
    "Public Relations": "DIGITAL-MEDIA",
    "Agriculture": "AGRICULTURE",
    "Design": "DESIGNER",
    "Marketing": "DIGITAL-MEDIA",
    "Operations": "BPO",
    "Product": "BUSINESS-DEVELOPMENT",
    "Data & AI": "INFORMATION-TECHNOLOGY",
    "Arts": "ARTS",
    "Aviation": "AVIATION",
    "Fitness": "FITNESS",
    "Apparel": "APPAREL",
    "BPO": "BPO",
}


def normalize_id(value: str) -> str:
    value = (value or "").strip()
    return value[:-2] if value.endswith(".0") else value


def employer_key(company_id: str, company_name: str) -> str:
    company_id = normalize_id(company_id)
    if company_id:
        return company_id
    digest = hashlib.sha1((company_name or "Unknown company").encode("utf-8")).hexdigest()[:16]
    return f"name-{digest}"


def employer_username(key: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "-", key)[:120]
    return f"linkedin_employer_{safe}"


def normalized_text(value: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip() + " "


def classify_job(row: dict[str, str], industries: list[str]) -> str:
    title = normalized_text(row.get("title", ""))
    description = normalized_text((row.get("description", "") or "")[:8000])
    industry_text = normalized_text(" ".join(industries))
    best_category = "BUSINESS-DEVELOPMENT"
    best_score = 0
    for category, keywords in CATEGORY_RULES.items():
        score = 0
        for keyword in keywords:
            needle = f" {keyword} "
            score += title.count(needle) * 8
            score += industry_text.count(needle) * 3
            score += description.count(needle)
        if score > best_score:
            best_category = category
            best_score = score
    return best_category


def open_csv_member(archive: zipfile.ZipFile, member: str):
    return io.TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="")


def proportional_targets(counts: Counter[str], sample_size: int) -> dict[str, int]:
    total = sum(counts.values())
    if sample_size > total:
        raise ValueError(f"Requested {sample_size:,} jobs but source contains only {total:,}")
    raw = {name: counts[name] * sample_size / total for name in SOURCE_JOB_TYPES}
    targets = {name: int(raw[name]) for name in SOURCE_JOB_TYPES}
    remaining = sample_size - sum(targets.values())
    for name in sorted(SOURCE_JOB_TYPES, key=lambda item: (raw[item] - targets[item], counts[item]), reverse=True)[:remaining]:
        targets[name] += 1
    if sample_size >= len(SOURCE_JOB_TYPES):
        for name in SOURCE_JOB_TYPES:
            if counts[name] and targets[name] == 0:
                donor = max(targets, key=targets.get)
                targets[donor] -= 1
                targets[name] = 1
    return targets


def select_category_enrichment(
    jobs_archive: zipfile.ZipFile,
    selected_rows: list[dict[str, str]],
    seed: int,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    portal_counts = Counter(CATEGORY_DISPLAY[row["resume_category"]] for row in selected_rows)
    portal_counts.update(CURATED_PORTAL_CATEGORY_COUNTS)
    deficits = {
        portal_category: max(0, PORTAL_CATEGORY_FLOOR - portal_counts[portal_category])
        for portal_category in PORTAL_CATEGORY_ENRICHMENT_SOURCES
    }

    targets_by_source: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for portal_category, deficit in deficits.items():
        if deficit:
            targets_by_source[PORTAL_CATEGORY_ENRICHMENT_SOURCES[portal_category]].append(
                (portal_category, deficit)
            )

    reservoir_sizes = {
        source_category: sum(count for _, count in targets)
        for source_category, targets in targets_by_source.items()
    }
    reservoirs: dict[str, list[dict[str, str]]] = {
        source_category: [] for source_category in reservoir_sizes
    }
    seen: Counter[str] = Counter()
    selected_job_ids = {normalize_id(row["job_id"]) for row in selected_rows}
    randomizers = {
        source_category: random.Random(f"{seed}:portal-category:{source_category}")
        for source_category in reservoir_sizes
    }

    with open_csv_member(jobs_archive, "postings.csv") as handle:
        for row in csv.DictReader(handle):
            job_id = normalize_id(row["job_id"])
            if job_id in selected_job_ids:
                continue
            source_category = classify_job(row, [])
            target_size = reservoir_sizes.get(source_category)
            if not target_size:
                continue
            seen[source_category] += 1
            bucket = reservoirs[source_category]
            if len(bucket) < target_size:
                bucket.append(row)
                continue
            replacement = randomizers[source_category].randrange(seen[source_category])
            if replacement < target_size:
                bucket[replacement] = row

    additions: list[dict[str, str]] = []
    for source_category, targets in sorted(targets_by_source.items()):
        bucket = reservoirs[source_category]
        required = reservoir_sizes[source_category]
        if len(bucket) < required:
            raise ValueError(
                f"Not enough {source_category} postings for category enrichment: "
                f"needed {required}, found {len(bucket)}"
            )
        random.Random(f"{seed}:portal-category:assignment:{source_category}").shuffle(bucket)
        offset = 0
        for portal_category, count in sorted(targets):
            for source_row in bucket[offset:offset + count]:
                row = dict(source_row)
                job_type = (row.get("formatted_work_type") or "Other").strip()
                row["formatted_work_type"] = job_type if job_type in SOURCE_JOB_TYPES else "Other"
                row["job_id"] = normalize_id(row["job_id"])
                row["company_external_id"] = employer_key(
                    row.get("company_id", ""), row.get("company_name", "")
                )
                row["resume_category"] = source_category
                row["portal_category"] = portal_category
                row["category_enrichment"] = "1"
                row["industries"] = ""
                additions.append(row)
            offset += count

    return additions, deficits


def select_sign_in_employers(rows: list[dict[str, str]], limit: int) -> set[str]:
    totals: Counter[str] = Counter()
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        key = row["company_external_id"]
        if not (row.get("company_name") or "").strip():
            continue
        totals[key] += 1
        by_type[row["formatted_work_type"]][key] += 1

    selected: set[str] = set()
    for job_type in SOURCE_JOB_TYPES:
        candidates = sorted(by_type[job_type], key=lambda key: (-by_type[job_type][key], -totals[key], key))
        if candidates:
            selected.add(candidates[0])
    for key in sorted(totals, key=lambda key: (-totals[key], key)):
        if len(selected) >= limit:
            break
        selected.add(key)
    return selected


def write_gzip_csv(path: Path, fieldnames: list[str], rows):
    with gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=6) as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_assets(args: argparse.Namespace) -> None:
    csv.field_size_limit(sys.maxsize)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(args.jobs_zip) as jobs_archive:
        counts: Counter[str] = Counter()
        with open_csv_member(jobs_archive, "postings.csv") as handle:
            for row in csv.DictReader(handle):
                job_type = (row.get("formatted_work_type") or "Other").strip()
                counts[job_type if job_type in SOURCE_JOB_TYPES else "Other"] += 1

        targets = proportional_targets(counts, args.sample_size)
        reservoirs: dict[str, list[dict[str, str]]] = {name: [] for name in SOURCE_JOB_TYPES}
        seen: Counter[str] = Counter()
        randomizers = {name: random.Random(f"{args.seed}:{name}") for name in SOURCE_JOB_TYPES}
        with open_csv_member(jobs_archive, "postings.csv") as handle:
            for row in csv.DictReader(handle):
                job_type = (row.get("formatted_work_type") or "Other").strip()
                if job_type not in SOURCE_JOB_TYPES:
                    job_type = "Other"
                row["formatted_work_type"] = job_type
                seen[job_type] += 1
                bucket = reservoirs[job_type]
                target = targets[job_type]
                if len(bucket) < target:
                    bucket.append(row)
                    continue
                replacement = randomizers[job_type].randrange(seen[job_type])
                if replacement < target:
                    bucket[replacement] = row

        selected_rows = [row for job_type in SOURCE_JOB_TYPES for row in reservoirs[job_type]]
        selected_job_ids = {normalize_id(row["job_id"]) for row in selected_rows}

        industry_names: dict[str, str] = {}
        with open_csv_member(jobs_archive, "mappings/industries.csv") as handle:
            for row in csv.DictReader(handle):
                industry_names[normalize_id(row["industry_id"])] = row["industry_name"].strip()

        job_industries: dict[str, list[str]] = defaultdict(list)
        with open_csv_member(jobs_archive, "jobs/job_industries.csv") as handle:
            for row in csv.DictReader(handle):
                job_id = normalize_id(row["job_id"])
                if job_id in selected_job_ids:
                    name = industry_names.get(normalize_id(row["industry_id"]))
                    if name:
                        job_industries[job_id].append(name)

        for row in selected_rows:
            row["job_id"] = normalize_id(row["job_id"])
            row["company_external_id"] = employer_key(row.get("company_id", ""), row.get("company_name", ""))
            row["resume_category"] = classify_job(row, job_industries[row["job_id"]])
            row["portal_category"] = CATEGORY_DISPLAY[row["resume_category"]]
            row["category_enrichment"] = "0"
            row["industries"] = " | ".join(job_industries[row["job_id"]])

        category_enrichment_rows, category_enrichment_counts = select_category_enrichment(
            jobs_archive,
            selected_rows,
            args.seed,
        )
        selected_rows.extend(category_enrichment_rows)

        selected_company_ids = {row["company_external_id"] for row in selected_rows}
        companies: dict[str, dict[str, str]] = {}
        with open_csv_member(jobs_archive, "companies/companies.csv") as handle:
            for row in csv.DictReader(handle):
                key = employer_key(row.get("company_id", ""), row.get("name", ""))
                if key in selected_company_ids:
                    row["company_external_id"] = key
                    companies[key] = row

        company_industries: dict[str, list[str]] = defaultdict(list)
        with open_csv_member(jobs_archive, "companies/company_industries.csv") as handle:
            for row in csv.DictReader(handle):
                key = normalize_id(row.get("company_id", ""))
                if key in selected_company_ids and row.get("industry"):
                    company_industries[key].append(row["industry"].strip())

    for row in selected_rows:
        key = row["company_external_id"]
        if key not in companies:
            companies[key] = {
                "company_external_id": key,
                "name": row.get("company_name") or "Unknown company",
                "description": "Company profile imported with the LinkedIn Job Postings dataset.",
                "country": "",
                "state": "",
                "city": "",
                "url": "",
            }

    sign_in_employers = select_sign_in_employers(
        [row for row in selected_rows if row["category_enrichment"] == "0"],
        args.sign_in_employers,
    )
    company_rows = []
    for key in sorted(companies):
        row = companies[key]
        company_rows.append(
            {
                "company_external_id": key,
                "username": employer_username(key),
                "login_enabled": "1" if key in sign_in_employers else "0",
                "name": row.get("name", "") or "Unknown company",
                "description": row.get("description", ""),
                "website": row.get("url", ""),
                "location": ", ".join(filter(None, [row.get("city", ""), row.get("state", ""), row.get("country", "")])),
                "industry": " | ".join(company_industries.get(key, [])),
            }
        )

    selected_rows.sort(key=lambda row: (SOURCE_JOB_TYPES.index(row["formatted_work_type"]), row["job_id"]))
    job_fields = [
        "job_id", "company_external_id", "company_name", "title", "description", "max_salary",
        "med_salary", "min_salary", "pay_period", "location", "formatted_work_type", "applies",
        "original_listed_time", "remote_allowed", "job_posting_url", "expiry",
        "formatted_experience_level", "skills_desc", "currency", "compensation_type",
        "resume_category", "portal_category", "category_enrichment", "industries",
    ]
    write_gzip_csv(output_dir / "linkedin_jobs.csv.gz", job_fields, selected_rows)
    write_gzip_csv(
        output_dir / "linkedin_companies.csv.gz",
        ["company_external_id", "username", "login_enabled", "name", "description", "website", "location", "industry"],
        company_rows,
    )

    resume_counts: Counter[str] = Counter()
    resume_rows = []
    with zipfile.ZipFile(args.resumes_zip) as resumes_archive:
        with open_csv_member(resumes_archive, "Resume/Resume.csv") as handle:
            for row in csv.DictReader(handle):
                category = (row.get("Category") or "").strip()
                if category not in CATEGORY_RULES:
                    continue
                resume_counts[category] += 1
                resume_rows.append(
                    {
                        "resume_id": normalize_id(row["ID"]),
                        "category": category,
                        "resume_text": row.get("Resume_str", ""),
                    }
                )
    resume_rows.sort(key=lambda row: (row["category"], row["resume_id"]))
    write_gzip_csv(output_dir / "resume_profiles.csv.gz", ["resume_id", "category", "resume_text"], resume_rows)

    sampled_counts = Counter(row["formatted_work_type"] for row in selected_rows)
    category_counts = Counter(row["resume_category"] for row in selected_rows)
    portal_category_counts = Counter(row["portal_category"] for row in selected_rows)
    sign_in_rows = [row for row in company_rows if row["login_enabled"] == "1"]
    metadata = {
        "seed": args.seed,
        "sample_size": len(selected_rows),
        "sampling_method": (
            "Proportional stratified reservoir sample without replacement by formatted_work_type, "
            "plus deterministic reservoir enrichment for portal categories below 100 jobs"
        ),
        "source_job_type_counts": dict(counts),
        "sampled_job_type_counts": dict(sampled_counts),
        "classified_job_counts": dict(sorted(category_counts.items())),
        "portal_category_counts": dict(sorted(portal_category_counts.items())),
        "portal_category_floor": PORTAL_CATEGORY_FLOOR,
        "category_enrichment_counts": dict(sorted(category_enrichment_counts.items())),
        "resume_category_counts": dict(sorted(resume_counts.items())),
        "resume_count": len(resume_rows),
        "company_count": len(company_rows),
        "sign_in_employer_count": len(sign_in_rows),
        "sign_in_employers": [
            {"company": row["name"], "username": row["username"]}
            for row in sorted(sign_in_rows, key=lambda item: item["name"].lower())
        ],
        "employer_password": args.employer_password,
        "sources": {
            "jobs": {
                "url": "https://www.kaggle.com/datasets/arshkon/linkedin-job-postings",
                "license": "CC BY-SA 4.0",
            },
            "resumes": {
                "url": "https://www.kaggle.com/datasets/hassnainzaidi/resume-classification-dataset-for-nlp",
                "license": "CC0: Public Domain",
            },
        },
    }
    (output_dir / "import_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output_dir),
        "sampled_job_type_counts": dict(sampled_counts),
        "category_enrichment_counts": dict(sorted(category_enrichment_counts.items())),
        "companies": len(company_rows),
        "sign_in_employers": len(sign_in_rows),
        "resumes": len(resume_rows),
    }, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs-zip", type=Path, required=True)
    parser.add_argument("--resumes-zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260710)
    parser.add_argument("--sign-in-employers", type=int, default=20)
    parser.add_argument("--employer-password", default="LinkedInDemo123!")
    return parser.parse_args()


if __name__ == "__main__":
    build_assets(parse_args())
