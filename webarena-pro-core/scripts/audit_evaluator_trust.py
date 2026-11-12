#!/usr/bin/env python3
"""Inventory fallback reachability without starting sites or calling a judge."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_TRUST = {
    "backend_state": "both", "answer_match": "both", "file_downloaded": "both",
    "ui_state": "pass_only", "browser_event": "pass_only", "llm_judge": "terminal",
}
CONFIG_ROOT = Path(__file__).resolve().parents[2] / "webarena-pro-core/src/webarena_pro_core/config"


def audit(config_root: Path) -> list[dict]:
    rows = []
    paths = [(path, "test") for path in sorted(config_root.glob("*.raw.json"))]
    paths.append((config_root / "splits/dev.json", "dev"))
    for path, split in paths:
        raw = json.loads(path.read_text())
        tasks = raw["tasks"] if isinstance(raw, dict) else raw
        for task in tasks:
            for node in task.get("eval", {}).get("nodes", []):
                strategies = node.get("eval_config", {}).get("strategies", [])
                for index, strategy in enumerate(strategies[:-1]):
                    trust = strategy.get("trust") or DEFAULT_TRUST.get(strategy.get("type"), "pass_only")
                    rows.append({
                        "split": split, "task_id": task["task_id"], "node_id": node["id"],
                        "source": str(path.relative_to(config_root)), "strategy_index": index,
                        "type": strategy.get("type"), "tier": strategy.get("tier"),
                        "effective_trust": trust,
                        "trust_source": "explicit" if strategy.get("trust") else "default",
                        "concrete_failure_escalates": trust == "pass_only",
                        "conditional_fallback": trust == "both",
                        "invalid_trust": trust not in {"both", "pass_only", "terminal"},
                    })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-root", type=Path, default=CONFIG_ROOT)
    parser.add_argument("--json", action="store_true", help="emit structured rows")
    args = parser.parse_args()
    rows = audit(args.config_root)
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    print("split task/node strategy trust source concrete-failure")
    for row in rows:
        action = "escalates" if row["concrete_failure_escalates"] else "stops"
        print(f'{row["split"]} {row["task_id"]}/{row["node_id"]} '
              f'{row["type"]} {row["effective_trust"]} {row["trust_source"]} {action}')
    conditional = sum(row["conditional_fallback"] for row in rows)
    print(f"{len(rows)} strategies with later strategies; {conditional} require inconclusive evidence to fall through.")


if __name__ == "__main__":
    main()
