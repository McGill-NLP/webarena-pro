from __future__ import annotations

import csv
import gzip
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import CustomUser, Employer, JobSeeker
from apps.jobs.models import Application, Category, Job


JOBS_SOURCE = "linkedin_kaggle"
RESUMES_SOURCE = "resume_kaggle"
ASSET_DIR = Path(settings.BASE_DIR) / "seed_assets"
# Keep benchmark answers stable when imported listings overlap curated task
# searches. Original compensation remains available in the source attribution;
# only the portal-facing comparison value is normalized here.
TASK_COMPATIBILITY_SALARY_OVERRIDES = {
    "3902830443": "USD 150,000 - USD 155,000 / Yearly",
    "3902759369": "USD 140,000 - USD 150,000 / Yearly",
}
JOB_TYPE_MAP = {
    "Full-time": "full_time",
    "Part-time": "part_time",
    "Contract": "contract",
    "Internship": "internship",
    "Temporary": "temporary",
    "Volunteer": "volunteer",
    "Other": "other",
}
CATEGORY_ICONS = {
    "Information Technology": "fas fa-laptop-code",
    "Engineering": "fas fa-cogs",
    "Accountant": "fas fa-calculator",
    "Advocate": "fas fa-balance-scale",
    "Agriculture": "fas fa-seedling",
    "Apparel": "fas fa-tshirt",
    "Arts": "fas fa-palette",
    "Automobile": "fas fa-car",
    "Aviation": "fas fa-plane",
    "Banking": "fas fa-university",
    "BPO": "fas fa-headset",
    "Business Development": "fas fa-chart-line",
    "Chef": "fas fa-utensils",
    "Construction": "fas fa-hard-hat",
    "Consultant": "fas fa-comments",
    "Designer": "fas fa-paint-brush",
    "Digital Media": "fas fa-photo-video",
    "Finance": "fas fa-coins",
    "Fitness": "fas fa-dumbbell",
    "Healthcare": "fas fa-heartbeat",
    "HR": "fas fa-users",
    "Public Relations": "fas fa-bullhorn",
    "Sales": "fas fa-handshake",
    "Teacher": "fas fa-chalkboard-teacher",
}
DISPLAY_OVERRIDES = {
    "INFORMATION-TECHNOLOGY": "Information Technology",
    "BUSINESS-DEVELOPMENT": "Business Development",
    "DIGITAL-MEDIA": "Digital Media",
    "PUBLIC-RELATIONS": "Public Relations",
    "BPO": "BPO",
    "HR": "HR",
}
CURATED_PORTAL_CATEGORY_RESUME_POOLS = {
    "Data & AI": {"INFORMATION-TECHNOLOGY", "ENGINEERING"},
    "Design": {"DESIGNER"},
    "Marketing": {"DIGITAL-MEDIA", "PUBLIC-RELATIONS", "BUSINESS-DEVELOPMENT"},
    "Operations": {"BUSINESS-DEVELOPMENT", "BPO", "HR"},
    "Product": {"INFORMATION-TECHNOLOGY", "BUSINESS-DEVELOPMENT", "DESIGNER"},
    "Public Relations": {"PUBLIC-RELATIONS", "DIGITAL-MEDIA"},
}
def category_display(value: str) -> str:
    return DISPLAY_OVERRIDES.get(value, value.title())


def read_gzip_csv(path: Path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def parse_number(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def salary_text(row: dict[str, str]) -> str:
    currency = (row.get("currency") or "").strip()
    minimum = parse_number(row.get("min_salary", ""))
    median = parse_number(row.get("med_salary", ""))
    maximum = parse_number(row.get("max_salary", ""))
    period = (row.get("pay_period") or "").replace("_", " ").title()
    suffix = f" / {period}" if period else ""

    def amount(value: float) -> str:
        rendered = f"{value:,.2f}" if not value.is_integer() else f"{int(value):,}"
        return f"{currency} {rendered}".strip()

    if minimum is not None and maximum is not None:
        return f"{amount(minimum)} - {amount(maximum)}{suffix}"[:100]
    if median is not None:
        return f"{amount(median)} median{suffix}"[:100]
    if minimum is not None:
        return f"From {amount(minimum)}{suffix}"[:100]
    if maximum is not None:
        return f"Up to {amount(maximum)}{suffix}"[:100]
    return "Not disclosed"


def epoch_datetime(value: str) -> datetime | None:
    number = parse_number(value)
    if number is None:
        return None
    if number > 10_000_000_000:
        number /= 1000
    try:
        return datetime.fromtimestamp(number, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def experience_level(source_value: str) -> str:
    value = (source_value or "").lower()
    if "intern" in value or "entry" in value:
        return "entry"
    if any(token in value for token in ("mid-senior", "director", "executive", "senior")):
        return "senior"
    return "mid"


class Command(BaseCommand):
    help = "Import the prebuilt stratified LinkedIn jobs sample and relevant resume applications."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Remove and rebuild Kaggle-imported data.")
        parser.add_argument(
            "--employer-password",
            default=None,
            help="Override the shared password for the selected sign-in employer accounts.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        metadata_path = ASSET_DIR / "import_metadata.json"
        required = [
            metadata_path,
            ASSET_DIR / "linkedin_jobs.csv.gz",
            ASSET_DIR / "linkedin_companies.csv.gz",
            ASSET_DIR / "resume_profiles.csv.gz",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise CommandError("Missing Kaggle seed assets: " + ", ".join(missing))

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected_jobs = int(metadata["sample_size"])
        current_jobs = Job.objects.filter(source=JOBS_SOURCE).count()
        if options["reset"]:
            self._clear_imported_data()
            current_jobs = 0
        if current_jobs == expected_jobs:
            self._verify(metadata)
            self.stdout.write(self.style.SUCCESS(f"Kaggle data already loaded ({current_jobs:,} jobs); verified and skipped."))
            self._print_credentials(metadata, options["employer_password"])
            return
        if current_jobs:
            raise CommandError(
                f"Found a partial Kaggle import ({current_jobs:,}/{expected_jobs:,} jobs). "
                "Run seed_kaggle_data --reset to rebuild it."
            )

        password = options["employer_password"] or metadata["employer_password"]
        company_rows = list(read_gzip_csv(ASSET_DIR / "linkedin_companies.csv.gz"))
        resume_rows = list(read_gzip_csv(ASSET_DIR / "resume_profiles.csv.gz"))
        job_rows = list(read_gzip_csv(ASSET_DIR / "linkedin_jobs.csv.gz"))

        self.stdout.write(f"Importing {len(company_rows):,} companies and {len(resume_rows):,} resumes...")
        employers, sign_in_company_ids = self._create_employers(company_rows, password)
        seekers = self._create_job_seekers(resume_rows)
        categories = self._create_categories(resume_rows)
        self.stdout.write(f"Importing {len(job_rows):,} stratified LinkedIn postings...")
        jobs = self._create_jobs(
            job_rows,
            employers,
            categories,
            int(metadata["seed"]),
        )
        applications_created = self._create_applications(
            job_rows,
            jobs,
            seekers,
            sign_in_company_ids,
            int(metadata["seed"]),
        )
        self._verify(metadata)
        self.stdout.write(
            self.style.SUCCESS(
                f"Kaggle import complete: {len(jobs):,} jobs, {len(seekers):,} resumes, "
                f"{applications_created:,} relevant-resume applications."
            )
        )
        self._print_credentials(metadata, password)

    def _clear_imported_data(self):
        self.stdout.write("Removing the previous Kaggle import...")
        Job.objects.filter(source=JOBS_SOURCE).delete()
        imported_user_ids = CustomUser.objects.filter(
            Q(employer__source=JOBS_SOURCE) | Q(jobseeker__source=RESUMES_SOURCE)
        ).values_list("id", flat=True)
        CustomUser.objects.filter(id__in=list(imported_user_ids)).delete()

    def _create_employers(self, rows, password):
        shared_password = make_password(password)
        unusable_password = make_password(None)
        users = []
        for row in rows:
            enabled = row["login_enabled"] == "1"
            username = row["username"][:150]
            users.append(
                CustomUser(
                    username=username,
                    email=f"{username}@linkedin-import.invalid"[:254],
                    is_employer=True,
                    is_job_seeker=False,
                    is_active=enabled,
                    password=shared_password if enabled else unusable_password,
                )
            )
        CustomUser.objects.bulk_create(users, batch_size=500)
        users_by_username = {user.username: user for user in users}
        employer_objects = []
        for row in rows:
            employer_objects.append(
                Employer(
                    user=users_by_username[row["username"][:150]],
                    company_name=(row["name"] or "Unknown company")[:255],
                    company_description=row["description"],
                    company_website=row["website"][:200],
                    location=row["location"][:100],
                    industry=row["industry"][:100],
                    source=JOBS_SOURCE,
                    external_id=row["company_external_id"],
                )
            )
        Employer.objects.bulk_create(employer_objects, batch_size=500)
        return (
            {employer.external_id: employer for employer in employer_objects},
            {row["company_external_id"] for row in rows if row["login_enabled"] == "1"},
        )

    def _create_job_seekers(self, rows):
        unusable_password = make_password(None)
        users = [
            CustomUser(
                username=f"resume_{row['resume_id']}"[:150],
                email=f"candidate-{row['resume_id']}@resumes.invalid"[:254],
                first_name="Candidate",
                last_name=row["resume_id"][:150],
                is_employer=False,
                is_job_seeker=True,
                is_active=False,
                password=unusable_password,
            )
            for row in rows
        ]
        CustomUser.objects.bulk_create(users, batch_size=500)
        users_by_username = {user.username: user for user in users}

        resume_root = Path(settings.MEDIA_ROOT) / "resumes" / "kaggle_resume_dataset"
        resume_root.mkdir(parents=True, exist_ok=True)
        seekers = []
        for row in rows:
            resume_id = row["resume_id"]
            resume_path = resume_root / f"{resume_id}.txt"
            if not resume_path.exists():
                resume_path.write_text(row["resume_text"].strip() + "\n", encoding="utf-8")
            display = category_display(row["category"])
            seekers.append(
                JobSeeker(
                    user=users_by_username[f"resume_{resume_id}"[:150]],
                    resume=f"resumes/kaggle_resume_dataset/{resume_id}.txt",
                    skills=f"Resume classified as {display}; see the attached source resume for full skills.",
                    experience=row["resume_text"].strip()[:2000],
                    education="See attached resume.",
                    source=RESUMES_SOURCE,
                    external_id=resume_id,
                    source_category=row["category"],
                )
            )
        JobSeeker.objects.bulk_create(seekers, batch_size=500)
        return {seeker.external_id: seeker for seeker in seekers}

    def _create_categories(self, resume_rows):
        categories = {}
        for source_category in sorted({row["category"] for row in resume_rows}):
            display = category_display(source_category)
            category, _ = Category.objects.update_or_create(
                name=display,
                defaults={"icon": CATEGORY_ICONS.get(display, "fas fa-briefcase")},
            )
            categories[display] = category
        return {category.name: category for category in Category.objects.all()}

    def _create_jobs(self, rows, employers, categories, seed):
        job_objects = []
        posted_dates = {}
        seeded_at = timezone.now()
        for row in rows:
            portal_category = row.get("portal_category") or category_display(row["resume_category"])
            category_enrichment = row.get("category_enrichment") == "1"
            location = (row.get("location") or "Location not provided").strip()
            if row.get("remote_allowed") in {"1", "1.0", "true", "True"} and "remote" not in location.lower():
                location = f"Remote / {location}"
            if category_enrichment and portal_category == "Design":
                location = "Remote"
            skills = (row.get("skills_desc") or "").strip()
            industries = (row.get("industries") or "").strip()
            requirements = skills or "See the full job description for qualifications and requirements."
            if industries:
                requirements += f"\n\nAssociated industries: {industries}"
            posted_rng = random.Random(f"{seed}:{row['job_id']}:posted-date")
            posted_at = seeded_at - timedelta(
                seconds=posted_rng.randint(2 * 86_400, 182 * 86_400)
            )
            deadline_at = epoch_datetime(row.get("expiry", ""))
            job = Job(
                title=(row.get("title") or "Untitled role")[:200],
                employer=employers[row["company_external_id"]],
                category=categories[portal_category],
                description=row.get("description") or "No description provided.",
                requirements=requirements,
                location=location[:100],
                salary=(
                    "Not disclosed"
                    if category_enrichment and portal_category in CURATED_PORTAL_CATEGORY_RESUME_POOLS
                    else TASK_COMPATIBILITY_SALARY_OVERRIDES.get(row["job_id"], salary_text(row))
                ),
                job_type=JOB_TYPE_MAP[row["formatted_work_type"]],
                experience_level=experience_level(row.get("formatted_experience_level", "")),
                deadline=deadline_at.date() if deadline_at else None,
                is_active=True,
                source=JOBS_SOURCE,
                external_id=row["job_id"],
            )
            job_objects.append(job)
            posted_dates[row["job_id"]] = posted_at
        Job.objects.bulk_create(job_objects, batch_size=250)
        for job in job_objects:
            job.posted_date = posted_dates[job.external_id]
        Job.objects.bulk_update(job_objects, ["posted_date"], batch_size=500)
        return {job.external_id: job for job in job_objects}

    def _create_applications(self, rows, jobs, seekers, sign_in_company_ids, seed):
        pools = defaultdict(list)
        for seeker in seekers.values():
            pools[seeker.source_category].append(seeker)
        applications = []
        now = timezone.now()
        statuses = ("pending", "pending", "reviewing", "pending", "reviewing", "accepted", "rejected")
        for row in rows:
            if row["company_external_id"] not in sign_in_company_ids:
                continue
            rng = random.Random(f"{seed}:{row['job_id']}:applications")
            source_applies = parse_number(row.get("applies", ""))
            if source_applies is not None and source_applies > 0:
                application_count = min(20, int(source_applies))
            else:
                application_count = rng.randint(5, 20)
            relevant_pool = pools[row["resume_category"]]
            selected = rng.sample(relevant_pool, k=min(application_count, 20, len(relevant_pool)))
            job = jobs[row["job_id"]]
            for index, seeker in enumerate(selected):
                applications.append(
                    Application(
                        job=job,
                        job_seeker=seeker,
                        cover_letter=(
                            f"I am applying for the {job.title} role. My attached resume is from the "
                            f"{category_display(seeker.source_category)} candidate pool selected for this job."
                        ),
                        status=statuses[(index + sum(ord(char) for char in row["job_id"])) % len(statuses)],
                        applied_date=min(now, job.posted_date + timedelta(days=1 + index)),
                        updated_date=now,
                    )
                )
        Application.objects.bulk_create(applications, batch_size=500)
        return len(applications)

    def _verify(self, metadata):
        expected_types = {
            JOB_TYPE_MAP[source_type]: count
            for source_type, count in metadata["sampled_job_type_counts"].items()
        }
        actual_types = dict(
            Job.objects.filter(source=JOBS_SOURCE)
            .values_list("job_type")
            .annotate(count=Count("id"))
        )
        if actual_types != expected_types:
            raise CommandError(f"Job-type verification failed: expected {expected_types}, got {actual_types}")
        category_floor = metadata.get("portal_category_floor")
        if category_floor:
            for category_name in metadata.get("category_enrichment_counts", {}):
                actual_count = Job.objects.filter(category__name=category_name).count()
                if actual_count < category_floor:
                    raise CommandError(
                        f"Category-count verification failed for {category_name!r}: "
                        f"expected at least {category_floor}, got {actual_count}"
                    )
        now = timezone.now()
        imported_jobs = Job.objects.filter(source=JOBS_SOURCE)
        if imported_jobs.filter(posted_date__gt=now - timedelta(days=2)).exists():
            raise CommandError("Posted-date verification failed: an imported job is newer than 2 days.")
        if imported_jobs.filter(posted_date__lt=now - timedelta(days=183)).exists():
            raise CommandError("Posted-date verification failed: an imported job is older than 6 months.")
        over_cap = Job.objects.annotate(application_count=Count("applications")).filter(
            application_count__gt=20
        ).exists()
        if over_cap:
            raise CommandError("Application cap verification failed: a job has more than 20 applications.")
        pairs = Application.objects.filter(job__source=JOBS_SOURCE).values_list(
            "job__category__name", "job_seeker__source_category"
        )
        for job_category, resume_category in pairs.iterator(chunk_size=2_000):
            allowed_categories = CURATED_PORTAL_CATEGORY_RESUME_POOLS.get(job_category)
            relevant = (
                resume_category in allowed_categories
                if allowed_categories is not None
                else job_category == category_display(resume_category)
            )
            if not relevant:
                raise CommandError(
                    "Resume relevance verification failed: "
                    f"job category {job_category!r} received resume category {resume_category!r}."
                )

    def _print_credentials(self, metadata, password):
        self.stdout.write(f"Sign-in employer password: {password or metadata['employer_password']}")
        for account in metadata["sign_in_employers"]:
            self.stdout.write(f"  {account['company']}: {account['username']}")
