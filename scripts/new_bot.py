#!/usr/bin/env python3
"""
bot.py — Vibe Telegram Bot
Smart Router: автоматическое переключение моделей через OpenRouter.
"""

import os
import logging
import tempfile
import subprocess
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import httpx
from groq import Groq

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
            verdict = resp.json()["choices"][0]["message"]["content"].strip().lower()
            logger.info(f"Router verdict: '{verdict}' for: {text[:60]!r}")
    except Exception as e:
        logger.warning(f"Router LLM failed, defaulting to simple: {e}")
        verdict = "simple"

    if "complex" in verdict:
        friendly = get_friendly_name(MODEL_COMPLEX)
        return MODEL_COMPLEX, text, f"🧠 Подключаю {friendly}..."
    else:
        return MODEL_SIMPLE, text, ""   # simple — без уведомления


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
                "messages": user_histories[user_id],
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
        "Голосовые сообщения распознаю через Groq Whisper 🎙️"
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
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("ping", ping))
app.add_handler(CommandHandler("clear", clear))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.VOICE, handle_voice))

if __name__ == "__main__":
    logger.info("Bot started with Smart Router (choose_model) + Groq Whisper STT")
    app.run_polling()
