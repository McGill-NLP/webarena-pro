# Task Configuration Guide

Each `<site>.raw.json` file is a JSON array of **Test tasks only**. Together,
the website files contain **300 Test tasks**. The **100 Dev tasks** and their
evaluators exist together in `splits/dev.json`, giving
**400 distinct tasks** with no overlap.

## Template

```json
{
	"sites": [
		"nextcloud",
		"mattermost"
	],
	"task_id": "000",
	"require_login": true,
	"login_usernames": {
		"nextcloud": "maya.patel",
		"mattermost": "admin"
	},
	"intent": "Delete all the individual contents of each folder then restore them using the trash folder and add them back to the folders they originally came from.",
	"startup_wait_seconds": 0,
	"eval": {
		"operator": "AND",
		"scoring": "partial",
		"nodes": [
			{
				"id": "r1",
				"type": "tiered",
				"depends_on": [],
				"eval_config": {
					"rubric": "Each deleted item is restored to its original folder.",
					"strategies": [
						{
							"tier": 2,
							"type": "llm_judge",
							"config": {
								"rubric": "Each deleted item is restored to its original folder."
							}
						}
					]
				}
			}
		]
	}
}
```

## Field Instructions

- `sites`: list of target site IDs (for example `"nextcloud"`, `"notion"`, `"flight-search"`). The first entry is the primary/start website. The legacy `website` field is still accepted for old single-site tasks, but new tasks should use `sites`.
- `task_id`: zero-padded numeric string identifier, unique across the packaged
  core task configs. Packaged IDs extend through `422`; removed IDs are not reused.
  The reviewed October additions use `300` through `345` and `403` through `420`.
  Each task is stored once, with its evaluation inside the same record.
- `require_login`: set to `true` if the task needs authenticated browser sessions. When enabled, setup logs into every site listed in `sites`.
- `login_usernames`: optional object mapping each selected site to the username/email to use for UI login. If omitted for a site, the first configured credential for that site is used. The legacy single-site `login_username` field still applies to the primary site.
- `intent`: the concrete natural-language instruction the agent must solve.
- `startup_wait_seconds`: optional delay in seconds during setup, before login
  and navigation. Defaults to `0`; negative values are clamped to `0`.
- `eval`: the task's evaluation DAG, including `operator`, `scoring`, and `nodes`.
  Snapshot-based checks also need `eval.baseline`, described below.

The starting URL is resolved from the deployment configuration for the first
entry in `sites`. Each selected site is reset before the agent begins a task by
default. The CLI's `--no-reset-per-task` option disables per-task reset, and
`WP_RESET_BACKEND` selects the reset strategy.

## Quick Checklist

- Keep each `task_id` unique across the packaged task set.
- Ensure `sites` contains every website the task expects the agent to visit.
- Use `login_usernames` for any selected website that must start under a specific account.
- Put the evaluation DAG under `eval` in each task record. Do not copy the
  task ID or intent into the DAG.
- Validate JSON format (no trailing commas, double quotes only).

The Dev set contains **100 tasks**.

## Tiered evaluations

Each active task contains its evaluation DAG in `eval`, alongside `task_id`,
`intent`, and setup fields. There are no active tiered sidecar files. Task
definitions omit original timestamp IDs and creator metadata. For older external
configs, the loader still accepts sidecars matched by original ID, task ID, or
intent; an embedded DAG takes precedence over a sidecar.
Tiered DAG nodes retain their criteria, deterministic checks, and LLM fallback
strategies. There is no additional whole-task rubric judge.

Every task uses `"scoring": "partial"`: its score is the number of passed
criteria divided by the total number of criteria. All criteria count equally,
including dependent criteria skipped after a failed prerequisite, which count
as failures. The supported scoring modes are `partial` and `binary`.

Strategies run in their JSON list order; `tier` is a trace label, not a sorting
key. Place deterministic checks first and terminal strategies last. Default
trust comes from the strategy `type`; use explicit `trust` when a check needs
a different policy. See the [DAG evaluator guide](../../../../docs/source/evaluators.md)
for verdicts, exhaustion behavior, and scoring.

## Snapshot baselines

To evaluate changes from the initial application state, add a `baseline` array
inside `eval`, alongside `nodes`. Each entry has a unique `name`, a registered
`provider`, and optional provider-specific `params`. For example:

```json
{
  "baseline": [
    {
      "name": "mydrive_files",
      "provider": "mydrive_files",
      "params": {"site": "mydrive"}
    }
  ]
}
```

This is a fragment of `eval`, not a complete task. A `backend_state` snapshot
check references the entry with `"baseline_ref": "mydrive_files"` in its
`eval_config` (or a tiered strategy's `config`). BrowserGym captures the
baseline after reset/login and before agent actions, then compares it with the
current state at grading. For a cross-site MyDrive task, `params.site` selects
MyDrive even when it is not the primary site. Provider parameters are specific
to each provider; `immich_assets`, for example, accepts `exclude_year`.

Unavailable snapshots do not count as empty collections or prove preservation.
Configure the intended fallback policy explicitly and preserve baseline evidence
when grading saved runs. See the
[snapshot configuration example](../../../../docs/source/evaluators.md#configuring-snapshot-evidence)
for the matching check and failure behavior.

## Previewing tasks

`webarena-pro run` uses tiered evaluation by default. Use `--split dev` or
`--split test` to select a partition, and `--list` to preview selected tasks.
Omitting `--split` loads the 300 Test tasks.
