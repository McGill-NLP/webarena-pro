---
title: JobPortal
emoji: 💼
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Job Portal

A modern job portal built with Django and Tailwind CSS, designed to connect job seekers with employers efficiently.

## Features

- User authentication for employers and job seekers
- Job posting and management
- Job search and filtering
- Application tracking
- Responsive UI for desktop and mobile

## Tech Stack

- Backend: Django
- Frontend: Tailwind CSS, Alpine.js
- Database: SQLite

## Local Development

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run migrations:

```bash
python manage.py migrate
```

4. Seed reproducible demo data:

```bash
python manage.py seed_demo_data --reset
```

5. Start server:

```bash
python manage.py runserver
```

## Docker (Port 4510)

1. Build image:

```bash
docker build -t jobportal:latest .
```

2. Run app on host port 4510:

```bash
docker run --rm -p 4510:8000 jobportal:latest
```

3. Run with forced reset/reseed on startup:

```bash
docker run --rm -p 4510:8000 -e SEED_DATA=1 -e SEED_RESET=1 jobportal:latest
```

Open: http://localhost:4510

## Docker Compose (Port 4510)

Start:

```bash
docker compose up --build -d
```

Follow logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

Force fresh seeded data on next start:

```bash
SEED_RESET=1 docker compose up --build -d
```

## Seeded Demo Data

- Command: `python manage.py seed_demo_data`
- Import the bundled Kaggle seed pack: `python manage.py seed_kaggle_data`
- Reset and reseed: `python manage.py seed_demo_data --reset`
- Script helper: `./scripts/seed_data.sh --reset`
- Default seeded user password: `DemoPass123!`

### Kaggle job and resume import

The bundled import adds exactly 10,000 postings without removing the curated demo
postings. It uses a reproducible, proportional stratified random sample over every
`formatted_work_type` in the LinkedIn source dataset (seed `20260710`):

| Source work type | Imported jobs |
| --- | ---: |
| Full-time | 7,979 |
| Contract | 978 |
| Part-time | 783 |
| Temporary | 96 |
| Internship | 79 |
| Volunteer | 46 |
| Other | 39 |

Twenty representative imported employer accounts are enabled for sign-in. Their
usernames are listed in `seed_assets/import_metadata.json` and their shared password
is `LinkedInDemo123!`. Each posting owned by an enabled employer has no more than 20
applications. Applicants are sampled without replacement from the resume dataset's
matching career category; the full source resume text is attached to the applicant.

To regenerate the compact seed assets from downloaded Kaggle archives:

```bash
python scripts/build_kaggle_seed_assets.py \
  --jobs-zip /path/to/linkedin-job-postings.zip \
  --resumes-zip /path/to/resume-classification.zip \
  --output-dir seed_assets
```

Sources:

- [LinkedIn Job Postings (2023–2024)](https://www.kaggle.com/datasets/arshkon/linkedin-job-postings), CC BY-SA 4.0
- [Resume Classification Dataset for NLP](https://www.kaggle.com/datasets/hassnainzaidi/resume-classification-dataset-for-nlp), CC0 / Public Domain

## License

WebArena-Pro's original application code and contributions in this directory are
licensed under the [MIT License](LICENSE).

Dependencies, datasets, media, and other third-party components retain their
respective licenses and attribution requirements. They are not relicensed by
this application's MIT license.

This implementation is adapted from
[aneebnaqvi15/jobportal](https://github.com/aneebnaqvi15/jobportal).
Its [upstream README](https://github.com/aneebnaqvi15/jobportal/blob/719b4be69ec80605fec3243d28ba1cdc3dc4ff00/README.md)
declares MIT, but that revision does not include the linked `LICENSE` file.
The WebArena-Pro copyright notice covers our contributions and does not replace
upstream authorship or grant additional rights to upstream code.
