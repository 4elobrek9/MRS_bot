import logging
import os
import aiosqlite
from pathlib import Path
from typing import Dict, Any, List, Tuple
from aiogram import types, Bot

logger = logging.getLogger(__name__)

# Импортируем модуль database как db
import database as db
from core.group.stat.manager import ProfileManager

# Глобальная блокировка для безопасной работы с файлом промокодов
import asyncio
promo_file_lock = asyncio.Lock()

# Путь к файлу с промокодами
PROMO_FILE_PATH = Path("C:/4chan/.GITHUB/MRS_bot/data/PROMO.txt")

async def load_promocodes() -> Dict[str, Tuple[int, int]]:
    """
    Загружает промокоды из файла
    Формат: CODE AMOUNT MAX_USES
    Возвращает словарь: {code: (amount, max_uses)}
    """
    async with promo_file_lock:
        promocodes = {}
        
        if not PROMO_FILE_PATH.exists():
            logger.warning(f"Promo file {PROMO_FILE_PATH} not found!")
            return promocodes
            
        try:
            with open(PROMO_FILE_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):  # Пропускаем пустые строки и комментарии
                        parts = line.split()
                        if len(parts) >= 3:
                            try:
                                code = parts[0].upper()
                                amount = int(parts[1])
                                max_uses = int(parts[2])
                                promocodes[code] = (amount, max_uses)
                            except ValueError:
                                logger.warning(f"Invalid line in promo file: {line}")
            logger.info(f"Loaded {len(promocodes)} promocodes from file")
        except Exception as e:
            logger.error(f"Error reading promo file: {e}")
            
        return promocodes

async def save_promocodes(promocodes: Dict[str, Tuple[int, int]]) -> None:
    """
    Сохраняет промокоды в файл
    """
    async with promo_file_lock:
        try:
            # Создаем директорию, если она не существует
            PROMO_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            with open(PROMO_FILE_PATH, 'w', encoding='utf-8') as f:
                for code, (amount, max_uses) in promocodes.items():
                    f.write(f"{code} {amount} {max_uses}\n")
            logger.info(f"Saved {len(promocodes)} promocodes to file")
        except Exception as e:
            logger.error(f"Error saving promo file: {e}")

async def update_promocode_use_count(code: str) -> bool:
    """
    Обновляет счетчик использований промокода
    Возвращает True если промокод еще действителен, False если удален
    """
    promocodes = await load_promocodes()
    code_upper = code.upper()
    
    if code_upper not in promocodes:
        return False
        
    amount, max_uses = promocodes[code_upper]
    
    if max_uses <= 1:
        # Удаляем промокод, если использований не осталось
        del promocodes[code_upper]
        await save_promocodes(promocodes)
        return True
    else:
        # Уменьшаем счетчик использований
        promocodes[code_upper] = (amount, max_uses - 1)
        await save_promocodes(promocodes)
        return True

async def handle_promo_command(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """Обработчик команды промо"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply("❌ Используйте: промо <код>")
            return
            
        promocode = parts[1]
        user_id = message.from_user.id
        
        # Проверяем, использовал ли уже пользователь этот промокод
        if await db.check_promo_used(user_id, promocode):
            await message.reply("❌ Вы уже использовали этот промокод!")
            return
        
        # Загружаем промокоды из файла
        promocodes = await load_promocodes()
        code_upper = promocode.upper()
        
        if code_upper not in promocodes:
            await message.reply("❌ Неверный или неактивный промокод")
            return
            
        amount, max_uses = promocodes[code_upper]
        
        # Проверяем, остались ли использования
        if max_uses <= 0:
            await message.reply("❌ У этого промокода закончились использования")
            return
            
        # Начисляем награду
        await profile_manager.update_lumcoins(user_id, amount)
        
        # Обновляем счетчик использований промокода
        still_valid = await update_promocode_use_count(promocode)
        
        # Помечаем промокод как использованный для этого пользователя
        await db.mark_promo_used(user_id, promocode)
        
        if still_valid:
            await message.reply(f"✅ Промокод активирован! Получено {amount} Lumcoins. Осталось использований: {max_uses - 1}")
        else:
            await message.reply(f"✅ Промокод активирован! Получено {amount} Lumcoins. Промокод больше недействителен.")
            
    except Exception as e:
        logger.error(f"Error activating promo code: {e}")
        await message.reply("❌ Произошла ошибка при активации промокода.")

def setup_promo_handlers(main_dp, bot_instance: Bot, profile_manager_instance: ProfileManager):
    """Настройка обработчиков промокодов"""
    # Добавляем обработчик для команды "промо"
    @main_dp.message(lambda message: message.text and message.text.lower().startswith(("промо", "promo")))
    async def promo_handler(message: types.Message):
        await handle_promo_command(message, bot_instance, profile_manager_instance)
    
    logger.info("Promo handlers setup complete")