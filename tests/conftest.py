"""
tests/conftest.py
Мокирует внешние зависимости (groq, telegram, httpx, pdfplumber, docx)
чтобы тесты работали без установки всего сервера.
"""

import sys
from unittest.mock import MagicMock

# ── Мокируем модули, которые есть только на VPS ──────────────────────────────
MOCKED_MODULES = [
    "groq",
    "telegram",
    "telegram.ext",
    "httpx",
    "pdfplumber",
    "docx",
    "python_dotenv",
    "dotenv",
]

for mod_name in MOCKED_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

# Специфичные атрибуты для telegram.ext
sys.modules["telegram"].Update = MagicMock
sys.modules["telegram.ext"].ApplicationBuilder = MagicMock()
sys.modules["telegram.ext"].CommandHandler = MagicMock()
sys.modules["telegram.ext"].MessageHandler = MagicMock()
sys.modules["telegram.ext"].filters = MagicMock()
sys.modules["telegram.ext"].ContextTypes = MagicMock()

# Мок для groq
sys.modules["groq"].Groq = MagicMock()

# Мок для python_dotenv / dotenv
sys.modules["dotenv"].load_dotenv = MagicMock()
