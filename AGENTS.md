## A. Project identity
GramLynx is a production-ready microservice for processing user-authored Russian text.

Core API contract (must remain unchanged unless explicitly decided):
- Input: `text` + `mode`
- Output: only `clean_text`
- Do not return explanations, tags, lemmas, morphology, or intermediate artifacts.

Current architectural course:
- The project is shifting toward context-aware candidate selection as the main development direction.
- The previous deterministic token-level path is retained as frozen baseline/fallback/reference, not as the main strategic direction.

## B. Global safety invariants (non-negotiable)
- Do not change API contract without explicit decision.
- Do not paraphrase.
- Do not rewrite meaning.
- Do not weaken Protected Zones, buffer logic, guardrails, or rollback.
- Do not modify text inside Protected Zones.
- Protected Zones must remain byte-to-byte stable after restore.
- Guardrails and rollback are mandatory.
- Fail-closed behavior is preferred over risky behavior.
- If unsure, prefer no change.
- No user text may leak into logs, metrics, or error messages.
- Python version: 3.10.

## C. Frozen baseline path (production-safe reference line)
Status:
- Current deterministic path is no longer the main development direction.
- It remains baseline/fallback/reference.
- Use it for comparison and safety reference only.

Purpose:
- Preserve stable production-safe behavior.
- Provide control line for research comparisons.
- Accept only explicit safe updates approved for baseline maintenance.

Frozen decisions:
- Previous apply micro-tuning path is frozen.
- Previous reranker path is frozen.
- Deterministic micro-packages are no longer the main strategic direction.

## D. Primary research path (main new direction)
Main direction:
- Context-aware candidate selection architecture for user text.

Core model:
- Large lexicon may be used as candidate source.
- Final candidate decision must be based on sentence-level context.
- Decision layer must remain fail-closed (`no candidate` / low confidence => keep original).

Execution mode:
- All such work starts offline-only in research branches.
- No production integration without explicit evidence cycle.
- No broad runtime/backend replacement by default.

Recommended research sequence:
- Phase 1: large lexicon candidate source + KenLM-style sentence scorer.
- Phase 2: compare against baseline on full public + holdout.
- Phase 3: only if evidence is strong, design guarded prototype.
- Phase 4: optionally evaluate masked-LM / edit-based branch if needed.

## E. Evaluation policy
Standard checks before completion:
- `ruff check .`
- `pytest -q`

Benchmark policy:
- **Primary benchmark:** full public RuSpellGold (`tests/cases/ruspellgold_full_public.jsonl`, 1711 cases).
- **Primary measurement path:** canonical reproducible harness path (`python -m tests.report_ruspellgold_tuning ...`, `symspell_apply`).
- **Secondary smoke/supporting checks:** subset benchmark (`tests/cases/ruspellgold_benchmark.jsonl`, 34 cases) and product-regression holdout (`tests/cases/product_regression_user_texts.yml`).

Research-branch evaluation requirements:
- Evaluate benchmark quality and harmful side effects together.
- Track at minimum: `exact_match_pass_count/rate`, `wrong_change`, `smart_regresses_expected_match`, `rollback_related`.
- Subset/holdout are for coarse regression signals, not the primary gate.

Source-of-truth clarification:
- Historical benchmark snapshots are reference-only.
- Current canonical harness path is the source-of-truth for new acceptance decisions.

## F. Branching policy
- `main` branch: stable/frozen baseline and accepted safe updates only.
- `research/*` branches: architecture experiments, offline scorers, large lexicon candidate generation, reranking/context selection.
- No direct merge of research path into `main` without explicit go/no-go review and evidence package.

## G. Working style with Codex
- Analyze first, then make the minimal correct implementation.
- Keep changes scoped and architecture-aligned.
- Reuse existing structure where possible; avoid parallel production systems.
- For ambiguity, choose conservative behavior.
- Each step should have explicit acceptance criteria.
- End with concrete verification commands.
- Respond with ready-to-run Codex prompts plus short explanation when prompting help is requested.
- Do not run `make_pr` unless explicitly requested.

## H. Current hold/freeze decisions
- Deterministic token-level expansion is frozen as strategic direction.
- Apply micro-tuning remains frozen.
- Previous reranker path remains frozen.
- Broad production integration of context-aware selection is on hold until explicit evidence cycle passes.

## I. What not to do
- Do not change PZ / buffer / guardrails / rollback without explicit request.
- Do not add runtime ML/LLM rewriting to `/clean`.
- Do not perform semantic rewriting in any path.
- Do not introduce unrelated refactors.
- Do not treat research/offline findings as production-ready without formal review.

Completion rule:
- A task is done only if requested scope is met, safety invariants hold, Protected Zones remain intact, relevant tests pass, and no unrelated production-path changes are introduced.
