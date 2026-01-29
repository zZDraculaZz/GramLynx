# Text → Clean Text Microservice (Skeleton)

Safe text cleaning service with strict guardrails. This repository is a **skeleton** implementation that follows the requested architecture and can run locally without external ML models.

## Quickstart

```bash
pip install -e .
uvicorn app.main:app --reload
```

## API

### POST `/clean`
Request:
```json
{
  "text": "Пример текста...",
  "mode": "strict"
}
```

Response:
```json
{
  "clean_text": "Пример текста..."
}
```

## Modes
- **strict**: minimal changes, high thresholds, more aggressive rollback.
- **smart**: allows a bit more safe formatting while preserving meaning.

## Testing

```bash
pytest -q
```

## Notes
- No external ML models are required. A rule-based model stub is used.
- Protected Zones are masked before any edits and restored at the end.
- Raw user text is not logged by default.
