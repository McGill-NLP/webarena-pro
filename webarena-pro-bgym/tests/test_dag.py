import pytest

from webarena_pro_core.eval.dag import (
    DAGEvaluator,
    EvalContext,
    EvalDAG,
    EvalNode,
    NodeEvaluator,
    get_node_evaluator,
    parse_eval_dag,
    register_node_evaluator,
)


# ---------------------------------------------------------------------------
# Helpers — mock evaluators
# ---------------------------------------------------------------------------

class AlwaysPass(NodeEvaluator):
    def evaluate(self, eval_config, context):
        return True


class AlwaysFail(NodeEvaluator):
    def evaluate(self, eval_config, context):
        return False


class ConfigDriven(NodeEvaluator):
    """Returns eval_config["result"]."""
    def evaluate(self, eval_config, context):
        return eval_config["result"]


@pytest.fixture(autouse=True)
def _register_mock_evaluators():
    """Override stub evaluators with mock ones for all tests."""
    register_node_evaluator("pass", AlwaysPass())
    register_node_evaluator("fail", AlwaysFail())
    register_node_evaluator("config", ConfigDriven())
    yield


def _ctx():
    return EvalContext()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_get_known():
    ev = get_node_evaluator("pass")
    assert isinstance(ev, AlwaysPass)


def test_registry_get_unknown():
    with pytest.raises(KeyError, match="no_such_type"):
        get_node_evaluator("no_such_type")


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------

def test_topo_linear_chain():
    dag = EvalDAG(operator="AND", nodes=[
        EvalNode(id="s0", type="pass", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="pass", eval_config={}, depends_on=["s0"]),
        EvalNode(id="s2", type="pass", eval_config={}, depends_on=["s1"]),
    ])
    order = DAGEvaluator(dag)._topological_sort()
    ids = [n.id for n in order]
    assert ids.index("s0") < ids.index("s1") < ids.index("s2")


def test_topo_parallel_branches():
    dag = EvalDAG(operator="AND", nodes=[
        EvalNode(id="s0", type="pass", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="pass", eval_config={}, depends_on=["s0"]),
        EvalNode(id="s2", type="pass", eval_config={}, depends_on=["s0"]),
        EvalNode(id="s3", type="pass", eval_config={}, depends_on=["s1", "s2"]),
    ])
    order = DAGEvaluator(dag)._topological_sort()
    ids = [n.id for n in order]
    assert ids.index("s0") < ids.index("s1")
    assert ids.index("s0") < ids.index("s2")
    assert ids.index("s1") < ids.index("s3")
    assert ids.index("s2") < ids.index("s3")


def test_topo_diamond():
    dag = EvalDAG(operator="AND", nodes=[
        EvalNode(id="a", type="pass", eval_config={}, depends_on=[]),
        EvalNode(id="b", type="pass", eval_config={}, depends_on=["a"]),
        EvalNode(id="c", type="pass", eval_config={}, depends_on=["a"]),
        EvalNode(id="d", type="pass", eval_config={}, depends_on=["b", "c"]),
    ])
    order = DAGEvaluator(dag)._topological_sort()
    ids = [n.id for n in order]
    assert ids[0] == "a"
    assert ids[-1] == "d"


def test_topo_cycle_raises():
    dag = EvalDAG(operator="AND", nodes=[
        EvalNode(id="a", type="pass", eval_config={}, depends_on=["b"]),
        EvalNode(id="b", type="pass", eval_config={}, depends_on=["a"]),
    ])
    with pytest.raises(ValueError, match="Cycle"):
        DAGEvaluator(dag)._topological_sort()


def test_topo_unknown_dep_raises():
    dag = EvalDAG(operator="AND", nodes=[
        EvalNode(id="a", type="pass", eval_config={}, depends_on=["nonexistent"]),
    ])
    with pytest.raises(ValueError, match="unknown node"):
        DAGEvaluator(dag)._topological_sort()


# ---------------------------------------------------------------------------
# Dependency skip
# ---------------------------------------------------------------------------

def test_dep_skip_on_failure():
    dag = EvalDAG(operator="AND", nodes=[
        EvalNode(id="s0", type="fail", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="pass", eval_config={}, depends_on=["s0"]),
    ])
    score, results = DAGEvaluator(dag).evaluate(_ctx())
    assert results["s0"]["passed"] is False
    assert results["s1"]["passed"] is False  # skipped, not evaluated


def test_dep_pass_allows_child():
    dag = EvalDAG(operator="AND", nodes=[
        EvalNode(id="s0", type="pass", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="pass", eval_config={}, depends_on=["s0"]),
    ])
    score, results = DAGEvaluator(dag).evaluate(_ctx())
    assert results["s0"]["passed"] is True
    assert results["s1"]["passed"] is True


def test_partial_dep_failure_skips_downstream():
    """s3 depends on s1 and s2; if s2 fails, s3 is skipped."""
    dag = EvalDAG(operator="AND", nodes=[
        EvalNode(id="s0", type="pass", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="pass", eval_config={}, depends_on=["s0"]),
        EvalNode(id="s2", type="fail", eval_config={}, depends_on=["s0"]),
        EvalNode(id="s3", type="pass", eval_config={}, depends_on=["s1", "s2"]),
    ])
    _, results = DAGEvaluator(dag).evaluate(_ctx())
    assert results["s1"]["passed"] is True
    assert results["s2"]["passed"] is False
    assert results["s3"]["passed"] is False  # skipped


# ---------------------------------------------------------------------------
# NotImplementedError handling — stub evaluators treated as failure
# ---------------------------------------------------------------------------

def test_stub_evaluator_treated_as_failure():
    dag = EvalDAG(operator="AND", nodes=[
        EvalNode(id="s0", type="browser_event", eval_config={}, depends_on=[]),
    ])
    _, results = DAGEvaluator(dag).evaluate(_ctx())
    assert results["s0"]["passed"] is False


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def test_scoring_binary_and_all_pass():
    dag = EvalDAG(operator="AND", scoring="binary", nodes=[
        EvalNode(id="s0", type="pass", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="pass", eval_config={}, depends_on=[]),
    ])
    score, _ = DAGEvaluator(dag).evaluate(_ctx())
    assert score == 1.0


def test_scoring_binary_and_one_fail():
    dag = EvalDAG(operator="AND", scoring="binary", nodes=[
        EvalNode(id="s0", type="pass", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="fail", eval_config={}, depends_on=[]),
    ])
    score, _ = DAGEvaluator(dag).evaluate(_ctx())
    assert score == 0.0


def test_scoring_binary_or_one_pass():
    dag = EvalDAG(operator="OR", scoring="binary", nodes=[
        EvalNode(id="s0", type="fail", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="pass", eval_config={}, depends_on=[]),
    ])
    score, _ = DAGEvaluator(dag).evaluate(_ctx())
    assert score == 1.0


def test_scoring_binary_or_all_fail():
    dag = EvalDAG(operator="OR", scoring="binary", nodes=[
        EvalNode(id="s0", type="fail", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="fail", eval_config={}, depends_on=[]),
    ])
    score, _ = DAGEvaluator(dag).evaluate(_ctx())
    assert score == 0.0


def test_scoring_partial():
    dag = EvalDAG(operator="AND", scoring="partial", nodes=[
        EvalNode(id="s0", type="pass", eval_config={}, depends_on=[]),
        EvalNode(id="s1", type="fail", eval_config={}, depends_on=[]),
        EvalNode(id="s2", type="pass", eval_config={}, depends_on=[]),
    ])
    score, _ = DAGEvaluator(dag).evaluate(_ctx())
    assert score == pytest.approx(2.0 / 3.0)


def test_scoring_unknown_mode_raises():
    dag = EvalDAG(operator="AND", scoring="unsupported", nodes=[
        EvalNode(id="s0", type="pass", eval_config={}),
    ])
    with pytest.raises(ValueError, match="Unknown scoring mode: 'unsupported'"):
        DAGEvaluator(dag).evaluate(_ctx())


def test_scoring_empty_dag():
    dag = EvalDAG(operator="AND", scoring="binary", nodes=[])
    score, results = DAGEvaluator(dag).evaluate(_ctx())
    assert score == 0.0
    assert results == {}


# ---------------------------------------------------------------------------
# parse_eval_dag
# ---------------------------------------------------------------------------

def test_parse_eval_dag_minimal():
    raw = {
        "operator": "AND",
        "nodes": [
            {"id": "s0", "type": "pass", "eval_config": {}},
        ],
    }
    dag = parse_eval_dag(raw)
    assert dag.operator == "AND"
    assert dag.scoring == "binary"
    assert len(dag.nodes) == 1
    assert dag.nodes[0].id == "s0"
    assert dag.nodes[0].depends_on == []


def test_parse_eval_dag_dark_mode_prototype():
    raw = {
        "operator": "AND",
        "scoring": "binary",
        "nodes": [
            {
                "id": "s0",
                "type": "browser_event",
                "depends_on": [],
                "eval_config": {
                    "event": "navigation",
                    "match": {"url_pattern": "*/settings*"},
                },
            },
            {
                "id": "s1",
                "type": "ui_state",
                "depends_on": ["s0"],
                "eval_config": {
                    "checks": [
                        {
                            "method": "element_exists",
                            "selector": "html.dark",
                            "min_count": 1,
                        }
                    ]
                },
            },
        ],
    }
    dag = parse_eval_dag(raw)
    assert dag.operator == "AND"
    assert len(dag.nodes) == 2
    assert dag.nodes[0].type == "browser_event"
    assert dag.nodes[1].type == "ui_state"
    assert dag.nodes[1].depends_on == ["s0"]
    assert dag.nodes[1].eval_config["checks"][0]["method"] == "element_exists"


def test_parse_eval_dag_partial_counts_skipped_dependencies_as_failures():
    raw = {
        "operator": "AND",
        "scoring": "partial",
        "nodes": [
            {"id": "s0", "type": "pass", "eval_config": {}},
            {"id": "s1", "type": "fail", "eval_config": {}, "intent": "main check"},
            {"id": "s2", "type": "pass", "depends_on": ["s1"]},
        ],
    }
    dag = parse_eval_dag(raw)
    assert dag.scoring == "partial"
    assert dag.nodes[1].intent == "main check"
    score, results = DAGEvaluator(dag).evaluate(_ctx())
    assert score == pytest.approx(1 / 3)
    assert results["s2"]["passed"] is False
    assert results["s2"]["reason"].startswith("dependency failed:")


# ---------------------------------------------------------------------------
# Integration: validate() via task.py (DAG path)
# ---------------------------------------------------------------------------

def test_task_validate_dag_path():
    from webarena_pro_bgym.benchmark.task import WebArenaProTask
    from webarena_pro_core.task import DEPLOYED_WEBSITE_URLS, WebArenaProTaskConfig

    config = WebArenaProTaskConfig(
        task_id="dag-test-1",
        intent="Test DAG eval",
        sites=("nextcloud",),
        container_name="test-container",
        start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
        evaluation={
            "operator": "AND",
            "scoring": "binary",
            "nodes": [
                {"id": "s0", "type": "pass", "eval_config": {}, "depends_on": []},
                {"id": "s1", "type": "pass", "eval_config": {}, "depends_on": ["s0"]},
            ],
        },
        raw_task={"task_id": "dag-test-1", "intent": "Test DAG eval"},
    )

    class DummyPage:
        pass

    task = WebArenaProTask(seed=0, config=config)
    score, done, msg, info = task.validate(
        page=DummyPage(),
        chat_messages=[],
        last_step_output={"episode_info": []},
        last_action="done()",
    )
    assert score == 1.0
    assert done is True
    assert info["dag_results"]["s0"]["passed"] is True
    assert info["dag_results"]["s1"]["passed"] is True


def test_task_validate_dag_path_partial_failure():
    from webarena_pro_bgym.benchmark.task import WebArenaProTask
    from webarena_pro_core.task import DEPLOYED_WEBSITE_URLS, WebArenaProTaskConfig

    config = WebArenaProTaskConfig(
        task_id="dag-test-2",
        intent="Test DAG partial",
        sites=("nextcloud",),
        container_name="test-container",
        start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
        evaluation={
            "operator": "AND",
            "scoring": "partial",
            "nodes": [
                {"id": "s0", "type": "pass", "eval_config": {}, "depends_on": []},
                {"id": "s1", "type": "fail", "eval_config": {}, "depends_on": []},
            ],
        },
        raw_task={},
    )

    class DummyPage:
        pass

    task = WebArenaProTask(seed=0, config=config)
    score, done, _, info = task.validate(
        page=DummyPage(),
        chat_messages=[],
        last_step_output={"episode_info": []},
        last_action="done()",
    )
    assert score == pytest.approx(0.5)
    assert done is True


def test_task_validate_no_eval_config():
    from webarena_pro_bgym.benchmark.task import WebArenaProTask
    from webarena_pro_core.task import DEPLOYED_WEBSITE_URLS, WebArenaProTaskConfig

    config = WebArenaProTaskConfig(
        task_id="dag-test-3",
        intent="No eval",
        sites=("nextcloud",),
        container_name="test-container",
        start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
        evaluation=None,
    )

    class DummyPage:
        pass

    task = WebArenaProTask(seed=0, config=config)
    score, done, _, info = task.validate(page=DummyPage(), chat_messages=[])
    assert score == 0.0
    assert done is False


def test_task_collects_private_ui_evidence_for_the_current_step(monkeypatch):
    from webarena_pro_bgym.benchmark.task import WebArenaProTask
    from webarena_pro_core.task import WebArenaProTaskConfig
    from webarena_pro_core.eval.ui_evidence import UIEvidence, UIProbeResult
    from webarena_pro_core.ui_evidence import sync_api

    evaluation = {"nodes": [{"id": "ui", "type": "ui_state", "eval_config": {
        "checks": [{"method": "element_exists", "selector": ".target"}],
    }}]}
    config = WebArenaProTaskConfig(task_id="fixture", intent="Test capture", sites=("nextcloud",),
                                  container_name="fixture", start_url="http://fixture/", evaluation=evaluation, raw_task={"eval": evaluation})
    page = object()
    seen = []

    def collect(actual_page, plan, *, step):
        assert actual_page is page
        seen.append(step)
        probe = plan.probes[0]
        return UIEvidence(evaluation_id="fixture", step=step, tab_id="0", url="http://fixture/",
                          captured_at=1.0, status="ok", plan_sha256=plan.sha256,
                          results={probe.key: UIProbeResult(probe=probe, status="ok", count=1)})

    monkeypatch.setattr(sync_api, "collect_ui_evidence", collect)
    observation = {"url": "http://fixture/", "axtree_txt": "Public observation"}
    result = WebArenaProTask(seed=0, config=config).validate(
        page, [], last_step_output={"obs": observation, "episode_info": [{"step": 5}]}, budget_checkpoint=True,
    )
    assert result[0] == 1 and seen == [5]
    assert result[3]["ui_evidence"]["step"] == 5
    assert result[3]["dag_results"]["ui"]["passed"]
    assert "ui_evidence" not in observation
