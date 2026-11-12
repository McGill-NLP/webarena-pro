from datetime import date

from webarena_pro_core.eval.backend_state import (
    BackendStateEvaluator,
    _add_calendar_months,
)
from webarena_pro_core.eval.dag import EvalContext


class JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _deadline_check(title: str) -> dict:
    return {
        "type": "json_array_date_relative",
        "path": "jobs",
        "match": {
            "title": {"regex": f"(?i)^{title}$"},
            "employer": "Acme Analytics",
            "is_active": True,
        },
        "date_field": "deadline",
        "months": 2,
    }


def test_json_array_date_relative_uses_task_execution_date() -> None:
    response = JsonResponse(
        {
            "jobs": [
                {
                    "title": "Product Design",
                    "employer": "Acme Analytics",
                    "is_active": True,
                    "deadline": "2026-07-05",
                }
            ]
        }
    )
    context = EvalContext(task_start_date=date(2026, 5, 5))

    ok, reason = BackendStateEvaluator()._run_check(
        _deadline_check("product design"), response, context
    )

    assert ok is True
    assert "2026-05-05 + 2 calendar month(s)" in reason


def test_json_array_date_relative_rejects_wrong_deadline() -> None:
    response = JsonResponse(
        {
            "jobs": [
                {
                    "title": "Data Science",
                    "employer": "Acme Analytics",
                    "is_active": True,
                    "deadline": "2026-07-06",
                }
            ]
        }
    )
    context = EvalContext(task_start_date=date(2026, 5, 5))

    ok, reason = BackendStateEvaluator()._run_check(
        _deadline_check("data science"), response, context
    )

    assert ok is False
    assert "expected 2026-07-05" in reason


def test_add_calendar_months_clamps_month_end() -> None:
    assert _add_calendar_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert _add_calendar_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
