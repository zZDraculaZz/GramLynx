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

## 5) CI benchmark artifacts

Используйте workflow **`benchmark-report`** (manual/nightly):
- Actions → `benchmark-report` → Run workflow,
- в run смотреть секцию **Artifacts**,
- artifact `benchmark-report-<run_id>` содержит:
  - `eval_candidate_harness.json`
  - `eval_ruspellgold_harness.json`
  - `baseline_report.md`

## 6) Red flags

Считать красными флагами:
- startup fail-closed error при корректном baseline-конфиге,
- `rollback_total > 0` в benchmark/report,
- `candidate_rejected_unsafe_candidate_total > 0` в benchmark/report.

При red flag: не продвигать baseline дальше, сначала устранить причину и повторить preflight + benchmark.
