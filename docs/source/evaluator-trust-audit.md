# Evaluator trust audit (October 27, 2026)

Issue #73 was audited against `46599d16fb71bcbe5a36196813e075dec571ef33`: **76 omitted-trust Tier-0 strategies in 76 nodes across 47 Test tasks**. Of these, 49 are answer matchers and 27 inspect backend state. This audit covers that reported inventory; the command below can inspect both current splits.

The resolver keeps conservative type defaults. This change explicitly makes **45 answer heuristics and one JSON-order-sensitive backend regex** `pass_only`. Two prompt-mandated answer formats explicitly retain `both`. The initial audit left 28 nodes unchanged: 19 with separate task-repair PRs, six authoritative state checks, and three task-contract mismatches. The November 4 follow-up removes the incomplete probes for tasks 159, 165 and 176 and aligns their rubrics with the requested participants and files; task 176's unrelated-room shortcut is also removed. A later strategy after `both` is reachable on an inconclusive probe or evaluator error, but cannot overturn a concrete failure.

Task 099 uses a narrow exact-answer fast path; Markdown, parentheses, or other equivalent phrasing reaches its semantic rubric. Contradictory or incorrect answers are not accepted by the fast path. DAG dependencies, task membership, and backend ground-truth defaults are unchanged.

The November 5 follow-up adds deterministic `nextcloud_saved_state` strategies
with explicit `trust: both` to all 12 nodes in tasks 159, 165, and 176. Talk
membership, poll options, current-user votes, and checkmark reactions are checked
through their native APIs. Task 176 captures file identities before execution,
verifies new folders and byte-identical copies with retained originals, and binds
the folder share to its saved group message. Room baselines and native creation events now reject pre-existing groups.
Reaction checks require all votes on the same poll and evidence that the
checkmark follows voting, with a scoped pass-only Tier 1 UI fallback. The
Safari judge rubrics list the source filenames explicitly. The original
incomplete probes remain removed; complete Tier 0 failures are authoritative
and unavailable or ambiguous evidence escalates. Criteria use equal partial
credit after merging the removal of weights from `main`. See the
[evaluator guide](evaluators.md#strategy-implementations) for evidence limits.

Run `python webarena-pro-core/scripts/audit_evaluator_trust.py` for the current inventory or add `--json` for structured output. The report exposes omitted and explicit trust and whether a concrete failure can reach a later strategy. An explicit `both` with a later strategy is flagged as a conditional fallback, not presumed contradictory: that fallback still handles unavailable evidence.

| Task/node | Strategy | Decision | Rationale |
|---|---|---|---|
| 041/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 041/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 041/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 042/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 043/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 045/r1 | `answer_match` | explicit both | The prompt explicitly requires a numeric-only answer with a negative sign and decimals. |
| 047/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 064/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 065/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 065/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 067/r2 | `answer_match` | separate task repair | Fare semantics are corrected by PR #39 (issue #29); preserve that separate change. |
| 068/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 077/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 077/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 077/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 089/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 089/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 094/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 094/r4 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 095/r1 | `backend_state` | explicit pass_only | JSON serialization order can make the job/applicant regex miss an existing matching application. |
| 099/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 100/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 101/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 102/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 123/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 123/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 126/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 126/r2 | `answer_match` | explicit both | The prompt explicitly requires the Product; $XXX.XX format. |
| 128/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 159/r1 | `backend_state` | deterministic task contract | Replace the title probe with native participant-account checks under any title; use semantic fallback only for unavailable or ambiguous evidence. |
| 160/r2 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #103; do not weaken its authoritative backend failures here. |
| 160/r3 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #103; do not weaken its authoritative backend failures here. |
| 161/r3 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #101; do not weaken its authoritative backend failures here. |
| 162/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 162/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 163/r2 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #106; do not weaken its authoritative backend failures here. |
| 163/r3 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #106; do not weaken its authoritative backend failures here. |
| 163/r4 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #106; do not weaken its authoritative backend failures here. |
| 165/r1 | `backend_state` | deterministic task contract | Replace the title probe with native participant-account checks under any title; use semantic fallback only for unavailable or ambiguous evidence. |
| 166/r1 | `backend_state` | separate task repair | PR #107 was declined by the maintainer. Preserve the current contact contract and trust behavior. |
| 166/r2 | `backend_state` | separate task repair | PR #107 was declined by the maintainer. Preserve the current contact contract and trust behavior. |
| 166/r3 | `backend_state` | separate task repair | PR #107 was declined by the maintainer. Preserve the current contact contract and trust behavior. |
| 168/r2 | `backend_state` | retain authoritative default | Saved backend state remains authoritative; later strategies are available only when the probe is inconclusive. |
| 168/r3 | `backend_state` | retain authoritative default | Saved backend state remains authoritative; later strategies are available only when the probe is inconclusive. |
| 169/r1 | `answer_match` | separate task repair | The redundant file-selection criterion is removed in PR #105 (issue #77). The remaining sharing and edit-access criteria each carry half the score. |
| 169/r2 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #105; do not weaken its authoritative backend failures here. |
| 169/r3 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #105; do not weaken its authoritative backend failures here. |
| 170/r1 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #104; do not weaken its authoritative backend failures here. |
| 170/r3 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #104; do not weaken its authoritative backend failures here. |
| 171/r1 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #102; do not weaken its authoritative backend failures here. |
| 171/r2 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #102; do not weaken its authoritative backend failures here. |
| 171/r3 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #102; do not weaken its authoritative backend failures here. |
| 171/r4 | `backend_state` | separate task repair | Task-specific state contract is repaired in PR #102; do not weaken its authoritative backend failures here. |
| 176/r2 | `backend_state` | deterministic task contract | Compare file IDs, versions, and content hashes against the baseline sources, under any new folder name. Originals must remain; r4 verifies the same folder's share. |
| 176/r3 | `backend_state` | deterministic task contract | Replace the unrelated-room shortcut with native participant-account checks for Susan, Matthew, Robert, and the current user. |
| 178/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 180/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 194/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 194/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 214/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 215/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 215/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 216/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 216/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 216/r4 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 217/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 218/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 219/r3 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 220/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 222/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 229/r1 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 229/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 231/r2 | `answer_match` | explicit pass_only | A lexical miss cannot disprove the requested semantic answer; the existing rubric checks the required facts. |
| 258/r2 | `backend_state` | retain authoritative default | Saved backend state remains authoritative; later strategies are available only when the probe is inconclusive. |
| 258/r3 | `backend_state` | retain authoritative default | Saved backend state remains authoritative; later strategies are available only when the probe is inconclusive. |
| 260/r2 | `backend_state` | retain authoritative default | Saved backend state remains authoritative; later strategies are available only when the probe is inconclusive. |
