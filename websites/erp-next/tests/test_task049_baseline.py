"""The clean ERPNext seed must leave task 049's unit creation to the agent."""

import importlib.util
from pathlib import Path

import pytest


MODULE = Path(__file__).parents[1] / "scripts/seed_erpnext.py"
spec = importlib.util.spec_from_file_location("seed_erpnext", MODULE)
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


@pytest.mark.parametrize("existing_unit", [None, "Percent"])
def test_seed_verification_rejects_a_precompleted_unit(monkeypatch, existing_unit):
    def query_first(**kwargs):
        assert kwargs["doctype"] == "UOM"
        assert kwargs["field_name"] == "uom_name"
        assert kwargs["field_value"] == "Percent"
        return existing_unit

    monkeypatch.setattr(seed, "query_first", query_first)
    monkeypatch.setattr(seed, "count_documents", lambda **kwargs: 100)
    monkeypatch.setattr(seed, "sum_numeric_field", lambda **kwargs: 100)
    monkeypatch.setattr(seed, "query_many", lambda **kwargs: [
        {"warehouse": f"Warehouse {index}", "stock_value": 100} for index in range(3)
    ])
    if existing_unit is None:
        seed.verify_seed_documents(None, "http://unused.invalid")
    else:
        with pytest.raises(RuntimeError, match="task 049 requires Percent UOM to be absent"):
            seed.verify_seed_documents(None, "http://unused.invalid")


def test_master_prerequisites_preserve_nos_and_leave_percent_for_the_agent(monkeypatch):
    units = []

    def seed_doctype(**kwargs):
        if kwargs["doctype"] == "UOM":
            units.extend(doc["uom_name"] for doc in kwargs["docs"])

    monkeypatch.setattr(seed, "seed_doctype", seed_doctype)
    seed.ensure_master_prerequisites(None, "http://unused.invalid")
    assert "Nos" in units
    assert "Percent" not in units
