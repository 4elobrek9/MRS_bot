import logging

# Отключаем отладочные сообщения от aiosqlite
logging.getLogger('aiosqlite').setLevel(logging.WARNING)
from typing import List, Dict, Any, Optional
import json
from datetime import datetime, timedelta
import aiosqlite
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.utils.markdown import hbold, hcode
from aiogram.enums import ParseMode

from core.group.stat.manager import ProfileManager
from core.group.stat.quests_config import QuestsConfig

logger = logging.getLogger(__name__)

# Роутер для квестов
quests_router = Router(name="quests_router")

async def ensure_quests_db():
    """Инициализация базы данных для заданий"""
    async with aiosqlite.connect('profiles.db') as db:
        # Таблица для активных заданий пользователя
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_quests (
                user_id INTEGER,
                quest_id TEXT,
                quest_type TEXT,  -- 'daily' или 'weekly'
                quest_data TEXT,  -- JSON с данными задания
                progress INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT FALSE,
                reward_claimed BOOLEAN DEFAULT FALSE,
                expires_at TIMESTAMP,
                PRIMARY KEY (user_id, quest_id)
            )
        ''')
        
        # Таблица для отслеживания последнего обновления заданий
        await db.execute('''
            CREATE TABLE IF NOT EXISTS quest_refresh_times (
                user_id INTEGER PRIMARY KEY,
                last_daily_refresh TIMESTAMP,
                last_weekly_refresh TIMESTAMP
            )
        ''')
        
        await db.commit()

async def get_user_quests(user_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """Получает текущие задания пользователя"""
    async with aiosqlite.connect('profiles.db') as db:
        db.row_factory = aiosqlite.Row
        
        now = datetime.now()
        
        # Получаем все активные задания
        cursor = await db.execute('''
            SELECT * FROM user_quests 
            WHERE user_id = ? AND expires_at > ?
        ''', (user_id, now))
        
        rows = await cursor.fetchall()
        
        quests = {"daily": [], "weekly": []}
        for row in rows:
            quest_data = json.loads(row['quest_data'])
            quest_data.update({
                'progress': row['progress'],
                'completed': bool(row['completed']),
                'reward_claimed': bool(row['reward_claimed']),
                'expires_at': row['expires_at']
            })
            quests[row['quest_type']].append(quest_data)
            
        return quests

async def refresh_user_quests(user_id: int, profile_manager: ProfileManager) -> None:
    """Обновляет задания пользователя, если пришло время"""
    async with aiosqlite.connect('profiles.db') as db:
        db.row_factory = aiosqlite.Row
        now = datetime.now()
        
        # Получаем время последнего обновления
        cursor = await db.execute('''
            SELECT * FROM quest_refresh_times WHERE user_id = ?
        ''', (user_id,))
        refresh_times = await cursor.fetchone()
        
        if not refresh_times:
            # Первый раз - создаём записи
            last_daily = (now - timedelta(days=1)).isoformat()
            last_weekly = (now - timedelta(days=7)).isoformat()
            await db.execute('''
                INSERT INTO quest_refresh_times (user_id, last_daily_refresh, last_weekly_refresh)
                VALUES (?, ?, ?)
            ''', (user_id, last_daily, last_weekly))
            refresh_times = {
                'last_daily_refresh': last_daily,
                'last_weekly_refresh': last_weekly
            }
        
        # Проверяем ежедневные задания
        last_daily = datetime.fromisoformat(refresh_times['last_daily_refresh'])
        if (now - last_daily).days >= 1:
            # Удаляем старые ежедневные задания
            await db.execute('''
                DELETE FROM user_quests 
                WHERE user_id = ? AND quest_type = 'daily'
            ''', (user_id,))
            
            # Добавляем новые
            daily_quests = QuestsConfig.get_daily_quests()
            for quest in daily_quests:
                await db.execute('''
                    INSERT INTO user_quests 
                    (user_id, quest_id, quest_type, quest_data, expires_at)
                    VALUES (?, ?, 'daily', ?, ?)
                ''', (
                    user_id,
                    quest['id'],
                    json.dumps(quest),
                    (now + timedelta(days=1)).isoformat()
                ))
            
            # Обновляем время обновления
            await db.execute('''
                UPDATE quest_refresh_times 
                SET last_daily_refresh = ?
                WHERE user_id = ?
            ''', (now.isoformat(), user_id))
        
        # Проверяем еженедельные задания
        last_weekly = datetime.fromisoformat(refresh_times['last_weekly_refresh'])
        if (now - last_weekly).days >= 7:
            # Удаляем старые еженедельные задания
            await db.execute('''
                DELETE FROM user_quests 
                WHERE user_id = ? AND quest_type = 'weekly'
            ''', (user_id,))
            
            # Добавляем новые
            weekly_quests = QuestsConfig.get_weekly_quests()
            for quest in weekly_quests:
                await db.execute('''
                    INSERT INTO user_quests 
                    (user_id, quest_id, quest_type, quest_data, expires_at)
                    VALUES (?, ?, 'weekly', ?, ?)
                ''', (
                    user_id,
                    quest['id'],
                    json.dumps(quest),
                    (now + timedelta(days=7)).isoformat()
                ))
            
            # Обновляем время обновления
            await db.execute('''
                UPDATE quest_refresh_times 
                SET last_weekly_refresh = ?
                WHERE user_id = ?
            ''', (now.isoformat(), user_id))
        
        await db.commit()

async def notify_quest_progress(bot: Bot, user_id: int, quest_data: dict, progress: int, completed: bool = False):
    """Отправляет уведомление о прогрессе задания"""
    try:
        text = f"📋 **Обновление задания**\n\n"
        text += f"🎯 {quest_data['name']}\n"
        text += f"└ Прогресс: {progress}/{quest_data['required']['count']}\n"
        
        if completed:
            text += f"\n✨ **Задание выполнено!**\n"
            text += f"💰 Используйте команду `задания` чтобы получить награду!"
        
        try:
            # Пробуем отправить в ЛС
            await bot.send_message(user_id, text, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление в ЛС {user_id}: {e}")
            # Если не получилось, попробуем найти последний групповой чат
            async with aiosqlite.connect('profiles.db') as db:
                cursor = await db.execute(
                    'SELECT last_group_chat_id FROM user_profiles WHERE user_id = ?', 
                    (user_id,)
                )
                result = await cursor.fetchone()
                if result and result[0]:
                    await bot.send_message(
                        result[0],
                        f"@{user_id}\n" + text,
                        parse_mode=ParseMode.MARKDOWN
                    )
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления о прогрессе задания: {e}")

async def update_quest_progress(
    user_id: int,
    quest_type: str,
    quest_id: str,
    progress: int,
    bot: Bot = None
) -> bool:
    """Обновляет прогресс задания"""
    async with aiosqlite.connect('profiles.db') as db:
        cursor = await db.execute('''
            SELECT quest_data, progress, completed
            FROM user_quests
            WHERE user_id = ? AND quest_id = ? AND quest_type = ?
        ''', (user_id, quest_id, quest_type))
        
        quest = await cursor.fetchone()
        if not quest:
            return False
            
        quest_data = json.loads(quest[0])
        required = quest_data['required']['count']
        old_progress = quest[1]
        was_completed = quest[2]
        
        new_progress = min(progress, required)
        completed = new_progress >= required
        
        # Обновляем только если есть изменения
        if new_progress > old_progress or (completed and not was_completed):
            await db.execute('''
                UPDATE user_quests
                SET progress = ?, completed = ?
                WHERE user_id = ? AND quest_id = ? AND quest_type = ?
            ''', (new_progress, completed, user_id, quest_id, quest_type))
            
            await db.commit()
            
            # Отправляем уведомление если есть бот
            if bot and (completed != was_completed or new_progress > old_progress):
                await notify_quest_progress(bot, user_id, quest_data, new_progress, completed)
        
        return completed

async def claim_quest_reward(
    user_id: int,
    quest_type: str,
    quest_id: str,
    profile_manager: ProfileManager
) -> Optional[Dict[str, int]]:
    """Забирает награду за выполненное задание"""
    async with aiosqlite.connect('profiles.db') as db:
        cursor = await db.execute('''
            SELECT quest_data, completed, reward_claimed
            FROM user_quests
            WHERE user_id = ? AND quest_id = ? AND quest_type = ?
        ''', (user_id, quest_id, quest_type))
        
        quest = await cursor.fetchone()
        if not quest:
            return None
            
        quest_data = json.loads(quest[0])
        completed = quest[1]
        reward_claimed = quest[2]
        
        if not completed or reward_claimed:
            return None
        
        # Определяем награду
        rewards = {}
        if quest_type == 'daily':
            rewards = QuestsConfig.DAILY_QUEST_REWARDS[quest_data['difficulty']]
            await profile_manager.update_lumcoins(user_id, rewards['lumcoins'])
            await profile_manager.update_exp(user_id, rewards['exp'])
        else:  # weekly
            plum_reward = QuestsConfig.WEEKLY_QUEST_PLUM_REWARDS[quest_data['difficulty']]
            await profile_manager.update_plumcoins(user_id, plum_reward)
            rewards = {'plumcoins': plum_reward}
        
        # Отмечаем награду как полученную
        await db.execute('''
            UPDATE user_quests
            SET reward_claimed = TRUE
            WHERE user_id = ? AND quest_id = ? AND quest_type = ?
        ''', (user_id, quest_id, quest_type))
        
        await db.commit()
        return rewards

def format_time_left(expires_at: str) -> str:
    """Форматирует оставшееся время"""
    expiry = datetime.fromisoformat(expires_at)
    now = datetime.now()
    diff = expiry - now
    
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    
    if diff.days > 0:
        return f"{diff.days}д {hours}ч"
    return f"{hours}ч {minutes}м"

@quests_router.message(F.text.lower().in_(["задания", "квесты", "/quests"]))
async def cmd_show_quests(message: types.Message, profile_manager: ProfileManager):
    """Показывает текущие задания пользователя"""
    user_id = message.from_user.id
    
    # Обновляем задания если нужно
    await refresh_user_quests(user_id, profile_manager)
    
    # Получаем текущие задания
    quests = await get_user_quests(user_id)
    
    builder = InlineKeyboardBuilder()
    
    text = f"📋 {hbold('Задания')}\n\n"
    
    # Ежедневные задания
    text += f"🌞 {hbold('Ежедневные задания:')}\n"
    if quests['daily']:
        for quest in quests['daily']:
            progress = min(quest['progress'], quest['required']['count'])
            status = "✅" if quest['completed'] else "⏳"
            reward = QuestsConfig.DAILY_QUEST_REWARDS[quest['difficulty']]
            
            text += (
                f"{status} {quest['name']}\n"
                f"└ {quest['description']}\n"
                f"├ Прогресс: {progress}/{quest['required']['count']}\n"
                f"├ Награда: {reward['lumcoins']}💰 {reward['exp']}✨\n"
                f"└ Осталось: {format_time_left(quest['expires_at'])}\n\n"
            )
            
            if quest['completed'] and not quest['reward_claimed']:
                builder.row(InlineKeyboardButton(
                    text=f"💰 Забрать награду: {quest['name']}",
                    callback_data=f"claim_quest:daily:{quest['id']}"
                ))
    else:
        text += "Нет активных ежедневных заданий\n\n"
    
    # Еженедельные задания
    text += f"\n🎯 {hbold('Еженедельные задания:')}\n"
    if quests['weekly']:
        for quest in quests['weekly']:
            progress = min(quest['progress'], quest['required']['count'])
            status = "✅" if quest['completed'] else "⏳"
            reward = QuestsConfig.WEEKLY_QUEST_PLUM_REWARDS[quest['difficulty']]
            
            text += (
                f"{status} {quest['name']}\n"
                f"└ {quest['description']}\n"
                f"├ Прогресс: {progress}/{quest['required']['count']}\n"
                f"├ Награда: {reward}🔮\n"
                f"└ Осталось: {format_time_left(quest['expires_at'])}\n\n"
            )
            
            if quest['completed'] and not quest['reward_claimed']:
                builder.row(InlineKeyboardButton(
                    text=f"🔮 Забрать награду: {quest['name']}",
                    callback_data=f"claim_quest:weekly:{quest['id']}"
                ))
    else:
        text += "Нет активных еженедельных заданий\n\n"
    
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_quests"))
    
    await message.answer(
        text,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

@quests_router.callback_query(F.data == "refresh_quests")
async def refresh_quests_callback(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Обновляет список заданий"""
    await cmd_show_quests(callback.message, profile_manager)
    await callback.answer()

@quests_router.callback_query(F.data.startswith("claim_quest:"))
async def claim_quest_callback(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Обработка получения награды за задание"""
    user_id = callback.from_user.id
    _, quest_type, quest_id = callback.data.split(":")
    
    rewards = await claim_quest_reward(user_id, quest_type, quest_id, profile_manager)
    if not rewards:
        await callback.answer("❌ Не удалось получить награду", show_alert=True)
        return
    
    # Формируем сообщение о награде
    reward_text = []
    if 'lumcoins' in rewards:
        reward_text.append(f"{rewards['lumcoins']}💰")
    if 'exp' in rewards:
        reward_text.append(f"{rewards['exp']}✨")
    if 'plumcoins' in rewards:
        reward_text.append(f"{rewards['plumcoins']}🔮")
    
    await callback.answer(
        f"✅ Получена награда: {' '.join(reward_text)}",
        show_alert=True
    )
    
    # Обновляем отображение заданий
    await cmd_show_quests(callback.message, profile_manager)