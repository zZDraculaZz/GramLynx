from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .replay import load_cases, load_config, run_replay
from .encoder_setup import encoder_backend_blocker_message, encoder_backend_ready


def _load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_mode(report: dict[str, Any], key: str) -> dict[str, Any]:
    mode = report[key]
    return {
        "exact_match_pass_count": mode["exact_match_pass_count"],
        "exact_match_pass_rate": mode["exact_match_pass_rate"],
        "wrong_change": mode["wrong_change"],
        "smart_regresses_expected_match": mode["smart_regresses_expected_match"],
        "rollback_related": mode["rollback_related"],
    }


def _keep_original_count(rows: list[dict[str, Any]], output_key: str) -> int:
    return sum(1 for r in rows if str(r[output_key]) == str(r["input_text"]))


def _gold_in_topk_selected_count(rows: list[dict[str, Any]], output_key: str) -> int:
    return sum(
        1
        for r in rows
        if str(r[output_key]) == str(r["expected_clean_text"])
        and str(r["expected_clean_text"]) != str(r["input_text"])
    )


def _sample_rows(rows: list[dict[str, Any]], output_key: str, reference_key: str, limit: int = 5) -> list[dict[str, str]]:
    samples: list[dict[str, str]] = []
    for row in rows:
        out = str(row[output_key])
        ref = str(row[reference_key])
        expected = str(row["expected_clean_text"])
        if out == expected and ref != expected:
            samples.append(
                {
                    "input_text": str(row["input_text"]),
                    "expected_clean_text": expected,
                    "encoder_output": out,
                    "reference_output": ref,
                }
            )
        if len(samples) >= limit:
            break
    return samples


def _build_dataset_summary(report: dict[str, Any], encoder_key: str) -> dict[str, Any]:
    raw_rows = list(report.get("rows", []))

    summary = {
        "baseline": _extract_mode(report, "baseline"),
        "current_apply": _extract_mode(report, "current_apply"),
        "encoder_ranker_replay": _extract_mode(report, encoder_key),
        "encoder_beats_current_apply": report["bucket_counts"]["research_v2_beats_current_apply"],
        "encoder_worse_than_current_apply": report["bucket_counts"]["research_v2_worse_than_current_apply"],
    }

    if raw_rows:
        summary["keep_original_count"] = _keep_original_count(raw_rows, "research_replay_v2_output")
        summary["gold_in_topk_selected_count"] = _gold_in_topk_selected_count(raw_rows, "research_replay_v2_output")
        summary["sample_wins"] = _sample_rows(raw_rows, "research_replay_v2_output", "current_apply_output")
        summary["sample_regressions"] = _sample_rows(raw_rows, "current_apply_output", "research_replay_v2_output")
    else:
        summary["keep_original_count"] = None
        summary["gold_in_topk_selected_count"] = None
        summary["sample_wins"] = []
        summary["sample_regressions"] = []

    return summary


def _run_encoder_report(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    cases = load_cases(Path(str(config["corpus_path"])))
    return run_replay(config, cases)


def main() -> None:
    parser = argparse.ArgumentParser(description="First offline encoder ranker comparison")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument(
        "--full-public-kenlm-report",
        type=Path,
        default=Path("research/context_rerank_v1/full_public_pretrained_report.json"),
    )
    parser.add_argument(
        "--holdout-kenlm-report",
        type=Path,
        default=Path("research/context_rerank_v1/holdout_pretrained_report.json"),
    )
    parser.add_argument(
        "--full-public-encoder-config",
        type=Path,
        default=Path("research/context_rerank_v1/examples/full_public_encoder_ranker.yaml"),
    )
    parser.add_argument(
        "--holdout-encoder-config",
        type=Path,
        default=Path("research/context_rerank_v1/examples/product_holdout_encoder_ranker.yaml"),
    )
    args = parser.parse_args()

    full_kenlm = _load_report(args.full_public_kenlm_report)
    holdout_kenlm = _load_report(args.holdout_kenlm_report)

    payload: dict[str, Any] = {
        "model_source": "ai-forever/ruBert-base",
        "status": "blocked",
        "blocker": None,
        "frozen_kenlm_reference": {
            "full_public": _build_dataset_summary(full_kenlm, "research_replay_v2"),
            "holdout": _build_dataset_summary(holdout_kenlm, "research_replay_v2"),
        },
    }

    if not encoder_backend_ready():
        payload["blocker"] = encoder_backend_blocker_message()
        args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    try:
        full_encoder = _run_encoder_report(args.full_public_encoder_config)
        holdout_encoder = _run_encoder_report(args.holdout_encoder_config)
    except Exception as exc:
        payload["blocker"] = f"encoder runtime blocked during model load/run: {exc}"
        args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    payload["status"] = "ok"
    payload["encoder_reports"] = {
        "full_public": _build_dataset_summary(full_encoder, "research_replay_v2"),
        "holdout": _build_dataset_summary(holdout_encoder, "research_replay_v2"),
    }
    payload["encoder_vs_kenlm_reference"] = {
        "full_public_exact_match_delta": payload["encoder_reports"]["full_public"]["encoder_ranker_replay"]["exact_match_pass_count"]
        - payload["frozen_kenlm_reference"]["full_public"]["encoder_ranker_replay"]["exact_match_pass_count"],
        "holdout_exact_match_delta": payload["encoder_reports"]["holdout"]["encoder_ranker_replay"]["exact_match_pass_count"]
        - payload["frozen_kenlm_reference"]["holdout"]["encoder_ranker_replay"]["exact_match_pass_count"],
    }

    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
