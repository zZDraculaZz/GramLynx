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

Когда запускать:
- перед controlled apply,
- перед promotion decision,
- после изменения baseline-конфига или rollout-фазы.


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
