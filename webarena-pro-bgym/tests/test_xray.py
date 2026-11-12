from types import SimpleNamespace

from webarena_pro_bgym.xray import render_step_dag


def test_render_step_dag_uses_serialized_per_step_trace():
    step = SimpleNamespace(
        task_info={
            "dag_trace": {
                "score": 1.0,
                "operator": "AND",
                "scoring": "binary",
                "nodes": [
                    {
                        "id": "r1",
                        "type": "backend_state",
                        "depends_on": [],
                        "intent": "File exists",
                        "status": "PASS",
                        "reason": "HTTP 207",
                    }
                ],
            }
        }
    )
    rendered = render_step_dag(step)
    assert "DAG evaluator" in rendered
    assert "`r1`" in rendered
    assert "HTTP 207" in rendered
