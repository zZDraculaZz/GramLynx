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
pip install -e ".[dev]"
ruff check .
pytest -q
uvicorn app.main:app --reload
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

```bash
ruff check .
pytest -q
```

## Метрики (опционально)

## YAML-конфигурация (опционально)

Чтобы загрузить правила из YAML, укажите путь в `GRAMLYNX_CONFIG_YAML`:

```bash
GRAMLYNX_CONFIG_YAML=./config.example.yml uvicorn app.main:app --reload
```

Если YAML невалидный, сервис не стартует (fail-closed).

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
