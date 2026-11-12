import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import requests

from webarena_pro_bgym.study import _SequentialContainerPipeline
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext
from webarena_pro_core.eval.providers.ocs_users import OCSUsersProvider
from webarena_pro_core.task import (
    DEPLOYED_WEBSITE_LOGIN_URLS,
    DEPLOYED_WEBSITE_URLS,
    WebArenaProTaskConfig,
)


def test_browser_backend_and_snapshots_follow_prewarm_transitions(monkeypatch):
    """A standby returning 503 must never receive a task's HTTP probes."""
    active_slot = 0
    requests_seen = []
    prewarmed = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            slot = self.server.slot
            requests_seen.append((slot, self.path))
            payload = {"slot": slot, "ocs": {"meta": {"status": "ok", "statuscode": 100},
                                              "data": {"users": [f"slot-{slot}"]}}}
            self.send_response(200 if slot == active_slot else 503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *args):
            pass

    servers = [ThreadingHTTPServer(("127.0.0.1", 0), Handler) for _ in range(2)]
    threads = []
    for slot, server in enumerate(servers):
        server.slot = slot
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        threads.append(thread)
    urls = [f"http://127.0.0.1:{server.server_port}" for server in servers]
    real_request = requests.Session.request

    def isolated_request(session, method, url, **kwargs):
        assert any(url == base or url.startswith(f"{base}/") for base in urls), url
        return real_request(session, method, url, **kwargs)

    monkeypatch.setattr(requests.Session, "request", isolated_request)
    cached_urls = dict(DEPLOYED_WEBSITE_URLS)
    cached_logins = dict(DEPLOYED_WEBSITE_LOGIN_URLS)
    original_env = dict(os.environ)
    # Register the pipeline's environment mutations for pytest cleanup too.
    for key in ("WP_EXP_HASH", "WP_ACTIVE_RUNTIME_SLOT", "WP_NEXTCLOUD_URL",
                "WP_NEXTCLOUD_HOST_PORT", "WP_NEXTCLOUD_CONTAINER_NAME", "WP_NEXTCLOUD_EXP_HASH"):
        monkeypatch.delenv(key, raising=False)

    class Job:
        def wait(self):
            return True

        def cancel(self):
            pass

    def launch(**kwargs):
        # Real prewarming passes a separate env to Popen; the active process
        # must continue to use its current environment while standby resets.
        assert kwargs["runtime_slot"] != active_slot
        assert kwargs["env"]["WP_NEXTCLOUD_URL"] == urls[1 - active_slot]
        prewarmed.append(kwargs["runtime_slot"])
        return Job()

    monkeypatch.setattr("webarena_pro_bgym.prewarm.launch_container_prewarm", launch)
    monkeypatch.setattr("webarena_pro_bgym.prewarm.cleanup_runtime_containers", lambda **kwargs: None)
    environments = [
        {"WP_EXP_HASH": f"w{slot}", "WP_ACTIVE_RUNTIME_SLOT": str(slot),
         "WP_NEXTCLOUD_URL": urls[slot]}
        for slot in range(2)
    ]
    raw_tasks = [
        {"task_id": str(index), "intent": "check active slot", "sites": ["nextcloud"]}
        for index in range(4)
    ]
    pipeline = _SequentialContainerPipeline(
        exp_args_list=[SimpleNamespace(env_args=SimpleNamespace(
            task_name=f"webarena-pro-bgym.{raw['task_id']}",
            task_config=SimpleNamespace(task_id=raw["task_id"], sites=("nextcloud",)),
        )) for raw in raw_tasks],
        sites=("nextcloud",), base_slot_index=0, base_slot=None,
        standby_slot=SimpleNamespace(worker_index=1, release=lambda: None),
        base_env=environments[0], standby_env=environments[1], restore_env=original_env,
    )
    evaluator = BackendStateEvaluator()
    provider = OCSUsersProvider()
    try:
        for index, raw in enumerate(raw_tasks):
            active_slot = index % 2
            pipeline.before_task(index)
            config = WebArenaProTaskConfig.from_raw_task(raw, container_name="test")
            assert config.start_url == urls[active_slot]
            assert requests.get(config.start_url, timeout=5).json()["slot"] == active_slot
            result = evaluator.evaluate(
                {"url": "__NEXTCLOUD__/state", "checks": [
                    {"type": "status_code", "expected": 200},
                    {"type": "json_path", "path": "slot", "value": active_slot},
                ]}, EvalContext(task_config=raw),
            )
            assert result.passed and not result.inconclusive, result.reason
            assert f"GET {urls[active_slot]}/state" in result.reason
            assert set(provider.fetch("nextcloud", {}).entries) == {f"slot-{active_slot}"}
            assert [slot for slot, _ in requests_seen[-3:]] == [active_slot] * 3
            pipeline.after_task(index)
        assert prewarmed == [1, 0, 1]
    finally:
        try:
            pipeline.close()
            from webarena_pro_core.website_metadata import deployed_website_urls
            restored_urls_match = DEPLOYED_WEBSITE_URLS == deployed_website_urls()
        finally:
            DEPLOYED_WEBSITE_URLS.clear()
            DEPLOYED_WEBSITE_URLS.update(cached_urls)
            DEPLOYED_WEBSITE_LOGIN_URLS.clear()
            DEPLOYED_WEBSITE_LOGIN_URLS.update(cached_logins)
            for server, thread in zip(servers, threads):
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
    assert restored_urls_match
