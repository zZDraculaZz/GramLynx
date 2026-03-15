# Slice A Coverage Atlas (deterministic-only backlog)

## Scope and intent

This artifact captures a consolidated **analysis-only** backlog for residual Slice A
(`unchanged_when_expected_change + candidate_rejected_no_result`) and is intended to guide
future safe deterministic coverage work.

Boundaries for this atlas:
- no runtime/API/config changes;
- no apply or reranker integration decisions;
- deterministic fail-closed direction only.

## Evidence sources

- Full public RuSpellGold: `tests/cases/ruspellgold_full_public.jsonl` (1711 cases).
- Product regression holdout: `tests/cases/product_regression_user_texts.yml`.
- Hold-state decisions and residual framing in `docs/runbook_smart_baseline.md`.
- Pilot manual review references in `tests/cases/pilot_manual_review.jsonl`.

## Residual Slice A framing

Current stable framing from runbook:
- Slice A size: **580**;
- interpreted as mostly generation/coverage misses, not apply-regression.

This atlas freezes a rough class-level split for Slice A:

| Coverage class | Rough count | Rough share |
|---|---:|---:|
| `single_token_typo` | 238 | ~41% |
| `multi_token_typo` | 108 | ~19% |
| `yo_e` | 103 | ~18% |
| `spacing_only` | 64 | ~11% |
| `punctuation_only` | 51 | ~9% |
| `hyphenation` | 16 | ~3% |
| `casing/capitalization` | ~5 | <1% |
| `morphology-sensitive` | minor | minor |
| `lexical ambiguity` | minor | minor |

## Coverage classes

### 1) `single_token_typo`

- **Rough frequency/significance**: highest residual class (~41%).
- **Representative examples**:
  - `отделного` → `отдельного`.
  - `севодня` → `сегодня`.
  - `превет` → `привет`.
- **Practical usefulness**: very high on user text quality, including chat-like typos.
- **Safety assessment**: strong candidate for deterministic handling via explicit token-level maps / conservative dictionary-backed candidates.
- **Priority label**: **recommended (strongest safe candidate)**.
- **Fail-closed compatibility**: high, because scope can remain token-exact with explicit allowlists and existing no-touch/protected-zone constraints.

### 2) `yo_e`

- **Rough frequency/significance**: large residual slice (~18%).
- **Representative examples**:
  - `еще` → `ещё`.
  - `поймете` → `поймёте`.
  - `черной` → `чёрной`.
- **Practical usefulness**: high for Russian text normalization quality.
- **Safety assessment**: safe when constrained to deterministic lexical/whitelist restoration points.
- **Priority label**: **recommended (strongest safe candidate)**.
- **Fail-closed compatibility**: high with conservative lexical gating and no-touch safeguards.

### 3) `spacing_only`

- **Rough frequency/significance**: meaningful (~11%).
- **Representative examples**:
  - extra spacing around punctuation and symbols.
  - repeated spaces/blank-line normalization patterns.
- **Practical usefulness**: high in noisy user input.
- **Safety assessment**: very safe when purely structural and deterministic.
- **Priority label**: **recommended (strong safe candidate)**.
- **Fail-closed compatibility**: very high; can stay semantics-preserving and reversible under guardrails.

### 4) `punctuation_only`

- **Rough frequency/significance**: meaningful (~9%).
- **Representative examples**:
  - `привет ,как дела ?` → `привет, как дела?`.
  - quote/spacing punctuation cleanup patterns.
- **Practical usefulness**: high for readability of user-authored text.
- **Safety assessment**: very safe under deterministic punctuation spacing rules.
- **Priority label**: **recommended**.

### 5) `hyphenation`

- **Rough frequency/significance**: small-to-moderate (~3%), but present in user-like holdout.
- **Representative examples**:
  - `порусски` → `по-русски`.
  - `почемуто` → `почему-то`.
  - `ктото` → `кто-то`.
- **Practical usefulness**: high on specific frequent lexical patterns.
- **Safety assessment**: moderate; safe only for narrow lexicalized pattern sets.
- **Priority label**: **borderline**.
- **Why risky now**: broad hyphen rules can over-correct and violate fail-closed intent.
- **Why not immediate target**: should follow safer high-volume classes first.

### 6) `multi_token_typo`

- **Rough frequency/significance**: large (~19%).
- **Representative examples**:
  - multi-error sentences where several tokens differ between input and expected.
- **Practical usefulness**: potentially high but mixed risk profile.
- **Safety assessment**: lower than single-token class due to higher chance of semantic drift.
- **Priority label**: **borderline**.
- **Why risky now**: coupled edits increase unintended-change risk.
- **Why not immediate target**: needs stronger per-pattern safety evidence before runtime consideration.

### 7) `morphology-sensitive`

- **Rough frequency/significance**: currently minor in Slice A backlog focus.
- **Representative examples**: omitted here intentionally (class treated as risk-heavy for apply-stage use).
- **Practical usefulness**: unclear without deeper language-model-like inference.
- **Safety assessment**: risky for deterministic fail-closed correction path.
- **Priority label**: **not recommended now**.
- **Why risky now**: tends to require morphological interpretation beyond conservative token coverage.
- **Why not immediate target**: conflicts with current hold-state and deterministic scope boundaries.

### 8) `lexical ambiguity`

- **Rough frequency/significance**: minor in current residual framing.
- **Representative examples**: omitted as backlog-only risk class.
- **Practical usefulness**: uncertain; high false-positive risk.
- **Safety assessment**: risky for deterministic no-rewrite policy.
- **Priority label**: **not recommended now**.
- **Why risky now**: ambiguity resolution is prone to meaning-changing guesses.
- **Why not immediate target**: not aligned with fail-closed conservative improvements.

## Strongest safe candidates (focused list)

1. `single_token_typo`
2. `yo_e`
3. `spacing_only` + `punctuation_only` deterministic cleanup

Why these are best aligned with fail-closed deterministic handling now:
- can be constrained to explicit token-level or structural normalization behavior;
- have clear user-facing value on holdout-like text;
- do not require free-form rewriting or ambiguous semantic disambiguation.

## Backlog priority and exploration order

Top-3 safest/highest-value classes:
1. `single_token_typo`
2. `yo_e`
3. `spacing_only` / `punctuation_only`

Recommended exploration order:
1. `single_token_typo` coverage atlas deepening (frequent misses and explicit rule-map candidates).
2. `yo_e` conservative lexical restoration points.
3. `spacing_only` and `punctuation_only` residual normalization gaps.
4. narrow `hyphenation` lexical patterns.
5. `multi_token_typo` only after additional safety evidence.
6. keep `morphology-sensitive` and `lexical ambiguity` out of immediate runtime-target backlog.

## Hold-state statement

`apply` micro-tuning track and offline `reranker` track remain on **hold-state**.
This atlas is evidence capture for future deterministic coverage work only and does not
change production runtime behavior.
