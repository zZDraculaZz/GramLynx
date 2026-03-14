# GramLynx Shadow-First Rollout Policy (Smart Baseline)

Formal ops-layer policy for safe rollout of feature-enabled smart baseline.

## Scope and invariants

- Scope: environment rollout policy only (no API/runtime pipeline change).
- API contract remains unchanged: input `text + mode`, output only `clean_text`.
- Protected Zones / buffer / guardrails / rollback semantics remain unchanged.
- Safe default remains OFF (`enable_candidate_generation_ru: false`).

## 1) Safe default OFF

Default startup path must keep candidate generation disabled.

- Baseline-safe startup:
  - `uvicorn app.main:app --reload`
- Expected behavior:
  - service starts without candidate backend dependencies,
  - no candidate-generation path is active.

## 2) Staging smart baseline profile (feature-enabled)

For opt-in staging readiness, use smart baseline profile and startup preflight.

- Required baseline:
  - `enable_candidate_generation_ru: true`
  - `candidate_backend: symspell`
  - `dictionary_source_ru: app/resources/ru_dictionary_v7.txt`
  - `max_candidates_ru: 3`
  - `max_edit_distance_ru: 1`

## 3) Shadow-first phase (no user-facing candidate apply)

First rollout phase in each environment is shadow-only.

- Required shadow setting:
  - `candidate_shadow_mode_ru: true`
- Meaning:
  - candidates may be generated for evaluation,
  - candidate changes are not applied to user-facing `clean_text`.

### What to monitor in artifacts

Use existing artifacts only:

- benchmark/report artifacts:
  - `eval_candidate_harness.json`
  - `eval_ruspellgold_harness.json`
  - `baseline_report.md`
- docker smoke artifacts:
  - `docker_smart_baseline_smoke_summary.json`
  - `docker_smart_baseline_smoke_summary.txt`
- promotion summary artifacts:
  - `smart_baseline_promotion_summary.md`
  - `smart_baseline_promotion_summary.json`

Shadow phase is considered healthy when:

- smoke status is OK,
- benchmark/report artifacts are present,
- no red flags are reported.

## 4) Controlled apply phase

Switch to apply mode only after shadow phase is stable.

- Apply setting:
  - `candidate_shadow_mode_ru: false`

### Preconditions before switching to apply

All of the following must hold for recent promotion checks:

- smoke OK,
- benchmark/report present,
- no missing artifacts,
- `rollback_total == 0`,
- `candidate_rejected_unsafe_candidate_total == 0`.

If any precondition is not satisfied, do not switch to apply.

## 5) Rollback conditions

Immediately stop rollout progression (or revert apply -> shadow/off) when any condition appears:

- `rollback_total > 0`,
- `candidate_rejected_unsafe_candidate_total > 0`,
- smoke failures,
- promotion summary marks missing artifacts or `promotion_ready: no`.

## 6) Operational sequence (per environment)

1. Keep safe default OFF for default runtime path.
2. Enable smart baseline in staging profile.
3. Run shadow-first (`candidate_shadow_mode_ru: true`) and collect artifacts.
4. Promote to controlled apply (`candidate_shadow_mode_ru: false`) only after preconditions are met.
5. On any rollback condition, stop promotion and revert to safer phase.
