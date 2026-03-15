## Project
GramLynx is a production-ready microservice for processing user-authored Russian text.

Core contract:
- Input: `text` + `mode`
- Output: only `clean_text`
- Do not return explanations, tags, lemmas, morphology, or intermediate artifacts.

## Main goal
Improve `clean_text` quality for Russian user text while preserving meaning and keeping behavior deterministic and safe.

## Hard constraints
- Do not change API contract.
- Do not paraphrase.
- Do not rewrite meaning.
- Do not weaken Protected Zones, buffer logic, guardrails, or rollback.
- Do not modify text inside Protected Zones.
- If unsure, prefer no change.
- All automatic edits must be deterministic.
- Python version: 3.10.

## Safety model
Protected Zones are mandatory and must remain byte-to-byte stable after restore.
Guardrails and rollback are mandatory.
Fail-closed behavior is preferred over risky behavior.
No user text may leak into logs, metrics, or error messages.

## Allowed kinds of improvements
Preferred improvements:
- conservative normalization
- safe whitespace cleanup
- safe punctuation spacing
- token-level typo correction from explicit rule maps
- Russian-specific no-touch / safety predicates
- morphology only as detector / blocker / scorer / ranker, not as a free-form text rewriter

Not allowed in the main `/clean` path:
- LLM-based rewriting
- probabilistic free-form correction
- non-deterministic edits
- substring replacements inside arbitrary tokens
- edits that require semantic rewriting

## Working style
- Make minimal, scoped changes.
- Read relevant files first.
- Reuse existing architecture and conventions.
- Prefer extending current stages/config/tests over inventing parallel systems.
- For complex tasks, plan before editing.
- If a task is ambiguous, choose the more conservative implementation.

## Architecture expectations
Respect and preserve:
- FastAPI API surface
- orchestrator flow
- policy/config loading
- stage pipeline S1-S7
- stage plugin registry/factory
- Protected Zones detection + masking + restore
- guardrails + rollback
- observability without text leakage

## Testing and verification
Before finishing:
- run the most relevant targeted tests first
- then run broader checks when dependencies allow

Standard checks:
- `ruff check .`
- `pytest -q`

### Acceptance benchmark policy (current)
- **Primary source of truth:** full public RuSpellGold (`tests/cases/ruspellgold_full_public.jsonl`, 1711 cases).
- **Primary measurement path:** current canonical reproducible harness path (`python -m tests.report_ruspellgold_tuning ...`, `symspell_apply`).
- **Secondary smoke only:** subset benchmark (`tests/cases/ruspellgold_benchmark.jsonl`, 34 cases) and product-regression holdout (`tests/cases/product_regression_user_texts.yml`).
- Subset/holdout signals should be used to detect **coarse breakage**, but they are not the primary acceptance gate when full public improves without safety regression.

### Acceptance logic for deterministic coverage steps
- full public `exact_match_pass_count` improves or at least does not degrade;
- full public `wrong_change` does not increase;
- full public `smart_regresses_expected_match` does not increase;
- `rollback_related` does not worsen materially;
- subset/product-regression are interpreted as secondary regression smoke checks.

Note:
- historical snapshots are not source-of-truth for new acceptance decisions;
- source-of-truth is the current canonical reproducible harness path.

If a task touches optional metrics functionality, use the environment/dependencies that include metrics extras.
If a full test run fails because of optional dependency setup, clearly distinguish:
- whether the new change is correct
- whether the environment is incomplete

## Done when
A task is complete only if:
- behavior matches the requested scope
- safety constraints still hold
- Protected Zones remain intact
- tests covering the change pass
- no unrelated refactor is introduced
- docs/config examples are updated if behavior or setup changed

## Preferred prompt response format
When working on a task:
1. Briefly state which files you will inspect/change.
2. Make the smallest correct implementation.
3. Show diff or summarize concrete file changes.
4. End with verification commands.

## Repository-specific priorities
Current product priority is not generic infra expansion.
Current priority is safe improvement of Russian text cleaning quality on top of the existing production foundation.

## Current stable baseline

- Safe default remains OFF: `enable_candidate_generation_ru: false`.
- Recommended feature-enabled smart baseline:
  - `candidate_backend: symspell`
  - `dictionary_source_ru: app/resources/ru_dictionary_v7.txt`
  - `max_candidates_ru: 3`
  - `max_edit_distance_ru: 1`
  - `candidate_shadow_mode_ru: false`
- Candidate path is fail-closed on startup if backend dependency or dictionary is missing.
- Do not change PZ / buffer / guardrails / rollback without explicit request.
- Do not add new runtime ML/LLM rewriting to `/clean`.
- Prefer eval-driven changes; use internal/external harness before changing runtime behavior.
- Treat v7 as the current stable baseline unless explicitly asked to experiment.
