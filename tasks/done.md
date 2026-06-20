## БАГ-ФИКС: parse_mode="Markdown" в ответах-анализах документов
Статус: DONE
Дата выполнения: 2026-06-20

Описание: Звёздочки markdown (`**Назначение:**`, `**Ключевая тема:**`, `**Содержимое для поиска:**`) отображались буквально в прямом ответе бота в топике Jade вместо жирного текста.

Что сделано:
- ✅ Найден код-путь: `handle_document` → `ask_llm` → `reply_text(final_reply)` (строка ~1857 `bot.py`) — `parse_mode` отсутствовал
- ✅ Проверены **все** вызовы `reply_text` / `edit_text` с LLM-ответами — найдено **6 мест** без `parse_mode`:
  - `handle_text` (~454) — ответ на текстовый запрос
  - `handle_voice` (~530) — голос + LLM ответ
  - `_send_xlsx_to_llm` (~1363) — ответ по Excel
  - `handle_document` (~1857) — **основной баг** (ответ-анализ в топике Jade)
  - `execute_deferred_analysis` (~2121) — `edit_text` с `*Глубокий анализ*`
  - `handle_document` / ZIP-путь (~1704) — **найдено после ручного теста в Telegram**: сводка архива содержит LLM-текст с `**Включено**:`, но `parse_mode` отсутствовал
- ✅ Во все 6 мест добавлен `parse_mode="Markdown"`
- ✅ Обновлены 2 существующих теста (`test_handle_voice_status_deletion_and_prefix`, `test_handle_document_plain_text_status_deletion_and_prefix`)
- ✅ Добавлен новый тест `TestHandleDocumentParseMode::test_handle_document_reply_has_markdown_parse_mode`
- ✅ Тесты локально и на VPS: `138 passed, 17 subtests passed`
- ✅ Деплой: `systemctl status vibe-bot` → `active (running)`

Gate пройден: все 6 мест исправлены, тесты зелёные, сервис активен.
Ручная проверка: отправить `.docx` и `.zip` в топик Jade — `**Назначение:**` и `**Включено**:` должны рендериться жирным без видимых звёздочек.

---

## TASK-001

Статус: DONE
Дата выполнения: 2026-06-12
Описание: Выполнить все шаги из PHASE_1_bot_echo.md на VPS 178.105.1.60 для развертывания echo Telegram-бота.

Результат:
- ✅ Зависимости установлены (python3, python3-venv и др.)
- ✅ Директория `/home/bridge/vibe-telegram-bot` создана
- ✅ venv создан, `python-telegram-bot==20.3` установлен
- ✅ Файл `.env` с `TELEGRAM_TOKEN` создан
- ✅ `bot.py` создан с обработчиками `/start`, `/ping` и echo
- ✅ systemd-сервис `vibe-bot.service` создан и добавлен в автозагрузку
- ✅ `systemctl status vibe-bot` → `active (running)`

Gate пройден: сервис запущен и работает стабильно.

---

## TASK-003
Статус: DONE
Дата выполнения: 2026-06-16
Описание: Фаза 3 — Groq Whisper STT для vibe-telegram-bot. Голосовые сообщения через Groq Whisper API.

Что сделано:
- ✅ `ffmpeg` установлен на VPS (v6.1.1-3ubuntu5)
- ✅ `groq==1.4.0` установлен в venv (+ pydantic, distro)
- ✅ `GROQ_API_KEY` добавлен в `/home/bridge/vibe-telegram-bot/.env`
- ✅ `bot.py.backup` создан (резервная копия старого бота)
- ✅ `bot.py` обновлён: добавлен `handle_voice()` handler
  - скачивает `.ogg` голосовое сообщение
  - конвертирует ffmpeg → `.mp3` (16kHz, mono)
  - отправляет в Groq Whisper API (модель `whisper-large-v3`, язык `ru`)
  - показывает `📝 Распознано: <текст>`
  - передаёт текст в OpenRouter → отвечает пользователю
- ✅ Сервис `vibe-bot` перезапущен и работает: `active (running)`
- ✅ Лог: `Bot started with Groq Whisper STT support`

Gate пройден: бот принимает голосовые сообщения и отвечает текстом через LLM.
Текстовый функционал не сломан.

---

## TASK — Фаза 4.4: Обработка Excel (.xlsx)
Статус: DONE
Дата выполнения: 2026-06-17
Коммит: `8c2d954` — feat: Фаза 4.4 — поддержка Excel (.xlsx) файлов

Что сделано:
- ✅ `openpyxl==3.1.5` установлен в venv на VPS
- ✅ `requirements.txt` создан в корне проекта
- ✅ `bot.py` обновлён — новые функции и диалоговая логика:
  - `sheet_to_markdown()` — конвертирует лист в Markdown-таблицу
  - `_open_xlsx_data()` — читает листы с data_only=True, fallback для невычисленных формул
  - `_process_xlsx_sheets()` — проверяет лимит 40 000 символов
  - `handle_xlsx_dialog()` — выбор листа и способа усечения
  - `handle_document()` — ветка .xlsx; `handle_text()` — перехват диалога
- ✅ `tests/test_phase_4_4_xlsx.py` — 14 тестов, **14/14 passed**
- ✅ Сервис vibe-bot перезапущен: active (running)
- ✅ Лог: Bot started with ... ZIP/XLSX support

Gate пройден: один лист → без диалога; несколько листов → выбор; формулы → пометка; большой файл → спрашивает 1/2; повреждённый → ошибка без краша.

---

## TASK-005
Статус: DONE
Дата выполнения: 2026-06-19
Описание: Исправить баги в Фазе 5 — пересылка файлов неподдерживаемых форматов в топики.

Что сделано:
- ✅ Найден баг: вызов `forward_to_topic` располагался ПОСЛЕ раннего `return` для неподдерживаемых форматов (строка ~1036 в `bot.py`), поэтому файлы типа `.rar` никогда не пересылались в топик `ATTENTION`.
- ✅ Исправление: блок `forward_to_topic` перенесён ДО проверки расширения (`if ext not in ...`), завёрнут в `try/except` — ошибки пересылки не роняют основной flow.
- ✅ Удалён дублирующий вызов `forward_to_topic` внутри `try`-блока скачивания файла.

Тесты (`pytest tests/test_phase_5_topics.py -v`):
```
32 passed, 18 subtests passed in 0.21s
```

Синтаксис: `python3 -m py_compile bot.py` → OK

Логи после перезапуска:
```
Started vibe-bot.service - Vibe Telegram Bot.
Bot started with Smart Router (choose_model) + Groq Whisper STT + PDF/DOCX/TXT/MD/JSON/ZIP/XLSX support + Фаза 5: маршрутизация по топикам Jade_Developer
```

Gate пройден: `systemctl status vibe-bot` → `active (running)`, бот стартует без ошибок, все 32 теста зелёные.

---

## TASK-006
Статус: DONE
Дата выполнения: 2026-06-19
Описание: Изменить формат вывода распознанных голосовых сообщений (в чате с пользователем и при пересылке в супергруппу).

Что сделано:
- ✅ Изменен формат ответа в чате бота (reply):
  ```python
  f"Распознано...\n🎙️ {recognized_text}"
  ```
  вместо старого `🎙️ Распознано:\n{recognized_text}`.
- ✅ Изменен формат отправки в топик супергруппы:
  ```python
  f"🎙️ {recognized_text}"
  ```
  вместо отправки простого текста.
- ✅ Изменен юнит-тест `test_voice_transcript_goes_to_texts_as_message` в `tests/test_phase_5_topics.py`, чтобы проверять наличие эмодзи микрофона `🎙️`.

Тесты на VPS (`pytest tests/test_phase_5_topics.py -v`):
```
32 passed, 18 subtests passed in 0.21s
```

Синтаксис: `python3 -m py_compile bot.py` на VPS → OK

Логи после перезапуска службы vibe-bot:
```
Jun 19 09:29:10 JadeAdvisor systemd[1]: Started vibe-bot.service - Vibe Telegram Bot.
Jun 19 09:29:10 JadeAdvisor python[121160]: INFO:__main__:Bot started with Smart Router (choose_model) + Groq Whisper STT + PDF/DOCX/TXT/MD/JSON/ZIP/XLSX support + Фаза 5: маршрутизация по топикам Jade_Developer
```

Gate пройден: бот успешно запущен, все тесты на сервере зеленые.

---

## TASK-007
Статус: DONE
Дата выполнения: 2026-06-19
Описание: Фаза 5.1 — PDF Thumbnail + Text Caption при форвардинге файлов в топики.

Что сделано:
- ✅ `poppler-utils` установлен на VPS (`apt install poppler-utils`)
- ✅ `pdf2image` установлен в venv (`pip install pdf2image`)
- ✅ `topic_router.py` — добавлены функции:
  - `generate_pdf_thumbnail(pdf_path)` → bytes | None (через pdf2image+poppler, graceful degradation)
  - `build_caption(file_name, extracted_text, metadata)` → str (max 1024 символа)
- ✅ `forward_to_topic` получил новые параметры: `file_path`, `file_type`, `extracted_text`, `metadata`
  - PDF + `file_path` → пробует отправить thumbnail как фото с подписью
  - PDF в `file_bytes` → сохраняет во temp, генерирует thumbnail, затем удаляет temp
  - Любой файл + `extracted_text`/`metadata` → добавляет caption
- ✅ `bot.py` — `handle_document` переработан:
  - Неподдерживаемые форматы → forward сразу с пометкой «не поддерживается»
  - XLSX → forward с `metadata={"sheets": [...]}` (список листов в подписи)
  - ZIP → forward с `extracted_text` после разбора архива (до early return по лимитам)
  - PDF → forward с `file_path=tmp_path` + `extracted_text` (thumbnail + превью текста)
  - DOCX/TXT/MD/JSON → forward с `extracted_text` после извлечения

Тесты (`pytest tests/test_phase_5_topics.py -v`):
```
49 passed, 18 subtests passed in 0.30s
```
Добавлено 17 новых тестов (классы TestBuildCaption, TestGeneratePdfThumbnail, TestForwardWithCaption, TestForwardPdfThumbnailFromBytes).

Синтаксис: `python3 -m py_compile bot.py && python3 -m py_compile topic_router.py` → OK

Логи после перезапуска:
```
Started vibe-bot.service - Vibe Telegram Bot.
Bot started with Smart Router (choose_model) + Groq Whisper STT + PDF/DOCX/TXT/MD/JSON/ZIP/XLSX support + Фаза 5: маршрутизация по топикам Jade_Developer
```

Gate пройден: `systemctl status vibe-bot` → `active (running)`, 49/49 тестов зелёные, ошибок при старте нет.

---

## TASK-004
Статус: DONE
Дата выполнения: 2026-06-16
Описание: Подключиться к VPS (178.105.1.60, пользователь bridge) по SSH через paramiko, выполнить аудит названий моделей в проекте vibe-telegram-bot и вывести результаты в таблице.

Что сделано:
- ✅ Создан скрипт для подключения по SSH.
- ✅ Проведен аудит всех файлов в проекте `/home/bridge/vibe-telegram-bot`, содержащих слово "model" или упоминания конкретных моделей.
- ✅ Результаты представлены в виде markdown-таблицы.
- ✅ Все требования к аутентификации и маскированию секретов соблюдены.

Gate пройден: аудит завершен, результаты выведены пользователю.

---

## БАГ: corrupted PDF не доходит в топик
Статус: DONE
Дата выполнения: 2026-06-19
Описание: Исправить баг, из-за которого невалидные (повреждённые) PDF-файлы не пересылались в Telegram-топик "Тексты".

Что сделано:
- ✅ Логика извлечения текста (`extract_text_from_pdf`) завернута в `try/except Exception` в `bot.py`
- ✅ Ошибка извлечения текста теперь не прерывает обработчик документа; `raw_text` устанавливается в `None`, и файл успешно отправляется в топик
- ✅ Аналогичные try-except обёртки добавлены для извлечения текста из `.docx`, `.txt`, `.md`, `.json` для отказоустойчивости
- ✅ Добавлен unit-тест `TestCorruptedPdfHandling` в `tests/test_phase_5_topics.py` для проверки сценария с поврежденным PDF
- ✅ Проведен деплой на VPS, тесты на VPS запущены и успешно пройдены (50/50 passed)

Gate пройден: битый PDF возвращает предупреждение пользователю в чате бота, но успешно пересылается в нужный топик супергруппы без thumbnail и caption.

✅ Ручное подтверждение в Telegram (19 июня 2026):
- corrupted_test.pdf → дошёл в топик «Тексты» как обычный документ, без превью и без caption (fallback работает)
- protected_test.pdf → дошёл в топик «Тексты» с превью-картинкой (рендер первой страницы) и caption с текстом «Dummy PDF file»
TASK-007 полностью закрыта.
