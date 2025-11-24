# background_tasks.py
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

async def mistral_health_check(mistral_handler, interval=300):
    """Периодическая проверка здоровья Mistral обработчика"""
    while True:
        try:
            await asyncio.sleep(interval)
            if mistral_handler:
                # Простая проверка - очистка старых контекстов
                await mistral_handler.cleanup_old_contexts()
                logger.debug("Mistral handler health check completed")
        except Exception as e:
            logger.error(f"Mistral health check error: {e}")

async def start_background_tasks(mistral_handler):
    """Запускает все фоновые задачи"""
    health_task = asyncio.create_task(mistral_health_check(mistral_handler))
    return [health_task]
