#!/usr/bin/env python3
"""
bot.py — Vibe Telegram Bot
Smart Router: автоматическое переключение моделей через OpenRouter.
"""

import os
import datetime
import logging
import tempfile
import subprocess
import zipfile
import shutil
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import httpx
from groq import Groq
import pdfplumber
import docx as python_docx

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
        f"Ты умный ассистент для вайбкодинга.\n"
        f"Текущая дата: {current_date}.\n"
        "Используй эту дату при ответах на вопросы о текущих событиях, "
        "актуальных технологиях, рейтингах и версиях ПО.\n"
        "Отвечай кратко и по делу."
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
        "Привет! Я вайб-бот с умным роутером 🤖\n\n"
        "Пиши вопросы — модель выберется автоматически.\n"
        "Или используй префикс:\n"
        "  • @claude — Sonnet для сложных задач\n"
        "  • @gemini — Flash для быстрых ответов\n\n"
        "Голосовые сообщения распознаю через Groq Whisper 🎙️\n"
        "Документы PDF, DOCX, TXT, MD, JSON — читаю и отвечаю по содержимому 📄\n"
        "ZIP-архивы с документами внутри — тоже поддерживаю 📦"
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
    """
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


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает документы PDF и DOCX.
    Извлекает текст → подмешивает в историю → отдаёт в Smart Router.
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
    if ext not in (".pdf", ".docx", ".txt", ".md", ".json", ".zip"):
        await update.message.reply_text(
            f"⚠️ Формат {ext or 'неизвестный'} пока не поддерживается.\n"
            "Поддерживаю: PDF (.pdf), Word (.docx), текст (.txt, .md), JSON (.json), архивы (.zip).\n"
            "Excel, RAR и другие форматы — не поддерживаются 🚧"
        )
        return

    if ext == ".zip":
        await update.message.reply_text(f"📦 Получил архив «{file_name}», распаковываю...")
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
        if ext == ".zip":
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
    logger.info("Bot started with Smart Router (choose_model) + Groq Whisper STT + PDF/DOCX/TXT/MD/JSON/ZIP support")
    app.run_polling()
