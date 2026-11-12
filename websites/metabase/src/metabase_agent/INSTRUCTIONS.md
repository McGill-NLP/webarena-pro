# WebArena Pro — Metabase Environment Contributor Guide

## Overview

You are responsible for designing and validating benchmark tasks for the
**Metabase** environment as part of the WebArena Pro project. WebArena Pro
is an extension of the original WebArena benchmark, aiming to create a
diverse, multi-modal web agent evaluation suite across 20 sandboxed
environments.

Your role is **not** to build Metabase itself — it is already an existing
open-source tool running in a pre-configured Docker environment with a mock
PostgreSQL database. Your job is to write meaningful, well-defined tasks
and validate them using AgentLab.

---

## Your Deliverables

1. **Task definition YAML files** for Metabase
2. **Correct success criteria** for each task
3. **Validation** that each task runs correctly in AgentLab without errors

---

## Environment

- **Metabase** runs locally at `http://localhost:3000`
- **PostgreSQL** mock database is pre-seeded with sample data (e.g. Orders,
  Order Items, Products, etc.)
- **AgentLab + BrowserGym** is your testing tool — the agent interacts with
  Metabase via real browser actions (click, type, scroll, etc.) executed
  through Playwright
- Everything runs in Docker containers that are already prepared

---

## Task Design

### Two Types of Tasks

#### 1. Find / Report Tasks
The agent navigates Metabase and returns an answer by calling `done()`.

**Example:**
> "How many rows are in the Orders table in the sample database?"

Success is verified by checking the agent's response contains the correct
answer.

#### 2. Action / Creation Tasks
The agent actually performs operations in Metabase (creates questions,
dashboards, sets up alerts, writes SQL, etc.).

**Example:**
> "Create a bar chart showing total revenue by product category and save it
> to the Our Analytics collection."

Success is verified by querying the **Metabase API** after the agent
finishes to confirm the artifact was correctly created or modified.

---

### Task Writing Rules

#### ✅ DO
- Write the instruction as a **goal**, not a script
- Use natural language that a real user would say
- Make the correct answer unambiguous and verifiable
- Include the actual correct answer in `response_contains` for report tasks
- Verify creation/modification via the Metabase API for action tasks
- Vary difficulty across beginner, intermediate, and advanced

#### ❌ DON'T
- Spell out step-by-step instructions (no "1. Click here, 2. Click there")
- Use vague success criteria like `response_contains: "Order ID"`
- Design tasks where the answer is ambiguous or changes with the data
- Make tasks that are impossible or require features not in the environment

---

### YAML Task Format

```yaml
id: unique_task_id
name: Short human-readable name
instruction: >
  Natural language goal for the agent. No step-by-step instructions.
  Just describe what needs to be accomplished.
start_url: http://localhost:3000/some/path
max_steps: 15
timeout_seconds: 300
success_criteria:
  - response_contains: "exact correct answer"  # for report tasks
  # OR for action tasks, a custom eval function that hits the Metabase API
tags:
  - difficulty_level   # beginner / intermediate / advanced
  - task_type          # browse / create / sql / dashboard / admin / etc.
notes: >
  Internal notes about the task. What data it relies on, any gotchas,
  how to verify manually, etc.
```

---

## Task List

Below are the tasks you need to implement, roughly ordered by complexity.

| # | Task | Type | Difficulty |
|---|------|------|------------|
| 1 | Filter and save a question | Action | Beginner |
| 2 | Bookmark and share a dashboard | Action | Beginner |
| 3 | Create a GUI question with grouping/sorting | Action | Intermediate |
| 4 | Create/update a dashboard with specific elements | Action | Intermediate |
| 5 | Filter a dashboard and export data (PDF/CSV/JSON) | Action | Intermediate |
| 6 | Set up a multi-card dashboard subscription | Action | Advanced |
| 7 | Set up a question alert | Action | Intermediate |
| 8 | Change user permissions for a specific collection | Action | Advanced |
| 9 | Write a SQL query with joins and add it to a dashboard | Action | Advanced |
| 10 | Data cleanup (archive old/duplicate questions) | Action | Advanced |

---

## Success Criteria Guidelines

### Report Tasks
```yaml
success_criteria:
  - response_contains: "42"  # the actual correct value from the mock DB
```

### Action Tasks
You need to verify state via the Metabase API after the agent completes.

Useful Metabase API endpoints:
- `GET /api/card` — list all saved questions
- `GET /api/dashboard` — list all dashboards
- `GET /api/alert` — list all alerts
- `GET /api/pulse` — list all subscriptions
- `GET /api/collection` — list collections and permissions

**Example:** To verify a question was saved to the correct collection,
query `GET /api/card` and check that a card with the expected name exists
in the expected collection.

---

## Validation Process (Using AgentLab)

For each task you write, go through this checklist:

1. **Run the agent** on the task in AgentLab
2. **Check the agent can attempt it** — if it's completely lost from the
   start, the instruction may be too vague or the `start_url` is wrong
3. **Check the success criteria** — does it correctly return pass when the
   agent succeeds and fail when it doesn't?
4. **Check difficulty** — if the agent trivially solves it in 1-2 steps,
   it may be too easy; if it never gets close, it may be too hard
5. **Iterate** — fix the instruction, start URL, or eval logic and re-run

> You are NOT responsible for achieving high agent success rates. You are
> responsible for ensuring the tasks are well-defined and the evaluation
> is correct.

---

## Constraints

- Tasks must be **reproducible** — the mock database is fixed, so correct
  answers must not change between runs
- Tasks must be **self-contained** — don't design tasks that depend on a
  previous task having been completed first
- Each task should have a **clean starting state** — if a task creates
  something, assume it doesn't already exist at the start
- Difficulty should be **varied** — not all tasks should be advanced; aim
  for a mix across the three levels
- Instructions must be written **without step-by-step guidance** — the
  agent should figure out the how, you only specify the what

---

## Summary

| What you do | What you don't do |
|---|---|
| Write task YAML files | Build or modify Metabase |
| Define success criteria | Maintain AgentLab/BrowserGym |
| Validate tasks with AgentLab | Run large-scale benchmarks |
| Query Metabase API for eval logic | Design other environments |
| Iterate based on agent runs | Write the research paper |