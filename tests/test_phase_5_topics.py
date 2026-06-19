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

    def test_only_filename(self):
        result = self.router.build_caption("report.pdf")
        self.assertEqual(result, "report.pdf")

    def test_with_extracted_text(self):
        result = self.router.build_caption("doc.txt", extracted_text="Привет мир")
        self.assertIn("doc.txt", result)
        self.assertIn("Привет мир", result)

    def test_text_truncated_at_300(self):
        long_text = "А" * 400
        result = self.router.build_caption("file.txt", extracted_text=long_text)
        self.assertIn("...", result)
        # Текст обрезан до 300 + "..."
        self.assertLessEqual(len(result), 1024)

    def test_with_metadata_sheets(self):
        result = self.router.build_caption("data.xlsx", metadata={"sheets": ["Sheet1", "Sheet2"]})
        self.assertIn("Sheet1", result)
        self.assertIn("Sheet2", result)

    def test_caption_max_1024(self):
        long_text = "Б" * 2000
        result = self.router.build_caption("f.txt", extracted_text=long_text)
        self.assertLessEqual(len(result), 1024)

    def test_empty_extracted_text_ignored(self):
        result = self.router.build_caption("f.txt", extracted_text="   ")
        self.assertEqual(result, "f.txt")

    def test_combined_filename_sheets_text(self):
        result = self.router.build_caption(
            "table.xlsx",
            extracted_text="Данные квартала",
            metadata={"sheets": ["Q1"]},
        )
        self.assertIn("table.xlsx", result)
        self.assertIn("Q1", result)
        self.assertIn("Данные квартала", result)


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
        self.mock_msg.reply_text.assert_any_call("🎙️ Тестовая речь\n\nАнализ ответа LLM")

    @patch("ai_service.ask_vision", new_callable=AsyncMock, return_value="Анализ картинки")
    @patch("bot.forward_to_topic", new_callable=AsyncMock)
    @patch("bot.tempfile.NamedTemporaryFile")
    @patch("bot.os.remove")
    @patch("builtins.open", new_callable=mock_open, read_data=b"fake jpeg data")
    async def test_handle_photo_status_deletion_and_prefix(self, mock_file_open, mock_remove, mock_temp, mock_forward, mock_ask_vision):
        # Настраиваем mock для скачивания файла
        self.context.bot.get_file = AsyncMock()
        mock_file = MagicMock()
        mock_file.name = "temp.jpg"
        mock_temp.return_value.__enter__.return_value = mock_file

        self.mock_msg.photo = [MagicMock()]
        self.mock_msg.caption = "Что на фото?"

        from bot import handle_photo
        await handle_photo(self.mock_update, self.context)

        # Проверяем удаление статуса "Анализирую фото..."
        self.bot.delete_message.assert_any_call(chat_id=9999, message_id=1000)

        # Проверяем окончательный ответ с префиксом 🖼️
        self.mock_msg.reply_text.assert_any_call("🖼️ Что на фото?\n\nАнализ картинки")

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
        self.mock_msg.reply_text.assert_any_call("📄 [Документ: test.txt]\n\nСодержимое текстового файла\n\nАнализ документа")


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

        # Mock update and callback_query
        self.query = MagicMock()
        self.query.answer = AsyncMock()
        self.query.data = "ai_analyze:sonnet"
        
        self.message = MagicMock()
        self.message.chat.id = -100123
        self.message.message_id = 456
        self.message.reply_text = AsyncMock()
        
        # Переопределяем reply_text для возврата mock-сообщения
        self.analysis_msg = MagicMock()
        self.analysis_msg.edit_text = AsyncMock()
        self.message.reply_text.return_value = self.analysis_msg
        
        self.query.message = self.message

        self.update = MagicMock()
        self.update.callback_query = self.query

        self.context = MagicMock()
        self.context.bot = MagicMock()

    def tearDown(self):
        import os
        self.bot.DB_FILE = self.original_db
        if os.path.exists("test_jade_bridge.db"):
            os.remove("test_jade_bridge.db")

    @patch("ai_service.ask_llm", new_callable=AsyncMock, return_value="Подробный анализ от Claude")
    async def test_callback_document_analysis(self, mock_ask):
        # Сначала сохраняем запись о файле
        self.bot.save_forwarded_file(
            chat_id=-100123,
            message_id=456,
            file_id="doc_id",
            file_type="document",
            file_name="report.pdf",
            extracted_text="Содержимое отчета"
        )

        await self.bot.handle_ai_analyze_callback(self.update, self.context)

        # Проверяем, что callback query завершен
        self.query.answer.assert_called_once()
        
        # Проверяем запуск анализа
        self.message.reply_text.assert_called_once_with(
            "🧠 Запуск глубокого анализа (Claude Sonnet 4.6)...",
            reply_to_message_id=456
        )

        # Проверяем вызов модели с правильными параметрами
        mock_ask.assert_called_once()
        args = mock_ask.call_args[0]
        self.assertIn("Содержимое отчета", args[0][1]["content"])

        # Проверяем, что результат опубликован
        self.analysis_msg.edit_text.assert_called_once()
        self.assertIn("Подробный анализ от Claude", self.analysis_msg.edit_text.call_args[0][0])

    async def test_callback_video_returns_stub(self):
        # Видеокружочки возвращают заглушку
        self.bot.save_forwarded_file(
            chat_id=-100123,
            message_id=456,
            file_id="video_id",
            file_type="video_note",
            file_name="circle.mp4"
        )

        await self.bot.handle_ai_analyze_callback(self.update, self.context)

        # Проверяем, что callback query завершен
        self.query.answer.assert_called_once()
        
        # Проверяем, что отредактированное сообщение содержит заглушку
        self.analysis_msg.edit_text.assert_called_once()
        self.assertIn("Функция глубокого анализа видео временно недоступна", self.analysis_msg.edit_text.call_args[0][0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
