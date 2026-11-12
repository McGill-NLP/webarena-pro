"""Shared execution helpers and a compatibility entry point for tiered runs.

The public CLI and this module's entry point delegate to ``run_tiered_cli``;
there is no whole-task rubric-judge mode.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from agentlab.agents.generic_agent import GenericAgentArgs

from webarena_pro_bgym.agent_flags import FLAGS_VISION
from webarena_pro_bgym.benchmark.benchmark import WebArenaProBenchmark
from webarena_pro_bgym.benchmark.defaults import DEPLOYED_WEBSITE_URLS
from webarena_pro_bgym.llm_configs import (
    WEBARENA_PRO_CHAT_MODEL_ARGS_DICT,
)
from webarena_pro_bgym.parallel import (
    reserved_worker_environment,
    worker_environment_overrides_present,
)
from webarena_pro_bgym.study import WebArenaProStudy
from webarena_pro_bgym.utils import has_ungraded_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)
DEFAULT_AGENT_MODEL = "gemini/gemini-3.1-pro-preview"


# ---------------------------------------------------------------------------
# Per-site health checks
# ---------------------------------------------------------------------------

def _check_nextcloud(
    url: str,
    headers: dict[str, str] | None = None,
    display_url: str | None = None,
) -> bool:
    resp = requests.get(f"{url}/status.php", timeout=30, headers=headers)
    if resp.status_code != 200:
        return False
    data = resp.json()
    logger.info(
        "NextCloud reachable at %s: version=%s installed=%s",
        display_url or url,
        data.get("versionstring", "?"),
        data.get("installed", "?"),
    )
    return True


def _check_mattermost(
    url: str,
    headers: dict[str, str] | None = None,
    display_url: str | None = None,
) -> bool:
    resp = requests.get(
        f"{url}/api/v4/system/ping",
        timeout=30,
        headers=headers,
    )
    if resp.status_code != 200:
        return False
    logger.info("Mattermost reachable at %s: %s", display_url or url, resp.json())
    return True


def _check_metabase(
    url: str,
    headers: dict[str, str] | None = None,
    display_url: str | None = None,
) -> bool:
    resp = requests.get(f"{url}/api/health", timeout=30, headers=headers)
    if resp.status_code != 200:
        return False
    logger.info("Metabase reachable at %s: %s", display_url or url, resp.json())
    return True


def _generic_site_check(
    url: str,
    headers: dict[str, str] | None = None,
    display_url: str | None = None,
) -> bool:
    resp = requests.get(url, timeout=30, allow_redirects=True, headers=headers)
    if resp.status_code >= 400:
        return False
    logger.info("Site reachable: %s (%s)", display_url or url, resp.status_code)
    return True


SITE_HEALTH_CHECKS = {site: _generic_site_check for site in DEPLOYED_WEBSITE_URLS}
SITE_HEALTH_CHECKS.update(
    {
        "nextcloud": _check_nextcloud,
        "mattermost": _check_mattermost,
        "metabase": _check_metabase,
    }
)


def supported_sites() -> list[str]:
    return sorted(SITE_HEALTH_CHECKS)


def check_site_reachable(site: str) -> bool:
    url = DEPLOYED_WEBSITE_URLS.get(site)
    if not url:
        logger.error("No URL configured for site '%s'", site)
        return False
    checker = SITE_HEALTH_CHECKS.get(site)
    if not checker:
        logger.error("No health check defined for site '%s'", site)
        return False

    fallback_url = None
    fallback_headers = None
    try:
        from webarena_pro_core import (
            uses_subdomain_urls,
            web_server_bind_host,
            web_server_domain,
            web_server_port,
            website_hostname,
        )
    except ImportError:
        pass
    else:
        if uses_subdomain_urls() and web_server_domain() in {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
        }:
            proxy_host = web_server_bind_host()
            if proxy_host in {"", "0.0.0.0", "::"}:
                proxy_host = "127.0.0.1"
            port = web_server_port()
            fallback_url = f"http://{proxy_host}:{port}"
            fallback_headers = {"Host": f"{website_hostname(site)}:{port}"}

    try:
        return checker(url, display_url=url)
    except requests.RequestException as e:
        if fallback_url is None:
            logger.debug("%s not reachable at %s: %s", site, url, e)
            return False

        logger.debug(
            "%s not reachable at %s; retrying local proxy %s with Host %s: %s",
            site,
            url,
            fallback_url,
            fallback_headers.get("Host") if fallback_headers else None,
            e,
        )
        try:
            return checker(
                fallback_url,
                headers=fallback_headers,
                display_url=url,
            )
        except Exception as fallback_error:
            logger.debug(
                "%s not reachable at %s via local proxy fallback %s: %s",
                site,
                url,
                fallback_url,
                fallback_error,
            )
            return False
    except Exception as e:
        logger.debug("%s not reachable at %s: %s", site, url, e)
        return False


# ---------------------------------------------------------------------------
# Docker + container bootstrap
# ---------------------------------------------------------------------------

def ensure_docker_running(timeout: int = 120) -> bool:
    """Ensure the Docker daemon is up. On macOS, launches Docker Desktop if
    needed. Returns True once ``docker info`` succeeds."""
    try:
        import docker as docker_sdk
    except ImportError:
        logger.error("docker SDK not installed; cannot auto-start Docker")
        return False

    def _ping() -> bool:
        try:
            docker_sdk.from_env().ping()
            return True
        except Exception:
            return False

    if _ping():
        return True

    if sys.platform == "darwin":
        logger.info("Docker daemon not running — launching Docker Desktop ...")
        subprocess.run(["open", "-a", "Docker"], check=False)
    else:
        logger.error(
            "Docker daemon not running. Start it manually, then re-run."
        )
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _ping():
            logger.info("Docker daemon is up.")
            return True
        time.sleep(2)
    logger.error("Docker did not become ready within %ds", timeout)
    return False


def ensure_site_up(site: str, wait_timeout: int = 180) -> bool:
    """Ensure the container for ``site`` is running and its HTTP endpoint
    answers. Starts it via ``DockerContainerManager`` if needed."""
    if check_site_reachable(site):
        return True

    if not ensure_docker_running():
        return False

    try:
        from webarena_pro_core import (
            WEBSITES_IMAGES,
            WEBSITES_HOST_PORTS,
            active_exp_hash,
            website_published_ports,
            container_name_for_site,
            labels_for_site,
            uses_subdomain_urls,
            website_environment,
        )
        from webarena_pro_core.nginx import NginxProxyManager, docker_network_name
        from webarena_pro_core.docker import DockerContainerManager
    except ImportError as e:
        logger.error("webarena_pro_core not importable: %s", e)
        return False

    if site not in WEBSITES_IMAGES:
        logger.error("Unknown env '%s' (known: %s)", site, sorted(WEBSITES_IMAGES))
        return False

    image = WEBSITES_IMAGES[site]
    host_port = int(WEBSITES_HOST_PORTS[site])
    use_proxy = uses_subdomain_urls()
    ports = website_published_ports(site, host_port=host_port, use_proxy=use_proxy)
    container_name = container_name_for_site(site)
    proxy = NginxProxyManager() if use_proxy else None
    if proxy is not None:
        proxy.ensure_network()

    logger.info(
        "[%s] Starting container %s (%s) on ports %s ...",
        site,
        container_name,
        image,
        ports,
    )
    manager = DockerContainerManager()
    manager.ensure_container_running(
        name=container_name,
        image=image,
        environment=website_environment(site, exp_hash=active_exp_hash()),
        ports=ports,
        labels=labels_for_site(site, exp_hash=active_exp_hash()),
        network=docker_network_name() if use_proxy else None,
        log=lambda msg, _name=site: logger.info("[%s] %s", _name, msg),
    )
    if proxy is not None:
        proxy.ensure_proxy()

    deadline = time.time() + wait_timeout
    while time.time() < deadline:
        if check_site_reachable(site):
            return True
        time.sleep(3)
    logger.error("[%s] did not become reachable within %ds", site, wait_timeout)
    return False


# ---------------------------------------------------------------------------
# Dry-run: fetch baseline + current + diff without running the agent
# ---------------------------------------------------------------------------

def dry_run_eval(
    site: str, task_ids: list[int] | None, *, split: str | None = None,
    config_dir: Path | None = None,
) -> None:
    from datetime import date

    from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
    from webarena_pro_core.eval.providers import get_provider
    from webarena_pro_core.eval.snapshot import Snapshot, build_snapshot_bundle

    benchmark = WebArenaProBenchmark(sites=[site], split=split, config_dir=config_dir)
    matched = 0
    for env_args in benchmark.env_args_list:
        tc = env_args.task_config
        if tc.website != site:
            continue
        tid = int(tc.task_id)
        if task_ids and tid not in task_ids:
            continue

        eval_cfg = tc.evaluation
        if not eval_cfg or "nodes" not in eval_cfg:
            logger.info("Task %s: no DAG eval tree, skipping", tid)
            continue

        matched += 1
        logger.info("Task %s: %s", tid, tc.intent[:80])

        baselines_bundle: dict = {}
        for spec in eval_cfg.get("baseline") or []:
            name = spec.get("name")
            snapshots = []
            for phase in ("baseline", "current"):
                try:
                    provider = get_provider(spec["provider"])
                    snapshot = provider.fetch(tc.website, spec.get("params") or {})
                except Exception as exc:
                    logger.error("  %s '%s' fetch failed: %s", phase, name, exc)
                    snapshot = Snapshot(error=f"{type(exc).__name__}: {exc}")
                snapshots.append(snapshot)
            baseline, current = snapshots
            baselines_bundle[name] = build_snapshot_bundle(baseline, current)
            diff = baselines_bundle[name]["diff"]
            if diff is not None:
                logger.info(
                    "  baseline '%s': %d entries, self-diff +%d -%d ~%d",
                    name,
                    len(baseline.entries),
                    len(diff.added),
                    len(diff.removed),
                    len(diff.changed),
                )

        dag = parse_eval_dag(eval_cfg)
        context = EvalContext(
            task_config=tc.raw_task or {},
            baselines=baselines_bundle,
            task_start_date=date.today(),
            # This only inspects existing state; no task setup/execution began.
            task_start_time_ms=None,
        )
        score, details = DAGEvaluator(dag).evaluate(context)
        for node_id, node_info in details.items():
            if isinstance(node_info, dict):
                passed = node_info.get("passed", False)
                reason = node_info.get("reason", "")
            else:
                passed, reason = bool(node_info), ""
            status = "PASS" if passed else "FAIL"
            logger.info("  [%s] %s%s", status, node_id, f" — {reason}" if reason else "")
        logger.info("  Score: %.2f (dry-run, no agent)", score)
        print()

    if matched == 0:
        logger.warning("No %s tasks with DAG eval matched the filter", site)


def _build_filtered_benchmark(
    site: str,
    task_ids: list[int] | None,
    max_steps: int,
) -> tuple[WebArenaProBenchmark, list[Any]]:
    return _build_filtered_benchmark_for_sites([site], task_ids, max_steps)


def _build_filtered_benchmark_for_sites(
    sites: list[str] | str,
    task_ids: list[int] | None,
    max_steps: int,
) -> tuple[WebArenaProBenchmark, list[Any]]:
    benchmark = WebArenaProBenchmark(sites=sites)
    selected_task_ids = set(task_ids) if task_ids is not None else None
    filtered = []
    for env_args in benchmark.env_args_list:
        tc = env_args.task_config
        tid = int(tc.task_id)
        if selected_task_ids is not None and tid not in selected_task_ids:
            continue
        env_args.max_steps = max_steps
        filtered.append(env_args)

    benchmark.env_args_list = filtered
    benchmark.task_dependencies = {
        f"{benchmark.name}.{e.task_config.task_id}": [] for e in filtered
    }
    return benchmark, filtered


def selected_sites_for_env_args(env_args_list: list[Any]) -> list[str]:
    sites: set[str] = set()
    for env_args in env_args_list:
        task_config = getattr(env_args, "task_config", None)
        task_sites = getattr(task_config, "sites", None)
        if task_sites:
            sites.update(str(site) for site in task_sites)
            continue
        site = getattr(task_config, "website", None)
        if site:
            sites.add(str(site))
    return sorted(sites)


def print_eval_results(results_dir: Path, label: str) -> None:
    print("\n" + "=" * 60)
    print(f"EVAL RESULTS — {label}")
    print("=" * 60)
    rewards = []
    for exp_dir in sorted(results_dir.iterdir()):
        summary_path = exp_dir / "summary_info.json"
        if not summary_path.exists():
            continue
        with open(summary_path) as f:
            info = json.load(f)
        task_name = exp_dir.name.split("webarena-pro-bgym.")[-1]
        reward = info.get("cum_reward", 0)
        ungraded = has_ungraded_score(info)
        rewards.append(1.0 if reward >= 1.0 and not info.get("err_msg") and not ungraded else 0.0)
        status = (
            f"ERROR (score={reward:.2f})"
            if info.get("err_msg")
            else f"UNGRADED (last evaluated score={reward:.2f})"
            if ungraded
            else "PASS"
            if reward >= 1.0
            else f"PARTIAL ({reward:.2f})"
            if reward > 0
            else "FAIL"
        )
        print(f"\n  Task {task_name}: {status}  (steps={info.get('n_steps', '?')})")
        dag = info.get("dag_results")
        if dag:
            for node_id, node_info in dag.items():
                if isinstance(node_info, dict):
                    passed = node_info.get("passed", False)
                    reason = node_info.get("reason", "")
                else:
                    passed = bool(node_info)
                    reason = ""
                mark = "PASS" if passed else "FAIL"
                print(f"    [{mark}] {node_id}" + (f" — {reason}" if reason else ""))
        if info.get("err_msg"):
            print(f"    Error: {info['err_msg'][:120]}")

    n_pass = sum(1 for r in rewards if r >= 1.0)
    avg = sum(rewards) / len(rewards) if rewards else 0
    print(f"\n  Total: {n_pass}/{len(rewards)} passed, avg_reward={avg:.3f}")
    print("=" * 60)
    logger.info("Results saved to %s", results_dir)


def _build_agent(model_name: str = DEFAULT_AGENT_MODEL) -> GenericAgentArgs:
    return GenericAgentArgs(
        chat_model_args=WEBARENA_PRO_CHAT_MODEL_ARGS_DICT[model_name],
        flags=deepcopy(FLAGS_VISION),
    )


def _required_api_key_env_var(agent_model: str) -> str | None:
    if agent_model.startswith("gemini/"):
        return "GEMINI_API_KEY"
    return None


def _requested_worker_count(args: argparse.Namespace) -> int:
    explicit_parallel = getattr(args, "parallel", None)
    requested = explicit_parallel if explicit_parallel is not None else args.n_jobs
    return max(1, int(requested))


def _make_parent_parallel_study(
    site: str,
    task_ids: list[int] | None,
    max_steps: int,
    agent_model: str,
    study_dir: str | None = None,
) -> WebArenaProStudy:
    benchmark, filtered = _build_filtered_benchmark(site, task_ids, max_steps)
    if not filtered:
        raise ValueError(f"No {site} tasks matched the filter.")

    return _make_parallel_study(
        benchmark=benchmark,
        comment=f"{site}-eval",
        suffix=f"{site}-parallel",
        agent_model=agent_model,
        study_dir=study_dir,
    )


def _make_parallel_study(
    *,
    benchmark: WebArenaProBenchmark,
    comment: str,
    suffix: str,
    agent_model: str,
    study_dir: str | None = None,
) -> WebArenaProStudy:
    study = WebArenaProStudy(
        agent_args=[_build_agent(agent_model)],
        benchmark=benchmark,
        comment=comment,
        suffix=suffix,
        dir=Path(study_dir) if study_dir else None,
    )
    from webarena_pro_bgym.queue_runner import queue_directory_lock

    study.make_dir()
    with queue_directory_lock(study.dir):
        if (study.dir / "study.pkl.gz").exists() or (study.dir / "queue.jsonl").exists():
            raise ValueError(f"Study directory already contains a run: {study.dir}. Use --resume-study {study.dir}")
        study.set_reproducibility_info(strict_reproducibility=False, comment=study.comment)
        study.save()
    return study


def _all_site_task_ids(site: str) -> list[int]:
    return _all_task_ids([site])


def _all_task_ids(sites: list[str] | str) -> list[int]:
    benchmark = WebArenaProBenchmark(sites=sites)
    return sorted(int(env_args.task_config.task_id) for env_args in benchmark.env_args_list)


def _task_sites_for_env_args(env_args: Any, default_site: str | None = None) -> list[str]:
    task_config = getattr(env_args, "task_config", None)
    if task_config is None:
        return [default_site] if default_site else []

    task_sites = getattr(task_config, "sites", None)
    if task_sites:
        return [str(site) for site in task_sites]

    website = getattr(task_config, "website", None) or default_site
    return [str(website)] if website else []


def current_attempt_summary_paths(directory: Path) -> list[Path]:
    """Select latest summaries, respecting the queue's current attempt owner.

    A retry may move to another worker, leaving the earlier error on disk for
    inspection. That historical result must not win over the current attempt
    or count as a second task in reports.
    """
    directory = Path(directory)
    queue_path = directory / "queue.jsonl"
    current = None
    if queue_path.exists():
        from webarena_pro_bgym.task_queue import TaskQueue

        current = {row["task_id"]: row for row in TaskQueue.load(queue_path).status()}
    selected: dict[str, Path] = {}
    candidates = sorted(directory.glob("**/summary_info.json"),
                        key=lambda path: (path.stat().st_mtime_ns, str(path)), reverse=True)
    for summary_path in candidates:
        exp_dir = summary_path.parent
        parts = exp_dir.relative_to(directory).parts
        if any(part.startswith(("_", ".")) for part in parts):
            continue
        if "webarena-pro-bgym." not in exp_dir.name:
            continue
        task_name = exp_dir.name.split("webarena-pro-bgym.")[-1]
        result_key = task_name
        if current is not None:
            try:
                task_id = int(task_name.split("_", 1)[0])
            except ValueError:
                continue
            row = current.get(task_id)
            if (row is None or row["worker_id"] is None or len(parts) < 3
                    or parts[0] != "workers" or parts[1] != row["worker_id"]):
                continue
            result_key = str(task_id)
        selected.setdefault(result_key, summary_path)
    return list(selected.values())


def aggregate_parallel_results(
    site: str,
    root_dir: Path | None = None,
    since: float | None = None,
) -> tuple[int, int]:
    """Collect per-task summaries from worker study dirs."""
    from agentlab.experiments.exp_utils import RESULTS_DIR

    if root_dir is not None:
        recent_dirs = [Path(root_dir)]
    else:
        results_root = Path(RESULTS_DIR)
        if not results_root.exists():
            logger.warning("No results directory found at %s", results_root)
            return 0, 0
        cutoff = since if since is not None else time.time() - 2 * 3600
        site_marker = f"-{site}-"
        recent_dirs = [
            directory
            for directory in results_root.iterdir()
            if directory.is_dir()
            and directory.stat().st_mtime >= cutoff
            and site_marker in directory.name
        ]
        recent_dirs.sort(key=lambda directory: directory.stat().st_mtime, reverse=True)

    all_results: list[tuple[str, dict]] = []
    seen_tasks: set[str] = set()
    for directory in recent_dirs:
        for summary_path in current_attempt_summary_paths(directory):
            exp_dir = summary_path.parent
            task_id = exp_dir.name.split("webarena-pro-bgym.")[-1]
            if task_id in seen_tasks:
                continue
            with summary_path.open(encoding="utf-8") as handle:
                summary = json.load(handle)
            all_results.append((task_id, summary))
            seen_tasks.add(task_id)

    print("\n" + "=" * 60)
    print(f"EVAL RESULTS (parallel) — {site}")
    print("=" * 60)
    rewards = []
    for task_id, summary in sorted(all_results, key=lambda item: item[0]):
        reward = summary.get("cum_reward", 0)
        ungraded = has_ungraded_score(summary)
        rewards.append(1.0 if reward >= 1.0 and not summary.get("err_msg") and not ungraded else 0.0)
        n_steps = summary.get("n_steps", "?")
        status = (
            f"ERROR (score={reward:.2f})"
            if summary.get("err_msg")
            else f"UNGRADED (last evaluated score={reward:.2f})"
            if ungraded
            else "PASS"
            if reward >= 1.0
            else f"PARTIAL ({reward:.2f})"
            if reward > 0
            else "FAIL"
        )
        print(f"\n  Task {task_id}: {status}  (steps={n_steps})")
        dag = summary.get("dag_results")
        if dag:
            for node_id, node_info in dag.items():
                if isinstance(node_info, dict):
                    passed = node_info.get("passed", False)
                    reason = node_info.get("reason", "")
                else:
                    passed, reason = bool(node_info), ""
                mark = "PASS" if passed else "FAIL"
                print(f"    [{mark}] {node_id}" + (f" — {reason}" if reason else ""))
        if summary.get("err_msg"):
            print(f"    Error: {summary['err_msg'][:120]}")

    n_pass = sum(1 for reward in rewards if reward >= 1.0)
    avg_reward = sum(rewards) / len(rewards) if rewards else 0
    print(f"\n  Total: {n_pass}/{len(rewards)} passed, avg_reward={avg_reward:.3f}")
    print("=" * 60)
    return n_pass, len(rewards)


def _run_parallel_compat(args: argparse.Namespace, task_ids: list[int] | None, site: str | None) -> int:
    from webarena_pro_bgym.run_tiered_cli import main as tiered_main

    argv = ["--n-jobs", str(_requested_worker_count(args)),
            "--max-steps", str(args.max_steps if args.max_steps is not None else 50),
            "--n-relaunch", str(args.n_relaunch), "--agent-model", args.agent_model]
    argv.extend(["--site", site] if site else ["--all"])
    if task_ids is not None:
        argv.extend(["--task", ",".join(str(task_id) for task_id in task_ids)])
    for flag, value in (("--study-dir", args.study_dir),
                        ("--split", getattr(args, "split", None)),
                        ("--config-dir", getattr(args, "config_dir", None))):
        if value is not None:
            argv.extend([flag, str(value)])
    for flag in ("dry_run", "verbose", "skip_preflight", "no_autostart"):
        if getattr(args, flag, False):
            argv.append("--" + flag.replace("_", "-"))
    return tiered_main(argv)


def run_parallel(site: str, args: argparse.Namespace, task_ids: list[int] | None) -> int:
    """Compatibility helper; parallel runs use the tiered shared queue."""
    return _run_parallel_compat(args, task_ids, site)


def run_parallel_all(args: argparse.Namespace, task_ids: list[int] | None) -> int:
    """Compatibility helper; parallel runs use the tiered shared queue."""
    return _run_parallel_compat(args, task_ids, None)


def run_agent(
    site: str,
    task_ids: list[int] | None,
    max_steps: int,
    n_jobs: int = 1,
    n_relaunch: int = 1,
    study_dir: str | None = None,
    agent_model: str = DEFAULT_AGENT_MODEL,
) -> None:
    required_env = _required_api_key_env_var(agent_model)
    if required_env and not os.environ.get(required_env):
        logger.error("%s not set. Add it to .env or export it.", required_env)
        sys.exit(1)

    benchmark, filtered = _build_filtered_benchmark(site, task_ids, max_steps)
    if not filtered:
        logger.error("No %s tasks matched the filter.", site)
        sys.exit(1)

    logger.info(
        "Running %d %s task(s): %s",
        len(filtered),
        site,
        [e.task_config.task_id for e in filtered],
    )

    agent = _build_agent(agent_model)

    study = WebArenaProStudy(
        agent_args=[agent],
        benchmark=benchmark,
        comment=f"{site}-eval",
        suffix=f"{site}-eval",
        dir=Path(study_dir) if study_dir else None,
    )
    study.run(
        n_jobs=1,
        parallel_backend="sequential",
        n_relaunch=n_relaunch,
    )
    print_eval_results(study.dir, site)


def run_agent_all(
    task_ids: list[int] | None,
    max_steps: int,
    n_jobs: int = 1,
    n_relaunch: int = 1,
    study_dir: str | None = None,
    agent_model: str = DEFAULT_AGENT_MODEL,
) -> None:
    required_env = _required_api_key_env_var(agent_model)
    if required_env and not os.environ.get(required_env):
        logger.error("%s not set. Add it to .env or export it.", required_env)
        sys.exit(1)

    benchmark, filtered = _build_filtered_benchmark_for_sites("all", task_ids, max_steps)
    if not filtered:
        logger.error("No tasks matched the filter.")
        sys.exit(1)

    logger.info(
        "Running %d task(s) across all sites: %s",
        len(filtered),
        [e.task_config.task_id for e in filtered],
    )

    study = WebArenaProStudy(
        agent_args=[_build_agent(agent_model)],
        benchmark=benchmark,
        comment="all-eval",
        suffix="all-eval",
        dir=Path(study_dir) if study_dir else None,
    )
    study.run(
        n_jobs=1,
        parallel_backend="sequential",
        n_relaunch=n_relaunch,
    )
    print_eval_results(study.dir, "all")


def study_sites(study: WebArenaProStudy) -> list[str]:
    sites = set()
    for exp_args in study.exp_args_list:
        env_args = getattr(exp_args, "env_args", None)
        task_config = getattr(env_args, "task_config", None)
        task_sites = getattr(task_config, "sites", None)
        if task_sites:
            sites.update(str(site) for site in task_sites)
            continue
        site = getattr(task_config, "website", None)
        if site:
            sites.add(site)
    return sorted(sites)


def override_study_max_steps(study: WebArenaProStudy, max_steps: int) -> None:
    for exp_args in study.exp_args_list:
        env_args = getattr(exp_args, "env_args", None)
        if env_args is not None:
            env_args.max_steps = max_steps


def resume_study(
    study: WebArenaProStudy,
    max_steps: int | None,
    n_jobs: int,
    n_relaunch: int,
    relaunch_errors: bool,
) -> None:
    n_incomplete, n_error = study.find_incomplete(include_errors=relaunch_errors)
    logger.info(
        "Loaded study %s with %d relaunch candidate(s), %d errored.",
        study.dir,
        n_incomplete,
        n_error,
    )

    if max_steps is not None:
        logger.info("Overriding max_steps to %d for resumed experiments.", max_steps)
        override_study_max_steps(study, max_steps)

    if n_incomplete == 0:
        logger.info("No experiments need relaunch in %s.", study.dir)
    else:
        study.run(
            n_jobs=1,
            parallel_backend="sequential",
            n_relaunch=n_relaunch,
            relaunch_errors=relaunch_errors,
        )

    label = ", ".join(study_sites(study)) or study.name
    print_eval_results(study.dir, label)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _per_task_reset_prepares_sites(args: argparse.Namespace) -> bool:
    if getattr(args, "dry_run", False):
        return False
    from webarena_pro_bgym.benchmark.container_reset import reset_enabled

    return reset_enabled()


def _ensure_one_site_ready(site: str, args: argparse.Namespace) -> bool:
    if args.no_autostart:
        if not check_site_reachable(site):
            logger.error(
                "%s not reachable. Start it first: "
                "cd ../webarena-pro-core && uv run webarena-pro env start %s",
                site,
                site,
            )
            return False
    else:
        if not ensure_site_up(site):
            logger.error("Failed to bring up %s", site)
            return False
    return True


def ensure_sites_ready(sites: list[str], args: argparse.Namespace) -> bool:
    if args.skip_preflight:
        return True

    target_sites = list(dict.fromkeys(sites))
    if _per_task_reset_prepares_sites(args):
        logger.info(
            "Skipping site preflight for %s; per-task environment reset will "
            "prepare containers.",
            ", ".join(target_sites),
        )
        return True

    if not target_sites:
        return True

    return all(_ensure_one_site_ready(site, args) for site in target_sites)


def _selected_sites_for_isolated_run(
    args: argparse.Namespace,
    task_ids: list[int] | None,
) -> list[str]:
    if args.all:
        if task_ids is not None:
            max_steps = args.max_steps if args.max_steps is not None else 50
            _, filtered = _build_filtered_benchmark_for_sites("all", task_ids, max_steps)
            return selected_sites_for_env_args(filtered)
        return supported_sites()

    if not args.site:
        return []

    max_steps = args.max_steps if args.max_steps is not None else 50
    _, filtered = _build_filtered_benchmark(args.site, task_ids, max_steps)
    if not filtered:
        return [args.site]
    return selected_sites_for_env_args(filtered)


def _maybe_delegate_to_isolated_worker(
    argv: list[str],
    args: argparse.Namespace,
    task_ids: list[int] | None,
) -> int | None:
    if getattr(args, "global_worker", False):
        return None
    if _requested_worker_count(args) > 1:
        return None
    if args.dry_run:
        return None

    selected_sites = _selected_sites_for_isolated_run(args, task_ids)
    if not selected_sites:
        return None

    if worker_environment_overrides_present(sites=selected_sites, env=os.environ):
        return None

    cmd = [sys.executable, str(Path(__file__).resolve()), *argv]
    with reserved_worker_environment(
        sites=selected_sites,
        base_env=os.environ,
        force_reset_per_task=False,
        set_parallel_worker_index=False,
    ) as (slot, env):
        logger.info(
            "Delegating run into isolated worker slot w%d for sites %s",
            slot.worker_index,
            selected_sites,
        )
        env["WP_ASSIGNED_RUN_SLOT"] = str(slot.worker_index)
        result = subprocess.run(cmd, env=env, check=False)
    return int(result.returncode)


def _run_one_site(site: str, args: argparse.Namespace, task_ids: list[int] | None) -> int:
    logger.info("=" * 60)
    logger.info("Running eval for site: %s", site)
    logger.info("=" * 60)

    if _requested_worker_count(args) > 1:
        if os.environ.get("WP_PARALLEL_WORKER_INDEX") is not None:
            logger.error("Refusing to spawn nested parallel workers.")
            return 2
        return run_parallel(site, args, task_ids)

    max_steps = args.max_steps if args.max_steps is not None else 50
    _, filtered = _build_filtered_benchmark(site, task_ids, max_steps)
    selected_sites = selected_sites_for_env_args(filtered)
    if not filtered:
        logger.error("No %s tasks matched the filter.", site)
        return 1

    if not ensure_sites_ready(selected_sites, args):
        return 1

    try:
        if args.dry_run:
            dry_run_eval(site, task_ids)
        else:
            run_agent(
                site,
                task_ids,
                max_steps,
                args.n_jobs,
                args.n_relaunch,
                study_dir=args.study_dir,
                agent_model=args.agent_model,
            )
    except SystemExit as e:
        return int(e.code or 0)
    except Exception:
        logger.exception("Eval for %s crashed", site)
        return 1
    return 0


def _resume_existing_study(args: argparse.Namespace) -> int:
    study_dir = Path(args.resume_study).expanduser()
    try:
        study = WebArenaProStudy.load(study_dir)
    except Exception:
        logger.exception("Failed to load study from %s", study_dir)
        return 1

    for experiment in study.exp_args_list:
        evaluation = getattr(experiment.env_args.task_config, "evaluation", None)
        if not isinstance(evaluation, dict) or not isinstance(evaluation.get("nodes"), list):
            logger.error("Only tiered studies can be resumed; this study contains a non-DAG task.")
            return 1

    if not getattr(args, "retry_from_start", False):
        logger.error(
            "Study %s has no queue checkpoints and cannot continue saved agent work safely. "
            "Use --resume-study %s --retry-from-start to migrate incomplete/errored tasks "
            "to a supervised queue with new agent calls. Add --incomplete-only to skip errors.",
            study_dir, study_dir,
        )
        return 1

    try:
        from webarena_pro_bgym.legacy_recovery import resume_legacy_study

        return resume_legacy_study(study, args)
    except SystemExit as e:
        return int(e.code or 0)
    except Exception:
        logger.exception("Resume failed for %s", study.dir)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Compatibility entry point: all new runs use tiered evaluation."""
    from webarena_pro_bgym.run_tiered_cli import main as tiered_main

    return tiered_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
