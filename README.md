# Микросервис «Text → Clean Text»

Production-ready микросервис очистки текста с жёсткими ограничениями.

## Гарантии сервиса

- Контракт API: вход `text + mode`, выход только `clean_text`.
- Сервис не добавляет объяснения, теги, леммы, морфологию и не делает перефразирование.
- Protected Zones не меняются byte-to-byte.
- При нарушении guardrails применяется rollback.

## Быстрый старт

Требуется Python: **3.10.x**.

```bash
pip install -e ".[dev,metrics,morph]"
# расширенный офлайн/dev scorer stack (включая KenLM):
# pip install -e ".[dev,metrics,morph,scorers]"
ruff check .
pytest -q
uvicorn app.main:app --reload
pytest -q
```

## API

### POST `/clean`
Запрос:
```json
{
  "text": "Пример текста...",
  "mode": "strict"
}
```

Ответ:
```json
{
  "clean_text": "Пример текста..."
}
```

## Режимы
- **strict**: минимальные изменения, высокие пороги уверенности, агрессивный откат.
- **smart**: допускает чуть больше безопасного форматирования при сохранении смысла.

## Тестирование

Для полного стандартного runtime-safe набора тестов (candidate backend tests, safety/fuzz и опциональный morph safety-layer) используйте установку с dev+metrics+morph extras:

```bash
pip install -e ".[dev,metrics,morph]"
```

Для расширенного офлайн/dev scorer workflow GramLynx v2 (включая KenLM scorer) используйте scorer extra:

```bash
pip install -e ".[dev,metrics,morph,scorers]"
```

KenLM поддерживается для офлайн контекстного scorer evaluation и A/B replay, но не включается как default runtime `/clean` dependency. Runtime activation остаётся evidence-gated.

```bash
ruff check .
pytest -q
docker build .
```

Offline evaluation harness for candidate-generation modes:

```bash
python tests/eval_candidate_harness.py
```

Offline external RU benchmark harness (RuSpellGold-style layer):

```bash
python tests/eval_ruspellgold_harness.py
```

Offline baseline summary report (internal + external harnesses):

```bash
python tests/report_candidate_baseline.py
```

Tiny V2 scorer comparison on curated slice (offline/dev):

```bash
# deterministic fallback path (RankBasedScorer vs ReverseRankScorer)
python tests/report_v2_slice_scorer_comparison.py   --dictionary app/resources/ru_dictionary_v7.txt   --mode deterministic

# KenLM model prep from local corpus (one sentence per line):
python tests/prepare_v2_kenlm_model.py   --corpus /path/to/lm_corpus.txt   --output /tmp/gramlynx_v2_local.arpa

# KenLM path (RankBasedScorer vs KenLMScorer)
# requires scorer extra + KenLM model path
GRAMLYNX_V2_KENLM_MODEL_PATH=/tmp/gramlynx_v2_local.arpa python tests/report_v2_slice_scorer_comparison.py   --dictionary app/resources/ru_dictionary_v7.txt   --mode kenlm
```

`tests/prepare_v2_kenlm_model.py` reuses the existing research KenLM bigram-ARPA preparation helper and only standardizes corpus-path -> model-path preparation for offline/dev runs.

If KenLM backend/model is unavailable, the runner stays fail-closed for KenLM mode and reports `kenlm_mode_blocker` while falling back to deterministic challenger.

Offline pilot/manual review utility (local artifact):

```bash
python tests/review_pilot_corpus.py
```

By default it reads `tests/cases/pilot_manual_review.jsonl` and writes `pilot_review_report.md`.

Product usefulness regression pack (user-like RU texts, exact-match acceptance):

```bash
pytest -q tests/test_product_regression_pack.py
```

Dataset: `tests/cases/product_regression_user_texts.yml`.

CI docker smoke job:
- non-blocking workflow `docker-smart-baseline-smoke` runs on manual trigger (`workflow_dispatch`) and nightly schedule,
- builds/starts `app-smart-baseline`, checks `/health`, `/docs`, and safe `/clean` status-only smoke calls,
- uploads smoke summary artifacts.

CI benchmark/report job:
- non-blocking workflow `benchmark-report` runs on manual trigger (`workflow_dispatch`) and nightly schedule,
- uploads artifacts with aggregated outputs from `eval_candidate_harness`, `eval_ruspellgold_harness` and `report_candidate_baseline`.

CI promotion-check job:
- non-blocking workflow `smart-baseline-promotion-check` runs on manual trigger (`workflow_dispatch`) and nightly schedule,
- builds promotion summary from benchmark/report + docker smoke artifacts,
- emits explicit status flags: smoke ok/not ok, benchmark/report present/not present, red flags (`rollback_total > 0`, `candidate_rejected_unsafe_candidate_total > 0`, missing artifacts),
- uploads `smart_baseline_promotion_summary.md` + `smart_baseline_promotion_summary.json` artifact for formal staging-ready → promotion-ready decision.

Можно переопределить путь к benchmark dataset через `GRAMLYNX_RUSPELLGOLD_PATH` (JSONL).
Для сравнения словарей в harness можно задать `GRAMLYNX_EVAL_DICTIONARY_SOURCE_RU` (например, `app/resources/ru_dictionary_v7.txt`).
Если выбран backend `rapidfuzz`/`symspell`, а зависимость отсутствует, harness завершится fail-closed ошибкой.

Operational runbook: `docs/runbook_smart_baseline.md`.

Shadow-first rollout policy: `docs/shadow_first_rollout_policy.md`.

### Dockerized smart baseline profile

Поднять контейнер с recommended smart baseline profile:

```bash
docker compose --profile smart-baseline up -d app-smart-baseline
```

Проверки:

```bash
curl -fsS http://localhost:8001/health
# docs: http://localhost:8001/docs
curl -fsS -X POST http://localhost:8001/clean -H "Content-Type: application/json" -d '{"text":"севодня будет встреча","mode":"smart"}'
```

Остановить профиль:

```bash
docker compose --profile smart-baseline down
```

## Local staging profile (recommended smart baseline)

Opt-in local staging profile for feature-enabled smart baseline (safe default remains off):

```bash
GRAMLYNX_CONFIG_YAML=./config.smart_baseline_staging.yml uvicorn app.main:app --reload
```

Shadow-first staging profile (candidate generation ON, apply OFF):

```bash
GRAMLYNX_CONFIG_YAML=./config.smart_baseline_shadow_staging.yml uvicorn app.main:app --reload
```

Quick smoke check (startup + `/health` + 3 safe `/clean` requests):

```bash
python scripts/smoke_smart_baseline.py
```

## Метрики (опционально)

## YAML-конфигурация (опционально)

Чтобы загрузить правила из YAML, укажите путь в `GRAMLYNX_CONFIG_YAML`:

```bash
GRAMLYNX_CONFIG_YAML=./config.example.yml uvicorn app.main:app --reload
```

Если YAML невалидный, сервис не стартует (fail-closed).


RulePack в YAML (`rulepack`) задаёт безопасные детерминированные правки:
- `typo_map_strict` — более узкий набор замен для strict,
- `typo_map_smart` — более широкий набор замен для smart,
- `enable_candidate_generation_ru` + `candidate_backend=...` — консервативный fallback-кандидат только для smart (если `typo_map` не сработал); глобальный safe default остаётся `enable_candidate_generation_ru: false` (feature выключен),
- рекомендуемый стабильный baseline для feature-enabled smart mode: `candidate_backend: symspell`, `dictionary_source_ru: app/resources/ru_dictionary_v7.txt`, `max_candidates_ru: 3`, `max_edit_distance_ru: 1`,
- при `enable_candidate_generation_ru: true` на старте выполняется fail-closed preflight: проверяются backend/dependency и доступность `dictionary_source_ru`,
- `candidate_shadow_mode_ru` — evaluation-режим: candidates считаются, но не применяются,
- `max_candidates_ru` / `max_edit_distance_ru` / `dictionary_source_ru` — строгие лимиты candidate generation,
- `punctuation.fix_space_before/fix_space_after` — механика пробелов вокруг `, . : ; ! ?`.

Включение Prometheus-метрик:

```bash
GRAMLYNX_ENABLE_METRICS=1 uvicorn app.main:app --reload
```

Endpoint метрик: `http://localhost:8000/metrics`.
Включён gzip-ответ (`should_gzip=True`), если клиент запрашивает `Accept-Encoding: gzip`.
Пользовательский текст не экспортируется. Примеры метрик: `gramlynx_rollbacks_total`, `gramlynx_pz_spans_total`, `gramlynx_changed_ratio_bucket`, `gramlynx_confidence_bucket`.

Лимит тела запроса задаётся env `GRAMLYNX_MAX_BODY_BYTES` (по умолчанию `1048576`).
Пример: `GRAMLYNX_MAX_BODY_BYTES=262144 uvicorn app.main:app --reload`.

## Audit-лог запросов

На каждый HTTP-запрос пишется одна структурированная строка аудита с `request_id` для корреляции.
Пример: `{"event":"request_audit","request_id":"...","method":"POST","path":"/clean","status_code":200,"duration_ms":12.3,"input_len_chars":10,"output_len_chars":10,"changed_ratio":0.0,"confidence":1.0,"rollback_applied":false,"pz_spans_count":0}`.
В audit-логе нет полей `text`/`clean_text` и нет содержимого пользовательского текста.

## Run в Docker

```bash
docker build -t gramlynx:local .
docker run --rm -p 8000:8000 gramlynx:local
```

Uvicorn пишет `http://0.0.0.0:8000` — это bind-адрес. В браузере открывать нужно
`http://localhost:8000/docs` (или `http://127.0.0.1:8000/docs`).

Проверка health endpoint локально: `http://localhost:8000/health` (или `http://127.0.0.1:8000/health`).

## Плагинная система стадий

Стадии собираются через реестр `stage_name -> StageClass`. Фабрика `build_pipeline` формирует пайплайн на основе `PolicyConfig.enabled_stages`.

Пример кастомной стадии находится в `app/core/stages/custom_example.py` и выключен по умолчанию. Чтобы включить:

1. Добавьте `"custom_example"` в `enabled_stages` нужной политики.
2. Убедитесь, что стадия не меняет Protected Zones (иначе guardrails откатят изменения).

## Примечания
- Внешние ML-модели не требуются: используется rule-based заглушка.
- Protected Zones маскируются до правок и восстанавливаются в конце.
- Сырые пользовательские тексты по умолчанию не логируются.
