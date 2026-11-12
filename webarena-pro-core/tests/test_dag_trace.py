from webarena_pro_core.eval.dag_trace import build_dag_trace, render_dag_trace_markdown


def test_build_and_render_dag_trace_includes_structure_and_results():
    trace = build_dag_trace(
        {
            "operator": "AND",
            "scoring": "partial",
            "nodes": [
                {"id": "r1", "type": "backend_state", "intent": "File exists"},
                {"id": "r2", "type": "tiered", "depends_on": ["r1"]},
            ],
        },
        score=0.0,
        results={
            "r1": {"passed": False, "reason": "HTTP 404"},
            "r2": {"passed": False, "reason": "dependency failed: r1"},
        },
    )

    assert trace["nodes"][0]["status"] == "FAIL"
    assert trace["nodes"][1]["status"] == "SKIP"
    assert trace["scoring"] == "partial"
    rendered = render_dag_trace_markdown(trace)
    assert "DAG" not in rendered
    assert "`r1`" in rendered
    assert "HTTP 404" in rendered
    assert "⏭️ SKIP" in rendered
