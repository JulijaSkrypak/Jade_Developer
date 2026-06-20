"""
topic_router.py — Фаза 5: маршрутизация файлов по топикам супергруппы Jade_Developer.

Ответственность:
  - get_topic_id_for_file(filename, mime_type) → int | None
  - forward_to_topic(bot, ...) → None (ошибки не выбрасываются наружу)

Конфигурация читается из .env:
  SUPERGROUP_ID       — ID супергруппы (например -1004295196278)
  TOPIC_TEXTS_ID      — PDF, DOCX, TXT, MD, JSON + голосовые транскрипции
  TOPIC_TABLES_ID     — CSV, XLSX, XLSM
  TOPIC_IMAGES_ID     — фото и видео (file_id), JPG, PNG, WEBP
  TOPIC_ARCHIVES_ID   — ZIP целиком
  TOPIC_ATTENTION_ID  — fallback: неизвестный тип, ошибка парсинга
"""

import io
import os
import re
import html
import logging
import tempfile

logger = logging.getLogger(__name__)


def sanitize_llm_for_html(text: str) -> str:
    """
    Конвертирует текст LLM-ответа в безопасный HTML для Telegram (parse_mode="HTML").

    - **текст** и *текст*  →  <b>текст</b>  (жирный)
    - * пункт             →  — пункт       (маркер списка → тире)
    - Остальное           →  html.escape()  (защита от <, >, &)

    Используется всегда при отображении LLM-саммари с parse_mode="HTML".
    """
    if not text:
        return ""
    # 1. Нормализуем GitHub-style ** → * (одиночные звёздочки)
    text = text.replace("**", "*")
    # 2. Заменяем маркеры списка (* item → — item) ДО разбора bold
    #    (?m) — multiline: ^ совпадает с началом каждой строки
    text = re.sub(r'(?m)^\* ', '— ', text)
    # 3. Разбиваем: чётные части — обычный текст, нечётные — содержимое *bold*
    parts = re.split(r'\*([^*\n]+)\*', text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            result.append(html.escape(part))
        else:
            result.append(f"<b>{html.escape(part)}</b>")
    return "".join(result)


# ── Конфиг из .env ─────────────────────────────────────────────────────────────

def _load_int(var_name: str) -> int | None:
    """Читает переменную окружения как int. Возвращает None при ошибке."""
    raw = os.getenv(var_name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning(f"[topic_router] Переменная {var_name}={raw!r} не является числом — игнорируется")
        return None


SUPERGROUP_ID    = _load_int("SUPERGROUP_ID")
TOPIC_TEXTS_ID   = _load_int("TOPIC_TEXTS_ID")
TOPIC_TABLES_ID  = _load_int("TOPIC_TABLES_ID")
TOPIC_IMAGES_ID  = _load_int("TOPIC_IMAGES_ID")
TOPIC_ARCHIVES_ID = _load_int("TOPIC_ARCHIVES_ID")
TOPIC_ATTENTION_ID = _load_int("TOPIC_ATTENTION_ID")

# ── Таблица маршрутизации по расширению ────────────────────────────────────────

_EXT_TO_TOPIC: dict[str, str] = {}

def _build_ext_map() -> dict[str, str]:
    """Строит словарь расширение→имя_топика."""
    return {
        # Тексты
        ".pdf":  "texts",
        ".docx": "texts",
        ".doc":  "texts",
        ".rtf":  "texts",
        ".txt":  "texts",
        ".md":   "texts",
        ".json": "texts",
        # Таблицы
        ".csv":  "tables",
        ".xlsx": "tables",
        ".xlsm": "tables",
        # Изображения
        ".jpg":  "images",
        ".jpeg": "images",
        ".png":  "images",
        ".webp": "images",
        ".gif":  "images",
        ".mp4":  "images",
        # Архивы
        ".zip":  "archives",
    }

_EXT_TO_TOPIC = _build_ext_map()

# ── MIME-fallback ──────────────────────────────────────────────────────────────

def _topic_name_from_mime(mime_type: str) -> str | None:
    """Определяет имя топика по MIME-типу. Возвращает None если не распознан."""
    if not mime_type:
        return None
    m = mime_type.lower().strip()

    if m.startswith("image/") or m.startswith("video/"):
        return "images"
    if m == "text/csv":
        return "tables"
    if m.startswith("text/"):
        return "texts"
    if m == "application/pdf":
        return "texts"
    # OOXML: spreadsheet → таблицы, word → тексты
    if "spreadsheetml" in m or "excel" in m:
        return "tables"
    if "wordprocessingml" in m or "msword" in m:
        return "texts"
    # Прочие application/* — не распознаём
    return None


# ── Маппинг имени топика → ID ──────────────────────────────────────────────────

def _topic_id_by_name(name: str) -> int | None:
    """
    Возвращает ID топика по его логическому имени.
    При отсутствии нужного ID — fallback на TOPIC_ATTENTION_ID.
    """
    mapping = {
        "texts":    TOPIC_TEXTS_ID,
        "tables":   TOPIC_TABLES_ID,
        "images":   TOPIC_IMAGES_ID,
        "archives": TOPIC_ARCHIVES_ID,
        "attention": TOPIC_ATTENTION_ID,
    }
    topic_id = mapping.get(name)
    if topic_id is None and name != "attention":
        logger.warning(
            f"[topic_router] TOPIC_{name.upper()}_ID не задан в .env — "
            f"используется TOPIC_ATTENTION_ID как fallback"
        )
        topic_id = TOPIC_ATTENTION_ID
    return topic_id


# ── Фаза 5.1: вспомогательные функции для thumbnail и caption ─────────────────

def generate_pdf_thumbnail(pdf_path: str) -> bytes | None:
    """
    Генерирует PNG-превью первой страницы PDF через pdf2image + poppler.
    Возвращает None при любой ошибке (graceful degradation).
    """
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(pdf_path, first_page=1, last_page=1, dpi=100)
        if not pages:
            return None
        buf = io.BytesIO()
        pages[0].save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[topic_router] PDF thumbnail не удалось для {pdf_path!r}: {e}")
        return None


def build_caption(
    file_name: str,
    extracted_text: str | None = None,
    metadata: dict | None = None,
    media_type: str = "document",
) -> str:
    """
    Строит подпись к файлу для отправки в топик (max 1024 символа — лимит Telegram).

    Формат (HTML, parse_mode="HTML"):
      📷 имя_файла             (только для photo — имя не видно в Telegram UI)
      <b>из архива:</b> имя   (если metadata["archive"])
      Листы: ...              (если metadata["sheets"])
      <b>Содержит:</b> <LLM-саммари> (если extracted_text)

    Все пользовательские строки экранируются через html.escape() во избежание
    ошибок «Can't parse entities» при наличии <, >, &, " в именах файлов/тексте.
    """
    parts = []
    # Для фото имя файла явно добавляем в подпись (send_photo не показывает имя)
    if media_type == "photo" and file_name:
        parts.append(f"📷 {html.escape(file_name)}")
    if metadata:
        archive = metadata.get("archive")
        if archive:
            parts.append(f"<b>из архива:</b> {html.escape(str(archive))}")
    if metadata:
        sheets = metadata.get("sheets")
        if sheets:
            parts.append("Листы: " + html.escape(", ".join(str(s) for s in sheets)))
    if extracted_text and extracted_text.strip():
        _safe_text = sanitize_llm_for_html(extracted_text.strip())
        parts.append("<b>Содержит:</b> " + _safe_text)
    return "\n".join(parts)[:1024]


# ── Публичная функция-роутер ───────────────────────────────────────────────────

def get_topic_id_for_file(filename: str, mime_type: str | None = None) -> int | None:
    """
    Определяет thread_id топика для файла.

    Логика:
      1. Ищет расширение в filename (case-insensitive).
      2. Если расширение не найдено или не распознано — пробует mime_type.
      3. Если ни то ни другое не дало результата — TOPIC_ATTENTION_ID.
      4. Если нужный TOPIC_*_ID не задан в .env — fallback на TOPIC_ATTENTION_ID.
      5. Если и TOPIC_ATTENTION_ID не задан — возвращает None (пересылка пропускается).

    Args:
        filename:  имя файла (может быть пустым или без расширения).
        mime_type: MIME-тип файла (опционально, для fallback).

    Returns:
        int — thread_id топика, или None если пересылку нужно пропустить.
    """
    if SUPERGROUP_ID is None:
        logger.warning("[topic_router] SUPERGROUP_ID не задан — пересылка в топики отключена")
        return None

    topic_name: str | None = None

    # 1. По расширению
    ext = os.path.splitext(filename)[1].lower() if filename else ""
    if ext and ext in _EXT_TO_TOPIC:
        topic_name = _EXT_TO_TOPIC[ext]
    elif ext:
        # Расширение есть, но не распознано → ATTENTION
        logger.info(f"[topic_router] Неизвестное расширение {ext!r} — маршрутизируется в ATTENTION")
        topic_name = "attention"

    # 2. MIME-fallback (только если расширение не дало результата)
    if topic_name is None and mime_type:
        topic_name = _topic_name_from_mime(mime_type)
        if topic_name:
            logger.info(f"[topic_router] Расширение не распознано, MIME {mime_type!r} → {topic_name}")

    # 3. Финальный fallback
    if topic_name is None:
        logger.info(
            f"[topic_router] Не удалось определить топик для {filename!r} "
            f"(mime={mime_type!r}) — маршрутизируется в ATTENTION"
        )
        topic_name = "attention"

    return _topic_id_by_name(topic_name)


# ── Публичная функция отправки в топик ────────────────────────────────────────

async def forward_to_topic(
    bot,
    *,
    topic_id: int | None = None,
    topic_name: str | None = None,
    # Один из нижеперечисленных параметров должен быть передан:
    text: str | None = None,
    file_id: str | None = None,
    file_bytes: bytes | None = None,
    file_name: str | None = None,
    media_type: str = "document",  # "document" | "photo" | "video" | "video_note" | "animation"
    # Фаза 5.1: дополнительные параметры для caption и thumbnail
    file_path: str | None = None,       # локальный путь (для генерации PDF thumbnail)
    file_type: str | None = None,       # "pdf", "docx" и т.п.
    extracted_text: str | None = None,  # текст для подписи
    metadata: dict | None = None,       # доп. метаданные (например {"sheets": [...]})
    reply_markup = None,                 # InlineKeyboardMarkup | None
) -> any:
    """
    Пересылает контент в топик супергруппы. Ошибки перехватываются и логируются,
    но НИКОГДА не выбрасываются наружу — основной flow пользователя не нарушается.

    Все caption отправляются с parse_mode="HTML". build_caption() экранирует
    все пользовательские строки через html.escape() — защита от Can't parse entities.

    Returns:
        Message | None — отправленное сообщение, или None при ошибке/пропуске.
    """
    # Определяем thread_id
    if topic_id is None and topic_name is not None:
        topic_id = _topic_id_by_name(topic_name)

    if SUPERGROUP_ID is None:
        logger.debug("[topic_router] SUPERGROUP_ID не задан — пересылка пропущен")
        return None

    if topic_id is None:
        logger.warning("[topic_router] Нет topic_id и TOPIC_ATTENTION_ID не задан — пересылка пропущена")
        return None

    try:
        if text is not None:
            # Текстовое сообщение (транскрипция голоса, расшифровка)
            caption_text = text[:4096]  # Telegram лимит
            msg = await bot.send_message(
                chat_id=SUPERGROUP_ID,
                message_thread_id=topic_id,
                text=caption_text,
                reply_markup=reply_markup,
            )
            logger.info(f"[topic_router] Текст отправлен в топик thread_id={topic_id}")
            return msg

        elif file_id is not None:
            # Отправка через file_id — дёшево, Telegram сам берёт из хранилища
            # Для photo строим caption всегда (имя файла нужно даже без extracted_text)
            _should_build = (extracted_text is not None or metadata is not None) or media_type == "photo"
            _raw_cap = build_caption(file_name or "", extracted_text, metadata, media_type=media_type) if _should_build else None
            caption = (_raw_cap.strip() or None) if _raw_cap is not None else None

            _is_pdf = (
                file_type == "pdf"
                or (file_name and file_name.lower().endswith(".pdf"))
            )
            # Пробуем отправить PDF thumbnail как фото с подписью
            if _is_pdf and file_path:
                thumb = generate_pdf_thumbnail(file_path)
                if thumb:
                    from telegram import InputFile
                    msg = await bot.send_photo(
                        chat_id=SUPERGROUP_ID,
                        message_thread_id=topic_id,
                        photo=InputFile(io.BytesIO(thumb), filename="preview.png"),
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                    logger.info(f"[topic_router] PDF thumbnail отправлен в топик thread_id={topic_id}")
                    return msg

            if media_type == "photo":
                msg = await bot.send_photo(
                    chat_id=SUPERGROUP_ID,
                    message_thread_id=topic_id,
                    photo=file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            elif media_type == "video":
                msg = await bot.send_video(
                    chat_id=SUPERGROUP_ID,
                    message_thread_id=topic_id,
                    video=file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            elif media_type == "video_note":
                msg = await bot.send_video_note(
                    chat_id=SUPERGROUP_ID,
                    message_thread_id=topic_id,
                    video_note=file_id,
                    reply_markup=reply_markup,
                )
            elif media_type == "animation":
                msg = await bot.send_animation(
                    chat_id=SUPERGROUP_ID,
                    message_thread_id=topic_id,
                    animation=file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            else:
                msg = await bot.send_document(
                    chat_id=SUPERGROUP_ID,
                    message_thread_id=topic_id,
                    document=file_id,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            logger.info(f"[topic_router] {media_type} (file_id) отправлен в топик thread_id={topic_id}")
            return msg

        elif file_bytes is not None:
            # Отправка байт (файлы из ZIP — у них нет Telegram file_id)
            from telegram import InputFile
            # Для photo строим caption всегда (имя файла нужно даже без extracted_text)
            _should_build = (extracted_text is not None or metadata is not None) or media_type == "photo"
            _raw_cap = build_caption(file_name or "", extracted_text, metadata, media_type=media_type) if _should_build else None
            caption = (_raw_cap.strip() or None) if _raw_cap is not None else None

            fname = file_name or "file"
            _is_pdf = (
                file_type == "pdf"
                or (fname.lower().endswith(".pdf"))
            )
            # PDF из ZIP: сохраняем во временный файл → генерируем thumbnail
            if _is_pdf:
                _tmp_pdf = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                        tf.write(file_bytes)
                        _tmp_pdf = tf.name
                    thumb = generate_pdf_thumbnail(_tmp_pdf)
                    if thumb:
                        msg = await bot.send_photo(
                            chat_id=SUPERGROUP_ID,
                            message_thread_id=topic_id,
                            photo=InputFile(io.BytesIO(thumb), filename="preview.png"),
                            caption=caption,
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                        )
                        logger.info(f"[topic_router] PDF thumbnail (из bytes) отправлен в топик thread_id={topic_id}")
                        return msg
                except Exception as _thumb_err:
                    logger.warning(f"[topic_router] PDF thumbnail из bytes не удалось: {_thumb_err}")
                finally:
                    if _tmp_pdf and os.path.exists(_tmp_pdf):
                        os.remove(_tmp_pdf)

            input_file = InputFile(io.BytesIO(file_bytes), filename=fname)
            if media_type == "photo":
                msg = await bot.send_photo(
                    chat_id=SUPERGROUP_ID,
                    message_thread_id=topic_id,
                    photo=input_file,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            elif media_type == "video":
                msg = await bot.send_video(
                    chat_id=SUPERGROUP_ID,
                    message_thread_id=topic_id,
                    video=input_file,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            elif media_type == "animation":
                msg = await bot.send_animation(
                    chat_id=SUPERGROUP_ID,
                    message_thread_id=topic_id,
                    animation=input_file,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            else:
                msg = await bot.send_document(
                    chat_id=SUPERGROUP_ID,
                    message_thread_id=topic_id,
                    document=input_file,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            logger.info(f"[topic_router] Файл {fname!r} ({media_type}, bytes) отправлен в топик thread_id={topic_id}")
            return msg

        else:
            logger.warning("[topic_router] forward_to_topic вызван без text/file_id/file_bytes — пропущен")
            return None

    except Exception as e:
        logger.error(
            f"[topic_router] Ошибка пересылки файла {file_name!r} в топик thread_id={topic_id}: {e} "
            f"(основной flow не затронут)"
        )
        return None
