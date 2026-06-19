## TASK-007
Статус: TODO
Описание: Фаза 5.1: PDF Thumbnail + Text Caption. Добавить генерацию миниатюры первой страницы PDF и превью текста (подписей) под файлами при их форвардинге в топики супергруппы.
Шаги:
1. Установить `poppler-utils` на VPS по SSH (`apt install poppler-utils`).
2. Установить `pdf2image` в venv бота на VPS (`pip install pdf2image`) и добавить в `requirements.txt`.
3. Добавить хелперы `build_caption` и `generate_pdf_thumbnail` в `topic_router.py`.
4. Обновить функцию `forward_to_topic` в `topic_router.py` для обработки новых параметров: `file_path`, `file_type`, `extracted_text`, `metadata`.
5. Обновить `handle_document` в `bot.py`: отложить вызов `forward_to_topic` до завершения извлечения текста для поддерживаемых типов файлов; для ZIP — сохранять bytes PDF во временный файл и вызывать генерацию превью; для неподдерживаемых файлов отправлять в топик сразу с подписью о неподдерживаемом формате.
6. Написать юнит-тесты в `tests/test_phase_5_topics.py` для проверки новой логики (успешный thumbnail, битый PDF, защищенный PDF, обрезка текста в caption, метаданные xlsx, очистка временных файлов).
7. Запустить все тесты (`pytest tests/test_phase_5_topics.py -v`) локально и на VPS, убедиться, что они проходят.
8. Перезапустить службу бота на VPS (`systemctl restart vibe-bot`) и проверить логи.
9. Провести ручное тестирование в Telegram-боте.
