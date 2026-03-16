A. Project identity
GramLynx is a production-oriented microservice for processing user-authored Russian text.

Core API contract (must remain unchanged unless explicitly decided):

- Input: text + mode
- Output: only clean_text
- Do not return explanations, tags, lemmas, morphology, or intermediate artifacts.

Current architectural course:

- GramLynx is moving toward GramLynx v2 as the primary architecture direction.
- The old deterministic token-level path is retained as a frozen baseline / fallback / reference path.
- The old deterministic path is no longer the main long-term strategic direction.

B. Global safety invariants (non-negotiable)

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

C. Frozen baseline path (production-safe reference line)

Status:

- The current deterministic token-level path is no longer the main development direction.
- It remains the baseline / fallback / reference path.
- It must be preserved as a stable production-safe control line.

Purpose:

- Preserve stable behavior for current production-safe flows.
- Provide a comparison line for new architecture work.
- Serve as a fallback/reference while GramLynx v2 is being developed.

Allowed work on the frozen baseline:

- Explicitly approved safe maintenance updates only.
- Regression fixes that do not expand the old path as the main strategy.
- Comparison/evaluation support for V2 work.

Frozen decisions:

- Previous apply micro-tuning path is frozen.
- Previous reranker path is frozen.
- Deterministic micro-packages are no longer the main strategic direction.
- The baseline remains in the repository, but it is not the primary long-term path.

D. Primary architecture path (GramLynx v2)

Main development direction:

- GramLynx v2 = context-aware candidate selection architecture for user-authored Russian text.

Target architecture:

1. Input + Protected Zones
2. Retrieval-oriented normalization
3. Candidate shortlist generation
4. Context-aware selector / scorer layer
5. Fail-closed decision layer
6. Safety shell (guardrails / rollback / no-touch / Protected Zones)
7. Reporting / evaluation

Core design principles:

- Candidate shortlist comes before final correction.
- Candidate generation and context scoring are separate concerns.
- Candidate generation may use SymSpell-like sources, retrieval-oriented normalization, lexicon-backed lookup, and other bounded candidate sources.
- The scorer does not perform free-form rewriting; it selects among bounded candidates in context.
- Final decision must be based on sentence-level or local context, not string similarity alone.
- Fail-closed keep-original remains mandatory on low confidence.
- Guardrails / rollback / Protected Zones remain mandatory.
- No semantic rewrite.
- No broad free-form generation path in /clean.

Current status in main:

- A V2 selector scaffold already exists in main.
- V2 architecture work is allowed in main, but it is not the default runtime behavior yet.
- The baseline path remains intact and coexists with the V2 scaffold.
- Current bottleneck is the selector / scorer layer, not further expansion of deterministic micro-fixes.

Candidate generation vs. context scoring:

- Candidate generation is responsible for producing a bounded shortlist of plausible correction candidates.
- Context scoring is responsible for ranking or selecting among those candidates using surrounding context.
- Similarity alone is not enough for final apply decisions.
- Context-aware selection is a required layer above shortlist generation.

KenLM clarification:

- KenLM is not the main identity of the project.
- KenLM is not the sole strategy of GramLynx v2.
- KenLM is a supported contextual scorer in the standard offline/dev GramLynx v2 evaluation workflow.
- KenLM is one scorer option within the selector/scorer layer, not the architecture itself.
- KenLM-backed scorer usage does not imply default runtime `/clean` activation.
- Runtime `/clean` activation remains explicitly evidence-gated.

What GramLynx v2 is not:

- Not a full rewrite path.
- Not a free-form LLM correction system.
- Not a replacement of safety shell with model-only behavior.
- Not a justification for weakening fail-closed behavior.

Canonical offline evaluation support (main-only):

- Shared offline dataset loading/adaptation for accepted workflows should live in `app/core/v2/offline_eval.py`.
- Offline replay/scorer utilities in tests/research should reuse canonical `app/core/v2` loaders and interfaces where feasible.
- Keep offline evidence helpers minimal, explicit, and non-runtime by default.

E. Evaluation policy

Standard checks before completion:

- ruff check .
- pytest -q

Benchmark policy:

- Primary benchmark: full public RuSpellGold (tests/cases/ruspellgold_full_public.jsonl)
- Primary source of truth for acceptance: current canonical reproducible harness path
- Supporting checks: subset benchmark (tests/cases/ruspellgold_benchmark.jsonl) and product-regression holdout (tests/cases/product_regression_user_texts.yml)

Quality/safety policy:

- Always evaluate both correction quality and harmful side effects.
- Track at minimum:
  - exact_match_pass_count
  - exact_match_pass_rate
  - wrong_change
  - smart_regresses_expected_match
  - rollback_related
  - kept_original_count
  - expected_match_when_changed_count
  - expected_match_when_changed_rate
  - decision_reason_counts
- Supporting checks are useful for regression signals, but they are not the primary acceptance gate when primary-benchmark evidence is available.

Source-of-truth clarification:

- Historical benchmark snapshots are reference-only.
- New acceptance decisions must rely on the current canonical reproducible measurement path.
- V2 work should always be compared against the frozen baseline.
- V2 scorer work should be developed and evaluated offline first, before any guarded runtime activation.

F. Development phases

Phase 1 — Architecture refocus

- Freeze the old deterministic path as baseline/reference.
- Establish GramLynx v2 interfaces and scaffold in main.

Phase 2 — Candidate source improvement

- Improve retrieval normalization and shortlist quality.
- Increase useful candidate coverage without weakening safety shell.
- Candidate-source work may include SymSpell-like or other bounded shortlist-generation approaches.

Phase 3 — Stronger contextual selector/scorer

- Develop context-aware candidate selection above the shortlist.
- Prefer selector-style architectures over rewrite-style architectures.
- Treat heuristic scorers, KenLM-like scorers, or other LM-style scorers as interchangeable scorer candidates, not as the architecture itself.

Phase 4 — Guarded activation

- Only after evidence, design guarded integration of V2 into runtime paths.
- V2 must not become default behavior without explicit evidence cycle.

Phase 5 — Production hardening

- Stability, observability, rollback safety, performance, documentation, and deployment readiness.

G. Repository policy (single canonical main)

main branch:

- `main` is the single canonical source of truth for accepted architecture and implementation.
- The frozen deterministic baseline remains in-repo as baseline/fallback/reference.
- Accepted GramLynx v2 architecture and offline evaluation support live in `main`.
- Unfinished or experimental logic must not be enabled by default in runtime paths.

Research/offline work:

- Research utilities may exist in the same repository, but they are non-runtime and optional by default.
- Research/offline helpers should reuse canonical loaders and interfaces from `app/core/v2` where feasible.
- Do not maintain parallel long-lived mini-cores that duplicate accepted main-path logic.

Merge policy:

- No direct promotion of exploratory scorer/model experiments into default runtime behavior without explicit evidence review.
- Keep accepted logic centralized in `main`; reduce drift and duplication over time.


H. Working style with Codex

- Analyze first, then make the minimal correct implementation.
- Keep changes scoped and architecture-aligned.
- Prefer small, explicit, testable steps.
- Reuse existing structure where possible; avoid parallel production systems unless explicitly intended.
- For ambiguity, choose conservative behavior.
- Each step should have explicit acceptance criteria.
- End with concrete verification commands.
- Respond with ready-to-run Codex prompts plus short explanation when prompting help is requested.
- Do not commit unless explicitly requested.
- Do not run make_pr unless explicitly requested.

I. Current hold / freeze decisions

- The old deterministic token-level path is frozen as strategic baseline/reference.
- Apply micro-tuning remains frozen.
- Previous reranker path remains frozen.
- KenLM line is frozen as a research reference and is not the main strategic direction.
- Deterministic micro-packages are no longer the main strategic direction.
- Broad production activation of context-aware selection is still gated by evidence.

J. What not to do

- Do not change Protected Zones / buffer / guardrails / rollback without explicit request.
- Do not add runtime ML/LLM rewriting to /clean.
- Do not perform semantic rewriting in any path.
- Do not treat research/offline findings as production-ready without formal review.
- Do not silently switch runtime defaults to unfinished V2 behavior.
- Do not let exploratory scorer/model work become mandatory for the baseline path.
- Do not introduce unrelated refactors while working on V2 architecture steps.

Completion rule:

- A task is done only if the requested scope is met, safety invariants hold, Protected Zones remain intact, relevant tests pass, and no unrelated production-path changes are introduced.
