# Nextcloud Seed Dataset

The Nextcloud image contains a deterministic, lightweight dataset for browser-agent and open-research evaluation. It models the fictional company Cedarstone Analytics using the reserved `cedarstone.test` domain. A fresh data volume is seeded with two primary employees, four supporting Talk users, and the following baseline totals:

| Entity | Maya Patel (`maya.patel`) | Daniel Brooks (`daniel.brooks`) | Supporting users | Total |
| --- | ---: | ---: | ---: | ---: |
| Files | 5,000 | 5,000 | 0 | 10,000 |
| Contacts | 100 | 100 | 0 | 200 |
| Calendar events | 50 | 50 | 0 | 100 |
| Notifications | 12 | 12 | 0 | 24 |
| Authored Talk messages | 178 | 167 | 80 | 425 |

## Content and provenance

Most records are deterministic synthetic office data generated from `seed_spec.json` using seed `20260713`. They contain fictional names, reserved example domains, synthetic amounts, and no intentionally collected personal data. The workspace uses realistic Analytics, Finance, Legal, Sales, Procurement, Operations, Meetings, Projects, Reports, Strategy, Presentations, People, and Marketing hierarchies. It includes populated invoices, orders, plots, meeting minutes, procedures, reports, spreadsheets, and multi-slide presentations in valid TXT, Markdown, CSV, JSON, SVG, PDF, DOCX, XLSX, and PPTX formats. No `Customer Support` folder or support-case corpus is generated.

Twenty managed business categories per user contain varied totals from 126 to 348 documents. Counts are intentionally irregular—for example 348 invoices, 212 or 216 budgets, 286 campaigns, 239 management reports, and 157 order plots—rather than round filler targets. Benchmark-sensitive folders and fixed structures such as annual procurement records, monthly timesheets, and the retained reference library remain outside this balancing rule.

The file total also includes 200 genuinely authored documents, split evenly between maya.patel and daniel.brooks under `Reference Library`. Of these, 160 are unmodified GitHub Docs pages from pinned revision `b78592c31a1589588c2e5a05d38968c215cf2698`, and 40 are unmodified Kubernetes community governance and contributor documents from pinned revision `dfc0a77ac0a9d5d0da8912704b2b18b4013701fe`. These files replace generated records rather than increasing the 5,000-file per-user target.

The Finance, Procurement, and Sales folders contain populated invoices and order data:

- Each user has 348 invoice PDFs directly under `Finance/Invoices`, with no year or source-record subfolders. Forty per user use five visibly different templates—Modern Banner, Classic Border, Compact Sidebar, Professional Services, and Retail Statement. Another 120 per user are linked to authentic order rows from the open dataset, with generated customer names and prices explicitly recorded as synthetic enrichment; the remaining documents are populated generated invoice records.
- Each user has 292 synthetic purchase-order PDFs under `Procurement/Purchase Orders`, organized by year: 42 in 2022, 57 in 2023, 76 in 2024, 68 in 2025, and 49 in 2026. The five visibly different templates are Modern Procurement, Classic Purchase Form, Vendor Sidebar, Operations Grid, and Executive Approval. Every order contains a fictional buyer and supplier, issue and required dates, shipping and payment terms, requester, cost center, six purchasable line items, subtotal, shipping, tax, total, approval, and delivery instructions.
- Procurement contains 672 linked files per user: 292 purchase orders, one matching requisition for every order, 40 annual vendor assessments, 40 annual vendor notes, and 8 readable DOCX vendor master records. Requisitions retain the order vendor, requester, project, cost center, line-item SKUs, and approved total; each assessment and note reconciles the actual orders for one vendor and year, while each master record presents that vendor's profile, annual summaries, and complete 2022–2026 purchase-order index. Requisitions and assessments are evenly divided between populated PDF and DOCX files; structured reconciliation fields remain in the provenance manifest rather than user-facing JSON documents.
- Each user's `All files` root contains six current working files for a less artificial home view: a reference copy of a real seeded purchase order, project status, meeting brief, budget forecast, open-order register, and operations review. Their source records remain in the appropriate organized folders, and these root files replace generic bulk records so the total remains exactly 5,000 files per user.
- 360 authentic customer orders selected from the 100,000-record [E-Commerce Dataset](https://data.mendeley.com/datasets/ggbkd8ck3x/1), split 180 per user. Each order is reformatted into an individual XLSX workbook, and both users also retain the complete original source workbook. The newer 160 workbooks per user link one-to-one with 120 dataset-derived invoices and feed 157 SVG quantity plots per user.

Each user has 54 monthly XLSX timesheets under `People/Timesheets`: 12 for every year from 2022 through 2025 and six for January through June 2026. Every workbook contains a separate populated worksheet for Full-Time Employees, Part-Time Employees, Contractors, Interns, Temporary Staff, and Consultants, including employee IDs, cost centers, regular, overtime and leave hours, totals, and approval status.

These files replace other generated records, so each user still has exactly 5,000 files. The invoices and purchase orders are explicitly marked as synthetic research fixtures. Each authentic customer-order workbook is a readable transformation with unchanged source values, not a claim that it is a retailer-issued order form.

Each user also receives a dense business calendar with several meetings per business day. Eight resources per user are recurring daily, weekly, or monthly series, while 42 are distinct one-time meetings such as customer workshops, interviews, audits, demonstrations, incident reviews, and planning sessions. Events use explicit `America/Toronto` local time and never start before 9:00 AM.

Cross-service links are validated during generation and startup. Each agent receives 100 unique CardDAV contacts. Calendar attendees reference real seeded contact UIDs, every event links to an existing file and shared customer/project/vendor/team identifiers, all Talk participants appear in both users' contacts, and every Talk room links to existing files for both agents. The live verifier checks these links, hashes, DAV counts, Talk authorship, threads, participants, and unread state.

Each primary user receives 12 unread business notifications. They cover invoice review, purchase-order delivery, vendor assessment, management reporting, quarterly presentations, customer orders, hiring, meeting follow-up, project milestones, budgets, inventory, and contracts. Every notification names a supporting colleague, references an existing file, and points the user to a relevant Talk room. Stable object identifiers make imports idempotent, and the live verifier compares the rendered notification subjects and messages with the generated source rows.

Talk contains 425 authored messages. The requested agent totals remain 178 messages from maya.patel and 167 from daniel.brooks. Sarah Chen, Priya Nair, Marcus Johnson, and Leon Greene contribute 20 messages each. Nine business rooms have varied memberships of three to five people; Project Alpha retains its isolated canonical eight-message history.

The room histories contain 54 named topic threads and 363 replies linked to their thread roots. Three deterministic rooms are left unread for maya.patel and three different rooms are left unread for daniel.brooks, with two to six unread messages per room. The importer explicitly restores these read markers after posting and the live verifier checks them without advancing the markers.

A small number of task-critical media assets are bundled from Wikimedia Commons and Freesound. Every file, contact, event, notification, and message has an entry in the generated `provenance/manifest.jsonl`, including its SHA-256 hash, source, creator, and SPDX license identifier. `seed/assets.json` is the checked-in source of truth for bundled media, `seed/real_documents.json` records every retained technical document, and `seed/financial_documents.json` pins the original order workbook, selected order identifiers, destinations, and transformations.

The generator fails when a bundled asset is undocumented, its checksum changes, or its license is outside the allowlist.

## Licensing

- Generated data and the dataset selection/arrangement: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), attributed to WebArena-Pro contributors.
- GitHub Docs content: [CC BY 4.0](https://github.com/github/docs/blob/b78592c31a1589588c2e5a05d38968c215cf2698/LICENSE), attributed to GitHub, Inc. and contributors.
- Kubernetes Community documents: [Apache License 2.0](https://github.com/kubernetes/community/blob/dfc0a77ac0a9d5d0da8912704b2b18b4013701fe/LICENSE), attributed to Kubernetes contributors.
- E-Commerce Dataset customer-order records: [CC BY 4.0](https://data.mendeley.com/datasets/ggbkd8ck3x/1), attributed to Debjit Roy and Vishal Bansal.
- Some retained work documents: [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
- Generator and importer code: [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
- Third-party CC BY 4.0 media remains attributed to its original creators in the manifest.

The generated manifest is authoritative for per-asset licensing. Do not infer an asset's license from its directory or filename.

## Reproduction

From `websites/nextcloud`:

```bash
python3 seed/fetch_real_documents.py --verify-only
python3 seed/fetch_financial_documents.py --verify-only
python3 seed/generate.py \
  --spec seed_spec.json \
  --media media \
  --output generated-seed
```

The Docker build runs the same verification and generation logic in a multi-stage build. The retained documents and order source are checked in, so generation requires only Python's standard library and performs no network requests. Running either fetcher without `--verify-only` restores its corpus from the pinned upstream files.

Exact counts apply to a fresh Nextcloud volume. Existing volumes may contain user-created or task-created data and are never pruned automatically. Reset with `docker compose down -v` before measuring the baseline.

## Limitations

The corpus is intentionally lightweight and should not be treated as representative of real organizational, demographic, financial, procurement, or conversational distributions. Synthetic organizations, invoices, purchase orders, transactions, people, and decisions remain fictional. The authentic technical documents and customer-order records are included for document navigation, reading, search, and spreadsheet evaluation under explicit compatible licenses; they are not records of the fictional seed organization. Derived order workbooks preserve source values and should not be treated as newly issued commercial documents. Dataset-derived invoices add fictional prices and customers solely for evaluation, and the manifest identifies that synthetic enrichment explicitly.
