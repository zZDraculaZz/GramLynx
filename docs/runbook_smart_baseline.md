# GramLynx Smart Baseline Runbook

Короткий operational runbook для текущего baseline и безопасной эксплуатации.

## 1) Safe default startup (feature OFF)

Глобальный safe default: candidate generation выключен.

```bash
uvicorn app.main:app --reload
```

Ожидание: сервис стартует без дополнительных baseline-зависимостей.

## 2) Feature-enabled smart baseline startup (recommended)

Рекомендуемый baseline:
- `enable_candidate_generation_ru: true`
- `candidate_backend: symspell`
- `dictionary_source_ru: app/resources/ru_dictionary_v7.txt`
- `max_candidates_ru: 3`
- `max_edit_distance_ru: 1`

Запуск через staging profile:

```bash
GRAMLYNX_CONFIG_YAML=./config.smart_baseline_staging.yml uvicorn app.main:app --reload
```

Shadow-first запуск (candidate apply выключен):

```bash
GRAMLYNX_CONFIG_YAML=./config.smart_baseline_shadow_staging.yml uvicorn app.main:app --reload
```

Подробная rollout-политика: `docs/shadow_first_rollout_policy.md`.

## 2.0) Shipped profile matrix (integrity baseline)

| Profile | Intended use | Key toggles | Notes |
|---|---|---|---|
| `config.example.yml` | safe default local run | `enable_candidate_generation_ru: false` | baseline-safe default OFF |
| `config.smart_baseline_shadow_staging.yml` | shadow-first staging | `enable_candidate_generation_ru: true`, `candidate_shadow_mode_ru: true` | evaluate candidates without apply |
| `config.smart_baseline_staging.yml` | controlled apply staging | `enable_candidate_generation_ru: true`, `candidate_shadow_mode_ru: false` | recommended smart baseline apply profile |

## 2.1) Dockerized smart baseline profile

```bash
docker compose --profile smart-baseline up -d app-smart-baseline
```

Проверка:

```bash
curl -fsS http://localhost:8001/health
# docs: http://localhost:8001/docs
curl -fsS -X POST http://localhost:8001/clean -H "Content-Type: application/json" -d '{"text":"севодня будет встреча","mode":"smart"}'
```

Остановка:

```bash
docker compose --profile smart-baseline down
```

## 3) Preflight expectations (fail-closed)

При `enable_candidate_generation_ru: true` startup preflight должен валидировать:
- backend value (`symspell` или `rapidfuzz`),
- доступность backend dependency,
- существование и читаемость `dictionary_source_ru`.

Если проверка не проходит — сервис **не должен стартовать** (fail-closed).

## 4) Benchmark/report commands

```bash
python tests/eval_candidate_harness.py
python tests/eval_ruspellgold_harness.py
python tests/report_candidate_baseline.py
```

Опционально быстрый локальный smoke:

```bash
python scripts/smoke_smart_baseline.py
```

## 4.1) Pilot/manual review workflow

Локальный pilot review (не observability, а offline artifact):

```bash
python tests/review_pilot_corpus.py
```

## 4.2) Product usefulness regression pack

Локальная проверка компактного acceptance-набора user-like RU текстов:

```bash
pytest -q tests/test_product_regression_pack.py
```

Dataset: `tests/cases/product_regression_user_texts.yml`.

## 4.3) Manual review pack generator (high-signal)

Собрать компактный human-review пакет из существующих eval/benchmark sources:

```bash
python tests/generate_manual_review_pack.py --config config.smart_baseline_staging.yml --limit 40
```

Результаты по умолчанию:
- `manual_review_pack.jsonl`
- `manual_review_pack.md`

Стабильная taxonomy reason buckets (`why_in_pack`):
- `rollback_related`
- `candidate_rejected_unsafe`
- `candidate_ambiguous`
- `candidate_generated_not_applied`
- `expected_mismatch`
- `user_visible_change`
- `protected_context_case`
- `complex_user_like`

Интерпретация перед rollout/apply:
- risk buckets: `rollback_related`, `candidate_rejected_unsafe`, `candidate_ambiguous`, `expected_mismatch`, `protected_context_case`;
- expected smart-improvement buckets: `candidate_generated_not_applied`, `user_visible_change`, `complex_user_like`;
- в markdown summary смотрите counts per reason и primary/secondary reasons по кейсам.

Когда запускать:
- перед controlled apply,
- перед promotion decision,
- после изменения baseline-конфига или rollout-фазы.

## 4.4) Product delta report (safe default vs smart baseline)

Сравнение на одном и том же product acceptance pack:

```bash
python tests/generate_product_delta_report.py --cases tests/cases/product_regression_user_texts.yml --safe-config config.example.yml --smart-config config.smart_baseline_staging.yml
```

Результаты по умолчанию:
- `product_delta_report.jsonl`
- `product_delta_report.md`

Использование перед controlled apply / promotion:
- посмотреть, какие кейсы меняются только в smart baseline,
- сравнить `smart_expected_matches` vs `safe_expected_matches`,
- выделить `cases_needing_human_look` для ручного решения,
- сопоставить delta-cases с taxonomy из manual review pack (`why_in_pack`, primary/secondary reasons).

## 4.5) Local readiness summary (single operator view)

Собрать компактный readiness summary из локально доступных сигналов:

```bash
python tests/generate_readiness_summary.py --config config.smart_baseline_staging.yml --run-product-regression --generate-delta-if-missing --generate-manual-if-missing
```

Выход:
- `smart_baseline_readiness_summary.json`
- `smart_baseline_readiness_summary.md`

Как читать `final_status`:
- `ready_for_review` — config integrity OK, product regression OK, delta/manual artifacts доступны (present/generated),
- `review_needed` — есть missing/not_run/drift сигналы, требуется ручная проверка,
- `not_ready` — fail-closed состояние (например, config fail или product regression fail).

Fail-closed смысл:
- отсутствие артефактов или пропущенные проверки не дают ложноположительный `ready_for_review`.

## 4.6) Local rollout evidence bundle

Собрать все ключевые operator-facing артефакты в один bundle directory:

```bash
python tests/generate_rollout_evidence_bundle.py --config config.smart_baseline_staging.yml --run-product-regression
```

Структура bundle (по умолчанию `rollout_evidence_bundle/smart_baseline_staging/`):
- `readiness_summary.json`
- `readiness_summary.md`
- `product_delta_report.jsonl`
- `product_delta_report.md`
- `manual_review_pack.jsonl`
- `manual_review_pack.md`
- `manifest.json`
- `INDEX.md`

Как использовать:
- сначала открыть `INDEX.md` (human entrypoint),
- затем проверить `manifest.json` (`available_artifacts`, `missing_artifacts`, `final_readiness_status`, `warnings`),
- при missing/failed артефактах считать bundle неполным и не трактовать как готовность к apply.

## 4.7) Local rollout decision record (verdict)

Преобразовать готовый evidence bundle в decision-ready verdict:

```bash
python tests/generate_rollout_decision_record.py --bundle-dir rollout_evidence_bundle/smart_baseline_staging
```

Выход:
- `rollout_decision_record.json`
- `rollout_decision_record.md`

Как читать verdict:
- `hold_not_ready` — блокирующие сигналы/неполный bundle, apply-review не начинать,
- `review_before_apply` — нужен дополнительный ручной review,
- `eligible_for_controlled_apply` — локальные сигналы консистентны для controlled apply review.

Recommended next action:
- `fix_config_drift`
- `rerun_product_regression`
- `inspect_manual_review_pack`
- `regenerate_missing_artifacts`
- `proceed_to_controlled_apply_review`

Fail-closed смысл:
- missing artifacts / warnings / incomplete bundle не дают optimistic verdict.

## 4.8) Review adjudication record (human approval loop)

После ручного review зафиксировать adjudication рядом с bundle:

```bash
python tests/generate_review_adjudication_record.py --bundle-dir rollout_evidence_bundle/smart_baseline_staging --accepted-case-count 10 --caution-case-count 2 --blocking-case-count 0 --reviewer-notes "manual review complete"
```

Выход:
- `review_adjudication.json`
- `review_adjudication.md`

`review_outcome`:
- `blocked`
- `needs_follow_up`
- `approved_for_controlled_apply_review`

Использование с decision record:
- сначала `rollout_decision_record.md` (операционный verdict),
- затем `review_adjudication.md` (формальная human фиксация reviewed/blocking/caution/unresolved),
- если `blocked` или `needs_follow_up` — не переходить к apply до follow-up.


По умолчанию:
- corpus: `tests/cases/pilot_manual_review.jsonl`
- report: `pilot_review_report.md`

Опционально можно передать свои пути:

```bash
python tests/review_pilot_corpus.py --corpus ./my_pilot.jsonl --report ./my_pilot_report.md
```

## 5) CI benchmark artifacts

Используйте workflow **`benchmark-report`** (manual/nightly):
- Actions → `benchmark-report` → Run workflow,
- в run смотреть секцию **Artifacts**,
- artifact `benchmark-report-<run_id>` содержит:
  - `eval_candidate_harness.json`
  - `eval_ruspellgold_harness.json`
  - `baseline_report.md`

## 5.1) CI docker smoke artifacts

Используйте workflow **`docker-smart-baseline-smoke`** (manual/nightly):
- Actions → `docker-smart-baseline-smoke` → Run workflow,
- в run смотреть секцию **Artifacts**,
- artifact `docker-smart-baseline-smoke-<run_id>` содержит краткий summary:
  - `docker_smart_baseline_smoke_summary.json`
  - `docker_smart_baseline_smoke_summary.txt`

## 5.2) CI promotion-ready check artifacts

Используйте workflow **`smart-baseline-promotion-check`** (manual/nightly):
- Actions → `smart-baseline-promotion-check` → Run workflow,
- отдельный ops-layer job `promotion-summary` использует GitHub Environment `smart-baseline-promotion` (можно добавить manual approval protection rule без deploy-шага),
- в run смотреть секцию **Artifacts**,
- artifact `smart-baseline-promotion-summary-<run_id>` содержит:
  - `smart_baseline_promotion_summary.md`
  - `smart_baseline_promotion_summary.json`

Promotion summary явно фиксирует:
- smoke ok / not ok,
- benchmark/report present / not present,
- red flags:
  - `rollback_total > 0`,
  - `candidate_rejected_unsafe_candidate_total > 0`,
  - missing artifacts.

## 5.3) Shadow-first rollout sequence

Для безопасного включения candidate generation используйте formal ops-layer policy:
- `docs/shadow_first_rollout_policy.md`.

Коротко:
- сначала shadow-only (`candidate_shadow_mode_ru: true`),
- затем controlled apply (`candidate_shadow_mode_ru: false`) только при зелёных promotion artifacts,
- при rollback/safety/smoke red flags — откатить фазу rollout.

## 6) Red flags

Считать красными флагами:
- startup fail-closed error при корректном baseline-конфиге,
- `rollback_total > 0` в benchmark/report,
- `candidate_rejected_unsafe_candidate_total > 0` в benchmark/report.

При red flag: не продвигать baseline дальше, сначала устранить причину и повторить preflight + benchmark.
