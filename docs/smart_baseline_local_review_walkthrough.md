# Smart Baseline Local Review Walkthrough

Компактный operator/demo сценарий для уже существующего local rollout-review contour.

Цель walkthrough:
- быстро пройти локальный review flow;
- получить и проверить ключевые артефакты;
- зафиксировать, что итог — это readiness/review decision, а не автоматический production rollout.

## 1) Что использовать

Рекомендуемый apply-profile для локального review:
- `config.smart_baseline_staging.yml`

Для shadow-only проверки можно использовать:
- `config.smart_baseline_shadow_staging.yml`

Во всех шагах ниже путь к конфигу можно менять через `--config`.

---

## 2) Quick path (минимальный операторский прогон)

### Шаг 1. Product regression pack

```bash
pytest -q tests/test_product_regression_pack.py
```

Ожидание: пакет проходит без regressions на компактных user-like кейсах.

### Шаг 2. Readiness summary (с автогенерацией missing delta/manual)

```bash
python tests/generate_readiness_summary.py \
  --profile-name smart_baseline_staging \
  --config config.smart_baseline_staging.yml \
  --run-product-regression \
  --generate-delta-if-missing \
  --generate-manual-if-missing \
  --output-json smart_baseline_readiness_summary.json \
  --output-md smart_baseline_readiness_summary.md
```

### Шаг 3. Decision record

```bash
python tests/generate_rollout_decision_record.py \
  --bundle-dir . \
  --output-json rollout_decision_record.json \
  --output-md rollout_decision_record.md
```

### Шаг 4. Adjudication record (после ручного review)

```bash
python tests/generate_review_adjudication_record.py \
  --bundle-dir . \
  --accepted-case-count 10 \
  --caution-case-count 0 \
  --blocking-case-count 0 \
  --reviewer-notes "local walkthrough complete" \
  --output-json review_adjudication.json \
  --output-md review_adjudication.md
```

---

## 3) Full path (полный local review contour)

### 3.1 Product regression

```bash
pytest -q tests/test_product_regression_pack.py
```

### 3.2 Delta report

```bash
python tests/generate_product_delta_report.py \
  --safe-config config.example.yml \
  --smart-config config.smart_baseline_staging.yml \
  --output-jsonl product_delta_report.jsonl \
  --output-md product_delta_report.md
```

### 3.3 Manual review pack

```bash
python tests/generate_manual_review_pack.py \
  --config config.smart_baseline_staging.yml \
  --output-jsonl manual_review_pack.jsonl \
  --output-md manual_review_pack.md
```

### 3.4 Readiness summary

```bash
python tests/generate_readiness_summary.py \
  --profile-name smart_baseline_staging \
  --config config.smart_baseline_staging.yml \
  --run-product-regression \
  --delta-jsonl product_delta_report.jsonl \
  --delta-md product_delta_report.md \
  --manual-jsonl manual_review_pack.jsonl \
  --manual-md manual_review_pack.md \
  --output-json smart_baseline_readiness_summary.json \
  --output-md smart_baseline_readiness_summary.md
```

### 3.5 Decision record

```bash
python tests/generate_rollout_decision_record.py \
  --bundle-dir . \
  --output-json rollout_decision_record.json \
  --output-md rollout_decision_record.md
```

### 3.6 Review adjudication record

```bash
python tests/generate_review_adjudication_record.py \
  --bundle-dir . \
  --accepted-case-count 10 \
  --caution-case-count 2 \
  --blocking-case-count 0 \
  --reviewer-notes "manual review complete" \
  --output-json review_adjudication.json \
  --output-md review_adjudication.md
```

---

## 4) Expected artifacts и порядок просмотра

Минимальный набор артефактов:
- `product_delta_report.jsonl`
- `product_delta_report.md`
- `manual_review_pack.jsonl`
- `manual_review_pack.md`
- `smart_baseline_readiness_summary.json`
- `smart_baseline_readiness_summary.md`
- `rollout_decision_record.json`
- `rollout_decision_record.md`
- `review_adjudication.json`
- `review_adjudication.md`

Рекомендуемый порядок чтения:
1. `smart_baseline_readiness_summary.md` (статусы/причины),
2. `rollout_decision_record.md` (операционный verdict + next action),
3. `manual_review_pack.md` и `product_delta_report.md` (human evidence),
4. `review_adjudication.md` (формальная фиксация ручного review).

---

## 5) Как интерпретировать итог (fail-closed)

Сигналы stop/hold (не переходить к apply):
- readiness `final_status: not_ready`;
- readiness `config_integrity_status: fail`;
- readiness `product_regression_status: failed`;
- decision `verdict: hold_not_ready`;
- adjudication `review_outcome: blocked` или `needs_follow_up`.

Сигнал “можно только к controlled apply review”:
- decision `verdict: eligible_for_controlled_apply` **и**
- adjudication `review_outcome: approved_for_controlled_apply_review`.

Важно:
- даже при зелёном локальном review outcome это **не означает автоматический production rollout**;
- перед production promotion нужны стандартные environment approvals, CI artifacts и rollout policy checks.
