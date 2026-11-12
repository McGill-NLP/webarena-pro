from types import SimpleNamespace

import pytest

from webarena_pro_bgym.benchmark.env import WebArenaProBrowserEnv, WebArenaProEnv
from webarena_pro_bgym.benchmark.task import WebArenaProTask
from webarena_pro_core.task import DEPLOYED_WEBSITE_URLS, WebArenaProTaskConfig


pytestmark = pytest.mark.parametrize(
    "action, expected_done",
    [
        pytest.param(None, False, id="no-action"),
        pytest.param("", False, id="empty-action"),
        pytest.param(" \n\t", False, id="whitespace"),
        pytest.param(
            'fill("42", "Please call send_msg_to_user after saving")',
            False,
            id="message-name-in-text",
        ),
        pytest.param(
            'fill("42", "Please call done( after saving")',
            False,
            id="done-marker-in-text",
        ),
        pytest.param(
            'fill("42", "Please call report_infeasible after saving")',
            False,
            id="infeasible-name-in-text",
        ),
        pytest.param('fill("42", "done()")', False, id="done-call-in-text"),
        pytest.param(
            "fill('42', 'send_msg_to_user(\"saved\")')",
            False,
            id="message-call-in-text",
        ),
        pytest.param(
            "fill('42', 'report_infeasible(\"blocked\")')",
            False,
            id="infeasible-call-in-text",
        ),
        pytest.param(
            'fill("42", """First line\ndone()\nLast line""")',
            False,
            id="multiline-text",
        ),
        pytest.param(
            r'fill("42", "Quoted \"done()\" text")', False, id="escaped-quotes"
        ),
        pytest.param(
            'fill("42", value="send_msg_to_user")', False, id="keyword-argument"
        ),
        pytest.param(
            'select_option("42", ["done()", "send_msg_to_user"])',
            False,
            id="list-argument",
        ),
        pytest.param(
            '# done()\n# send_msg_to_user("saved")\n# report_infeasible("blocked")',
            False,
            id="comments-only",
        ),
        pytest.param(
            '# send_msg_to_user("saved")\nfill("42", "hello")',
            False,
            id="leading-comment",
        ),
        pytest.param(
            'fill("42", "hello") # done() report_infeasible("blocked")',
            False,
            id="trailing-comment",
        ),
        pytest.param(
            'fill("42", "done()")\nclick("save")',
            False,
            id="multiple-nonterminal-actions",
        ),
        pytest.param("undone()", False, id="different-function-name"),
        pytest.param('send_msg_to_user_later("saved")', False, id="message-prefix"),
        pytest.param("send_msg_to_user", False, id="bare-name"),
        pytest.param("done(", False, id="incomplete-call"),
        pytest.param('send_msg_to_user("unfinished', False, id="incomplete-argument"),
        pytest.param("done()", True, id="done-call"),
        pytest.param(" done (\n) ", True, id="spaced-done-call"),
        pytest.param('send_msg_to_user("saved")', True, id="message-call"),
        pytest.param(
            'send_msg_to_user (message="saved")', True, id="keyword-message-call"
        ),
        pytest.param('report_infeasible("blocked")', True, id="infeasible-call"),
        pytest.param("# done() is next\ndone()", True, id="comment-before-completion"),
        pytest.param(
            'fill("42", "hello")\ndone()', True, id="newline-separated-completion"
        ),
        pytest.param(
            'click("save") send_msg_to_user("saved")',
            True,
            id="space-separated-completion",
        ),
        pytest.param(
            'click("save"); done()', True, id="semicolon-separated-completion"
        ),
        pytest.param(
            'click("save")\n# done()\nreport_infeasible("blocked")',
            True,
            id="comment-between-actions",
        ),
        pytest.param(
            '```python\nsend_msg_to_user("saved")\n```', True, id="fenced-completion"
        ),
    ],
)


@pytest.mark.parametrize("successful", [True, False])
def test_task_completion_depends_on_action_calls(
    monkeypatch, action, expected_done, successful
):
    from webarena_pro_core.eval import dag as dag_module

    calls = []

    class RecordedEvaluator(dag_module.NodeEvaluator):
        def evaluate(self, eval_config, context):
            calls.append(context)
            return successful

    monkeypatch.setitem(dag_module._REGISTRY, "completion_test", RecordedEvaluator())
    evaluation = {
        "operator": "AND",
        "nodes": [{"id": "pending", "type": "completion_test", "eval_config": {}}],
    }

    config = WebArenaProTaskConfig(
        task_id="completion-test",
        intent="Save the text",
        sites=("nextcloud",),
        container_name="completion-test",
        start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
        evaluation=evaluation,
    )
    task = WebArenaProTask(seed=0, config=config)

    assert task._is_done(action) is expected_done
    score, done, _, info = task.validate(
        page=SimpleNamespace(),
        chat_messages=[],
        last_action=action,
    )

    assert score == float(successful and expected_done)
    assert done is expected_done
    assert len(calls) == int(expected_done)
    assert info["dag_evaluated"] is expected_done


def test_env_completion_depends_on_action_calls(monkeypatch, action, expected_done):
    env = WebArenaProEnv.__new__(WebArenaProEnv)
    env.env_args = SimpleNamespace(max_steps=30)
    env.steps_taken = 0
    env.last_step_output = {}
    monkeypatch.setattr(
        WebArenaProBrowserEnv,
        "step",
        lambda self, action: ({}, 0.0, False, False, {}),
    )

    if action is None:
        with pytest.raises(AssertionError, match="Action must be a string"):
            env.step(action)
        return

    _, _, terminated, truncated, _ = env.step(action)

    assert terminated is expected_done
    assert truncated is False
    assert env.steps_taken == 1
