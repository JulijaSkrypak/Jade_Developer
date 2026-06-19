"""
ai_service.py — Модуль интеграции с нейросетями через OpenRouter.
Отделяет бизнес-логику бота от генерации ответов (Правило 14).
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)

# Чтение конфигурации OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()

# Дефолтные модели (в случае если не переопределены в env)
MODEL_SIMPLE = os.getenv("MODEL_SIMPLE", "google/gemini-3.5-flash")
MODEL_COMPLEX = os.getenv("MODEL_COMPLEX", "anthropic/claude-sonnet-4-6")


async def ask_llm(messages: list[dict], model: str) -> str:
    """
    Отправляет текстовый запрос (диалог) в OpenRouter.

    Args:
        messages: Список сообщений в формате [{"role": "user/assistant/system", "content": "..."}]
        model: Идентификатор модели OpenRouter (например, "google/gemini-3.5-flash")

    Returns:
        str — ответ от модели.
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY не задан в переменных окружения")

    url = f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
    }

    # Логируем отправку запроса без вывода токена
    logger.info(f"[ai_service] Отправка запроса в {model} (сообщений: {len(messages)})")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    try:
        reply = data["choices"][0]["message"]["content"]
        if not reply:
            raise ValueError("Модель вернула пустой ответ")
        return reply.strip()
    except (KeyError, IndexError) as e:
        logger.error(f"[ai_service] Ошибка парсинга ответа OpenRouter: {e}. Тело ответа: {data}")
        raise RuntimeError(f"Некорректный формат ответа от нейросети: {e}")


async def ask_vision(image_b64: str, question: str, model: str) -> str:
    """
    Отправляет изображение (base64) и текстовый вопрос в OpenRouter для Vision-анализа.

    Args:
        image_b64: Строка изображения в кодировке base64.
        question: Вопрос к изображению.
        model: Идентификатор модели (например, "anthropic/claude-sonnet-4-6").

    Returns:
        str — ответ от Vision-модели.
    """
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY не задан в переменных окружения")

    url = f"{OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # Формируем контент для мультимодальной модели
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}"
                    }
                }
            ]
        }
    ]
    
    payload = {
        "model": model,
        "messages": messages,
    }

    logger.info(f"[ai_service] Отправка Vision запроса в {model}")

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    try:
        reply = data["choices"][0]["message"]["content"]
        if not reply:
            raise ValueError("Vision-модель вернула пустой ответ")
        return reply.strip()
    except (KeyError, IndexError) as e:
        logger.error(f"[ai_service] Ошибка парсинга Vision-ответа OpenRouter: {e}. Тело ответа: {data}")
        raise RuntimeError(f"Некорректный формат ответа от Vision-модели: {e}")
