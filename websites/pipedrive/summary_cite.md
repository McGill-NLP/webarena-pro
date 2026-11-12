# PipeCRM — Pipedrive Replica Summary

## Feature Assessment

### What's Solid (Core Pipedrive Features)

- **Kanban Pipeline** — Drag-and-drop deal management across stages with real-time reordering, stage value aggregation, and transactional integrity. The strongest part of the replica.
- **Contacts & Companies** — Full CRUD with search, pagination, sorting, and relationship linking. Detail pages show related deals and activities.
- **Activities** — 5 types (call, email, meeting, task, note), date grouping, completion tracking, linked to deals/contacts/companies.
- **Dashboard** — Summary cards, deals by stage chart, 6-month revenue forecast with probability weighting, win/loss breakdown.
- **Global Search** — Cmd+K command palette searching across all entities with debounced real-time results.
- **Pipeline Settings** — Stage management with customizable probability percentages.

### What's Missing vs Real Pipedrive

| Feature | Status |
|---|---|
| Multi-user / teams | Not implemented — single user only |
| Email integration (send/receive) | Missing |
| Custom fields | Missing |
| File attachments | Missing |
| Bulk operations | Missing |
| Import/export (CSV) | Missing |
| Activity reminders/notifications | Missing |
| Deal rotting indicators | Missing |
| Multiple pipelines | Partial — schema supports it, UI doesn't |
| Workflow automations | Missing |
| Integrations (calendar, Slack, etc.) | Missing |
| Reporting/goals | Basic dashboard only |
| Lead inbox | Missing |

### Verdict

As a **visual replica / demo**: **7.5/10** — The UI is clean, the kanban feels right, and the core CRM loop (deals → contacts → companies → activities) works. Someone clicking around would recognize it as Pipedrive-like.

As a **functional replica**: **4/10** — Pipedrive's value is in the workflow — email sync, automations, team collaboration, reporting depth. Those are all absent.

For a portfolio piece or demo environment, it's strong. For actually replacing Pipedrive, it's an MVP at best.

---

## LLM Agent Evaluation Tasks

10 tasks designed around what a salesperson actually does in Pipedrive, graded by interaction complexity.

### Easy (1-3 clicks)

**Task 1 — Check pipeline health**

> What is the current win rate percentage shown on the dashboard?

Tests: Navigation to dashboard, reading a metric. (1-2 clicks)

**Task 2 — Complete an activity after a call**

> Mark the activity "Discovery call with John Smith" as done.

Tests: Finding an activity, toggling completion. Activity-based selling is Pipedrive's core philosophy. (2-3 clicks)

**Task 3 — Look up a contact before a meeting**

> Using the search, find the contact Daniel Harris and report his job title and company.

Tests: Global search (Cmd+K), reading contact info. Salespeople do this constantly before calls. (2-3 clicks)

### Medium (3-8 clicks)

**Task 4 — Log a new sales activity**

> Go to the deal "FinanceHub Trading Platform" and log a completed call activity with the subject "Discussed pricing tiers with Robert".

Tests: Deal navigation, activity creation form, type selection. Core Pipedrive workflow — every interaction gets logged. (5-6 clicks)

**Task 5 — Advance a deal through the pipeline**

> Move the deal "RetailMax POS System" from its current stage to "Negotiation".

Tests: Kanban drag-and-drop OR edit form with stage change. This is THE defining Pipedrive interaction. (3-5 clicks)

**Task 6 — Qualify a new lead into the pipeline**

> Create a new contact "Alex Rivera" (alex@cloudnine.io, Solutions Engineer) at CloudNine, then create a deal "CloudNine Expansion" worth $55,000 in the "Lead In" stage linked to this contact.

Tests: Contact creation with company association, then deal creation linking to that contact. Reflects the lead qualification workflow. (7-8 clicks)

**Task 7 — Filter activities to plan your day**

> On the activities page, filter to show only pending meetings, and report how many there are.

Tests: Activity filtering by type AND completion status. Salespeople start each day planning their activities. (3-4 clicks)

### Hard (8+ clicks)

**Task 8 — Prep a deal for pipeline review**

> Find the deal "SafeGuard Pen Testing". Update its value to $60,000 and its expected close date to next month. Then schedule a meeting activity with subject "Contract review with Nancy Robinson" due in 3 days.

Tests: Deal lookup, editing multiple fields, then adding a linked activity. Reflects preparing for a weekly pipeline review meeting. (10+ clicks)

**Task 9 — Customize pipeline stages**

> In settings, add a new stage called "Verbal Commit" with 90% probability. Then move the deal "BioGenix Lab System" into this new stage.

Tests: Settings navigation, stage creation, then returning to kanban to move a deal into the new stage. Pipedrive's customizable pipeline is a key differentiator. (8-10 clicks)

**Task 10 — Investigate an account and take action**

> Navigate to the company Acme Corp. Find their highest-value open deal. Go to that deal, mark it as "Won", and then log a note activity with subject "Contract signed — Q1 target exceeded" on it.

Tests: Multi-entity navigation (company → deals list → deal detail), decision-making (identifying highest value), status change, activity logging. This is the full sales closing workflow. (10-12 clicks)

---

### Task Coverage

These tasks cover the core Pipedrive value propositions:

- **Visual pipeline management** — Tasks 5, 9
- **Activity-based selling** — Tasks 2, 4, 7, 8
- **Deal lifecycle** — Tasks 6, 10
- **Relationship tracking** — Tasks 3, 6, 10
- **Analytics** — Task 1
