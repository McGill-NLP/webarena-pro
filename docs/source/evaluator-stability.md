# Repeated checkpoint judgments

BrowserGym owns one in-memory judge reuse scope per task execution. It replaces
the scope on setup, including checkpoint recovery that resets and replays the
environment. No verdict cache is persisted in checkpoints or shared between
workers, tasks, or runs.

The default policy is `identical_input`. A valid positive **or negative**
single regular judge response can be reused only when all captured inputs
remain identical: the task and evaluation DAG, execution date, full rendered
action/reasoning history, current screenshot and accessibility tree, current
URL, last action, chat/download records and backend snapshot bundle, rubric,
node ID, current tiered probe results, prompt version, model, endpoint, sampling
and retry settings.
Any observed evidence change clears earlier entries, including entries for
nodes skipped by a failed dependency. Returning from state A to B and then A
therefore requires fresh judgments; it does not revive an older success.
DAG dependencies and deterministic checks still execute at every checkpoint.
An authoritative non-judge result or dependency skip discards that node's older
fallback judgment.

This requires an explicit current observation containing an accessibility tree
or screenshot. An unencodable screenshot or unsupported evidence value disables
reuse. Callers without a current observation record
`missing_current_observation` and make fresh judge calls.
Standalone Core callers must explicitly provide a `JudgeVerdictCache` in
`EvalContext.judge_cache` to enable reuse. Custom judge hooks are never cached.

Model/parse/configuration failures are not cached. Nor are verdicts obtained
after a retry, prompt repair, or a pruned prompt. An error at one checkpoint
cannot become a persistent failed score. At most 128 node entries are retained.

To measure independent model variation, disable reuse:

```bash
export WEBARENAPRO_LLM_JUDGE_REUSE=none
```

A judge node/strategy can override this with `"reuse": "none"` or
`"reuse": "identical_input"`. Invalid policy names produce an audited
configuration error. Model and sampling defaults are unchanged.

Each judgment records its node ID, effective configuration and reuse policy.
A hit records the input hash, execution-scope ID and source audit ID, with
`attempts: []` because no new request was submitted. Its embedded
`source_audit` retains the original request and response so a standalone
checkpoint artifact remains auditable and replayable. The replay command
follows that source and always submits fresh requests; hits are not additional
independent samples. DAG results retain the hit and the dependency skip reasons.

## Limits of the policy

Exact-input reuse removes repeat-sampling flips for unchanged captured inputs;
it does not establish that the first verdict is correct. Hidden application
changes absent from the captured evidence cannot be inferred. The full
trajectory generally changes between steps 30, 50 and 100, even when a completed
action appears unchanged. Those checkpoints are deliberately rejudged.
Consequently cache reuse alone does not resolve changing-trajectory judgments.
The historical task 112/344 judge requests still need comparison before claiming
their captured evidence was identical. Use the judge audit replay tool to measure
model variation on those requests; never replace current scores with an
unconditional historical maximum. Current task 112/344 grading first uses the
deterministic checks below. Task 344 retains Tier 2 only for inconclusive probes.

## Deterministic tasks 112 and 344

Both tasks retain their intents, equal criterion scoring, and DAG dependencies. Each node
starts with an authoritative Tier 0 strategy (`trust: both`). Every checkpoint
re-reads the backend; neither successful nor failed scores are latched. A
definitive Tier 0 pass or failure is final. Task 112 has no LLM fallback, so
inconclusive probes receive no credit. Task 344's original Tier 2 rubric judges
run only when their deterministic probe is inconclusive, including unavailable,
malformed, or truncated evidence. Dependency failures still skip child nodes.

Task 112 uses `backend_state` with the existing `user_by_name`, `channel_by_name`,
and `channel_posts` API templates. Its reusable `json_collection_contains` checks
resolve the actual user and Water Cooler channel, paginate current posts, and
exclude deleted, system,
other-author, other-channel, and pre-execution posts. `r1` requires all three
recipe names in one message, ignoring case and punctuation differences. `r2`
requires an actual Markdown destination or bare URL on the deployed YT-lite
origin, with exactly `/watch/fv238` or `/watch/fv337`. Query parameters and
fragments are allowed; wrong hosts, video IDs, path suffixes, code snippets,
images, and misleading link labels do not count. The two nodes stay independent.
Editing away names or the link removes only that node's credit; deleting the
matching post removes both unless another qualifying post remains.

Task 344 uses `backend_state` with the Flight Search `eval_state` API template and
a shared `json_predicate` check. Evidence guards, execution filtering, inclusive
duration comparisons, eligible origins, search/booking joins, and the latest
Boston route are all declared in task JSON. There is no Flight Search grading
helper or separately registered evaluator. The deterministic path requires the updated
Flight Search image providing authenticated `GET /api/eval/state`. The application
records the filtered offers actually returned by searches, with real request timestamps
independent of the frozen benchmark clock. It also records booking creation IDs
and serves the current booking records without passenger/payment data.

- `r1`: a search in this execution returned a nonstop flight **from YUL** with
  a displayed duration of 180–240 minutes inclusive. Catalogue presence and
  chat claims do not count. Completed research is historical evidence: moving
  to another page does not undo it.
- `r2`: the latest submitted Boston route selects a researched origin in the
  existing 18-city list, or a current qualifying booking already proves that
  choice. A new incompatible choice removes unbooked selection credit.
- `r3`: a booking created in this execution still exists, is confirmed and
  one-way, and goes from a researched eligible city to BOS. The booked leg has
  no duration/nonstop restriction. Cancellation/removal loses booking credit;
  research and an otherwise valid selection retain their partial credit.

These checks use the shared worker-specific URLs and `task_start_time_ms` supplied
by BrowserGym. Missing execution time, missing/old endpoint schemas, and
truncated execution history are explicitly inconclusive and trigger task 344's
Tier 2 fallback, retaining the probe reason in the tiered trace. A successful
fallback at an earlier checkpoint cannot override a later definitive backend
failure, such as a cancelled or removed booking. Reset clears the flight
journal and changes its generation; older bookings/searches cannot establish
completion in a new execution. The endpoint requires `X-Eval-Token`, provisioned
by the standard Core launcher, even when the site's passkey gate is disabled.

Rebuild and deploy Flight Search to enable deterministic grading of task 344;
existing images without the endpoint use its Tier 2 fallback. LLM fallback can
still vary across checkpoints when deterministic evidence is unavailable.
Source-level API tests and packaged-DAG integration tests cover the staged
0 → 1/3 → 2/3 → 1
progression and the reverse transitions. They do not reproduce the historical
LLM verdicts. The older judge-cache regressions retain archived pre-change DAGs.
