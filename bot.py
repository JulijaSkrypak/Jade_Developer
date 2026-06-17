#!/usr/bin/env python3
"""
bot.py — JadeBridge Telegram Bot
Smart Router: автоматическое переключение моделей через OpenRouter.
"""

import os
import datetime
import logging
import tempfile
import subprocess
import zipfile
import shutil
import math
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import httpx
from groq import Groq
import pdfplumber
import docx as python_docx
import openpyxl

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ── Модели ────────────────────────────────────────────────────────────────────
MODEL_SIMPLE   = "google/gemini-3.5-flash"          # быстрые ответы
MODEL_COMPLEX  = "anthropic/claude-sonnet-4-6"       # сложные задачи
MODEL_ROUTER   = "google/gemini-3.5-flash"            # классификатор
MODEL_VOICE    = "google/gemini-3.5-flash"           # голос/фото — всегда flash

# ── Отображаемые имена моделей для уведомлений ──────────────────────────────────
MODEL_FRIENDLY_NAMES = {
    "google/gemini-3.5-flash": "Gemini 3.5",
    "anthropic/claude-sonnet-4-6": "Claude Sonnet 4.6",
    "anthropic/claude-opus-4-8": "Claude Opus 4.8",
}

def get_friendly_name(model_id: str) -> str:
    return MODEL_FRIENDLY_NAMES.get(model_id, model_id)

# ── Системный промпт роутера ───────────────────────────────────────────────────
ROUTER_SYSTEM_PROMPT = (
    "Ты классификатор. Ответь ТОЛЬКО словом simple или complex.\n"
    "simple = приветствие, факт, перевод, короткий вопрос, что такое X\n"
    "complex = написать код, архитектура, отладка, баг, рефакторинг, "
    "сравнение технологий, объясни как работает X подробно, спроектируй"
)

logging.basicConfig(level=logging.INFO)
# Отключаем логирование HTTP-запросов (содержащих токен бота) в stdout
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

user_histories: dict[int, list] = {}
groq_client = Groq(api_key=GROQ_API_KEY)


# ══════════════════════════════════════════════════════════════════════════════
# SMART ROUTER
# ══════════════════════════════════════════════════════════════════════════════

async def choose_model(text: str) -> tuple[str, str, str]:
    """
    Определяет модель и уведомление для текстового сообщения.

    Returns:
        (model_id, clean_text, notification_message)
        notification_message — пустая строка, если уведомление не нужно.
    """
    low = text.strip().lower()

    # 1. Проверяем явные префиксы
    if low.startswith("@claude"):
        clean = text.strip()[7:].strip()   # убираем "@claude"
        friendly = get_friendly_name(MODEL_COMPLEX)
        return MODEL_COMPLEX, clean, f"🎯 Подключаю {friendly}..."

    if low.startswith("@gemini"):
        clean = text.strip()[7:].strip()   # убираем "@gemini"
        friendly = get_friendly_name(MODEL_SIMPLE)
        return MODEL_SIMPLE, clean, f"⚡ Подключаю {friendly}..."

    # 2. Router LLM — быстрый вызов для классификации
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL_ROUTER,
                    "messages": [
                        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                        {"role": "user",   "content": text},
                    ],
                    "max_tokens": 5,
                },
            )
            resp.raise_for_status()
            choices = resp.json().get("choices", [])
            content = None
            if choices:
                content = choices[0].get("message", {}).get("content")

            if content is not None:
                verdict = content.strip().lower()
                logger.info(f"Router verdict: '{verdict}' for: {text[:60]!r}")
            else:
                logger.warning("Router LLM returned empty/null content. Defaulting to simple.")
                verdict = "simple"
    except Exception as e:
        logger.warning(f"Router LLM failed, defaulting to simple: {e}")
        verdict = "simple"

    if "complex" in verdict:
        friendly = get_friendly_name(MODEL_COMPLEX)
        return MODEL_COMPLEX, text, f"🧠 Подключаю {friendly}..."
    else:
        return MODEL_SIMPLE, text, ""   # simple — без уведомления



# ══════════════════════════════════════════════════════════════════════════════
# СИСТЕМНЫЙ ПРОМПТ (с динамической датой)
# ══════════════════════════════════════════════════════════════════════════════

def get_system_prompt() -> str:
    """Возвращает системный промпт с актуальной датой. Вызывается при каждом запросе."""
    current_date = datetime.datetime.now().strftime("%d %B %Y")
    prompt = (
        f"Ты умный ассистент JadeBridge.\n"
        f"Текущая дата: {current_date}.\n"
        "Используй эту дату при ответах на вопросы о текущих событиях, "
        "актуальных технологиях, рейтингах и версиях ПО.\n"
        "Отвечай кратко и по делу.\n"
        "\n"
        "ВАЖНОЕ ПРАВИЛО для работы с Excel-таблицами:\n"
        "Если в данных встречается пометка вида [формула, не вычислено: <формула>], "
        "это означает, что значение ячейки НЕ было сохранено в исходном файле — "
        "показан только текст формулы, но не её результат. "
        "В этом случае ты ОБЯЗАН явно сообщить пользователю об этом факте. "
        "Ты можешь высказать предположение о вероятном результате ТОЛЬКО если "
        "прямо обозначишь его как предположение — например: "
        "«вероятно, результат — X, но это не подтверждено файлом: "
        "формула не была пересчитана». "
        "НИКОГДА не приводи предположительный результат как установленный факт, "
        "независимо от того, насколько простой кажется формула."
    )
    import logging
    logging.getLogger(__name__).info(f"[SYSTEM PROMPT] Дата в промпте: {current_date}")
    return prompt

# ══════════════════════════════════════════════════════════════════════════════
# LLM — единый интерфейс (смена модели через .env без правки кода)
# ══════════════════════════════════════════════════════════════════════════════

async def ask_llm(user_id: int, user_message: str, model: str) -> str:
    """Отправляет сообщение в OpenRouter с нужной моделью, хранит историю."""
    if user_id not in user_histories:
        user_histories[user_id] = []
    user_histories[user_id].append({"role": "user", "content": user_message})

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "system", "content": get_system_prompt()}] + user_histories[user_id],
            },
        )
        response.raise_for_status()
        data = response.json()

    reply = data["choices"][0]["message"]["content"]
    user_histories[user_id].append({"role": "assistant", "content": reply})
    return reply


# ══════════════════════════════════════════════════════════════════════════════
# АУДИО (Groq Whisper)
# ══════════════════════════════════════════════════════════════════════════════

async def transcribe_audio(ogg_path: str) -> str:
    """Конвертирует .ogg → .mp3 через ffmpeg, затем транскрибирует через Groq Whisper."""
    mp3_path = ogg_path.replace(".ogg", ".mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", "-q:a", "4", mp3_path],
        check=True,
        capture_output=True,
    )
    with open(mp3_path, "rb") as f:
        transcription = groq_client.audio.transcriptions.create(
            file=(os.path.basename(mp3_path), f.read()),
            model="whisper-large-v3",
            language="ru",
            response_format="text",
        )
    os.remove(mp3_path)
    return transcription


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я JadeBridge — бот с умным роутером 🤖\n\n"
        "Пиши вопросы — модель выберется автоматически.\n"
        "Или используй префикс:\n"
        "  • @claude — Sonnet для сложных задач\n"
        "  • @gemini — Flash для быстрых ответов\n\n"
        "Голосовые сообщения распознаю через Groq Whisper 🎙️\n"
        "Документы PDF, DOCX, TXT, MD, JSON — читаю и отвечаю по содержимому 📄\n"
        "ZIP-архивы с документами внутри — тоже поддерживаю 📦\n"
        "Excel таблицы .xlsx — анализирую, поддержка формул и нескольких листов 📊"
    )


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
            )
            if r.status_code == 200:
                await update.message.reply_text("Pong! ✓ OpenRouter живой.")
            else:
                await update.message.reply_text(f"OpenRouter ответил: {r.status_code}")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_histories[user_id] = []
    await update.message.reply_text("История очищена ✓")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает текстовые сообщения со Smart Router.
    Голос и фото — в отдельных обработчиках, здесь не трогаются.
    При активном xlsx-диалоге — перенаправляет ответ пользователя в handle_xlsx_dialog.
    """
    # ── Перехват xlsx-диалога ────────────────────────────────────────────────
    if context.user_data.get("xlsx_pending"):
        await handle_xlsx_dialog(update, context)
        return
    # ────────────────────────────────────────────────────────────────────────

    user_id = update.effective_user.id
    raw_text = update.message.text

    # Определяем модель
    model, clean_text, notification = await choose_model(raw_text)

    # Уведомление — только для complex / явных префиксов
    if notification:
        await update.message.reply_text(notification)
    else:
        await update.message.reply_text("Думаю... 🤔")

    try:
        reply = await ask_llm(user_id, clean_text, model)
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"LLM error (model={model}): {e}")
        await update.message.reply_text(f"Ошибка LLM: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает голосовые сообщения.
    Всегда использует MODEL_VOICE (Gemini Flash) — не затронуто роутером.
    """
    user_id = update.effective_user.id
    await update.message.reply_text("🎙️ Слышу тебя, распознаю...")

    try:
        voice = update.message.voice
        voice_file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            ogg_path = tmp.name

        await voice_file.download_to_drive(ogg_path)

        recognized_text = await transcribe_audio(ogg_path)
        os.remove(ogg_path)

        if not recognized_text or not recognized_text.strip():
            await update.message.reply_text("❌ Не удалось распознать речь. Попробуй ещё раз.")
            return

        await update.message.reply_text(f"📝 Распознано:\n{recognized_text}")
        await update.message.reply_text("Думаю... 🤔")
        reply = await ask_llm(user_id, recognized_text, MODEL_VOICE)
        await update.message.reply_text(reply)

    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg error: {e.stderr.decode()}")
        await update.message.reply_text("❌ Ошибка конвертации аудио (ffmpeg).")
    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await update.message.reply_text(f"❌ Ошибка обработки голосового: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# ДОКУМЕНТЫ (PDF / DOCX / TXT / MD / JSON / ZIP)
# ══════════════════════════════════════════════════════════════════════════════

MAX_DOC_CHARS = 15_000  # лимит символов для передачи в LLM

# ── ZIP-лимиты (страховочные, не защита от атак) ─────────────────────────────
ZIP_MAX_FILES       = 20          # максимум файлов в архиве
ZIP_MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 МБ суммарный распакованный размер

# Расширения, которые умеем парсить внутри ZIP
ZIP_SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md", ".json"}

# Системный мусор от macOS — игнорируем
ZIP_IGNORE_PREFIXES = ("__MACOSX", ".DS_Store")

# ── XLSX-лимиты ───────────────────────────────────────────────────────────────
# ~10K токенов — оставляет запас для системного промпта, истории диалога и ответа модели.
# Обоснование: claude-sonnet-4-6 имеет 200K контекст; xlsx таблица в 40K символов ≈ 10K токенов
# — это 5% контекста, что разумно при наличии истории диалога.
XLSX_MAX_CHARS = 40_000


def extract_text_from_pdf(path: str) -> str:
    """Извлекает текст из PDF через pdfplumber (все страницы)."""
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def extract_text_from_docx(path: str) -> str:
    """Извлекает текст из DOCX: параграфы + таблицы."""
    doc = python_docx.Document(path)
    parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                parts.append(row_text)
    return "\n".join(parts)


def extract_text_from_plain(path: str) -> str:
    """Извлекает текст из .txt/.md — обычное чтение файла в UTF-8."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def extract_text_from_json(path: str) -> str:
    """Извлекает и красиво форматирует JSON для удобства чтения LLM."""
    import json
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    try:
        parsed = json.loads(raw)
        return json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        # Если JSON невалидный — вернуть как обычный текст, не падать
        return raw


def extract_text_from_zip(zip_path: str, archive_name: str) -> tuple[str, bool]:
    """
    Распаковывает ZIP-архив и извлекает текст из поддерживаемых файлов.

    Returns:
        (combined_text, limits_exceeded)
        limits_exceeded=True если превышены лимиты (в этом случае combined_text
        содержит сообщение об ошибке для пользователя).
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        all_entries = zf.infolist()

        # Фильтруем системный мусор macOS ДО проверки лимитов
        entries = [
            e for e in all_entries
            if not any(
                e.filename.startswith(prefix) or os.path.basename(e.filename) == prefix
                for prefix in ZIP_IGNORE_PREFIXES
            )
            and not e.is_dir()
        ]

        total_files = len(entries)
        total_size = sum(e.file_size for e in entries)

        # Проверяем лимиты ДО распаковки
        if total_files > ZIP_MAX_FILES:
            msg = (
                f"⚠️ В архиве слишком много файлов: {total_files} шт.\n"
                f"Лимит: {ZIP_MAX_FILES} файлов.\n"
                "Пожалуйста, уменьшите количество файлов в архиве и отправьте снова."
            )
            return msg, True

        total_size_mb = total_size / (1024 * 1024)
        if total_size > ZIP_MAX_TOTAL_BYTES:
            msg = (
                f"⚠️ Суммарный размер файлов в архиве слишком большой: {total_size_mb:.1f} МБ.\n"
                f"Лимит: {ZIP_MAX_TOTAL_BYTES // (1024*1024)} МБ.\n"
                "Пожалуйста, уменьшите архив и отправьте снова."
            )
            return msg, True

        # Распаковываем во временную папку
        tmp_dir = tempfile.mkdtemp(prefix="vibe_zip_")
        try:
            zf.extractall(tmp_dir)

            processed_texts = []
            unsupported_files = []
            processed_count = 0

            for entry in entries:
                file_path = os.path.join(tmp_dir, entry.filename)
                short_name = entry.filename  # путь внутри архива (может включать подпапки)

                ext = os.path.splitext(entry.filename)[1].lower()

                if ext not in ZIP_SUPPORTED_EXTS:
                    unsupported_files.append(short_name)
                    continue

                try:
                    if ext == ".pdf":
                        text = extract_text_from_pdf(file_path)
                    elif ext == ".docx":
                        text = extract_text_from_docx(file_path)
                    elif ext in (".txt", ".md"):
                        text = extract_text_from_plain(file_path)
                    elif ext == ".json":
                        text = extract_text_from_json(file_path)
                    else:
                        unsupported_files.append(short_name)
                        continue

                    if text and text.strip():
                        processed_texts.append(f"[Файл: {short_name}]\n{text.strip()}")
                        processed_count += 1
                    else:
                        unsupported_files.append(f"{short_name} (пустой)")

                except Exception as file_err:
                    logger.warning(f"ZIP: не удалось прочитать {short_name}: {file_err}")
                    unsupported_files.append(f"{short_name} (ошибка чтения)")

            # Собираем результат
            header = (
                f"[Архив: {archive_name}]\n"
                f"[Обработано файлов: {processed_count} из {total_files}]"
            )
            parts = [header] + processed_texts

            if unsupported_files:
                parts.append(
                    "[Не обработаны (формат не поддерживается): "
                    + ", ".join(unsupported_files)
                    + "]"
                )

            combined = "\n\n".join(parts)
            return combined, False

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# EXCEL (.xlsx)
# ══════════════════════════════════════════════════════════════════════════════

def sheet_to_markdown(ws) -> str:
    """
    Конвертирует лист openpyxl в Markdown-таблицу.

    - Первая строка → заголовки (| Col1 | Col2 | ...)
    - Вторая строка → разделитель (| --- | --- | ...)
    - Остальные строки → данные
    - Формулы с вычисленным значением → показываем значение
    - Формулы без вычисленного значения (None) → "[формула, не вычислено]"
    """
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return ""

    def fmt_cell(val) -> str:
        """Форматирует значение ячейки в строку."""
        if val is None:
            return ""
        s = str(val)
        # Если это формула (начинается с =) и значение None уже заменено пустой строкой
        # выше — этот случай не сработает. Но если data_only=False случайно вернул формулу:
        if s.startswith("="):
            return f"[формула, не вычислено: {s}]"
        # Экранируем | чтобы не сломать markdown-таблицу
        return s.replace("|", "\\|")

    def fmt_row(row_vals) -> str:
        return "| " + " | ".join(fmt_cell(v) for v in row_vals) + " |"

    header = rows[0]
    col_count = len(header)

    lines = []
    lines.append(fmt_row(header))
    lines.append("| " + " | ".join(["---"] * col_count) + " |")

    for row in rows[1:]:
        lines.append(fmt_row(row))

    return "\n".join(lines)


def _open_xlsx_data(path: str) -> dict:
    """
    Открывает .xlsx файл с data_only=True и читает все листы в память.
    Возвращает словарь:
    {
        "sheet_names": [...],
        "sheets": {
            "SheetName": {
                "markdown": "...",
                "rows": N,
                "cols": M,
            },
            ...
        }
    }
    Вызывает исключение при повреждённом файле.
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    result = {"sheet_names": wb.sheetnames, "sheets": {}}

    for name in wb.sheetnames:
        try:
            ws = wb[name]
            rows_list = list(ws.iter_rows(values_only=True))
            n_rows = max(0, len(rows_list) - 1)  # не считаем строку заголовков
            n_cols = len(rows_list[0]) if rows_list else 0

            # Проверяем наличие None-значений в формульных ячейках:
            # openpyxl с data_only=True вернёт None если файл не был пересохранён
            # через Excel/LibreOffice. В этом случае нужно открыть без data_only
            # и взять саму формулу как fallback.
            has_uncalculated = False
            for row in rows_list:
                for val in row:
                    if val is None:
                        # Может быть просто пустая ячейка — не паникуем
                        pass

            markdown = sheet_to_markdown(ws)

            # Fallback: если формулы не вычислены (data_only=True вернул None)
            # открываем ещё раз без data_only чтобы взять текст формул
            wb2 = openpyxl.load_workbook(path, data_only=False)
            ws2 = wb2[name]
            rows2 = list(ws2.iter_rows(values_only=True))

            # Если в data_only версии ячейка None, а в raw версии — формула
            merged_rows = []
            for r_idx, (row_d, row_r) in enumerate(zip(rows_list, rows2)):
                merged = []
                for v_data, v_raw in zip(row_d, row_r):
                    if v_data is None and v_raw is not None and str(v_raw).startswith("="):
                        # Формула не была вычислена
                        merged.append(f"[формула, не вычислено: {v_raw}]")
                        has_uncalculated = True
                    else:
                        merged.append(v_data)
                merged_rows.append(tuple(merged))

            if has_uncalculated:
                # Пересчитываем markdown с fallback-значениями
                import io
                from openpyxl.worksheet.worksheet import Worksheet
                # Создаём временный лист для форматирования через sheet_to_markdown
                # путём прямой передачи строк
                lines = []

                def fmt_cell_merged(val) -> str:
                    if val is None:
                        return ""
                    s = str(val)
                    if s.startswith("="):
                        return f"[формула, не вычислено: {s}]"
                    return s.replace("|", "\\|")

                def fmt_row_merged(row_vals) -> str:
                    return "| " + " | ".join(fmt_cell_merged(v) for v in row_vals) + " |"

                if merged_rows:
                    header = merged_rows[0]
                    col_count = len(header)
                    lines.append(fmt_row_merged(header))
                    lines.append("| " + " | ".join(["---"] * col_count) + " |")
                    for row in merged_rows[1:]:
                        lines.append(fmt_row_merged(row))
                markdown = "\n".join(lines)

            result["sheets"][name] = {
                "markdown": markdown,
                "rows": n_rows,
                "cols": n_cols,
            }

        except Exception as sheet_err:
            logger.warning(f"XLSX: ошибка чтения листа '{name}': {sheet_err}")
            result["sheets"][name] = {
                "markdown": f"[Ошибка чтения листа '{name}': {sheet_err}]",
                "rows": 0,
                "cols": 0,
            }

    return result


def build_sheet_text(sheet_name: str, sheet_data: dict) -> str:
    """
    Формирует итоговый текст для одного листа, готовый к передаче в LLM.
    Формат:
        [Лист: «Название» | N строк × M столбцов]
        | Col1 | Col2 | ...
        | --- | --- | ...
        | ... | ... | ...
    """
    return (
        f"[Лист: «{sheet_name}» | {sheet_data['rows']} строк × {sheet_data['cols']} столбцов]\n"
        f"{sheet_data['markdown']}"
    )


def split_text_into_parts(text: str, max_chars: int) -> list[str]:
    """
    Делит большой текст на части по max_chars символов,
    стараясь разбивать по переносу строки (не рвать строки таблицы).
    """
    if len(text) <= max_chars:
        return [text]

    parts = []
    lines = text.split("\n")
    current = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # +1 за \n
        if current_len + line_len > max_chars and current:
            parts.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len

    if current:
        parts.append("\n".join(current))

    return parts


async def _process_xlsx_sheets(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sheet_names: list[str],
    xlsx_data: dict,
    file_name: str,
    caption: str,
    user_id: int,
) -> None:
    """
    Общая логика обработки выбранных листов xlsx:
    - Строит текст, проверяет лимит, при необходимости запрашивает выбор усечения.
    - Если данные в норме — сразу отправляет в LLM.
    """
    # Собираем текст для выбранных листов
    parts_text = []
    for name in sheet_names:
        if name in xlsx_data["sheets"]:
            parts_text.append(build_sheet_text(name, xlsx_data["sheets"][name]))

    header = f"[Файл: {file_name} | Листы: {', '.join(sheet_names)}]\n"
    combined = header + "\n\n".join(parts_text)

    if len(combined) > XLSX_MAX_CHARS:
        # Сохраняем состояние и спрашиваем пользователя
        n_parts = math.ceil(len(combined) / XLSX_MAX_CHARS)
        approx_rows_limit = sum(
            xlsx_data["sheets"].get(n, {}).get("rows", 0) for n in sheet_names
        )
        rows_per_part = max(1, approx_rows_limit // n_parts)

        context.user_data["xlsx_pending"] = {
            "state": "awaiting_size_choice",
            "file_name": file_name,
            "sheet_names": sheet_names,
            "xlsx_data": xlsx_data,
            "combined_text": combined,
            "caption": caption,
            "user_id": user_id,
            "n_parts": n_parts,
            "rows_per_part": rows_per_part,
        }
        await update.message.reply_text(
            f"⚠️ Таблица слишком большая ({len(combined):,} символов, лимит {XLSX_MAX_CHARS:,}).\n"
            f"Примерно {n_parts} части.\n\n"
            f"Что делать?\n"
            f"1️⃣ — Обрезать: взять первые ~{XLSX_MAX_CHARS} символов\n"
            f"2️⃣ — Прислать частями ({n_parts} сообщения)"
        )
        return

    # Данные в норме — отправляем в LLM
    await _send_xlsx_to_llm(update, context, combined, caption, user_id)


async def _send_xlsx_to_llm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    combined: str,
    caption: str,
    user_id: int,
) -> None:
    """Формирует промпт и отправляет данные xlsx в LLM через Smart Router."""
    if caption.strip():
        user_prompt = f"{combined}\n\n{caption.strip()}"
    else:
        user_prompt = (
            f"{combined}\n\n"
            "[Системный запрос: пользователь прислал таблицу без конкретного вопроса. "
            "Кратко резюмируй содержимое: о чём таблица, ключевые данные, структура.]"
        )

    model, clean_prompt, notification = await choose_model(user_prompt)
    if notification:
        await update.message.reply_text(notification)
    else:
        await update.message.reply_text("Думаю... 🤔")

    reply = await ask_llm(user_id, clean_prompt, model)
    await update.message.reply_text(reply)


async def handle_xlsx_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает ответы пользователя в диалоге xlsx (выбор листа / усечение).
    Вызывается из handle_text когда context.user_data['xlsx_pending'] существует.
    """
    pending = context.user_data.get("xlsx_pending", {})
    state = pending.get("state")
    user_text = update.message.text.strip().lower()

    if state == "awaiting_sheet_choice":
        sheet_names_all: list[str] = pending["sheet_names_all"]
        file_name: str = pending["file_name"]
        xlsx_data: dict = pending["xlsx_data"]
        caption: str = pending["caption"]
        user_id: int = pending["user_id"]

        chosen_sheets: list[str] = []

        if user_text in ("все", "all", "0"):
            chosen_sheets = sheet_names_all
        else:
            # Парсим номера: "1", "1 2", "1,2", "1, 3"
            import re
            numbers = re.findall(r"\d+", user_text)
            for n_str in numbers:
                idx = int(n_str) - 1
                if 0 <= idx < len(sheet_names_all):
                    name = sheet_names_all[idx]
                    if name not in chosen_sheets:
                        chosen_sheets.append(name)

        if not chosen_sheets:
            sheets_list = "\n".join(
                f"{i+1}. {name}" for i, name in enumerate(sheet_names_all)
            )
            await update.message.reply_text(
                f"❓ Не понял выбор. Пожалуйста, введи номер листа (1–{len(sheet_names_all)}) "
                f"или напиши «все».\n\nДоступные листы:\n{sheets_list}"
            )
            return

        # Очищаем ожидание — обработаем листы (возможно войдём в диалог размера)
        del context.user_data["xlsx_pending"]
        await update.message.reply_text(f"📊 Обрабатываю лист(ы): {', '.join(chosen_sheets)}...")
        await _process_xlsx_sheets(update, context, chosen_sheets, xlsx_data, file_name, caption, user_id)

    elif state == "awaiting_size_choice":
        file_name: str = pending["file_name"]
        sheet_names: list[str] = pending["sheet_names"]
        xlsx_data: dict = pending["xlsx_data"]
        combined: str = pending["combined_text"]
        caption: str = pending["caption"]
        user_id: int = pending["user_id"]
        n_parts: int = pending["n_parts"]

        del context.user_data["xlsx_pending"]

        if user_text in ("1", "обрезать", "обрезать"):
            truncated = combined[:XLSX_MAX_CHARS]
            truncated += "\n\n[текст таблицы обрезан до первых символов по лимиту]"
            await update.message.reply_text("✂️ Беру первые данные...")
            await _send_xlsx_to_llm(update, context, truncated, caption, user_id)

        elif user_text in ("2", "частями", "частями"):
            text_parts = split_text_into_parts(combined, XLSX_MAX_CHARS)
            await update.message.reply_text(f"📨 Отправляю {len(text_parts)} части...")
            for i, part in enumerate(text_parts, 1):
                part_text = f"[Часть {i} из {len(text_parts)}]\n{part}"
                await _send_xlsx_to_llm(update, context, part_text, caption if i == 1 else "", user_id)
        else:
            n_parts = pending.get("n_parts", 2)
            context.user_data["xlsx_pending"] = pending  # восстанавливаем
            await update.message.reply_text(
                "❓ Не понял. Введи 1️⃣ (обрезать) или 2️⃣ (частями)."
            )
    else:
        # Неизвестное состояние — очищаем
        context.user_data.pop("xlsx_pending", None)
        await update.message.reply_text(
            "⚠️ Сессия обработки xlsx устарела. Пожалуйста, пришли файл заново."
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает документы: PDF, DOCX, TXT, MD, JSON, ZIP, XLSX.
    Извлекает текст → подмешивает в историю → отдаёт в Smart Router.
    Для XLSX: при нескольких листах запускает диалог с пользователем.
    """
    user_id = update.effective_user.id
    document = update.message.document
    file_name = document.file_name or "document"
    caption = update.message.caption or ""

    # Проверка размера (Telegram лимит на скачивание ботом — 20MB)
    if document.file_size and document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "❌ Файл слишком большой (более 20 МБ).\n"
            "Telegram не позволяет боту скачивать файлы такого размера."
        )
        return

    # Проверка расширения
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in (".pdf", ".docx", ".txt", ".md", ".json", ".zip", ".xlsx"):
        await update.message.reply_text(
            f"⚠️ Формат {ext or 'неизвестный'} пока не поддерживается.\n"
            "Поддерживаю: PDF (.pdf), Word (.docx), текст (.txt, .md), JSON (.json), "
            "архивы (.zip), Excel (.xlsx).\n"
            "RAR и другие форматы — не поддерживаются 🚧"
        )
        return

    if ext == ".zip":
        await update.message.reply_text(f"📦 Получил архив «{file_name}», распаковываю...")
    elif ext == ".xlsx":
        await update.message.reply_text(f"📊 Получил таблицу «{file_name}», читаю...")
    else:
        await update.message.reply_text(f"📄 Получил документ «{file_name}», читаю...")

    # Скачиваем файл во временную папку
    tmp_path = None
    try:
        tg_file = await context.bot.get_file(document.file_id)
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)

        # Извлекаем текст
        if ext == ".xlsx":
            # ── XLSX: читаем все листы в память сразу, tmp файл больше не нужен ──
            try:
                xlsx_data = _open_xlsx_data(tmp_path)
            except Exception as xlsx_err:
                logger.error(f"XLSX: не удалось открыть файл '{file_name}': {xlsx_err}")
                await update.message.reply_text(
                    f"❌ Не удалось открыть файл Excel.\n"
                    f"Возможно, файл повреждён или не является корректным .xlsx файлом.\n"
                    f"Ошибка: {xlsx_err}"
                )
                return

            sheet_names = xlsx_data["sheet_names"]

            if len(sheet_names) == 0:
                await update.message.reply_text(
                    "⚠️ В файле нет листов. Возможно, файл пустой или повреждён."
                )
                return

            if len(sheet_names) == 1:
                # Один лист — обрабатываем сразу без диалога
                await _process_xlsx_sheets(
                    update, context, sheet_names, xlsx_data, file_name, caption, user_id
                )
            else:
                # Несколько листов — запускаем диалог
                sheets_list = "\n".join(
                    f"{i+1}. {name}" for i, name in enumerate(sheet_names)
                )
                context.user_data["xlsx_pending"] = {
                    "state": "awaiting_sheet_choice",
                    "file_name": file_name,
                    "sheet_names_all": sheet_names,
                    "xlsx_data": xlsx_data,
                    "caption": caption,
                    "user_id": user_id,
                }
                await update.message.reply_text(
                    f"📋 Файл «{file_name}» содержит {len(sheet_names)} листа(ов):\n"
                    f"{sheets_list}\n\n"
                    f"Напиши номер листа (1–{len(sheet_names)}), несколько через запятую, "
                    f"или напиши «все» для обработки всех листов."
                )
            return  # xlsx обработан (или запущен диалог) — дальше не идём

        elif ext == ".zip":
            try:
                raw_text, limits_exceeded = extract_text_from_zip(tmp_path, file_name)
            except zipfile.BadZipFile:
                await update.message.reply_text(
                    "❌ Архив повреждён или не является корректным ZIP-файлом.\n"
                    "Пожалуйста, проверьте целостность архива и попробуйте снова."
                )
                return
            if limits_exceeded:
                await update.message.reply_text(raw_text)
                return
        elif ext == ".pdf":
            raw_text = extract_text_from_pdf(tmp_path)
        elif ext == ".docx":
            raw_text = extract_text_from_docx(tmp_path)
        elif ext in (".txt", ".md"):
            raw_text = extract_text_from_plain(tmp_path)
        elif ext == ".json":
            raw_text = extract_text_from_json(tmp_path)

        if not raw_text or not raw_text.strip():
            await update.message.reply_text(
                "⚠️ Не удалось извлечь текст из документа.\n"
                "Возможно, это отсканированный PDF без распознанного текста."
            )
            return

        # Обрезаем до лимита
        truncated = False
        if len(raw_text) > MAX_DOC_CHARS:
            raw_text = raw_text[:MAX_DOC_CHARS]
            truncated = True

        # Формируем сообщение для LLM
        # Для ZIP архив уже содержит заголовки файлов, не дублируем
        if ext == ".zip":
            doc_content = raw_text
        else:
            doc_content = f"[Документ: {file_name}]\n\n{raw_text}"
        if truncated:
            doc_content += "\n\n[текст обрезан, архив слишком большой]" if ext == ".zip" else "\n\n[текст обрезан, документ слишком длинный]"

        # Если пользователь написал подпись — это его вопрос к документу/архиву
        # Если нет — просим LLM кратко резюмировать
        if caption.strip():
            user_prompt = f"{doc_content}\n\n{caption.strip()}"
        else:
            if ext == ".zip":
                summary_request = (
                    "[Системный запрос: пользователь прислал архив без конкретного вопроса. "
                    "Кратко резюмируй содержимое архива: что это за файлы, "
                    "о чём они, ключевые моменты.]"
                )
            else:
                summary_request = (
                    "[Системный запрос: пользователь не указал конкретный вопрос. "
                    "Кратко резюмируй содержимое документа: о чём он, "
                    "ключевые моменты, структура.]"
                )
            user_prompt = f"{doc_content}\n\n{summary_request}"

        # Прогоняем через Smart Router — как обычный текст
        model, clean_prompt, notification = await choose_model(user_prompt)
        if notification:
            await update.message.reply_text(notification)
        else:
            await update.message.reply_text("Думаю... 🤔")

        reply = await ask_llm(user_id, clean_prompt, model)
        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Document handler error: {e}")
        await update.message.reply_text(
            f"❌ Не удалось обработать документ.\n"
            f"Возможно, файл повреждён или недоступен для чтения.\n"
            f"Ошибка: {e}"
        )
    finally:
        # Удаляем временный файл в любом случае
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ping", ping))
app.add_handler(CommandHandler("clear", clear))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))
app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

if __name__ == "__main__":
    logger.info(
        "Bot started with Smart Router (choose_model) + Groq Whisper STT "
        "+ PDF/DOCX/TXT/MD/JSON/ZIP/XLSX support"
    )
    app.run_polling()
