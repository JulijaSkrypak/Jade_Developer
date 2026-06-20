# ЗАДАЧА ДЛЯ CLAUDE CODE — ШАГ 1

Необходимо исправить предсуществующий баг в тестовом файле `tests/test_phase_4_4_xlsx.py`.

## Что нужно сделать:
В функции `test_size_limit_user_picks_truncate` измените сигнатуру локальной функции-эффекта `capture_send` (~строка 455). Функция `_send_xlsx_to_llm` в `bot.py` теперь принимает 6 аргументов (последний — `status_msg_ids`), а тестовый мок принимает только 5.

Замените:
```python
        async def capture_send(update, context, combined, caption, user_id):
            sent_texts.append(combined)
```

На:
```python
        async def capture_send(update, context, combined, caption, user_id, status_msg_ids=None):
            sent_texts.append(combined)
```

## Проверка и коммит:
1. Запустите `pytest` в корне проекта и убедитесь, что теперь все тесты проходят (должно быть 149 passed).
2. Сделайте отдельный git-коммит с этим изменением. Сообщение коммита должно явно указывать, что это исправление теста и оно не связано с фиксом `should_process_message`. Пример сообщения:
   `fix(tests): resolve signature mismatch in xlsx test mock`
3. После завершения этого шага оставьте отчет о количестве пройденных тестов.
