"""Check Docker's available trial-network capacity before dispatching agents."""

from __future__ import annotations

import math
import re
import subprocess
import time
import uuid


def preflight_networks(concurrency=1, timeout=120):
    """Temporarily allocate both networks for each concurrent trial, then release.

    This is a point-in-time allocation probe, not a reservation or a scheduler.
    The active Docker context must be the one Harbor will use.
    """
    if type(concurrency) is not int or not 1 <= concurrency <= 1024:
        raise ValueError("concurrency must be an integer between 1 and 1024")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    count = 2 * concurrency
    deadline = time.monotonic() + timeout
    run_id = uuid.uuid4().hex
    allocated = []
    failure = None
    uncertain = None
    try:
        for index in range(count):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Network allocation preflight timed out")
            name = f"wp-preflight-{run_id}-{index}"
            command = [
                "docker", "network", "create", "--driver", "bridge",
                "--label", f"webarena-pro.preflight={run_id}",
            ]
            if index % 2:
                command.append("--internal")
            try:
                result = subprocess.run(
                    [*command, name], check=True, capture_output=True, text=True,
                    timeout=min(30, remaining),
                )
            except subprocess.TimeoutExpired as exc:
                # A request may have reached the daemon. Without its returned ID
                # we cannot safely claim ownership and remove a network by name.
                uncertain = name
                raise RuntimeError(f"Docker network creation timed out for {name}") from exc
            except (KeyboardInterrupt, SystemExit):
                uncertain = name
                raise
            except subprocess.CalledProcessError as exc:
                reason = (exc.stderr or exc.stdout or "Docker network creation failed").strip()
                raise RuntimeError(reason[-1000:]) from exc
            network_id = result.stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{64}", network_id):
                uncertain = name
                raise RuntimeError(f"Docker returned no valid network ID for {name}")
            allocated.append(network_id)
    except BaseException as exc:
        failure = exc
    finally:
        # Never prune, remove existing study networks, or guess names. Cleanup
        # has its own bounded budget even when allocation exhausted its deadline.
        cleanup_deadline = time.monotonic() + 30
        leftovers = []
        for network_id in reversed(allocated):
            remaining = cleanup_deadline - time.monotonic()
            try:
                if remaining <= 0:
                    raise RuntimeError("cleanup timed out")
                subprocess.run(
                    ["docker", "network", "rm", network_id], check=True,
                    capture_output=True, text=True, timeout=min(10, remaining),
                )
            except (OSError, RuntimeError, subprocess.SubprocessError):
                leftovers.append(network_id)

    detail = ""
    if uncertain:
        detail += f" Inspect possible unfinished probe {uncertain} before removing it."
    if leftovers:
        detail += " Could not remove these probe network IDs: " + ", ".join(leftovers) + "."
    if failure is not None or leftovers:
        message = (
            f"Docker network preflight failed ({len(allocated)}/{count} networks allocated "
            f"for {concurrency} concurrent trials). "
            + (str(failure) if failure else "Probe cleanup failed.")
            + detail
            + " Do not start the study. Verify the Docker context/daemon; reduce concurrency "
            "or arrange non-overlapping Docker address pools with the host administrator "
            "and rerun this check. Do not prune networks belonging to other studies."
        )
        if isinstance(failure, (KeyboardInterrupt, SystemExit)):
            failure.add_note(message)
            raise failure
        raise RuntimeError(message) from failure
    return {"concurrency": concurrency, "networks": count, "reserved": False}
