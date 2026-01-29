"""Regex patterns for protected zones."""
from __future__ import annotations

import re

URL = re.compile(r"https?://[^\s]+", re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
DATE = re.compile(r"\b\d{2}[./-]\d{2}[./-]\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
NUMBER = re.compile(r"\b\d[\d\s,.-]*\d\b")
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
TICKET = re.compile(r"\b[A-Z]{2,10}-\d{1,6}\b")
PATH = re.compile(r"\b(?:[A-Za-z]:\\|/)[^\s]+")
COMMAND = re.compile(r"\b(?:sudo|git|docker|kubectl|python|pip)\b[^\n]*")
CODE_BLOCK = re.compile(r"```[\s\S]*?```|<code>[\s\S]*?</code>|\{\s*\"[^\"]+\"\s*:\s*[^}]+\}", re.MULTILINE)

PATTERNS = {
    "url": URL,
    "email": EMAIL,
    "phone": PHONE,
    "date": DATE,
    "time": TIME,
    "number": NUMBER,
    "uuid": UUID,
    "ticket": TICKET,
    "path": PATH,
    "command": COMMAND,
    "code": CODE_BLOCK,
}
