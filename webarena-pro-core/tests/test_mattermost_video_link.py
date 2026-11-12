"""Task 112 links must use YT-lite's /watch/<video_id> route."""
import json
from pathlib import Path

import pytest
import requests

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag

CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config/mattermost.raw.json"
TASK = next(task for task in json.loads(CONFIG.read_text()) if task["task_id"] == "112")
NODE = TASK["eval"]["nodes"][1]


def response(payload):
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps(payload).encode()
    return result


@pytest.fixture(autouse=True)
def video_origin(monkeypatch):
    monkeypatch.setenv("WP_YT_LITE_URL", "http://yt-lite.localhost")


def matches(message):
    text_check = NODE["eval_config"]["strategies"][0]["config"]["checks"][0]["text"]
    return BackendStateEvaluator()._run_check({
        "type": "json_collection_contains", "path": "posts", "text": text_check,
    }, response({"posts": [{"message": message}]}))[0]


@pytest.mark.parametrize("video", ["fv238", "fv337"])
@pytest.mark.parametrize("base", ["http://yt-lite.localhost", "http://yt-lite-w3.localhost:8080", "http://127.0.0.1:7860", "https://video.lab.example:8443"])
@pytest.mark.parametrize("format", ["{url}", "Recipe: [breakfast]({url})", "{url}?t=30", "{url}#details", 'I said "try this": {url}\n'])
def test_actual_watch_links_match(monkeypatch, video, base, format):
    monkeypatch.setenv("WP_YT_LITE_URL", base)
    assert matches(format.format(url=f"{base}/watch/{video}"))


@pytest.mark.parametrize("url", [
    "http://yt-lite.localhost/watch?/fv238", "http://yt-lite.localhost/watch?v=fv238",
    "http://yt-lite.localhost/watch/fv2380", "http://yt-lite.localhost/watch/fv337-other",
    "http://yt-lite.localhost/watch/fv238/extra", "http://yt-lite.localhost/watch/fv238.evil",
    "http://yt-lite.localhost/watch/fv239", "http://yt-lite.localhost/rewatch/fv238",
    "http://yt-lite.localhost/path/watch/fv238", "watch/fv238", "fv238",
    "https://evil.example/watch/fv238", "http://yt-liteXlocalhost/watch/fv238",
    "http://yt-lite.localhost.evil.example/watch/fv238",
    "http://yt-lite.localhost@evil.example/watch/fv238",
    "https://evil.example/?url=http://yt-lite.localhost/watch/fv238",
    "http://yt-lite.localhost:9999/watch/fv238",
    "prefixhttp://yt-lite.localhost/watch/fv238",
    "http://[invalid/watch/fv238",
])
def test_wrong_ids_and_malformed_links_fail(url):
    assert not matches(url)


@pytest.mark.parametrize("message", [
    "`http://yt-lite.localhost/watch/fv238`",
    "```\nhttp://yt-lite.localhost/watch/fv238\n```",
    "![image](http://yt-lite.localhost/watch/fv238)",
    "[http://yt-lite.localhost/watch/fv238](https://evil.example/watch/fv238)",
    "[http://yt-lite.localhost/watch/fv238][wrong]\n\n[wrong]: https://evil.example/",
])
def test_code_images_and_misleading_link_labels_do_not_count(message):
    assert not matches(message)


def test_markdown_reference_destination_counts():
    assert matches("[recipe][breakfast]\n\n[breakfast]: http://yt-lite.localhost/watch/fv238")


def test_malformed_url_does_not_hide_a_separate_valid_link():
    assert matches("http://[invalid\nhttp://yt-lite.localhost/watch/fv238")


def test_saved_link_passes_r2_without_a_judge(monkeypatch):
    monkeypatch.setenv("WP_YT_LITE_URL", "http://yt-lite-w3.localhost")
    def request(method, url, **kwargs):
        if url.endswith("/users/username/john.doe"):
            return response({"id": "john-id"})
        if "/channels/name/" in url:
            return response({"id": "watercooler-id", "delete_at": 0})
        if "/channels/watercooler-id/posts?" in url:
            return response({"posts": {"post": {
                "id": "post", "user_id": "john-id", "channel_id": "watercooler-id",
                "create_at": 1010, "delete_at": 0, "type": "",
                "message": "[Breakfast](http://yt-lite-w3.localhost/watch/fv337)",
            }}, "order": ["post"]})
        raise AssertionError(f"Unexpected request: {method} {url}")
    monkeypatch.setattr(BackendStateEvaluator, "_resolve_bearer_token", lambda *args: "test-token")
    monkeypatch.setattr(requests, "request", request)
    dag = {"operator": "AND", "scoring": "partial", "nodes": [NODE]}
    score, results = DAGEvaluator(parse_eval_dag(dag)).evaluate(
        EvalContext(task_config=TASK, task_start_time_ms=1000))
    assert score == 1.0
    assert results["r2"]["passed"]
    assert "decided_by=T0:backend_state" in results["r2"]["reason"]


def test_video_origin_is_resolved_again_after_worker_switch(monkeypatch):
    assert matches("http://yt-lite.localhost/watch/fv238")
    monkeypatch.setenv("WP_YT_LITE_URL", "https://video.lab.example:8443/")
    assert not matches("http://yt-lite.localhost/watch/fv238")
    assert matches("https://video.lab.example:8443/watch/fv238")
    assert not matches("https://videoXlabXexample:8443/watch/fv238")


@pytest.mark.parametrize("check_type", ["body_regex", "body_not_regex"])
def test_unknown_regex_url_placeholder_is_inconclusive(monkeypatch, check_type):
    evaluator = BackendStateEvaluator()
    monkeypatch.setattr(evaluator, "_send", lambda *args: response({"message": "anything"}))
    result = evaluator.evaluate({"url": "http://unused", "checks": [
        {"type": check_type, "pattern": "__UNKNOWN-SITE__/watch/fv238"}
    ]}, EvalContext(task_config=TASK))
    assert not result.passed
    assert result.inconclusive
    assert "unknown or unconfigured website URL placeholder" in result.reason
