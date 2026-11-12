import logging
import os
import time
from datetime import date
from typing import Any

import playwright.sync_api as pw

from browsergym.core.env import AbstractBrowserTask

from webarena_pro_core.task import WebArenaProTaskConfig
from webarena_pro_core.eval.judge_cache import JudgeVerdictCache

from .actions import is_completion_action
from .instance import WebArenaProInstance
from .navigation import TaskNavigationGuard


logger = logging.getLogger(__name__)


def _safe_size(path: str) -> int:
    try:
        return os.path.getsize(path) if path else 0
    except OSError:
        return 0


class WebArenaProTask(AbstractBrowserTask):
    def __init__(self, seed: int, config: WebArenaProTaskConfig):
        super().__init__(seed=seed)
        self.config = config
        self.instance = WebArenaProInstance()
        self.navigation_guard = TaskNavigationGuard(self._selected_website_urls().values())
        # name -> Snapshot, captured during setup() before the agent runs.
        self.baselines: dict[str, Any] = {}
        # Browser downloads captured via page.on("download") during setup().
        # Each entry: {"path": str, "suggested_filename": str, "url": str}.
        self.downloads: list[dict[str, str]] = []
        # Set at the start of setup(), before resets/login/navigation. DAG checks
        # for relative dates use the execution day, not the later grading day.
        self.task_start_date: date | None = None
        self.task_start_time_ms: int | None = None
        self.judge_cache = JudgeVerdictCache()

    def setup(self, page: pw.Page):
        self.task_start_date = date.today()
        self.task_start_time_ms = time.time_ns() // 1_000_000
        self.judge_cache = JudgeVerdictCache()
        # Default behavior: reset each selected site to a pristine baseline
        # before every task. Most sites restore state in place; Docker recreate
        # is retained as a bootstrap/fallback path.
        from webarena_pro_bgym.benchmark.container_reset import reset_enabled
        from webarena_pro_bgym.prewarm import PREWARMED_TASK_ENV_VAR
        from webarena_pro_core.state_reset import (
            NOOP_BACKEND, reset_backend_for_site, reset_site, wait_until_site_ready,
        )

        resets_enabled = reset_enabled()
        prewarmed_task_id = os.environ.pop(PREWARMED_TASK_ENV_VAR, None)
        use_prewarmed_sites = (
            resets_enabled
            and prewarmed_task_id is not None
            and prewarmed_task_id == str(self.config.task_id)
        )
        if use_prewarmed_sites:
            logger.info(
                "%s: using prewarmed containers for task %s",
                self._worker_log_label(),
                self.config.task_id,
            )
            for site in self.config.sites:
                wait_until_site_ready(site)
        elif resets_enabled:
            for site in self.config.sites:
                self._reset_site_for_task(site, reset_site)

        if self.config.startup_wait_seconds > 0:
            time.sleep(self.config.startup_wait_seconds)

        if not resets_enabled:
            for site in self.config.sites:
                wait_until_site_ready(site)

        # Set only after every selected site's reset/readiness check succeeded.
        # Checkpoint replay forces a direct reset instead of accepting prewarm.
        self.checkpoint_reset_verified = resets_enabled and all(
            reset_backend_for_site(site) != NOOP_BACKEND for site in self.config.sites
        )

        website_urls = self._selected_website_urls()
        target_url = website_urls.get(self.config.website, self.config.start_url)
        if not target_url:
            raise RuntimeError(
                f"Could not resolve start URL for website '{self.config.website}'."
            )

        self._attach_download_listener(page)

        if self.config.require_login:
            login_usernames = self.config.login_usernames or {}
            for site in self.config.sites:
                self.instance.ui_login(
                    site=site,
                    page=page,
                    username=login_usernames.get(site),
                )

        # Fetch baseline snapshots BEFORE the agent starts mutating state.
        # Do this after login but before navigating into the app, so the
        # baseline reflects the starting state the agent will see.
        self._fetch_baselines()
        self.navigation_guard.install(page)

        info = {
            "task_id": self.config.task_id,
            "website": self.config.website,
            "sites": list(self.config.sites),
            "start_url": target_url,
            "website_urls": website_urls,
        }
        page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
        self.navigation_guard.remember_pages([page])
        return self.add_websites_urls_to_goal(), info

    def _reset_site_for_task(self, site: str, reset_site_fn) -> None:
        from webarena_pro_core import container_name_for_site
        from webarena_pro_core.website_metadata import deployed_website_url
        from webarena_pro_core.state_reset import (
            CONTAINER_BACKEND,
            reset_backend_for_site,
        )

        worker_label = self._worker_log_label()
        container_name = container_name_for_site(site)
        site_url = deployed_website_url(site)
        backend = reset_backend_for_site(site)
        target_kind = "container" if backend == CONTAINER_BACKEND else "site"

        logger.info(
            "%s: starting %s for %s (%s) at %s [task=%s]",
            worker_label,
            target_kind,
            site,
            container_name,
            site_url,
            self.config.task_id,
        )
        started_at = time.time()
        reset_site_fn(site)
        logger.info(
            "%s: %s ready for %s (%s) at %s after %.1fs [task=%s]",
            worker_label,
            target_kind,
            site,
            container_name,
            site_url,
            time.time() - started_at,
            self.config.task_id,
        )

    @staticmethod
    def _worker_log_label() -> str:
        worker_index = os.environ.get("WP_PARALLEL_WORKER_INDEX")
        runtime_slot = os.environ.get("WP_ACTIVE_RUNTIME_SLOT")
        if worker_index not in {None, ""}:
            if runtime_slot not in {None, "", worker_index}:
                return f"worker {worker_index} slot {runtime_slot}"
            return f"worker {worker_index}"

        if runtime_slot not in {None, ""}:
            return f"runtime slot {runtime_slot}"

        exp_hash = os.environ.get("WP_EXP_HASH")
        if exp_hash not in {None, "", "local"}:
            return f"worker {exp_hash}"

        return "local worker"

    def _selected_website_urls(self) -> dict[str, str]:
        return {
            site: self.instance.urls[site]
            for site in self.config.sites
            if site in self.instance.urls
        }

    def add_websites_urls_to_goal(self) -> str:
        lines = [
            self.config.intent,
            "",
            "Available websites for this task:",
        ]
        for site, url in self._selected_website_urls().items():
            lines.append(f"- {site}: {url}")
        return "\n".join(lines)

    def _attach_download_listener(self, page: pw.Page) -> None:
        """Capture browser downloads into ``self.downloads`` for the
        ``file_downloaded`` eval node. Listens on both the current page and
        any future pages spawned in the same browser context so downloads
        that open in a new tab are also caught.
        """
        def _on_download(download: Any) -> None:
            try:
                local_path = download.path()
                entry = {
                    "path": str(local_path) if local_path else "",
                    "suggested_filename": getattr(download, "suggested_filename", "") or "",
                    "url": getattr(download, "url", "") or "",
                }
                self.downloads.append(entry)
                logger.info(
                    "Captured download: %s (%s bytes)",
                    entry["suggested_filename"] or entry["path"],
                    _safe_size(entry["path"]),
                )
            except Exception:
                logger.exception("Failed to capture download event")

        try:
            page.on("download", _on_download)
            context = getattr(page, "context", None)
            if context is not None:
                context.on("page", lambda p: p.on("download", _on_download))
        except Exception:
            logger.exception("Failed to attach download listener")

    def _fetch_baselines(self) -> None:
        """Parse eval.baseline from the task config and fetch each snapshot.

        Stores results in ``self.baselines`` as ``{name: Snapshot}``. Fetch
        failures are retained in ``Snapshot.error`` so validation can report
        unavailable evidence instead of comparing against an empty collection.
        """
        eval_cfg = self.config.evaluation or {}
        baseline_specs = eval_cfg.get("baseline") or []
        if not baseline_specs:
            return

        from webarena_pro_core.eval.providers import get_provider

        site = self.config.website
        for spec in baseline_specs:
            name = spec.get("name")
            provider_name = spec.get("provider")
            params = spec.get("params") or {}
            if not name or not provider_name:
                logger.warning("Skipping malformed baseline spec: %r", spec)
                continue
            try:
                provider = get_provider(provider_name)
                snap = provider.fetch(site, params)
                self.baselines[name] = snap
                logger.info(
                    "Baseline '%s' fetched via %s: %d entries",
                    name,
                    provider_name,
                    len(snap.entries),
                )
            except Exception as exc:
                logger.exception(
                    "Failed to fetch baseline '%s' via %s; recording unavailable state",
                    name,
                    provider_name,
                )
                from webarena_pro_core.eval.snapshot import Snapshot
                self.baselines[name] = Snapshot(error=f"{type(exc).__name__}: {exc}")

    def _is_done(self, last_action: str | None) -> bool:
        return is_completion_action(last_action)

    def validate(
        self,
        page: pw.Page,
        chat_messages,
        last_step_output: Any | None = None,
        last_action: str | None = None,
        budget_exhausted: bool = False,
        budget_checkpoint: bool = False,
        termination_reason: str | None = None,
        **_: Any,
    ):
        # The environment contains navigation before collecting evidence. Keep
        # a final guard here for direct callers, without grading a stale page.
        page_context = getattr(page, "context", None)
        open_pages = getattr(page_context, "pages", None)
        if open_pages is not None:
            if any(not self.navigation_guard.is_allowed_page(p.url) for p in open_pages):
                self.navigation_guard.contain(page_context)
                return 0.0, False, "\n".join(self.navigation_guard.drain_warnings()), {
                    "dag_evaluated": False, "navigation_blocked": True,
                }

        # Parse the evaluation config for this task and run the appropriate evaluation logic.
        eval_cfg = self.config.evaluation
        if not eval_cfg:
            return 0.0, False, "", {"score": 0.0}

        if "nodes" in eval_cfg:
            # Grade live reporting cutoffs without inventing a completion
            # action or terminating the episode at an intermediate checkpoint.
            agent_done = self._is_done(last_action)
            if not agent_done and not budget_exhausted and not budget_checkpoint and not termination_reason:
                return 0.0, False, "", {"score": 0.0, "dag_evaluated": False}

            from webarena_pro_core.eval.dag import parse_eval_dag, DAGEvaluator, EvalContext

            dag = parse_eval_dag(eval_cfg)

            # Re-fetch each baseline's current state and compute the diff.
            baselines_bundle = self._compute_current_diffs()

            from webarena_pro_core.eval.ui_evidence import build_ui_evidence_plan
            from webarena_pro_core.ui_evidence.sync_api import collect_ui_evidence

            episode = (last_step_output or {}).get("episode_info") or []
            last = episode[-1] if episode else None
            step = last.get("step") if isinstance(last, dict) else getattr(last, "step", None)
            evidence = collect_ui_evidence(page, build_ui_evidence_plan(eval_cfg), step=step)
            context = EvalContext(
                ui_evidence=evidence,
                evaluation_id=evidence.evaluation_id,
                evaluation_step=evidence.step,
                evaluation_tab_id=evidence.tab_id,
                trajectory=(
                    last_step_output.get("episode_info", [])
                    if last_step_output
                    else []
                ),
                last_step_output=last_step_output,
                task_config=self.config.raw_task or {},
                baselines=baselines_bundle,
                chat_messages=list(chat_messages or []),
                downloads=list(self.downloads),
                last_action=last_action,
                task_start_date=self.task_start_date or date.today(),
                task_start_time_ms=getattr(self, "task_start_time_ms", None),
                judge_cache=self.judge_cache,
            )
            score, details = DAGEvaluator(dag).evaluate(context)
            from webarena_pro_core.eval.dag_trace import build_dag_trace

            dag_trace = build_dag_trace(eval_cfg, score=score, results=details)
            return score, agent_done or bool(termination_reason), "", {
                "score": score,
                "dag_evaluated": True,
                "evaluation_trigger": (
                    "agent_completion" if agent_done else
                    "early_termination" if termination_reason else
                    "budget_exhaustion" if budget_exhausted else "budget_checkpoint"
                ),
                **({"termination_reason": termination_reason} if termination_reason else {}),
                "dag_results": details,
                "ui_evidence": evidence.model_dump(mode="json"),
                "dag_trace": dag_trace,
            }

        eval_types = eval_cfg.get("eval_types") or []
        if isinstance(eval_types, list) and "rubric_verifier" in eval_types:
            raise ValueError("Whole-task rubric evaluation was removed; use a tiered DAG")

        # Old flat path — not yet wired up
        return 0.0, False, "", {"score": 0.0}

    def _compute_current_diffs(self) -> dict[str, dict]:
        """For each baseline captured in setup(), fetch current state + diff.

        Returns a dict suitable for ``EvalContext.baselines``:
        ``{name: {"baseline": Snapshot, "current": Snapshot, "diff": SnapshotDiff}}``.
        Unavailable snapshots produce ``diff=None`` and an explicit ``error``.
        """
        if not self.baselines:
            return {}

        from webarena_pro_core.eval.providers import get_provider
        from webarena_pro_core.eval.snapshot import Snapshot, build_snapshot_bundle

        eval_cfg = self.config.evaluation or {}
        baseline_specs = {
            s["name"]: s for s in (eval_cfg.get("baseline") or []) if "name" in s
        }
        site = self.config.website

        bundle: dict[str, dict] = {}
        for name, baseline_snap in self.baselines.items():
            spec = baseline_specs.get(name)
            if spec is None:
                continue
            try:
                provider = get_provider(spec["provider"])
                current = provider.fetch(site, spec.get("params") or {})
            except Exception as exc:
                logger.exception("Failed to fetch current state for baseline '%s'", name)
                current = Snapshot(error=f"{type(exc).__name__}: {exc}")
            bundle[name] = build_snapshot_bundle(baseline_snap, current)
            diff = bundle[name]["diff"]
            if diff is None:
                continue
            logger.info(
                "Diff '%s': +%d -%d ~%d",
                name,
                len(diff.added),
                len(diff.removed),
                len(diff.changed),
            )
        return bundle

    def cheat(self, page: pw.Page, chat_messages):
        raise NotImplementedError

    def teardown(self):
        from webarena_pro_bgym.benchmark.container_reset import (
            reset_enabled,
            stop_site,
        )

        if not reset_enabled():
            return

        try:
            for site in self.config.sites:
                stop_site(site)
        except Exception:
            logger.exception(
                "Failed to stop selected containers for task '%s' during teardown",
                self.config.task_id,
            )
