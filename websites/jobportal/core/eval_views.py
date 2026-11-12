"""Read-only evaluation API for the WebArena-Pro evaluator.

Exposes backend state as JSON so tasks can be graded deterministically instead
of relying on an LLM judge. Strictly read-only and gated by a secret token
(WP_EVAL_TOKEN) the agent under test never sees, so it cannot be used to read
answers. Disabled (403) when WP_EVAL_TOKEN is unset. No passwords are returned.
"""

import os

from django.http import JsonResponse

from apps.accounts.models import Employer, JobSeeker
from apps.jobs.models import Application, Category, Job


def _authorized(request):
    token = os.environ.get("WP_EVAL_TOKEN")
    return bool(token) and request.headers.get("X-Eval-Token") == token


def eval_state(request):
    if not _authorized(request):
        return JsonResponse({"error": "forbidden"}, status=403)

    # Scope to the demo seed. The LinkedIn/Kaggle import (~10k jobs, ~5k
    # employers, ~9k applications) exists for agent-facing realism only and
    # inflates this payload past 15MB. Demo rows have source == "" and demo
    # accounts don't use the import's reserved ".invalid" email domains
    # (@linkedin-import.invalid / @resumes.invalid), so agent writes (new
    # postings by demo employers, applications by demo seekers to ANY job,
    # Kaggle jobs included) still show up here.
    kaggle_email = ".invalid"
    jobs_qs = Job.objects.exclude(source="linkedin_kaggle")
    applications_qs = Application.objects.select_related(
        "job", "job_seeker__user"
    ).exclude(job_seeker__user__email__endswith=kaggle_email)
    employers_qs = Employer.objects.select_related("user").exclude(
        user__email__endswith=kaggle_email
    )
    job_seekers_qs = JobSeeker.objects.select_related("user").exclude(
        user__email__endswith=kaggle_email
    )

    data = {
        "categories": [
            {"id": c.id, "name": c.name} for c in Category.objects.all()
        ],
        "jobs": [
            {
                "id": j.id,
                "title": j.title,
                "employer": j.employer.company_name if j.employer_id else None,
                "category": j.category.name if j.category_id else None,
                "location": j.location,
                "salary": j.salary,
                "job_type": j.job_type,
                "requirements": j.requirements,
                "experience_level": j.experience_level,
                "deadline": j.deadline.isoformat() if j.deadline else None,
                "is_active": j.is_active,
                "posted_date": j.posted_date.isoformat() if j.posted_date else None,
            }
            for j in jobs_qs
        ],
        "applications": [
            {
                "id": a.id,
                "job_id": a.job_id,
                "job_title": a.job.title,
                "applicant": a.job_seeker.user.username,
                "status": a.status,
                "cover_letter": a.cover_letter,
                "applied_date": a.applied_date.isoformat() if a.applied_date else None,
            }
            for a in applications_qs
        ],
        "employers": [
            {
                "id": e.id,
                "username": e.user.username,
                "company_name": e.company_name,
                "location": e.location,
                "industry": e.industry,
                "website": e.company_website,
            }
            for e in employers_qs
        ],
        "job_seekers": [
            {
                "id": s.id,
                "username": s.user.username,
                "skills": s.skills,
                "experience": s.experience,
                "education": s.education,
            }
            for s in job_seekers_qs
        ],
    }
    return JsonResponse(data)
