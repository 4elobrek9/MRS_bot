import os
import logging
from typing import Dict, Tuple, Optional
from aiogram import types, Bot, Router, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from pathlib import Path

from database import check_promo_used, mark_promo_used, get_promo_use_count, DB_PATH
import aiosqlite
from core.group.stat.manager import ProfileManager

logger = logging.getLogger(__name__)

PROMO_FILE = Path("data/PROMO.txt")

def load_promocodes() -> Dict[str, Tuple[int, int]]:
    promocodes = {}
    if not PROMO_FILE.exists():
        logger.warning(f"Promo file {PROMO_FILE} does not exist")
        return promocodes
    
    try:
        with open(PROMO_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split()
                if len(parts) < 3:
                    continue
                
                code = parts[0].upper()
                try:
                    max_uses = int(parts[1])
                    coins = int(parts[2])
                    promocodes[code] = (max_uses, coins)
                except ValueError:
                    logger.warning(f"Invalid promo line: {line}")
                    continue
    except Exception as e:
        logger.error(f"Error loading promocodes: {e}")
    
    return promocodes

async def handle_promo_command(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ Использование: /промо <код>")
        return
    
    promocode = args[1].upper()
    user_id = message.from_user.id
    
    promocodes = load_promocodes()
    
    if promocode not in promocodes:
        await message.reply("❌ Неверный промокод.")
        return
    
    if await check_promo_used(user_id, promocode):
        await message.reply("❌ Вы уже использовали этот промокод.")
        return
    
    max_uses, coins = promocodes[promocode]
    
    if max_uses > 0:
        used_count = await get_promo_use_count(promocode)
        if used_count >= max_uses:
            await message.reply("❌ Лимит использований этого промокода исчерпан.")
            return
    
    try:
        profile = await profile_manager.get_user_profile(message.from_user)
        current_balance = profile.get('balance', 0) if profile else 0
        
        await profile_manager.update_user_balance(user_id, current_balance + coins)
        
        await mark_promo_used(user_id, promocode)
        
        await message.reply(f"✅ Промокод активирован! Вам начислено {coins} монет.")
    except Exception as e:
        logger.error(f"Error activating promo code: {e}")
        await message.reply("❌ Произошла ошибка при активации промокода.")

def setup_promo_handlers(main_dp: Router, bot_instance: Bot, profile_manager_instance: ProfileManager):
    promo_router = Router()
    
    @promo_router.message(Command("промо", "promo"))
    async def promo_command(message: types.Message):
        await handle_promo_command(message, bot_instance, profile_manager_instance)
    
    main_dp.include_router(promo_router)