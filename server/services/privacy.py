"""Privacy filter — strip sensitive data before storage."""
import re

PATTERNS = [
    (r'sk-[a-zA-Z0-9]{32,}', '[API_KEY_REDACTED]'),
    (r'sk-ant-[a-zA-Z0-9\-_]{32,}', '[ANTHROPIC_KEY_REDACTED]'),
    (r'Bearer\s+[a-zA-Z0-9\-_\.]{20,}', '[TOKEN_REDACTED]'),
    (r'password\s*[:=]\s*\S{3,}', '[PASSWORD_REDACTED]'),
    (r'api[_-]?key\s*[:=]\s*\S{8,}', '[API_KEY_REDACTED]'),
    (r'1[3-9]\d{9}', '[PHONE_REDACTED]'),  # Chinese mobile numbers
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[EMAIL_REDACTED]'),
]


def filter_sensitive(text: str) -> str:
    """Strip API keys, tokens, passwords, phone numbers, emails from text."""
    if not text:
        return text
    for pattern, replacement in PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text
