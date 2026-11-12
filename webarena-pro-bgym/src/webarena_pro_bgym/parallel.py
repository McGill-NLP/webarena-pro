from __future__ import annotations

import fcntl
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable, Mapping

from webarena_pro_core import (
    EXP_HASH_ENV_VAR,
    WEBSITES_ADDITIONAL_HOST_PORT_ENV_VARS,
    WEBSITES_ADDITIONAL_PORTS,
    WEBSITES_HOST_PORTS,
    URL_MODE_ENV_VAR,
    build_website_url,
    site_env_var_key,
)


_AUTO_WORKER_SLOT_ROOT = Path(tempfile.gettempdir()) / "webarena-pro-bgym-worker-slots"
RESET_BACKEND_ENV_VAR = "WP_RESET_BACKEND"
CONTAINER_RESET_BACKEND = "container"
ACTIVE_RUNTIME_SLOT_ENV_VAR = "WP_ACTIVE_RUNTIME_SLOT"


def site_exp_hash_env_var(site: str) -> str:
    return f"WP_{site_env_var_key(site)}_EXP_HASH"


@dataclass
class ReservedWorkerSlot:
    worker_index: int
    claimed_dirs: tuple[Path, ...]

    def release(self) -> None:
        for claimed_dir in reversed(self.claimed_dirs):
            shutil.rmtree(claimed_dir, ignore_errors=True)


def split_task_ids(task_ids: list[int], worker_count: int) -> list[list[int]]:
    """Round-robin split task ids across worker subprocesses."""
    if worker_count <= 0:
        raise ValueError("worker_count must be positive")

    groups: list[list[int]] = [[] for _ in range(worker_count)]
    for index, task_id in enumerate(task_ids):
        groups[index % worker_count].append(task_id)
    return [group for group in groups if group]


def build_worker_environment(
    *,
    sites: Iterable[str],
    worker_index: int,
    base_env: Mapping[str, str] | None = None,
    force_reset_per_task: bool = True,
    reset_backend: str | None = CONTAINER_RESET_BACKEND,
    set_parallel_worker_index: bool = True,
) -> dict[str, str]:
    """Build process env for one parallel worker's selected websites."""
    source_env = os.environ if base_env is None else base_env
    env = dict(source_env)

    target_sites = list(dict.fromkeys(sites))
    if not target_sites:
        raise ValueError("sites must contain at least one website")

    worker_hash = f"w{worker_index}"
    env[EXP_HASH_ENV_VAR] = worker_hash

    for target_site in target_sites:
        site_token = site_env_var_key(target_site)
        base_host_port = int(WEBSITES_HOST_PORTS[target_site])
        worker_host_port = base_host_port + int(worker_index)
        port_offset = worker_host_port - base_host_port

        env[f"WP_{site_token}_HOST_PORT"] = str(worker_host_port)
        env[f"WP_{site_token}_URL"] = build_website_url(
            target_site,
            exp_hash=worker_hash,
            mode=env.get(URL_MODE_ENV_VAR),
            host_port=worker_host_port,
        )
        env[f"WP_{site_token}_CONTAINER_NAME"] = f"{target_site}-w{worker_index}"
        env[site_exp_hash_env_var(target_site)] = worker_hash

        for container_port, env_var in WEBSITES_ADDITIONAL_HOST_PORT_ENV_VARS.get(
            target_site, {}
        ).items():
            base_port = int(source_env.get(
                env_var, WEBSITES_ADDITIONAL_PORTS[target_site][container_port]
            ))
            env[env_var] = str(base_port + port_offset)

    if force_reset_per_task or "WP_RESET_CONTAINER_PER_TASK" not in env:
        env["WP_RESET_CONTAINER_PER_TASK"] = "1"
    if reset_backend is not None:
        env[RESET_BACKEND_ENV_VAR] = reset_backend
    if set_parallel_worker_index:
        env["WP_PARALLEL_WORKER_INDEX"] = str(worker_index)

    return env


def reassign_worker_environment(
    *,
    sites: Iterable[str],
    from_worker_index: int,
    to_worker_index: int,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Move an existing worker environment to another isolated runtime slot.

    ``build_worker_environment`` starts from the package's import-time base
    ports.  A worker subprocess has already imported those values with its
    assigned offsets, so rebuilding there would apply the offset twice.  This
    helper instead shifts the active worker's explicit ports by the slot delta.
    """
    source_env = os.environ if base_env is None else base_env
    env = dict(source_env)
    target_sites = list(dict.fromkeys(str(site) for site in sites))
    if not target_sites:
        raise ValueError("sites must contain at least one website")

    slot_delta = int(to_worker_index) - int(from_worker_index)
    worker_hash = f"w{to_worker_index}"
    env[EXP_HASH_ENV_VAR] = worker_hash
    env[ACTIVE_RUNTIME_SLOT_ENV_VAR] = str(to_worker_index)

    for target_site in target_sites:
        site_token = site_env_var_key(target_site)
        host_port_key = f"WP_{site_token}_HOST_PORT"
        current_host_port = int(
            env.get(host_port_key, WEBSITES_HOST_PORTS[target_site])
        )
        target_host_port = current_host_port + slot_delta

        env[host_port_key] = str(target_host_port)
        env[f"WP_{site_token}_URL"] = build_website_url(
            target_site,
            exp_hash=worker_hash,
            mode=env.get(URL_MODE_ENV_VAR),
            host_port=target_host_port,
        )
        env[f"WP_{site_token}_CONTAINER_NAME"] = (
            f"{target_site}-w{to_worker_index}"
        )
        env[site_exp_hash_env_var(target_site)] = worker_hash

        for container_port, env_var in (
            WEBSITES_ADDITIONAL_HOST_PORT_ENV_VARS.get(target_site, {}).items()
        ):
            current_additional_port = int(
                source_env.get(
                    env_var,
                    WEBSITES_ADDITIONAL_PORTS[target_site][container_port],
                )
            )
            env[env_var] = str(current_additional_port + slot_delta)

    return env


def activate_worker_environment(
    *,
    sites: Iterable[str],
    env: Mapping[str, str],
) -> None:
    """Activate one runtime slot's URL/container overrides in this process."""
    keys = {EXP_HASH_ENV_VAR, ACTIVE_RUNTIME_SLOT_ENV_VAR}
    for target_site in dict.fromkeys(str(site) for site in sites):
        site_token = site_env_var_key(target_site)
        keys.update(
            {
                f"WP_{site_token}_HOST_PORT",
                f"WP_{site_token}_URL",
                f"WP_{site_token}_CONTAINER_NAME",
                site_exp_hash_env_var(target_site),
            }
        )
        keys.update(
            WEBSITES_ADDITIONAL_HOST_PORT_ENV_VARS.get(target_site, {}).values()
        )

    for key in keys:
        value = env.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = str(value)

    # Snapshot providers and other legacy consumers retain references to these
    # shared maps. Refresh them in place at task boundaries (and on restore),
    # after all slot overrides have been applied. Prewarming runs separately
    # with its own subprocess environment and must not activate the standby here.
    from webarena_pro_core.website_metadata import deployed_website_login_urls, deployed_website_urls
    from webarena_pro_core.task import (
        DEPLOYED_WEBSITE_LOGIN_URLS,
        DEPLOYED_WEBSITE_URLS,
    )

    DEPLOYED_WEBSITE_URLS.clear()
    DEPLOYED_WEBSITE_URLS.update(deployed_website_urls())
    DEPLOYED_WEBSITE_LOGIN_URLS.clear()
    DEPLOYED_WEBSITE_LOGIN_URLS.update(deployed_website_login_urls())


def worker_environment_overrides_present(
    *,
    sites: Iterable[str],
    env: Mapping[str, str] | None = None,
) -> bool:
    target_env = os.environ if env is None else env
    if "WP_PARALLEL_WORKER_INDEX" in target_env:
        return True

    for site in dict.fromkeys(sites):
        site_token = site_env_var_key(str(site))
        if (
            f"WP_{site_token}_HOST_PORT" in target_env
            or f"WP_{site_token}_URL" in target_env
            or f"WP_{site_token}_CONTAINER_NAME" in target_env
        ):
            return True

    return False


def reserve_worker_slot(
    *,
    sites: Iterable[str],
    max_workers: int = 32,
    lock_root: str | os.PathLike[str] | None = None,
    worker_index: int | None = None,
) -> ReservedWorkerSlot:
    target_sites = [str(site) for site in dict.fromkeys(sites)]
    if not target_sites:
        raise ValueError("sites must contain at least one website")
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")
    if worker_index is not None and (type(worker_index) is not int or worker_index < 0):
        raise ValueError("worker_index must be a nonnegative integer")

    slot_root = Path(lock_root) if lock_root is not None else _AUTO_WORKER_SLOT_ROOT
    slot_root.mkdir(parents=True, exist_ok=True)
    allocator_lock_path = slot_root / ".allocator.lock"

    with allocator_lock_path.open("a+", encoding="utf-8") as allocator_lock:
        fcntl.flock(allocator_lock.fileno(), fcntl.LOCK_EX)
        candidates = range(max_workers) if worker_index is None else [worker_index]
        for candidate_index in candidates:
            claimed_dirs: list[Path] = []
            for site in target_sites:
                claimed_dir = slot_root / site / f"w{candidate_index}"
                if not _claim_worker_dir(claimed_dir):
                    for stale_dir in reversed(claimed_dirs):
                        shutil.rmtree(stale_dir, ignore_errors=True)
                    claimed_dirs.clear()
                    break
                claimed_dirs.append(claimed_dir)
            if claimed_dirs:
                return ReservedWorkerSlot(
                    worker_index=candidate_index,
                    claimed_dirs=tuple(claimed_dirs),
                )

    site_label = ", ".join(target_sites)
    unavailable = (f"All {max_workers} slots are currently in use." if worker_index is None
                   else f"Requested slot {worker_index} is currently in use.")
    raise RuntimeError(
        f"Could not reserve an isolated worker slot for site(s) {site_label}. "
        f"{unavailable}"
    )


@contextmanager
def reserved_worker_environment(
    *,
    sites: Iterable[str],
    base_env: Mapping[str, str] | None = None,
    max_workers: int = 32,
    force_reset_per_task: bool = True,
    reset_backend: str | None = CONTAINER_RESET_BACKEND,
    set_parallel_worker_index: bool = True,
):
    slot = reserve_worker_slot(sites=sites, max_workers=max_workers)
    try:
        env = build_worker_environment(
            sites=sites,
            worker_index=slot.worker_index,
            base_env=base_env,
            force_reset_per_task=force_reset_per_task,
            reset_backend=reset_backend,
            set_parallel_worker_index=set_parallel_worker_index,
        )
        yield slot, env
    finally:
        slot.release()


def _claim_worker_dir(claimed_dir: Path) -> bool:
    owner_file = claimed_dir / "owner.pid"
    for _ in range(2):
        try:
            claimed_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            owner_pid = _read_owner_pid(owner_file)
            if owner_pid is not None and _pid_is_running(owner_pid):
                return False
            shutil.rmtree(claimed_dir, ignore_errors=True)
            continue

        owner_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
        return True

    return False


def _read_owner_pid(owner_file: Path) -> int | None:
    try:
        return int(owner_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
