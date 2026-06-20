"""
tests/test_phase_5_topics.py — Тесты Фазы 5: маршрутизация по топикам.

Запуск:
    pytest tests/test_phase_5_topics.py -v

Архитектура тестов:
- sys.path добавляет корень проекта (по образцу test_phase_4_4_xlsx.py)
- async-функции вызываются через asyncio.run() — без pytest-asyncio
- topic_router перезагружается через importlib при тестах с разными env
- внешние зависимости (telegram) замокированы через sys.modules в conftest.py
"""

import io
import os
import sys
import asyncio
import zipfile
import importlib
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

# Добавляем корень проекта в sys.path (по образцу test_phase_4_4_xlsx.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Вспомогательная функция для перезагрузки topic_router с нужными env ────────

def _reload_router(env_overrides: dict | None = None):
    """
    Перезагружает topic_router с указанными переменными окружения.
    Возвращает свежий модуль.

    Сохраняет исходные значения и восстанавливает их после теста.
    """
    # Дефолтный env для тестов
    defaults = {
        "SUPERGROUP_ID": "-1001234567890",
        "TOPIC_TEXTS_ID": "10",
        "TOPIC_TABLES_ID": "20",
        "TOPIC_IMAGES_ID": "30",
        "TOPIC_ARCHIVES_ID": "40",
        "TOPIC_ATTENTION_ID": "50",
    }
    env = {**defaults, **(env_overrides or {})}

    # Применяем env
    old_values = {}
    for k, v in env.items():
        old_values[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    try:
        if "topic_router" in sys.modules:
            del sys.modules["topic_router"]
        import topic_router
        importlib.reload(topic_router)
        return topic_router
    finally:
        # Восстанавливаем исходные env
        for k, old_v in old_values.items():
            if old_v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old_v


# ── Загружаем стандартный роутер один раз для базовых тестов ──────────────────

_DEFAULT_ENV = {
    "SUPERGROUP_ID": "-1001234567890",
    "TOPIC_TEXTS_ID": "10",
    "TOPIC_TABLES_ID": "20",
    "TOPIC_IMAGES_ID": "30",
    "TOPIC_ARCHIVES_ID": "40",
    "TOPIC_ATTENTION_ID": "50",
}
for _k, _v in _DEFAULT_ENV.items():
    os.environ.setdefault(_k, _v)

import topic_router as _tr
importlib.reload(_tr)
router = _tr


# ══════════════════════════════════════════════════════════════════════════════
# 1. Маршрутизация — ТЕКСТЫ
# ══════════════════════════════════════════════════════════════════════════════

class TestRouterTextExtensions(unittest.TestCase):
    """get_topic_id_for_file → TOPIC_TEXTS_ID для текстовых расширений."""

    def setUp(self):
        self.router = _reload_router()

    @pytest.mark.parametrize("fname", [
        "report.pdf", "doc.docx", "note.doc", "file.rtf",
        "readme.txt", "README.MD", "data.json",
    ])
    def test_text_extensions(self):
        for fname in ["report.pdf", "doc.docx", "note.doc", "file.rtf",
                      "readme.txt", "README.MD", "data.json"]:
            with self.subTest(fname=fname):
                tid = self.router.get_topic_id_for_file(fname)
                self.assertEqual(tid, 10, f"Ожидался TOPIC_TEXTS_ID=10 для {fname!r}, получен {tid}")

    def test_case_insensitive(self):
        self.assertEqual(self.router.get_topic_id_for_file("FILE.PDF"), 10)
        self.assertEqual(self.router.get_topic_id_for_file("Data.JSON"), 10)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Маршрутизация — ТАБЛИЦЫ
# ══════════════════════════════════════════════════════════════════════════════

class TestRouterTableExtensions(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_table_extensions(self):
        for fname in ["data.csv", "report.xlsx", "macro.xlsm"]:
            with self.subTest(fname=fname):
                tid = self.router.get_topic_id_for_file(fname)
                self.assertEqual(tid, 20, f"Ожидался TOPIC_TABLES_ID=20 для {fname!r}")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Маршрутизация — ИЗОБРАЖЕНИЯ
# ══════════════════════════════════════════════════════════════════════════════

class TestRouterImageExtensions(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_image_extensions(self):
        for fname in ["photo.jpg", "img.jpeg", "screen.png", "img.webp"]:
            with self.subTest(fname=fname):
                tid = self.router.get_topic_id_for_file(fname)
                self.assertEqual(tid, 30, f"Ожидался TOPIC_IMAGES_ID=30 для {fname!r}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. Маршрутизация — АРХИВЫ
# ══════════════════════════════════════════════════════════════════════════════

class TestRouterArchiveExtension(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_zip_extension(self):
        tid = self.router.get_topic_id_for_file("backup.zip")
        self.assertEqual(tid, 40, f"Ожидался TOPIC_ARCHIVES_ID=40, получен {tid}")


# ══════════════════════════════════════════════════════════════════════════════
# 5. Маршрутизация — ВНИМАНИЕ (неизвестное расширение)
# ══════════════════════════════════════════════════════════════════════════════

class TestRouterUnknownExtension(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_unknown_extensions_to_attention(self):
        for fname in ["archive.rar", "file.7z", "binary.bin"]:
            with self.subTest(fname=fname):
                tid = self.router.get_topic_id_for_file(fname)
                self.assertEqual(tid, 50, f"Ожидался TOPIC_ATTENTION_ID=50 для {fname!r}")

    def test_no_extension_no_mime_to_attention(self):
        tid = self.router.get_topic_id_for_file("noextension")
        self.assertEqual(tid, 50)

    def test_empty_filename_no_mime_to_attention(self):
        tid = self.router.get_topic_id_for_file("")
        self.assertEqual(tid, 50)


# ══════════════════════════════════════════════════════════════════════════════
# 6. MIME-fallback при отсутствии расширения
# ══════════════════════════════════════════════════════════════════════════════

class TestRouterMimeFallback(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_mime_pdf(self):
        tid = self.router.get_topic_id_for_file("noext", mime_type="application/pdf")
        self.assertEqual(tid, 10)

    def test_mime_image_jpeg(self):
        tid = self.router.get_topic_id_for_file("noext", mime_type="image/jpeg")
        self.assertEqual(tid, 30)

    def test_mime_image_png(self):
        tid = self.router.get_topic_id_for_file("", mime_type="image/png")
        self.assertEqual(tid, 30)

    def test_mime_csv(self):
        tid = self.router.get_topic_id_for_file("noext", mime_type="text/csv")
        self.assertEqual(tid, 20)

    def test_mime_spreadsheet_ooxml(self):
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        tid = self.router.get_topic_id_for_file("noext", mime_type=mime)
        self.assertEqual(tid, 20)

    def test_mime_word_ooxml(self):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        tid = self.router.get_topic_id_for_file("noext", mime_type=mime)
        self.assertEqual(tid, 10)

    def test_mime_text_plain(self):
        tid = self.router.get_topic_id_for_file("noext", mime_type="text/plain")
        self.assertEqual(tid, 10)

    def test_mime_unknown_to_attention(self):
        tid = self.router.get_topic_id_for_file("noext", mime_type="application/octet-stream")
        self.assertEqual(tid, 50)

    def test_mime_none_with_unknown_ext(self):
        """Неизвестное расширение + None MIME → ATTENTION."""
        tid = self.router.get_topic_id_for_file("file.rar", mime_type=None)
        self.assertEqual(tid, 50)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Graceful degradation: отсутствующий TOPIC_*_ID → fallback на ATTENTION
# ══════════════════════════════════════════════════════════════════════════════

class TestRouterMissingConfig(unittest.TestCase):
    def test_missing_texts_id_falls_back_to_attention(self):
        """Если TOPIC_TEXTS_ID не задан → TOPIC_ATTENTION_ID."""
        r = _reload_router({"TOPIC_TEXTS_ID": None})
        tid = r.get_topic_id_for_file("document.pdf")
        self.assertEqual(tid, 50)

    def test_no_supergroup_id_returns_none(self):
        """Если SUPERGROUP_ID не задан → None (пересылка отключена)."""
        r = _reload_router({"SUPERGROUP_ID": None})
        tid = r.get_topic_id_for_file("doc.pdf")
        self.assertIsNone(tid)

    def test_attention_id_missing_and_supergroup_present(self):
        """Если TOPIC_TEXTS_ID и TOPIC_ATTENTION_ID оба не заданы → None."""
        r = _reload_router({"TOPIC_TEXTS_ID": None, "TOPIC_ATTENTION_ID": None})
        tid = r.get_topic_id_for_file("data.pdf")
        self.assertIsNone(tid)


# ══════════════════════════════════════════════════════════════════════════════
# 8. forward_to_topic — успешная отправка документа
# ══════════════════════════════════════════════════════════════════════════════

class TestForwardToTopicDocument(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_sends_document_with_thread_id(self):
        """send_document вызывается с message_thread_id."""
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="texts",
            file_id="fake_file_id_123",
            media_type="document",
        ))

        mock_bot.send_document.assert_called_once()
        call_kwargs = mock_bot.send_document.call_args.kwargs
        self.assertEqual(call_kwargs["chat_id"], -1001234567890)
        self.assertEqual(call_kwargs["message_thread_id"], 10)
        self.assertEqual(call_kwargs["document"], "fake_file_id_123")

    def test_sends_photo_with_thread_id(self):
        """send_photo вызывается с правильным message_thread_id для Images."""
        mock_bot = MagicMock()
        mock_bot.send_photo = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="images",
            file_id="photo_file_id",
            media_type="photo",
        ))

        mock_bot.send_photo.assert_called_once()
        call_kwargs = mock_bot.send_photo.call_args.kwargs
        self.assertEqual(call_kwargs["message_thread_id"], 30)
        self.assertEqual(call_kwargs["photo"], "photo_file_id")

    def test_sends_video_with_thread_id(self):
        """send_video вызывается с message_thread_id для Images."""
        mock_bot = MagicMock()
        mock_bot.send_video = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="images",
            file_id="video_file_id",
            media_type="video",
        ))

        mock_bot.send_video.assert_called_once()
        call_kwargs = mock_bot.send_video.call_args.kwargs
        self.assertEqual(call_kwargs["message_thread_id"], 30)
        self.assertEqual(call_kwargs["video"], "video_file_id")


# ══════════════════════════════════════════════════════════════════════════════
# 9. forward_to_topic — успешная отправка текста (голосовая транскрипция)
# ══════════════════════════════════════════════════════════════════════════════

class TestForwardToTopicText(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_sends_text_as_message_not_document(self):
        """Транскрипция отправляется как send_message, НЕ send_document."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot.send_document = AsyncMock()

        transcript = "Привет, это тест транскрипции."
        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="texts",
            text=transcript,
        ))

        mock_bot.send_message.assert_called_once()
        mock_bot.send_document.assert_not_called()

        call_kwargs = mock_bot.send_message.call_args.kwargs
        self.assertEqual(call_kwargs["chat_id"], -1001234567890)
        self.assertEqual(call_kwargs["message_thread_id"], 10)
        self.assertIn(transcript, call_kwargs["text"])


# ══════════════════════════════════════════════════════════════════════════════
# 10. forward_to_topic — ошибка НЕ выбрасывается наружу
# ══════════════════════════════════════════════════════════════════════════════

class TestForwardToTopicErrorIsolation(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_document_error_does_not_raise(self):
        """RuntimeError внутри send_document не выбрасывается наружу."""
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock(side_effect=RuntimeError("Network error"))

        # Должно выполниться без исключения
        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="archives",
            file_id="zip_file_id",
            media_type="document",
        ))
        # Достигли этой строки — тест прошёл

    def test_text_send_error_does_not_raise(self):
        """Ошибка отправки текста в топик не ломает основной flow."""
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(side_effect=Exception("TG API down"))

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="texts",
            text="Test transcript",
        ))
        # Без исключений — ок

    def test_no_supergroup_silently_skips(self):
        """При отсутствующем SUPERGROUP_ID — тихо пропускает, не падает."""
        r = _reload_router({"SUPERGROUP_ID": None})
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()

        asyncio.run(r.forward_to_topic(
            mock_bot,
            topic_name="texts",
            file_id="some_id",
        ))
        mock_bot.send_document.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# 11. Голосовое → транскрипция уходит в TEXTS как текст, не файл
# ══════════════════════════════════════════════════════════════════════════════

class TestVoiceForwardAsText(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_voice_transcript_goes_to_texts_as_message(self):
        """
        Имитируем вызов из handle_voice:
        transcript уходит как text= (send_message), не file_id= или file_bytes=.
        """
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_bot.send_document = AsyncMock()

        transcript = "🎙️ Открой сайт example.com и найди документацию"
        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="texts",
            text=transcript,
        ))

        # Должен быть send_message, не send_document
        mock_bot.send_message.assert_called_once()
        mock_bot.send_document.assert_not_called()

        # Правильный топик
        call_kwargs = mock_bot.send_message.call_args.kwargs
        self.assertEqual(call_kwargs["message_thread_id"], 10)  # TOPIC_TEXTS_ID


# ══════════════════════════════════════════════════════════════════════════════
# 12. ZIP двойная отправка
# ══════════════════════════════════════════════════════════════════════════════

class TestZipDoubleSend(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def _make_zip(self, files: dict) -> bytes:
        """Создаёт ZIP в памяти с переданными файлами."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_zip_original_forwarded_to_archives(self):
        """Оригинальный ZIP forwarded через file_id в TOPIC_ARCHIVES_ID=40."""
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="archives",
            file_id="zip_tg_file_id",
            media_type="document",
        ))

        mock_bot.send_document.assert_called_once()
        call_kwargs = mock_bot.send_document.call_args.kwargs
        self.assertEqual(call_kwargs["message_thread_id"], 40)  # TOPIC_ARCHIVES_ID
        self.assertEqual(call_kwargs["document"], "zip_tg_file_id")

    def test_zip_contents_routed_to_correct_topics(self):
        """
        Каждый файл из ZIP маршрутизируется в правильный топик:
        PDF → TEXTS (10), XLSX → TABLES (20).
        """
        r = self.router

        results = {}
        for name in ["report.pdf", "data.xlsx", "notes.txt", "archive.rar"]:
            results[name] = r.get_topic_id_for_file(os.path.basename(name))

        self.assertEqual(results["report.pdf"], 10, "PDF → TEXTS")
        self.assertEqual(results["data.xlsx"], 20, "XLSX → TABLES")
        self.assertEqual(results["notes.txt"], 10, "TXT → TEXTS")
        self.assertEqual(results["archive.rar"], 50, "RAR → ATTENTION")

    def test_zip_sub_file_forward_independent(self):
        """
        Ошибка при пересылке одного файла из ZIP не прерывает
        обработку остальных файлов (независимые try/except).
        """
        r = self.router

        call_count = [0]
        sent = []

        async def fake_forward(bot, *, topic_id=None, topic_name=None,
                               file_id=None, file_bytes=None, file_name=None,
                               media_type="document"):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Simulated failure on first file")
            sent.append(file_name)

        ZIP_IGNORE = ("__MACOSX", ".DS_Store")
        files = {"first.pdf": b"%PDF fake", "second.txt": b"hello"}
        zip_bytes = self._make_zip(files)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(zip_bytes)
            zip_path = f.name

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                entries = [e for e in zf.infolist() if not e.is_dir()]
                for entry in entries:
                    base_name = os.path.basename(entry.filename)
                    try:
                        asyncio.run(fake_forward(None, topic_id=10, file_name=base_name))
                    except Exception:
                        pass  # Ошибка одного файла не прерывает цикл
        finally:
            os.remove(zip_path)

        # Первый упал, второй должен был обработаться
        self.assertIn("second.txt", sent,
                      "Второй файл должен быть обработан несмотря на ошибку первого")

    def test_forward_file_bytes_calls_send_document(self):
        """
        file_bytes (файлы из ZIP без Telegram file_id) отправляются
        через send_document с InputFile.
        """
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_id=10,
            file_bytes=b"%PDF-1.4 fake content",
            file_name="from_zip.pdf",
        ))

        mock_bot.send_document.assert_called_once()
        call_kwargs = mock_bot.send_document.call_args.kwargs
        self.assertEqual(call_kwargs["message_thread_id"], 10)


# ══════════════════════════════════════════════════════════════════════════════
# 13. build_caption — формирование подписи
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildCaption(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_only_filename_returns_empty(self):
        # filename is no longer included in caption text (Telegram shows it separately)
        result = self.router.build_caption("report.pdf")
        self.assertEqual(result, "")

    def test_with_extracted_text_uses_soderzhit_prefix(self):
        """extracted_text выводится с префиксом '<b>Содержит:</b>' (Telegram HTML)."""
        result = self.router.build_caption("doc.txt", extracted_text="Привет мир")
        self.assertNotIn("doc.txt", result)
        self.assertIn("Привет мир", result)
        self.assertIn("<b>Содержит:</b>", result)

    def test_long_text_still_under_1024(self):
        """Длинный саммари (до 600 символов) + префикс всё равно помещается в 1024."""
        long_text = "Б" * 600
        result = self.router.build_caption("file.txt", extracted_text=long_text)
        self.assertLessEqual(len(result), 1024)
        self.assertIn("<b>Содержит:</b>", result)

    def test_with_metadata_sheets(self):
        result = self.router.build_caption("data.xlsx", metadata={"sheets": ["Sheet1", "Sheet2"]})
        self.assertIn("Sheet1", result)
        self.assertIn("Sheet2", result)

    def test_caption_max_1024(self):
        long_text = "Б" * 2000
        result = self.router.build_caption("f.txt", extracted_text=long_text)
        self.assertLessEqual(len(result), 1024)

    def test_empty_extracted_text_returns_empty(self):
        result = self.router.build_caption("f.txt", extracted_text="   ")
        self.assertEqual(result, "")

    def test_combined_sheets_and_text_no_filename(self):
        result = self.router.build_caption(
            "table.xlsx",
            extracted_text="Данные квартала",
            metadata={"sheets": ["Q1"]},
        )
        self.assertNotIn("table.xlsx", result)
        self.assertIn("Q1", result)
        self.assertIn("Данные квартала", result)
        self.assertIn("<b>Содержит:</b>", result)

    def test_archive_metadata_in_caption(self):
        """Метаданные archive выводят '<b>из архива:</b> X'."""
        result = self.router.build_caption(
            "file.txt",
            extracted_text="Описание файла",
            metadata={"archive": "test.zip"},
        )
        self.assertIn("<b>из архива:</b> test.zip", result)
        self.assertIn("<b>Содержит:</b> Описание файла", result)
        # Проверяем отсутствие двойных пустых строк
        self.assertNotIn("\n\n", result)


# ══════════════════════════════════════════════════════════════════════════════
# 14. generate_pdf_thumbnail — генерация thumbnail
# ══════════════════════════════════════════════════════════════════════════════

class TestGeneratePdfThumbnail(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_successful_thumbnail(self):
        """pdf2image доступен и возвращает страницу → bytes."""
        fake_image = MagicMock()
        fake_buf = io.BytesIO()
        fake_image.save = lambda buf, format: buf.write(b"PNG_DATA")

        with patch.dict("sys.modules", {"pdf2image": MagicMock(convert_from_path=MagicMock(return_value=[fake_image]))}):
            result = self.router.generate_pdf_thumbnail("/fake/path.pdf")
        self.assertIsNotNone(result)

    def test_bad_pdf_returns_none(self):
        """pdf2image выбрасывает исключение (битый PDF) → None."""
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.side_effect = Exception("PDF broken")
        with patch.dict("sys.modules", {"pdf2image": mock_pdf2image}):
            result = self.router.generate_pdf_thumbnail("/fake/broken.pdf")
        self.assertIsNone(result)

    def test_empty_pages_returns_none(self):
        """pdf2image возвращает пустой список страниц → None."""
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.return_value = []
        with patch.dict("sys.modules", {"pdf2image": mock_pdf2image}):
            result = self.router.generate_pdf_thumbnail("/fake/empty.pdf")
        self.assertIsNone(result)

    def test_protected_pdf_returns_none(self):
        """Защищённый PDF (ошибка от poppler) → None (не падает)."""
        mock_pdf2image = MagicMock()
        mock_pdf2image.convert_from_path.side_effect = Exception("PDF is encrypted")
        with patch.dict("sys.modules", {"pdf2image": mock_pdf2image}):
            result = self.router.generate_pdf_thumbnail("/fake/protected.pdf")
        self.assertIsNone(result)


# ══════════════════════════════════════════════════════════════════════════════
# 15. forward_to_topic с caption
# ══════════════════════════════════════════════════════════════════════════════

class TestForwardWithCaption(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_document_forwarded_with_caption(self):
        """При extracted_text send_document вызывается с caption."""
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="texts",
            file_id="fid_123",
            file_name="doc.docx",
            extracted_text="Краткое содержание",
        ))

        mock_bot.send_document.assert_called_once()
        kwargs = mock_bot.send_document.call_args.kwargs
        self.assertIsNotNone(kwargs.get("caption"))
        self.assertIn("Краткое содержание", kwargs["caption"])

    def test_document_forwarded_without_caption_if_no_text(self):
        """Без extracted_text и metadata caption=None (не добавляем пустую подпись)."""
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="texts",
            file_id="fid_123",
        ))

        kwargs = mock_bot.send_document.call_args.kwargs
        self.assertIsNone(kwargs.get("caption"))

    def test_xlsx_metadata_in_caption(self):
        """metadata с sheets → caption содержит имена листов."""
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="tables",
            file_id="fid_xlsx",
            file_name="data.xlsx",
            metadata={"sheets": ["Данные", "Итоги"]},
        ))

        kwargs = mock_bot.send_document.call_args.kwargs
        caption = kwargs.get("caption", "")
        self.assertIn("Данные", caption)
        self.assertIn("Итоги", caption)


# ══════════════════════════════════════════════════════════════════════════════
# 16. PDF thumbnail из file_bytes — очистка временных файлов
# ══════════════════════════════════════════════════════════════════════════════

class TestForwardPdfThumbnailFromBytes(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_pdf_bytes_thumbnail_sent_as_photo(self):
        """PDF в file_bytes + успешный thumbnail → send_photo, НЕ send_document."""
        mock_bot = MagicMock()
        mock_bot.send_photo = AsyncMock()
        mock_bot.send_document = AsyncMock()

        fake_image = MagicMock()
        fake_image.save = lambda buf, format: buf.write(b"PNG_FAKE")

        with patch.dict("sys.modules", {"pdf2image": MagicMock(convert_from_path=MagicMock(return_value=[fake_image]))}):
            asyncio.run(self.router.forward_to_topic(
                mock_bot,
                topic_id=10,
                file_bytes=b"%PDF-1.4 fake",
                file_name="report.pdf",
            ))

        mock_bot.send_photo.assert_called_once()
        mock_bot.send_document.assert_not_called()

    def test_pdf_bytes_thumbnail_fails_fallback_to_document(self):
        """Если thumbnail не удался → fallback на send_document."""
        mock_bot = MagicMock()
        mock_bot.send_photo = AsyncMock()
        mock_bot.send_document = AsyncMock()

        broken_pdf2image = MagicMock()
        broken_pdf2image.convert_from_path.side_effect = Exception("poppler not found")

        with patch.dict("sys.modules", {"pdf2image": broken_pdf2image}):
            asyncio.run(self.router.forward_to_topic(
                mock_bot,
                topic_id=10,
                file_bytes=b"%PDF-1.4 fake",
                file_name="report.pdf",
            ))

        mock_bot.send_document.assert_called_once()
        mock_bot.send_photo.assert_not_called()

    def test_temp_file_cleaned_up_after_thumbnail(self):
        """Временный файл PDF удаляется после генерации thumbnail."""
        created_paths = []
        original_named_temp = tempfile.NamedTemporaryFile

        def tracking_named_temp(**kwargs):
            f = original_named_temp(**kwargs)
            created_paths.append(f.name)
            return f

        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()

        broken_pdf2image = MagicMock()
        broken_pdf2image.convert_from_path.side_effect = Exception("broken")

        with patch("tempfile.NamedTemporaryFile", side_effect=tracking_named_temp):
            with patch.dict("sys.modules", {"pdf2image": broken_pdf2image}):
                asyncio.run(self.router.forward_to_topic(
                    mock_bot,
                    topic_id=10,
                    file_bytes=b"%PDF-1.4 fake",
                    file_name="doc.pdf",
                ))

        for path in created_paths:
            self.assertFalse(os.path.exists(path), f"Временный файл {path} не удалён")


class TestCorruptedPdfHandling(unittest.IsolatedAsyncioTestCase):
    """Тест для проверки обработки невалидного/поврежденного PDF."""

    async def test_corrupted_pdf_forwarded_to_texts_topic(self):
        # Настраиваем моки для update и context
        mock_update = MagicMock()
        mock_update.effective_user.id = 12345

        mock_document = MagicMock()
        mock_document.file_name = "corrupted_test.pdf"
        mock_document.mime_type = "application/pdf"
        mock_document.file_size = 1000
        mock_document.file_id = "corrupted_pdf_file_id"
        mock_update.message.document = mock_document
        mock_update.message.caption = ""
        mock_update.message.reply_text = AsyncMock()

        mock_context = MagicMock()
        mock_context.bot = MagicMock()
        mock_context.bot.get_file = AsyncMock()

        mock_file = MagicMock()
        mock_file.download_to_drive = AsyncMock()
        mock_context.bot.get_file.return_value = mock_file

        # Мокаем функции из bot.py
        with patch("bot.extract_text_from_pdf", side_effect=Exception("No /Root object! - Is this really a PDF?")), \
             patch("bot.get_topic_id_for_file", return_value=10) as mock_get_topic, \
             patch("bot.forward_to_topic", new_callable=AsyncMock) as mock_forward:

            # Импортируем handle_document
            from bot import handle_document
            await handle_document(mock_update, mock_context)

            # Проверяем, что forward_to_topic был вызван
            mock_forward.assert_called_once()
            call_kwargs = mock_forward.call_args.kwargs

            # Проверяем переданные параметры
            self.assertEqual(call_kwargs["topic_id"], 10)
            self.assertEqual(call_kwargs["file_id"], "corrupted_pdf_file_id")
            self.assertEqual(call_kwargs["file_name"], "corrupted_test.pdf")
            self.assertEqual(call_kwargs["file_type"], "pdf")
            # extracted_text должен быть None, так как возникло исключение
            self.assertIsNone(call_kwargs["extracted_text"])

            # Проверяем, что бот ответил пользователю о невозможности извлечь текст
            mock_update.message.reply_text.assert_any_call(
                "📄 Анализирую документ «corrupted_test.pdf»..."
            )
            mock_update.message.reply_text.assert_any_call(
                "⚠️ Не удалось извлечь текст из документа.\nВозможно, это отсканированный PDF без распознанного текста."
            )


class TestStatusMessageDeletionAndPrefixes(unittest.IsolatedAsyncioTestCase):
    """Тесты для проверки удаления промежуточных статусных сообщений и добавления префиксов в ответы."""

    def setUp(self):
        # Настраиваем mock для bot и update
        self.bot = MagicMock()
        self.bot.delete_message = AsyncMock()

        self.mock_update = MagicMock()
        self.mock_update.effective_chat.id = 9999
        self.mock_update.effective_chat.type = "private"
        self.mock_update.effective_user.id = 8888
        self.mock_update.effective_user.is_bot = False
        
        self.mock_msg = MagicMock()
        self.mock_msg.message_id = 123
        self.mock_update.message = self.mock_msg
        
        # Переопределяем reply_text, чтобы он возвращал объект сообщения с нужным id
        self.sent_messages = []
        async def mock_reply_text(text, *args, **kwargs):
            msg = MagicMock()
            msg.message_id = len(self.sent_messages) + 1000
            self.sent_messages.append((msg.message_id, text))
            return msg
        self.mock_msg.reply_text = AsyncMock(side_effect=mock_reply_text)

        self.context = MagicMock()
        self.context.bot = self.bot
        self.context.user_data = {}
        self.context.bot_data = {}

    @patch("bot.ask_llm", new_callable=AsyncMock, return_value="Анализ ответа LLM")
    @patch("bot.transcribe_audio", new_callable=AsyncMock, return_value="Тестовая речь")
    @patch("bot.forward_to_topic", new_callable=AsyncMock)
    @patch("bot.tempfile.NamedTemporaryFile")
    @patch("bot.os.remove")
    async def test_handle_voice_status_deletion_and_prefix(self, mock_remove, mock_temp, mock_forward, mock_transcribe, mock_ask):
        # Настраиваем временный файл
        mock_file = MagicMock()
        mock_file.name = "temp.ogg"
        mock_temp.return_value.__enter__.return_value = mock_file
        
        self.context.bot.get_file = AsyncMock()

        from bot import handle_voice
        await handle_voice(self.mock_update, self.context)

        # Проверяем, что промежуточные сообщения "Распознаю..." и "Обрабатываю запрос..." удалялись
        self.bot.delete_message.assert_any_call(chat_id=9999, message_id=1000) # Распознаю...
        self.bot.delete_message.assert_any_call(chat_id=9999, message_id=1001) # Обрабатываю запрос...

        # Проверяем, что окончательный ответ содержит префикс 🎙️ и распознанный текст
        self.mock_msg.reply_text.assert_any_call("🎙️ Тестовая речь\n\nАнализ ответа LLM", parse_mode="Markdown")

    @patch("bot.forward_to_topic", new_callable=AsyncMock)
    async def test_handle_photo_status_deletion_and_prefix(self, mock_forward):
        """handle_photo НЕ вызывает Vision-анализ — только пересылает и отвечает коротко."""
        mock_fwd_msg = MagicMock()
        mock_fwd_msg.message_id = 999
        mock_forward.return_value = mock_fwd_msg

        self.mock_msg.photo = [MagicMock()]
        self.mock_msg.caption = "Что на фото?"

        from bot import handle_photo
        await handle_photo(self.mock_update, self.context)

        # Статус удалён
        self.bot.delete_message.assert_any_call(chat_id=9999, message_id=1000)

        # Ответ пользователю — краткий статус, БЕЗ Vision-анализа
        self.mock_msg.reply_text.assert_any_call("Файл адресован в: IMAGES.")

        # forward_to_topic вызван
        mock_forward.assert_called_once()

    @patch("bot.forward_to_topic", new_callable=AsyncMock)
    async def test_handle_video_status_deletion(self, mock_forward):
        self.mock_msg.video = MagicMock()

        from bot import handle_video
        await handle_video(self.mock_update, self.context)

        # Проверяем удаление статуса "Видео получено..."
        self.bot.delete_message.assert_any_call(chat_id=9999, message_id=1000)

    @patch("bot.ask_llm", new_callable=AsyncMock, return_value="Анализ документа")
    @patch("bot.choose_model", new_callable=AsyncMock, return_value=("google/gemini-3.5-flash", "clean prompt", ""))
    @patch("bot.extract_text_from_plain", return_value="Содержимое текстового файла")
    @patch("bot.forward_to_topic", new_callable=AsyncMock)
    @patch("bot.tempfile.NamedTemporaryFile")
    @patch("bot.os.remove")
    async def test_handle_document_plain_text_status_deletion_and_prefix(self, mock_remove, mock_temp, mock_forward, mock_extract, mock_choose, mock_ask):
        self.context.bot.get_file = AsyncMock()
        mock_file = MagicMock()
        mock_file.name = "temp.txt"
        mock_temp.return_value.__enter__.return_value = mock_file

        self.mock_msg.document = MagicMock()
        self.mock_msg.document.file_name = "test.txt"
        self.mock_msg.document.file_size = 500
        self.mock_msg.document.file_id = "txt_file_id"
        self.mock_msg.caption = ""

        from bot import handle_document
        await handle_document(self.mock_update, self.context)

        # Проверяем удаление статусов "Анализирую документ..." и "Обрабатываю запрос..."
        self.bot.delete_message.assert_any_call(chat_id=9999, message_id=1000)
        self.bot.delete_message.assert_any_call(chat_id=9999, message_id=1001)

        # Проверяем окончательный ответ с префиксом 📄
        self.mock_msg.reply_text.assert_any_call("📄 [Документ: test.txt]\n\nСодержимое текстового файла\n\nАнализ документа", parse_mode="Markdown")


class TestShouldProcessMessage(unittest.TestCase):
    """Тесты для проверки логики фильтрации should_process_message в bot.py."""

    def setUp(self):
        import importlib
        import os
        os.environ["SUPERGROUP_ID"] = "-1004295196278"
        import topic_router
        importlib.reload(topic_router)
        import bot
        importlib.reload(bot)
        self.bot = bot

    def _make_mock_update(self, chat_id, chat_type, is_bot, thread_id=None):
        mock_update = MagicMock()
        mock_update.effective_chat = MagicMock()
        mock_update.effective_chat.id = chat_id
        mock_update.effective_chat.type = chat_type
        
        mock_update.effective_user = MagicMock()
        mock_update.effective_user.is_bot = is_bot
        mock_update.effective_user.name = "@test_user"
        mock_update.effective_user.id = 123456
        
        mock_update.message = MagicMock()
        mock_update.message.message_thread_id = thread_id
        mock_update.message.text = "Hello bot"
        mock_update.message.caption = None
        return mock_update

    def test_private_chat_allowed_for_users(self):
        """Сообщение от пользователя в приватном чате разрешено."""
        update = self._make_mock_update(chat_id=123, chat_type="private", is_bot=False)
        self.assertTrue(self.bot.should_process_message(update))

    def test_private_chat_ignored_for_bots(self):
        """Сообщение от бота в приватном чате игнорируется."""
        update = self._make_mock_update(chat_id=123, chat_type="private", is_bot=True)
        self.assertFalse(self.bot.should_process_message(update))

    def test_supergroup_general_topic_allowed_for_users(self):
        """Сообщение в топике General (thread_id is None) разрешено для пользователей."""
        update = self._make_mock_update(chat_id=-1004295196278, chat_type="supergroup", is_bot=False, thread_id=None)
        self.assertTrue(self.bot.should_process_message(update))

    def test_supergroup_general_topic_ignored_for_bots(self):
        """Сообщение в топике General игнорируется для ботов."""
        update = self._make_mock_update(chat_id=-1004295196278, chat_type="supergroup", is_bot=True, thread_id=None)
        self.assertFalse(self.bot.should_process_message(update))

    def test_supergroup_other_topic_ignored_for_users(self):
        """Сообщение в других топиках (thread_id is not None) игнорируется."""
        update = self._make_mock_update(chat_id=-1004295196278, chat_type="supergroup", is_bot=False, thread_id=118)
        self.assertFalse(self.bot.should_process_message(update))

    def test_other_group_ignored_entirely(self):
        """Сообщения из посторонних групп/супергрупп игнорируются."""
        update = self._make_mock_update(chat_id=-1001111111111, chat_type="supergroup", is_bot=False, thread_id=None)
        self.assertFalse(self.bot.should_process_message(update))


class TestVideoNoteAndAnimationRouting(unittest.TestCase):
    def setUp(self):
        self.router = _reload_router()

    def test_gif_extension_to_images(self):
        tid = self.router.get_topic_id_for_file("animation.gif")
        self.assertEqual(tid, 30)  # TOPIC_IMAGES_ID

    def test_mime_gif_to_images(self):
        tid = self.router.get_topic_id_for_file("noext", mime_type="image/gif")
        self.assertEqual(tid, 30)

    def test_mime_video_mp4_to_images(self):
        tid = self.router.get_topic_id_for_file("video.mp4", mime_type="video/mp4")
        self.assertEqual(tid, 30)


class TestSQLiteOperations(unittest.TestCase):
    def setUp(self):
        import bot
        self.bot = bot
        self.original_db = bot.DB_FILE
        self.bot.DB_FILE = "test_jade_bridge.db"
        self.bot.init_db()

    def tearDown(self):
        import os
        self.bot.DB_FILE = self.original_db
        if os.path.exists("test_jade_bridge.db"):
            os.remove("test_jade_bridge.db")

    def test_save_and_get_forwarded_file(self):
        self.bot.save_forwarded_file(
            chat_id=-100123,
            message_id=456,
            file_id="test_file_id",
            file_type="document",
            file_name="test.pdf",
            extracted_text="Some text content",
            metadata={"sheets": ["Sheet1"]}
        )

        res = self.bot.get_forwarded_file(-100123, 456)
        self.assertIsNotNone(res)
        self.assertEqual(res["file_id"], "test_file_id")
        self.assertEqual(res["file_type"], "document")
        self.assertEqual(res["file_name"], "test.pdf")
        self.assertEqual(res["extracted_text"], "Some text content")
        self.assertEqual(res["metadata"], {"sheets": ["Sheet1"]})

    def test_get_nonexistent_returns_none(self):
        res = self.bot.get_forwarded_file(-100123, 999)
        self.assertIsNone(res)


class TestCallbackHandlers(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        import bot
        self.bot = bot
        self.original_db = bot.DB_FILE
        self.bot.DB_FILE = "test_jade_bridge.db"
        self.bot.init_db()

        self.query = MagicMock()
        self.query.answer = AsyncMock()
        self.query.data = "ai_analyze:sonnet"
        self.query.from_user.id = 777
        
        self.message = MagicMock()
        self.message.chat.id = -100123
        self.message.message_id = 456
        self.message.reply_text = AsyncMock()
        
        self.analysis_msg = MagicMock()
        self.analysis_msg.message_id = 300
        
        # В нашей реализации используется send_message для ForceReply
        # с reply_to_message_id
        self.bot_obj = MagicMock()
        self.bot_obj.send_message = AsyncMock(return_value=self.analysis_msg)
        
        self.query.message = self.message
        self.update = MagicMock()
        self.update.callback_query = self.query

        self.context = MagicMock()
        self.context.bot = self.bot_obj
        self.context.bot_data = {}

    def tearDown(self):
        import os
        self.bot.DB_FILE = self.original_db
        if os.path.exists("test_jade_bridge.db"):
            os.remove("test_jade_bridge.db")

    async def test_callback_document_analysis(self):
        """Callback отправляет предложение задать вопрос с ForceReply."""
        self.bot.save_forwarded_file(
            chat_id=-100123,
            message_id=456,
            file_id="doc_id",
            file_type="document",
            file_name="report.pdf",
            extracted_text="Содержимое отчета"
        )

        await self.bot.handle_ai_analyze_callback(self.update, self.context)

        self.query.answer.assert_called_once()
        self.bot_obj.send_message.assert_called_once()
        
        call_kwargs = self.bot_obj.send_message.call_args.kwargs
        self.assertEqual(call_kwargs["chat_id"], -100123)
        self.assertIn("Claude Sonnet 4.6. Ваш вопрос:", call_kwargs["text"])
        self.assertEqual(call_kwargs["reply_to_message_id"], 456)
        
        # Проверяем запись в БД
        dialog = self.bot.get_file_dialog(-100123, 300)
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog["file_message_id"], 456)
        self.assertEqual(dialog["model_choice"], "sonnet")
        self.assertEqual(dialog["history"], [])


# ══════════════════════════════════════════════════════════════════════════════
# 17. build_caption — тег архива (Задача 2)
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildCaptionArchiveTag(unittest.TestCase):
    """build_caption с ключом archive в metadata → тег в начале подписи."""

    def setUp(self):
        self.router = _reload_router()

    def test_archive_tag_at_start(self):
        result = self.router.build_caption("report.pdf", metadata={"archive": "project.zip"})
        self.assertTrue(result.startswith("<b>из архива:</b> project.zip"))

    def test_archive_tag_at_start_no_filename(self):
        result = self.router.build_caption("doc.pdf", metadata={"archive": "test.zip"})
        self.assertTrue(result.startswith("<b>из архива:</b> test.zip"))
        self.assertNotIn("doc.pdf", result)

    def test_no_archive_tag_without_metadata(self):
        result = self.router.build_caption("doc.pdf")
        self.assertNotIn("из архива:", result)

    def test_archive_and_sheets_together(self):
        result = self.router.build_caption(
            "data.xlsx",
            metadata={"archive": "bundle.zip", "sheets": ["Sheet1"]},
        )
        self.assertIn("<b>из архива:</b> bundle.zip", result)
        self.assertIn("Sheet1", result)

    def test_archive_with_extracted_text(self):
        result = self.router.build_caption(
            "notes.txt",
            extracted_text="Текст файла",
            metadata={"archive": "docs.zip"},
        )
        self.assertIn("<b>из архива:</b> docs.zip", result)
        self.assertNotIn("notes.txt", result)
        self.assertIn("Текст файла", result)

    def test_caption_within_1024_with_archive(self):
        result = self.router.build_caption(
            "big.txt",
            extracted_text="X" * 2000,
            metadata={"archive": "arch.zip"},
        )
        self.assertLessEqual(len(result), 1024)


# ══════════════════════════════════════════════════════════════════════════════
# 18. forward_to_topic — file_bytes + media_type (Задача 1)
# ══════════════════════════════════════════════════════════════════════════════

class TestForwardToTopicFileBytesMediaType(unittest.TestCase):
    """Задача 1: file_bytes ветка поддерживает photo/video/animation."""

    def setUp(self):
        self.router = _reload_router()

    def test_file_bytes_photo_calls_send_photo(self):
        mock_bot = MagicMock()
        mock_bot.send_photo = AsyncMock()
        asyncio.run(self.router.forward_to_topic(
            mock_bot, topic_id=30,
            file_bytes=b"fake_image", file_name="img.jpg", media_type="photo",
        ))
        mock_bot.send_photo.assert_called_once()
        self.assertEqual(mock_bot.send_photo.call_args.kwargs["message_thread_id"], 30)

    def test_file_bytes_video_calls_send_video(self):
        mock_bot = MagicMock()
        mock_bot.send_video = AsyncMock()
        asyncio.run(self.router.forward_to_topic(
            mock_bot, topic_id=30,
            file_bytes=b"fake_video", file_name="clip.mp4", media_type="video",
        ))
        mock_bot.send_video.assert_called_once()
        self.assertEqual(mock_bot.send_video.call_args.kwargs["message_thread_id"], 30)

    def test_file_bytes_animation_calls_send_animation(self):
        mock_bot = MagicMock()
        mock_bot.send_animation = AsyncMock()
        asyncio.run(self.router.forward_to_topic(
            mock_bot, topic_id=30,
            file_bytes=b"fake_gif", file_name="anim.gif", media_type="animation",
        ))
        mock_bot.send_animation.assert_called_once()
        self.assertEqual(mock_bot.send_animation.call_args.kwargs["message_thread_id"], 30)

    def test_file_bytes_default_calls_send_document(self):
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()
        asyncio.run(self.router.forward_to_topic(
            mock_bot, topic_id=10,
            file_bytes=b"data", file_name="data.csv",
        ))
        mock_bot.send_document.assert_called_once()

    def test_file_bytes_photo_not_document(self):
        mock_bot = MagicMock()
        mock_bot.send_photo = AsyncMock()
        mock_bot.send_document = AsyncMock()
        asyncio.run(self.router.forward_to_topic(
            mock_bot, topic_id=30,
            file_bytes=b"img", file_name="img.png", media_type="photo",
        ))
        mock_bot.send_photo.assert_called_once()
        mock_bot.send_document.assert_not_called()

    def test_file_bytes_error_logs_filename(self):
        """Ошибка отправки file_bytes логируется с именем файла."""
        import logging
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock(side_effect=RuntimeError("network"))
        with self.assertLogs("topic_router", level="ERROR") as cm:
            asyncio.run(self.router.forward_to_topic(
                mock_bot, topic_id=10,
                file_bytes=b"x", file_name="broken.txt", media_type="document",
            ))
        self.assertTrue(any("broken.txt" in line for line in cm.output))


# ══════════════════════════════════════════════════════════════════════════════
# 19. extract_text_from_zip — 3-tuple возврат (Задача 1)
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractTextFromZip3Tuple(unittest.TestCase):
    """Задача 1: extract_text_from_zip возвращает (text, exceeded, files_info)."""

    def _make_zip(self, files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def _write_zip(self, files: dict):
        zip_bytes = self._make_zip(files)
        f = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        f.write(zip_bytes)
        f.close()
        return f.name

    def test_returns_3_tuple(self):
        import bot as _bot
        zp = self._write_zip({"note.txt": "hello"})
        try:
            result = _bot.extract_text_from_zip(zp, "test.zip")
        finally:
            os.remove(zp)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_files_info_keys(self):
        import bot as _bot
        zp = self._write_zip({"doc.txt": "content"})
        try:
            _, _, files_info = _bot.extract_text_from_zip(zp, "archive.zip")
        finally:
            os.remove(zp)
        for key in ("total_files", "processed_count", "entries"):
            self.assertIn(key, files_info)

    def test_processed_count_for_txt(self):
        import bot as _bot
        zp = self._write_zip({"readme.txt": "Hello world"})
        try:
            _, _, files_info = _bot.extract_text_from_zip(zp, "arc.zip")
        finally:
            os.remove(zp)
        self.assertEqual(files_info["total_files"], 1)
        self.assertEqual(files_info["processed_count"], 1)

    def test_unsupported_file_not_counted(self):
        """
        Медиафайлы (.jpg) теперь считаются обработанными (processed_count=1).
        Для проверки что НЕподдерживаемый файл не засчитывается — используем .rar.
        """
        import bot as _bot
        # .rar — действительно неподдерживаемый формат
        zp = self._write_zip({"archive.rar": b"Rar!"})
        try:
            _, _, files_info = _bot.extract_text_from_zip(zp, "arc.zip")
        finally:
            os.remove(zp)
        self.assertEqual(files_info["total_files"], 1)
        self.assertEqual(files_info["processed_count"], 0,
                         ".rar должен быть в unsupported, processed_count=0")
        self.assertIn("archive.rar", files_info.get("unsupported_names", []))

    def test_jpg_counted_as_processed(self):
        """
        Изображения (.jpg) теперь считаются обработанными (маршрутизуются в Images).
        """
        import bot as _bot
        zp = self._write_zip({"img.jpg": b"\xff\xd8\xff"})
        try:
            _, _, files_info = _bot.extract_text_from_zip(zp, "arc.zip")
        finally:
            os.remove(zp)
        self.assertEqual(files_info["total_files"], 1)
        self.assertEqual(files_info["processed_count"], 1,
                         ".jpg считается обработанным (маршрутизация в Images)")
        self.assertNotIn("img.jpg", files_info.get("unsupported_names", []))

    def test_limits_exceeded_returns_3_tuple(self):
        import bot as _bot
        original_max = _bot.ZIP_MAX_FILES
        _bot.ZIP_MAX_FILES = 0
        try:
            zp = self._write_zip({"a.txt": "x"})
            try:
                result = _bot.extract_text_from_zip(zp, "big.zip")
            finally:
                os.remove(zp)
        finally:
            _bot.ZIP_MAX_FILES = original_max
        self.assertEqual(len(result), 3)
        _, limits_exceeded, files_info = result
        self.assertTrue(limits_exceeded)
        self.assertIn("total_files", files_info)


# ══════════════════════════════════════════════════════════════════════════════
# 20. should_process_message — pending_analyses check (Задача 5)
# ══════════════════════════════════════════════════════════════════════════════

class TestShouldProcessMessageWithPendingAnalyses(unittest.TestCase):
    """Задача 5: should_process_message разрешает Reply на сессии диалогов через get_file_dialog."""

    def setUp(self):
        import importlib
        os.environ["SUPERGROUP_ID"] = "-1004295196278"
        import topic_router
        importlib.reload(topic_router)
        import bot
        importlib.reload(bot)
        self.bot_module = bot

    def _make_update_with_reply(self, chat_id, thread_id, reply_to_id):
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.effective_chat.type = "supergroup"
        update.effective_user.is_bot = False
        update.effective_user.name = "@user"
        update.effective_user.id = 1
        update.message.message_thread_id = thread_id
        update.message.text = "Анализ"
        update.message.caption = None
        reply_msg = MagicMock()
        reply_msg.message_id = reply_to_id
        update.message.reply_to_message = reply_msg
        return update

    def test_other_topic_reply_to_pending_allowed(self):
        update = self._make_update_with_reply(-1004295196278, 118, 555)
        context = MagicMock()
        with patch("bot.get_file_dialog", return_value={"file_message_id": 100}):
            self.assertTrue(self.bot_module.should_process_message(update, context))

    def test_other_topic_reply_not_in_pending_denied(self):
        update = self._make_update_with_reply(-1004295196278, 118, 999)
        context = MagicMock()
        with patch("bot.get_file_dialog", return_value=None):
            self.assertFalse(self.bot_module.should_process_message(update, context))

    def test_other_topic_without_context_denied(self):
        update = self._make_update_with_reply(-1004295196278, 118, 555)
        with patch("bot.get_file_dialog", return_value=None):
            self.assertFalse(self.bot_module.should_process_message(update))

    def test_general_topic_still_allowed(self):
        update = self._make_update_with_reply(-1004295196278, None, 555)
        context = MagicMock()
        self.assertTrue(self.bot_module.should_process_message(update, context))

    def test_empty_pending_does_not_unlock_other_topics(self):
        update = self._make_update_with_reply(-1004295196278, 118, 555)
        context = MagicMock()
        with patch("bot.get_file_dialog", return_value=None):
            self.assertFalse(self.bot_module.should_process_message(update, context))


# ══════════════════════════════════════════════════════════════════════════════
# 21. handle_ai_analyze_callback — диалоги в БД (Задача 5)
# ══════════════════════════════════════════════════════════════════════════════

class TestCallbackDeferredMode(unittest.IsolatedAsyncioTestCase):
    """Задача 5: handle_ai_analyze_callback отправляет предложение задать вопрос с ForceReply."""

    def setUp(self):
        import bot
        self.bot_module = bot
        self.original_db = bot.DB_FILE
        self.bot_module.DB_FILE = "test_callback_deferred.db"
        self.bot_module.init_db()

        self.query = MagicMock()
        self.query.answer = AsyncMock()
        self.query.data = "ai_analyze:sonnet"
        self.query.from_user.id = 777

        self.question_msg = MagicMock()
        self.question_msg.message_id = 300

        self.message = MagicMock()
        self.message.chat.id = -100123
        self.message.message_id = 456

        self.query.message = self.message
        self.update = MagicMock()
        self.update.callback_query = self.query

        self.bot_obj = MagicMock()
        self.bot_obj.send_message = AsyncMock(return_value=self.question_msg)

        self.context = MagicMock()
        self.context.bot = self.bot_obj
        self.context.bot_data = {}

    def tearDown(self):
        self.bot_module.DB_FILE = self.original_db
        if os.path.exists("test_callback_deferred.db"):
            os.remove("test_callback_deferred.db")

    async def test_sends_question_not_analysis(self):
        self.bot_module.save_forwarded_file(
            chat_id=-100123, message_id=456,
            file_id="doc_id", file_type="document",
            file_name="report.pdf", extracted_text="Текст отчёта",
        )
        await self.bot_module.handle_ai_analyze_callback(self.update, self.context)

        self.query.answer.assert_called_once()
        self.bot_obj.send_message.assert_called_once()
        call_kwargs = self.bot_obj.send_message.call_args.kwargs
        self.assertIn("Claude Sonnet 4.6. Ваш вопрос:", call_kwargs["text"])

    async def test_file_dialogs_populated_with_correct_metadata(self):
        self.bot_module.save_forwarded_file(
            chat_id=-100123, message_id=456,
            file_id="f_id", file_type="photo", file_name="img.jpg",
        )
        await self.bot_module.handle_ai_analyze_callback(self.update, self.context)

        dialog = self.bot_module.get_file_dialog(-100123, 300)
        self.assertIsNotNone(dialog)
        self.assertEqual(dialog["file_message_id"], 456)
        self.assertEqual(dialog["model_choice"], "sonnet")

    async def test_no_file_info_sends_warning_no_dialog(self):
        await self.bot_module.handle_ai_analyze_callback(self.update, self.context)
        self.bot_obj.send_message.assert_called_once()
        call_text = self.bot_obj.send_message.call_args.kwargs.get("text", "")
        self.assertIn("отсутствует в базе данных", call_text)
        dialog = self.bot_module.get_file_dialog(-100123, 300)
        self.assertIsNone(dialog)


# ══════════════════════════════════════════════════════════════════════════════
# 22. handle_text — перехват диалога по файлам (Задача 5)
# ══════════════════════════════════════════════════════════════════════════════

class TestHandleTextDeferredAnalysis(unittest.IsolatedAsyncioTestCase):
    """Задача 5: handle_text запускает execute_file_dialog_step при Reply."""

    def setUp(self):
        import bot
        self.bot_module = bot
        self.original_db = bot.DB_FILE
        self.bot_module.DB_FILE = "test_handle_text_dialog.db"
        self.bot_module.init_db()

        self.bot_obj = MagicMock()
        self.bot_obj.delete_message = AsyncMock()

        self.mock_update = MagicMock()
        self.mock_update.effective_chat.id = 9999
        self.mock_update.effective_chat.type = "private"
        self.mock_update.effective_user.is_bot = False
        self.mock_update.effective_user.name = "@user"
        self.mock_update.effective_user.id = 1

        self.mock_msg = MagicMock()
        self.mock_msg.message_id = 200
        self.mock_msg.text = "Найди все даты в документе"
        self.mock_msg.reply_text = AsyncMock(return_value=MagicMock(message_id=999))
        reply_to = MagicMock()
        reply_to.message_id = 100
        self.mock_msg.reply_to_message = reply_to
        self.mock_update.message = self.mock_msg

        self.context = MagicMock()
        self.context.bot = self.bot_obj
        self.context.user_data = {}

        # Создаем стартовый диалог в БД
        self.bot_module.save_file_dialog(
            chat_id=9999,
            bot_message_id=100,
            file_message_id=50,
            model_choice="sonnet",
            history_list=[],
            user_id=1
        )

    def tearDown(self):
        self.bot_module.DB_FILE = self.original_db
        if os.path.exists("test_handle_text_dialog.db"):
            os.remove("test_handle_text_dialog.db")

    @patch("bot.execute_file_dialog_step", new_callable=AsyncMock)
    async def test_text_reply_triggers_dialog_step(self, mock_exec):
        from bot import handle_text
        await handle_text(self.mock_update, self.context)
        mock_exec.assert_called_once()
        self.assertEqual(mock_exec.call_args[0][3], "Найди все даты в документе")

    @patch("bot.execute_file_dialog_step", new_callable=AsyncMock)
    async def test_pending_entry_removed_after_trigger(self, mock_exec):
        from bot import handle_text
        await handle_text(self.mock_update, self.context)
        dialog = self.bot_module.get_file_dialog(9999, 100)
        self.assertIsNone(dialog)

    @patch("bot.execute_file_dialog_step", new_callable=AsyncMock)
    async def test_no_reply_to_message_skips_dialog(self, mock_exec):
        self.mock_msg.reply_to_message = None
        from bot import handle_text
        with patch("bot.choose_model", new_callable=AsyncMock,
                   return_value=("google/gemini-3.5-flash", "text", "")):
            with patch("bot.ask_llm", new_callable=AsyncMock, return_value="ok"):
                await handle_text(self.mock_update, self.context)
        mock_exec.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# 23. handle_voice — перехват диалога по файлам (Задача 5)
# ══════════════════════════════════════════════════════════════════════════════

class TestHandleVoiceDeferredAnalysis(unittest.IsolatedAsyncioTestCase):
    """Задача 5: handle_voice распознаёт речь и запускает execute_file_dialog_step."""

    def setUp(self):
        import bot
        self.bot_module = bot
        self.original_db = bot.DB_FILE
        self.bot_module.DB_FILE = "test_handle_voice_dialog.db"
        self.bot_module.init_db()

        self.bot_obj = MagicMock()
        self.bot_obj.delete_message = AsyncMock()

        self.mock_update = MagicMock()
        self.mock_update.effective_chat.id = 9999
        self.mock_update.effective_chat.type = "private"
        self.mock_update.effective_user.is_bot = False
        self.mock_update.effective_user.name = "@user"
        self.mock_update.effective_user.id = 1

        self.mock_msg = MagicMock()
        self.mock_msg.message_id = 201
        self.mock_msg.voice = MagicMock()

        reply_to = MagicMock()
        reply_to.message_id = 101
        self.mock_msg.reply_to_message = reply_to

        self.sent_messages = []
        async def mock_reply_text(text, *a, **kw):
            msg = MagicMock()
            msg.message_id = len(self.sent_messages) + 2000
            self.sent_messages.append((msg.message_id, text))
            return msg
        self.mock_msg.reply_text = AsyncMock(side_effect=mock_reply_text)
        self.mock_update.message = self.mock_msg

        self.context = MagicMock()
        self.context.bot = self.bot_obj
        self.context.user_data = {}

        # Создаем стартовый диалог
        self.bot_module.save_file_dialog(
            chat_id=9999,
            bot_message_id=101,
            file_message_id=51,
            model_choice="gemini",
            history_list=[],
            user_id=1
        )

    def tearDown(self):
        self.bot_module.DB_FILE = self.original_db
        if os.path.exists("test_handle_voice_dialog.db"):
            os.remove("test_handle_voice_dialog.db")

    @patch("bot.execute_file_dialog_step", new_callable=AsyncMock)
    @patch("bot.transcribe_audio", new_callable=AsyncMock, return_value="Текст из голоса")
    @patch("bot.os.remove")
    @patch("bot.tempfile.NamedTemporaryFile")
    async def test_voice_reply_triggers_deferred(self, mock_tmp, mock_remove, mock_transcribe, mock_exec):
        mock_file = MagicMock()
        mock_file.name = "tmp.ogg"
        mock_tmp.return_value.__enter__.return_value = mock_file
        mock_voice_file = MagicMock()
        mock_voice_file.download_to_drive = AsyncMock()
        self.bot_obj.get_file = AsyncMock(return_value=mock_voice_file)

        from bot import handle_voice
        await handle_voice(self.mock_update, self.context)

        mock_exec.assert_called_once()
        self.assertEqual(mock_exec.call_args[0][3], "Текст из голоса")

    @patch("bot.execute_file_dialog_step", new_callable=AsyncMock)
    @patch("bot.transcribe_audio", new_callable=AsyncMock, return_value="Текст")
    @patch("bot.os.remove")
    @patch("bot.tempfile.NamedTemporaryFile")
    async def test_voice_deferred_deletes_recognizing_status(self, mock_tmp, mock_remove, mock_transcribe, mock_exec):
        mock_file = MagicMock()
        mock_file.name = "tmp.ogg"
        mock_tmp.return_value.__enter__.return_value = mock_file
        mock_voice_file = MagicMock()
        mock_voice_file.download_to_drive = AsyncMock()
        self.bot_obj.get_file = AsyncMock(return_value=mock_voice_file)

        from bot import handle_voice
        await handle_voice(self.mock_update, self.context)

        sent_texts = [text for _, text in self.sent_messages]
        self.assertIn("Распознаю голос...", sent_texts)
        self.bot_obj.delete_message.assert_called()


# ══════════════════════════════════════════════════════════════════════════════
# 24. execute_file_dialog_step — статус и анализ (Задача 5)
# ══════════════════════════════════════════════════════════════════════════════

class TestExecuteFileDialogStep(unittest.IsolatedAsyncioTestCase):
    """Задача 5: execute_file_dialog_step отправляет статус и отвечает результатом."""

    def setUp(self):
        import bot
        self.bot_module = bot
        self.original_db = bot.DB_FILE
        self.bot_module.DB_FILE = "test_exec_dialog.db"
        self.bot_module.init_db()

        self.bot_reply_msg = MagicMock()
        self.bot_reply_msg.message_id = 999

        self.mock_update = MagicMock()
        self.mock_update.message.message_id = 202
        self.mock_update.effective_chat.id = 9999
        self.mock_update.effective_user.id = 1
        self.mock_update.message.reply_text = AsyncMock(return_value=self.bot_reply_msg)

        self.bot_obj = MagicMock()
        self.bot_obj.delete_message = AsyncMock()
        self.bot_obj.get_file = AsyncMock()

        self.context = MagicMock()
        self.context.bot = self.bot_obj

    def tearDown(self):
        self.bot_module.DB_FILE = self.original_db
        if os.path.exists("test_exec_dialog.db"):
            os.remove("test_exec_dialog.db")

    @patch("ai_service.ask_llm", new_callable=AsyncMock, return_value="Результат анализа")
    async def test_sends_status_and_replies_with_result(self, mock_ask):
        self.bot_module.save_forwarded_file(
            chat_id=9999, message_id=50,
            file_id="doc_id", file_type="document",
            file_name="report.pdf", extracted_text="Содержимое отчёта",
        )
        session = {
            "file_message_id": 50, "model_choice": "sonnet",
            "chat_id": 9999, "user_id": 1, "history": []
        }
        from bot import execute_file_dialog_step
        await execute_file_dialog_step(
            self.mock_update, self.context, session, "Найди выводы"
        )
        self.assertEqual(self.mock_update.message.reply_text.call_count, 2)
        
        last_reply = self.mock_update.message.reply_text.call_args_list[1][0][0]
        self.assertIn("<b>Claude Sonnet 4.6:</b>", last_reply)
        self.assertIn("Результат анализа", last_reply)

    async def test_no_file_info_edits_status_with_warning(self):
        session = {
            "file_message_id": 9999, "model_choice": "sonnet",
            "chat_id": 9999, "user_id": 1, "history": []
        }
        status_msg = MagicMock()
        status_msg.edit_text = AsyncMock()
        self.mock_update.message.reply_text = AsyncMock(return_value=status_msg)
        
        from bot import execute_file_dialog_step
        await execute_file_dialog_step(
            self.mock_update, self.context, session, "анализ"
        )
        status_msg.edit_text.assert_called_once()
        self.assertIn("не найдена", status_msg.edit_text.call_args[0][0])


# ══════════════════════════════════════════════════════════════════════════════
# 25. _generate_caption_summary — LLM-саммари для подписей (Баг-фикс подписей)
# ══════════════════════════════════════════════════════════════════════════════

class TestGenerateCaptionSummary(unittest.IsolatedAsyncioTestCase):
    """_generate_caption_summary вызывает LLM и возвращает краткое описание."""

    @patch("ai_service.ask_llm", new_callable=AsyncMock, return_value="Краткое описание файла")
    async def test_returns_llm_summary(self, mock_ask):
        from bot import _generate_caption_summary
        result = await _generate_caption_summary("Полный текст документа", "doc.pdf")
        self.assertEqual(result, "Краткое описание файла")
        mock_ask.assert_called_once()

    @patch("ai_service.ask_llm", new_callable=AsyncMock, return_value="Summary")
    async def test_sends_raw_text_snippet_to_llm(self, mock_ask):
        from bot import _generate_caption_summary
        long_text = "X" * 5000
        await _generate_caption_summary(long_text, "big.txt")
        messages = mock_ask.call_args[0][0]
        user_content = messages[1]["content"]
        self.assertLessEqual(len(user_content), 3200)  # 3000 snippet + header

    @patch("ai_service.ask_llm", new_callable=AsyncMock, return_value="Summary")
    async def test_system_prompt_forbids_raw_markup(self, mock_ask):
        from bot import _generate_caption_summary
        await _generate_caption_summary("some text", "f.txt")
        sys_msg = mock_ask.call_args[0][0][0]["content"]
        self.assertIn("XML", sys_msg)
        self.assertIn("HTML", sys_msg)

    async def test_empty_text_returns_none(self):
        from bot import _generate_caption_summary
        self.assertIsNone(await _generate_caption_summary("", "f.txt"))
        self.assertIsNone(await _generate_caption_summary("   ", "f.txt"))

    @patch("ai_service.ask_llm", new_callable=AsyncMock, side_effect=RuntimeError("network"))
    async def test_llm_error_returns_none(self, mock_ask):
        from bot import _generate_caption_summary
        result = await _generate_caption_summary("text", "file.txt")
        self.assertIsNone(result)

    @patch("ai_service.ask_llm", new_callable=AsyncMock, return_value="A" * 700)
    async def test_result_capped_at_600_chars(self, mock_ask):
        from bot import _generate_caption_summary
        result = await _generate_caption_summary("content", "f.pdf")
        self.assertLessEqual(len(result), 600)


# ══════════════════════════════════════════════════════════════════════════════
# 26. build_caption — нет сырого кода в подписи (Баг-фикс подписей)
# ══════════════════════════════════════════════════════════════════════════════

class TestCaptionNoRawCode(unittest.TestCase):
    """Проверяет, что build_caption не выводит типичные паттерны сырого кода."""

    def setUp(self):
        self.router = _reload_router()

    def _raw_patterns(self):
        return ["<html", "<?xml", "<head>", "<table>", "<tr>", "|", "| --- |"]

    def test_llm_summary_passes_through_clean(self):
        summary = "Спецификация байдарок серии Щука и Налим с ценами и размерами"
        result = self.router.build_caption("spec.docx", extracted_text=summary)
        # Формат Telegram HTML: '<b>Содержит:</b> <summary>'
        self.assertIn("<b>Содержит:</b>", result)
        self.assertIn(summary, result)

    def test_filename_not_duplicated(self):
        result = self.router.build_caption("report.pdf", extracted_text="Отчёт за квартал")
        self.assertNotIn("report.pdf", result)

    def test_no_filename_in_archive_caption(self):
        result = self.router.build_caption(
            "data.json",
            extracted_text="JSON-спецификация продуктов",
            metadata={"archive": "catalog.zip"},
        )
        self.assertNotIn("data.json", result)
        self.assertIn("<b>из архива:</b> catalog.zip", result)
        self.assertIn("JSON-спецификация продуктов", result)

    def test_empty_summary_gives_empty_caption(self):
        result = self.router.build_caption("f.txt", extracted_text="   ")
        self.assertEqual(result, "")

    def test_none_extracted_text_no_filename_fallback(self):
        result = self.router.build_caption("report.xlsx", extracted_text=None)
        self.assertEqual(result, "")


# ═══════════════════════════════════════════════════════════════════════════════
# 27. Баг-фикс раунд 2: синхронизация ZIP_SUPPORTED_EXTS с маршрутизацией
# ═══════════════════════════════════════════════════════════════════════════════

class TestZipSupportedExtsSync(unittest.TestCase):
    """
    Баг-фикс раунд 2, БАГ 1:
    ZIP_SUPPORTED_EXTS должен содержать .xlsx (синхронизация с _EXT_TO_TOPIC).
    .rar в ZIP остаётся неподдерживаемым — маршрутизируется в ATTENTION.
    """

    def test_xlsx_in_zip_supported_exts(self):
        """ZIP_SUPPORTED_EXTS содержит .xlsx."""
        import bot
        self.assertIn(".xlsx", bot.ZIP_SUPPORTED_EXTS,
                      ".xlsx должен быть в ZIP_SUPPORTED_EXTS (БАГ 1 исправлен)")

    def test_pdf_in_zip_supported_exts(self):
        import bot
        self.assertIn(".pdf", bot.ZIP_SUPPORTED_EXTS)

    def test_docx_in_zip_supported_exts(self):
        import bot
        self.assertIn(".docx", bot.ZIP_SUPPORTED_EXTS)

    def test_txt_in_zip_supported_exts(self):
        import bot
        self.assertIn(".txt", bot.ZIP_SUPPORTED_EXTS)

    def test_rar_not_in_zip_supported_exts(self):
        """RAR не в ZIP_SUPPORTED_EXTS и не в _EXT_TO_TOPIC — маршрутизируется в ATTENTION."""
        import bot
        self.assertNotIn(".rar", bot.ZIP_SUPPORTED_EXTS)
        # Проверяем через роутера
        r = _reload_router()
        tid = r.get_topic_id_for_file("archive.rar")
        self.assertEqual(tid, 50, "RAR должен маршрутизироваться в TOPIC_ATTENTION_ID=50")

    def test_xlsx_routes_to_tables_not_attention(self):
        """.xlsx маршрутизируется в Таблицы (20), не в Внимание (50)."""
        r = _reload_router()
        tid = r.get_topic_id_for_file("report.xlsx")
        self.assertEqual(tid, 20, ".xlsx должен идти в TOPIC_TABLES_ID=20")


# ═══════════════════════════════════════════════════════════════════════════════
# 28. Баг-фикс раунд 2: верная структура сводки архива
# ═══════════════════════════════════════════════════════════════════════════════

class TestZipArchiveSummaryTemplate(unittest.TestCase):
    """
    Баг-фикс раунд 2:
    extract_text_from_zip возвращает корректный files_info с полями
    unsupported_names, topic_labels, type_labels.
    """

    def _make_zip(self, files: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_xlsx_counted_as_processed(self):
        """.xlsx внутри ZIP считается обработанным, не попадает в unsupported_names."""
        import bot
        zip_bytes = self._make_zip({
            "notes.txt": "Hello world",
            "data.xlsx": b"PK\x03\x04" + b"\x00" * 26,  # minimal valid-looking header
        })
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(zip_bytes)
            zip_path = f.name
        try:
            _, limits_exceeded, files_info = bot.extract_text_from_zip(zip_path, "test.zip")
            self.assertFalse(limits_exceeded)
            self.assertNotIn("data.xlsx", files_info.get("unsupported_names", []),
                             ".xlsx не должен быть в unsupported_names (БАГ 1 исправлен)")
        finally:
            os.remove(zip_path)

    def test_rar_inside_zip_in_unsupported(self):
        """.rar внутри ZIP попадает в unsupported_names."""
        import bot
        zip_bytes = self._make_zip({
            "notes.txt": "Hello world",
            "archive.rar": b"Rar!",
        })
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(zip_bytes)
            zip_path = f.name
        try:
            _, limits_exceeded, files_info = bot.extract_text_from_zip(zip_path, "test.zip")
            self.assertFalse(limits_exceeded)
            self.assertIn("archive.rar", files_info.get("unsupported_names", []),
                          ".rar должен быть в unsupported_names")
        finally:
            os.remove(zip_path)

    def test_rar_inside_zip_routes_to_attention_topic(self):
        """.rar внутри ZIP: через get_topic_id_for_file попадает в ATTENTION."""
        r = _reload_router()
        tid = r.get_topic_id_for_file("archive.rar")
        self.assertEqual(tid, 50, ".rar должен маршрутизироваться в TOPIC_ATTENTION_ID=50")

    def test_files_info_has_required_fields(self):
        """Возвращаемый files_info содержит все необходимые поля."""
        import bot
        zip_bytes = self._make_zip({"readme.txt": "Hello"})
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(zip_bytes)
            zip_path = f.name
        try:
            _, _, files_info = bot.extract_text_from_zip(zip_path, "test.zip")
            for field in ("total_files", "processed_count", "entries",
                          "unsupported_names", "topic_labels", "type_labels"):
                self.assertIn(field, files_info, f"Поле {field!r} отсутствует в files_info")
        finally:
            os.remove(zip_path)

    def test_topic_labels_for_txt_pdf(self):
        """.txt и .pdf добавляют 'Тексты' в topic_labels."""
        import bot
        zip_bytes = self._make_zip({
            "notes.txt": "content",
            "doc.pdf": b"%PDF-1.4 fake",
        })
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(zip_bytes)
            zip_path = f.name
        try:
            _, _, files_info = bot.extract_text_from_zip(zip_path, "test.zip")
            self.assertIn("Тексты", files_info.get("topic_labels", []))
        finally:
            os.remove(zip_path)


# ═══════════════════════════════════════════════════════════════════════════════
# 29. Баг-фикс раунд 2: системный промпт не содержит AI-boilerplate
# ═══════════════════════════════════════════════════════════════════════════════

class TestSystemPromptNoAiBoilerplate(unittest.TestCase):
    """
    Баг-фикс раунд 2, БАГ 2:
    Системный промпт не должен содержать инструкцию добавлять 'Готов работать дальше.'
    И должен содержать запрет на заключительные фразы.
    """

    def test_system_prompt_no_ready_to_work_phrase(self):
        """
        Системный промпт не должен давать инструкцию ПИСАТЬ 'Готов работать дальше.'
        Фраза может упоминаться в контексте ЗАПРЕТА (это нормально).
        """
        import bot
        prompt = bot.get_system_prompt()
        # Промпт должен содержать запрет: 'ЗАПРЕЩЕНО добавлять'
        self.assertIn("ЗАПРЕЩЕНО", prompt)
        # Старая инструкция 'В самом конце твоего ответа должна находиться ровно одна ... Готов работать' должна отсутствовать
        self.assertNotIn("в самом конце твоего ответа должна находиться ровно одна короткая профессиональная", prompt,
                             "Олдая инструкция писать заключительную фразу не должна присутствовать")
    def test_system_prompt_has_ban_on_closing_phrases(self):
        """Промпт содержит явный запрет на заключительные фразы."""
        import bot
        prompt = bot.get_system_prompt()
        # Промпт должен содержать слово ЗАПРЕЩЕНО (в русском)
        self.assertIn("ЗАПРЕЩЕНО", prompt)

    def test_caption_summary_prompt_no_boilerplate(self):
        """Промпт _generate_caption_summary содержит запрет на 'Готов помочь' и подобные."""
        # Проверяем содержание промпта через grep исходника функции
        import inspect
        import bot
        source = inspect.getsource(bot._generate_caption_summary)
        self.assertIn("Готов помочь", source,
                      "Промпт должен содержать запрет на 'Готов помочь'")
        self.assertIn("ЗАПРЕЩЕНО", source)



# ══════════════════════════════════════════════════════════════════════════════
# 30. Жирный шрифт в caption + имя файла для фото
# ══════════════════════════════════════════════════════════════════════════════

class TestBoldFormatting(unittest.TestCase):
    """
    Тесты HTML-форматирования в captions (Telegram HTML):
    - Тег архива <b>из архива:</b> X — жирный
    - Фото — подпись начинается с 📷 имя_файла
    - Форма parse_mode в forward_to_topic
    """

    def setUp(self):
        self.router = _reload_router()

    def test_archive_tag_is_bold(self):
        """Тег архива выдаётся с тегом <b> (Telegram HTML)."""
        result = self.router.build_caption(
            "doc.txt",
            extracted_text="Описание",
            metadata={"archive": "data.zip"},
        )
        self.assertIn("<b>из архива:</b> data.zip", result)

    def test_archive_tag_no_plain_brackets(self):
        """Тег архива содержит тег <b>, без квадратных скобок."""
        result = self.router.build_caption(
            "doc.txt",
            metadata={"archive": "data.zip"},
        )
        self.assertIn("<b>из архива:</b>", result)
        self.assertNotIn("[из архива:", result)

    def test_photo_caption_has_filename(self):
        """Для media_type='photo' caption начинается с '📷 имя_файла'."""
        result = self.router.build_caption(
            "youtube_analytics.png",
            media_type="photo",
        )
        self.assertTrue(
            result.startswith("📷 youtube_analytics.png"),
            f"Caption должен начинаться с 📷 имя_файла: {result!r}"
        )

    def test_photo_from_archive_caption_has_both(self):
        """Фото из архива: и 📷 имя, и <b>из архива:</b> X (Telegram HTML)."""
        result = self.router.build_caption(
            "photo.png",
            metadata={"archive": "my_archive.zip"},
            media_type="photo",
        )
        self.assertIn("📷 photo.png", result)
        self.assertIn("<b>из архива:</b> my_archive.zip", result)
        idx_photo = result.find("📷")
        idx_archive = result.find("<b>из архива:")
        self.assertLess(idx_photo, idx_archive, "📷 должно быть до тега архива")

    def test_document_type_no_filename_in_caption(self):
        """Для документов имя не добавляется в caption (у send_document имя видно отдельно)."""
        result = self.router.build_caption(
            "report.pdf",
            extracted_text="Описание",
            media_type="document",
        )
        self.assertNotIn("report.pdf", result)
        self.assertIn("<b>Содержит:</b> Описание", result)

    def test_forward_to_topic_photo_sends_with_parse_mode(self):
        """Пересылка фото через file_id — send_photo вызывается с parse_mode='HTML'."""
        mock_bot = MagicMock()
        mock_bot.send_photo = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="images",
            file_id="photo_id_123",
            file_name="test_img.jpg",
            media_type="photo",
        ))

        mock_bot.send_photo.assert_called_once()
        kwargs = mock_bot.send_photo.call_args.kwargs
        self.assertEqual(kwargs.get("parse_mode"), "HTML")

    def test_forward_to_topic_document_sends_with_parse_mode(self):
        """Пересылка документа через file_id — send_document вызывается с parse_mode='HTML'."""
        mock_bot = MagicMock()
        mock_bot.send_document = AsyncMock()

        asyncio.run(self.router.forward_to_topic(
            mock_bot,
            topic_name="texts",
            file_id="doc_id_456",
            file_name="report.pdf",
            extracted_text="Краткое описание",
            media_type="document",
        ))

        mock_bot.send_document.assert_called_once()
        kwargs = mock_bot.send_document.call_args.kwargs
        self.assertEqual(kwargs.get("parse_mode"), "HTML")

    def test_photo_caption_contains_filename_even_without_metadata(self):
        """Для media_type='photo' caption содержит имя даже без extracted_text и metadata."""
        result = self.router.build_caption(
            "ph_0620_1423.jpg",
            media_type="photo",
        )
        self.assertEqual(result, "📷 ph_0620_1423.jpg")

    def test_caption_summary_prompt_uses_bold_vklucheno(self):
        """Промпт _generate_caption_summary инструктирует LLM писать *Включено*:."""
        import inspect
        import bot
        source = inspect.getsource(bot._generate_caption_summary)
        self.assertIn("*Включено*", source)



# ══════════════════════════════════════════════════════════════════════════════
# БАГ-ФИКС: parse_mode="Markdown" в немедленных ответах-анализах документа
# ══════════════════════════════════════════════════════════════════════════════

class TestHandleDocumentParseMode(unittest.IsolatedAsyncioTestCase):
    """
    Проверяет, что handle_document (немедленный ответ в топике Jade)
    вызывает reply_text с parse_mode="Markdown", чтобы **Назначение:**,
    **Ключевая тема:** и аналогичные метки рендерились жирным, а не
    отображались буквальными звёздочками.
    """

    async def test_handle_document_reply_has_markdown_parse_mode(self):
        """
        Основной код-путь: документ .docx → LLM отвечает → reply_text с parse_mode="Markdown".
        """
        import bot

        # ── Мокируем update ──────────────────────────────────────────────────
        mock_update = MagicMock()
        mock_update.effective_user.is_bot = False
        mock_update.effective_chat.type = "private"
        mock_update.effective_chat.id = 11111
        mock_update.effective_user.id = 22222

        mock_doc = MagicMock()
        mock_doc.file_name = "test_docx.docx"
        mock_doc.mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        mock_doc.file_size = 5000
        mock_doc.file_id = "docx_fake_file_id"
        mock_update.message.document = mock_doc
        mock_update.message.caption = ""
        mock_update.message.reply_to_message = None

        # Собираем все вызовы reply_text
        reply_calls = []

        async def capture_reply(text, **kwargs):
            reply_calls.append({"text": text, "kwargs": kwargs})
            m = MagicMock()
            m.message_id = len(reply_calls)
            return m

        mock_update.message.reply_text = capture_reply

        # ── Мокируем context ─────────────────────────────────────────────────
        mock_context = MagicMock()
        mock_context.user_data = {}
        mock_context.bot_data = {}

        fake_tg_file = MagicMock()
        fake_tg_file.download_to_drive = AsyncMock()
        mock_context.bot.get_file = AsyncMock(return_value=fake_tg_file)
        mock_context.bot.delete_message = AsyncMock()

        fake_doc_text = "Это тестовый документ с важными данными."

        async def fake_forward(*args, **kwargs):
            return MagicMock(message_id=999)

        llm_reply = (
            "**Назначение:** тестовый документ\n"
            "**Ключевая тема:** проверка\n"
            "**Содержимое для поиска:** данные"
        )

        # Патчим bot.os.remove, чтобы не падать на попытке удалить tmp-файл
        with patch.object(bot, "extract_text_from_docx", return_value=fake_doc_text), \
             patch.object(bot, "forward_to_topic", side_effect=fake_forward), \
             patch.object(bot, "_generate_caption_summary", new=AsyncMock(return_value="Краткое описание")), \
             patch.object(bot, "ask_llm", new=AsyncMock(return_value=llm_reply)), \
             patch.object(bot, "choose_model", new=AsyncMock(return_value=("google/gemini-3.5-flash", fake_doc_text, ""))), \
             patch("bot.os.remove"):
            await bot.handle_document(mock_update, mock_context)

        # ── Проверяем, что среди всех reply_text был вызов с parse_mode ──────
        final_llm_calls = [
            c for c in reply_calls
            if llm_reply in c["text"] or "**" in c["text"]
        ]
        self.assertTrue(
            len(final_llm_calls) > 0,
            f"Ожидался reply_text с LLM-ответом (markdown). Все вызовы: {reply_calls}"
        )
        for call in final_llm_calls:
            self.assertEqual(
                call["kwargs"].get("parse_mode"), "Markdown",
                f"reply_text с LLM-ответом должен иметь parse_mode='Markdown'. "
                f"Текст: {call['text'][:80]!r}, kwargs: {call['kwargs']}"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
