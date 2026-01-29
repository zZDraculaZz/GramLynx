"""Fixture cases for before/after examples."""
from __future__ import annotations

FIXTURES = [
    {
        "name": "basic_whitespace",
        "input_text": "Привет   мир",
        "mode": "strict",
        "expected_clean_text": "Привет мир",
    },
    {
        "name": "url_preserved",
        "input_text": "Ссылка https://example.com  тут",
        "mode": "strict",
        "expected_clean_text": "Ссылка https://example.com тут",
    },
    {
        "name": "email_preserved",
        "input_text": "Почта test@example.com  ок",
        "mode": "smart",
        "expected_clean_text": "Почта test@example.com ок",
    },
    {
        "name": "phone_preserved",
        "input_text": "Телефон +7 999 111-22-33",
        "mode": "strict",
        "expected_clean_text": "Телефон +7 999 111-22-33",
    },
    {
        "name": "date_preserved",
        "input_text": "Дата 2024-01-31",
        "mode": "smart",
        "expected_clean_text": "Дата 2024-01-31",
    },
    {
        "name": "time_preserved",
        "input_text": "Время 10:30",
        "mode": "strict",
        "expected_clean_text": "Время 10:30",
    },
    {
        "name": "ticket_preserved",
        "input_text": "Тикет ABC-123 закрыт",
        "mode": "smart",
        "expected_clean_text": "Тикет ABC-123 закрыт",
    },
    {
        "name": "uuid_preserved",
        "input_text": "ID 123e4567-e89b-12d3-a456-426614174000",
        "mode": "strict",
        "expected_clean_text": "ID 123e4567-e89b-12d3-a456-426614174000",
    },
    {
        "name": "path_preserved",
        "input_text": "Путь /var/log/syslog",
        "mode": "smart",
        "expected_clean_text": "Путь /var/log/syslog",
    },
    {
        "name": "command_preserved",
        "input_text": "Запусти git status",
        "mode": "strict",
        "expected_clean_text": "Запусти git status",
    },
    {
        "name": "code_block_preserved",
        "input_text": "```{"\"a\"": 1}```",
        "mode": "smart",
        "expected_clean_text": "```{"\"a\"": 1}```",
    },
    {
        "name": "number_preserved",
        "input_text": "Сумма 1 000,50 руб",
        "mode": "strict",
        "expected_clean_text": "Сумма 1 000,50 руб",
    },
    {
        "name": "mixed_spaces",
        "input_text": "Смешанный   текст  с  пробелами",
        "mode": "smart",
        "expected_clean_text": "Смешанный текст с пробелами",
    },
    {
        "name": "newline_normalize",
        "input_text": "Строка\n\nвторая",
        "mode": "strict",
        "expected_clean_text": "Строка вторая",
    },
    {
        "name": "capitalized_name",
        "input_text": "Встреча с Иван Иванов завтра",
        "mode": "smart",
        "expected_clean_text": "Встреча с Иван Иванов завтра",
    },
    {
        "name": "percent_preserved",
        "input_text": "Скидка 10% сегодня",
        "mode": "strict",
        "expected_clean_text": "Скидка 10% сегодня",
    },
    {
        "name": "range_preserved",
        "input_text": "Диапазон 10-20",
        "mode": "smart",
        "expected_clean_text": "Диапазон 10-20",
    },
    {
        "name": "email_and_space",
        "input_text": "Пиши   на a@b.co",
        "mode": "strict",
        "expected_clean_text": "Пиши на a@b.co",
    },
    {
        "name": "path_windows",
        "input_text": "Файл C:\\Temp\\log.txt",
        "mode": "smart",
        "expected_clean_text": "Файл C:\\Temp\\log.txt",
    },
    {
        "name": "unicode_norm",
        "input_text": "Тест\u200bневидимый",
        "mode": "strict",
        "expected_clean_text": "Тестневидимый",
    },
]
