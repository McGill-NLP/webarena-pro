# Nextcloud Data Seeding

The image generates its deterministic open-research seed during `docker build`. See `DATASET_CARD.md` for counts, provenance, licensing, and limitations.

Start a fresh instance with:

```bash
docker compose down -v
docker compose up --build -d
```

Wait until the `nextcloud` service is healthy. The health check does not pass until files, contacts, calendar events, notifications, Talk messages, and the Office handshake have been verified.

Exact target counts apply only to a fresh volume. Existing user or benchmark data is never deleted during reseeding.

To generate and inspect the seed without Docker:

```bash
python3 seed/fetch_real_documents.py --verify-only
python3 seed/fetch_financial_documents.py --verify-only
python3 seed/generate.py \
  --spec seed_spec.json \
  --media media \
  --output generated-seed
```

The real-document and order-source corpora are checked in so Docker builds remain offline. Run `python3 seed/fetch_financial_documents.py` to restore and verify the pinned order workbook, or `python3 seed/fetch_real_documents.py` to restore the GitHub and Kubernetes documents.

Generated procurement data includes 292 purchase-order PDFs per user under `Procurement/Purchase Orders/<year>`. Annual counts are pinned in `seed_spec.json`, remain between 40 and 76, and are distributed across five distinct layouts. Every order has one requisition under the same year with matching vendor, requester, project, cost center, line items, and total.

The `All files` root contains six current work files per user: a linked purchase-order reference copy plus project, meeting, budget, order, and operations documents in varied formats. The count is pinned by `root_work_files_per_user`; these files replace generic bulk records and do not increase the 5,000-file target.

Each user receives exactly 5,000 files and 100 unique CardDAV contacts. `managed_folder_targets` pins 20 logical business-category counts between 126 and 348, with deliberately varied non-round totals. The checked-in E-Commerce Dataset contributes 160 additional authentic order workbooks, 120 linked dataset-derived invoices, and 157 SVG order plots per user. Calendar attendees link to CardDAV contacts, calendar events link to files and shared business entities, and Talk rooms link to existing files for both users; unit and live checks reject broken links.

Each user also receives 12 unread, idempotently seeded business notifications tied to real generated files and the relevant Talk rooms. The notification importer uses stable `webarena_seed` object IDs, so rerunning it replaces the managed notification instead of adding a duplicate.

Purchase requisitions and vendor assessments are generated only as populated PDF and DOCX documents. Each vendor has one assessment and one review note per year, plus one readable DOCX master record that presents its profile, annual summaries, and complete purchase-order history. The build and live verifier check these links and totals across all five procurement folders and reject unsupported formats.

Timesheets are monthly XLSX workbooks: 12 per complete year from 2022–2025 and January–June for 2026. Each workbook has one worksheet for every configured worker category. The yearly counts and category list are pinned in `seed_spec.json`.
