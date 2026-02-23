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

```bash
ruff check .
pytest -q
docker build .
```

## Run в Docker

```bash
docker build -t gramlynx:local .
docker run --rm -p 8000:8000 gramlynx:local
```

## Метрики (опционально)

Включение Prometheus-метрик:

```bash
GRAMLYNX_ENABLE_METRICS=1 uvicorn app.main:app --reload
```

Endpoint метрик: `http://localhost:8000/metrics`.
Метрики не содержат пользовательский текст.

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
