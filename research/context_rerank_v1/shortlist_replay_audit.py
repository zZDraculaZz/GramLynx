from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from .audit_decision_profile import _compute_metrics, _load_cases, _run_kenlm_v2_with_audit
from .replay import CurrentApplyResult, ReplayCase, _run_current_apply


def run_once(config_path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cases = _load_cases(Path(str(cfg["corpus_path"])))

    replay_cases = tuple(ReplayCase(input_text=i, expected_clean_text=e) for i, e in cases)
    current_apply_outputs = _run_current_apply(replay_cases)
    # reuse public helper via simple extract
    apply_outputs = [current_apply_outputs[i].output for i, _ in cases]
    v2_outputs, v2_audit = _run_kenlm_v2_with_audit(cases, cfg)
    metrics = _compute_metrics(v2_outputs, cases, apply_outputs, [False] * len(v2_outputs))

    gold = v2_audit.get("gold_in_topk_failure_audit", {})
    return {
        **metrics,
        "keep_original_count": v2_audit.get("keep_original_count", 0),
        "gold_in_topk_selected_count": gold.get("selected", 0),
        "gold_present_in_topk_but_not_selected": gold.get("not_selected_original_wins", 0)
        + gold.get("not_selected_other_candidate_wins", 0)
        + gold.get("blocked_fail_closed", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Lightweight replay audit for shortlist experiments")
    parser.add_argument("--before-config", type=Path, required=True)
    parser.add_argument("--after-config", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    payload = {"before": run_once(args.before_config), "after": run_once(args.after_config)}
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
