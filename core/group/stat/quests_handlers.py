# quests_handlers.py
import logging

# Отключаем отладочные сообщения от aiosqlite
logging.getLogger('aiosqlite').setLevel(logging.WARNING)
from typing import List, Dict, Any, Optional, Tuple
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
    """Инициализация базы данных для заданий с безопасной миграцией"""
    async with aiosqlite.connect('profiles.db') as db:
        # Проверяем существование таблицы user_quests
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_quests'")
        table_exists = await cursor.fetchone()
        
        if table_exists:
            # Проверяем структуру существующей таблицы
            cursor = await db.execute("PRAGMA table_info(user_quests)")
            columns = await cursor.fetchall()
            column_names = [column[1] for column in columns]
            
            # Добавляем отсутствующие столбцы
            if 'user_quest_id' not in column_names:
                logger.info("Добавляем отсутствующие столбцы в таблицу user_quests...")
                
                try:
                    # Добавляем user_quest_id как PRIMARY KEY
                    await db.execute('ALTER TABLE user_quests ADD COLUMN user_quest_id TEXT')
                    
                    # Генерируем user_quest_id для существующих записей
                    await db.execute('''
                        UPDATE user_quests 
                        SET user_quest_id = 
                            CASE 
                                WHEN original_quest_id IS NOT NULL THEN 
                                    original_quest_id || '_' || user_id || '_' || strftime('%s', COALESCE(created_at, datetime('now')))
                                ELSE 
                                    'legacy_' || user_id || '_' || strftime('%s', COALESCE(created_at, datetime('now')))
                            END
                        WHERE user_quest_id IS NULL
                    ''')
                    
                    # Теперь делаем user_quest_id PRIMARY KEY
                    # SQLite не поддерживает ADD PRIMARY KEY через ALTER TABLE, поэтому создаем новую таблицу
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS user_quests_new (
                            user_id INTEGER,
                            user_quest_id TEXT PRIMARY KEY,
                            original_quest_id TEXT,
                            quest_type TEXT,
                            quest_data TEXT,
                            progress INTEGER DEFAULT 0,
                            completed BOOLEAN DEFAULT FALSE,
                            reward_claimed BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP
                        )
                    ''')
                    
                    # Копируем данные в новую таблицу
                    await db.execute('''
                        INSERT OR IGNORE INTO user_quests_new 
                        SELECT * FROM user_quests
                    ''')
                    
                    # Заменяем старую таблицу новой
                    await db.execute('DROP TABLE user_quests')
                    await db.execute('ALTER TABLE user_quests_new RENAME TO user_quests')
                    
                    logger.info("Миграция таблицы user_quests завершена")
                    
                except Exception as e:
                    logger.error(f"Ошибка при миграции user_quests: {e}")
                    # Если миграция не удалась, создаем таблицу заново
                    await db.execute('DROP TABLE IF EXISTS user_quests')
        
        # Создаем таблицы с правильной структурой (если они не существуют)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_quests (
                user_id INTEGER,
                user_quest_id TEXT PRIMARY KEY,
                original_quest_id TEXT,
                quest_type TEXT,
                quest_data TEXT,
                progress INTEGER DEFAULT 0,
                completed BOOLEAN DEFAULT FALSE,
                reward_claimed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS quests_statistics (
                user_id INTEGER,
                quest_type TEXT,
                original_quest_id TEXT,
                completed_count INTEGER DEFAULT 0,
                last_completed TIMESTAMP,
                PRIMARY KEY (user_id, original_quest_id)
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS quest_refresh_times (
                user_id INTEGER PRIMARY KEY,
                last_daily_refresh TIMESTAMP,
                last_weekly_refresh TIMESTAMP
            )
        ''')
        
        await db.commit()
        logger.info("База данных заданий инициализирована")


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
                'user_quest_id': row['user_quest_id'],
                'progress': row['progress'],
                'completed': bool(row['completed']),
                'reward_claimed': bool(row['reward_claimed']),
                'expires_at': row['expires_at'],
                'created_at': row['created_at']
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
            daily_quests = QuestsConfig.get_daily_quests_for_user(user_id)
            for quest in daily_quests:
                await db.execute('''
                    INSERT INTO user_quests 
                    (user_id, user_quest_id, original_quest_id, quest_type, quest_data, expires_at)
                    VALUES (?, ?, ?, 'daily', ?, ?)
                ''', (
                    user_id,
                    quest['user_quest_id'],
                    quest['original_id'],
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
            weekly_quests = QuestsConfig.get_weekly_quests_for_user(user_id)
            for quest in weekly_quests:
                await db.execute('''
                    INSERT INTO user_quests 
                    (user_id, user_quest_id, original_quest_id, quest_type, quest_data, expires_at)
                    VALUES (?, ?, ?, 'weekly', ?, ?)
                ''', (
                    user_id,
                    quest['user_quest_id'],
                    quest['original_id'],
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
    user_quest_id: str,
    progress: int,
    bot: Bot = None
) -> bool:
    """Обновляет прогресс задания"""
    async with aiosqlite.connect('profiles.db') as db:
        cursor = await db.execute('''
            SELECT quest_data, progress, completed
            FROM user_quests
            WHERE user_id = ? AND user_quest_id = ? AND quest_type = ?
        ''', (user_id, user_quest_id, quest_type))
        
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
                WHERE user_id = ? AND user_quest_id = ? AND quest_type = ?
            ''', (new_progress, completed, user_id, user_quest_id, quest_type))
            
            # Если задание завершено, обновляем статистику
            if completed and not was_completed:
                await db.execute('''
                    INSERT INTO quests_statistics 
                    (user_id, quest_type, original_quest_id, completed_count, last_completed)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(user_id, original_quest_id) 
                    DO UPDATE SET 
                        completed_count = completed_count + 1,
                        last_completed = ?
                ''', (
                    user_id, 
                    quest_type, 
                    quest_data['original_id'],
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            
            await db.commit()
            
            # Отправляем уведомление если есть бот
            if bot and (completed != was_completed or new_progress > old_progress):
                await notify_quest_progress(bot, user_id, quest_data, new_progress, completed)
        
        return completed

async def increment_quest_progress(
    user_id: int,
    quest_type: str,
    user_quest_id: str,
    increment: int = 1,
    bot: Bot = None
) -> bool:
    """Увеличивает прогресс задания на указанное значение"""
    async with aiosqlite.connect('profiles.db') as db:
        cursor = await db.execute('''
            SELECT quest_data, progress, completed
            FROM user_quests
            WHERE user_id = ? AND user_quest_id = ? AND quest_type = ?
        ''', (user_id, user_quest_id, quest_type))
        
        quest = await cursor.fetchone()
        if not quest:
            return False
            
        quest_data = json.loads(quest[0])
        old_progress = quest[1]
        was_completed = quest[2]
        
        new_progress = min(old_progress + increment, quest_data['required']['count'])
        completed = new_progress >= quest_data['required']['count']
        
        # Обновляем только если есть изменения
        if new_progress > old_progress or (completed and not was_completed):
            await db.execute('''
                UPDATE user_quests
                SET progress = ?, completed = ?
                WHERE user_id = ? AND user_quest_id = ? AND quest_type = ?
            ''', (new_progress, completed, user_id, user_quest_id, quest_type))
            
            # Если задание завершено, обновляем статистику
            if completed and not was_completed:
                await db.execute('''
                    INSERT INTO quests_statistics 
                    (user_id, quest_type, original_quest_id, completed_count, last_completed)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(user_id, original_quest_id) 
                    DO UPDATE SET 
                        completed_count = completed_count + 1,
                        last_completed = ?
                ''', (
                    user_id, 
                    quest_type, 
                    quest_data['original_id'],
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            
            await db.commit()
            
            # Отправляем уведомление если есть бот
            if bot and (completed != was_completed or new_progress > old_progress):
                await notify_quest_progress(bot, user_id, quest_data, new_progress, completed)
        
        return completed

async def claim_quest_reward(
    user_id: int,
    quest_type: str,
    user_quest_id: str,
    profile_manager: ProfileManager
) -> Optional[Dict[str, int]]:
    """Забирает награду за выполненное задание"""
    async with aiosqlite.connect('profiles.db') as db:
        cursor = await db.execute('''
            SELECT quest_data, completed, reward_claimed
            FROM user_quests
            WHERE user_id = ? AND user_quest_id = ? AND quest_type = ?
        ''', (user_id, user_quest_id, quest_type))
        
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
            WHERE user_id = ? AND user_quest_id = ? AND quest_type = ?
        ''', (user_id, user_quest_id, quest_type))
        
        await db.commit()
        return rewards

async def get_quest_statistics(user_id: int, quest_type: str = None) -> Dict[str, Any]:
    """Получает статистику выполнения заданий"""
    async with aiosqlite.connect('profiles.db') as db:
        db.row_factory = aiosqlite.Row
        
        if quest_type:
            cursor = await db.execute('''
                SELECT original_quest_id, completed_count, last_completed
                FROM quests_statistics
                WHERE user_id = ? AND quest_type = ?
            ''', (user_id, quest_type))
        else:
            cursor = await db.execute('''
                SELECT original_quest_id, quest_type, completed_count, last_completed
                FROM quests_statistics
                WHERE user_id = ?
            ''', (user_id,))
        
        rows = await cursor.fetchall()
        
        # Общая статистика
        total_completed = 0
        quests_by_type = {}
        
        for row in rows:
            total_completed += row['completed_count']
            quest_type = row['quest_type']
            if quest_type not in quests_by_type:
                quests_by_type[quest_type] = 0
            quests_by_type[quest_type] += row['completed_count']
        
        return {
            'total_completed': total_completed,
            'quests_by_type': quests_by_type,
            'detailed_stats': [dict(row) for row in rows]
        }

async def get_global_command_stats(command_name: str = None) -> Dict[str, Any]:
    """Получает глобальную статистику использования команд"""
    async with aiosqlite.connect('profiles.db') as db:
        db.row_factory = aiosqlite.Row
        
        if command_name:
            # Статистика по конкретной команде
            cursor = await db.execute('''
                SELECT COUNT(*) as usage_count, 
                       COUNT(DISTINCT user_id) as unique_users
                FROM analytics_interactions 
                WHERE action_type = 'command' AND mode = ?
            ''', (command_name,))
        else:
            # Общая статистика по всем командам
            cursor = await db.execute('''
                SELECT action_type as command_name, 
                       COUNT(*) as usage_count,
                       COUNT(DISTINCT user_id) as unique_users
                FROM analytics_interactions 
                WHERE action_type = 'command'
                GROUP BY action_type
            ''')
        
        result = await cursor.fetchall()
        return [dict(row) for row in result]

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
    
    # Принудительно получаем актуальные данные из базы
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
                    callback_data=f"claim_quest:daily:{quest['user_quest_id']}"
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
                    callback_data=f"claim_quest:weekly:{quest['user_quest_id']}"
                ))
    else:
        text += "Нет активных еженедельных заданий\n\n"
    
    # Кнопка статистики
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="quests_stats"))
    builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_quests"))
    
    # Всегда отправляем новое сообщение вместо редактирования
    await message.answer(
        text,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

@quests_router.callback_query(F.data == "refresh_quests")
async def refresh_quests_callback(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Обновляет список заданий"""
    # Создаем объект message из callback для совместимости
    class MockMessage:
        def __init__(self, callback):
            self.from_user = callback.from_user
            self.message_id = callback.message.message_id
            self.edit_text = callback.message.edit_text
            self.answer = callback.message.answer
    
    mock_message = MockMessage(callback)
    await cmd_show_quests(mock_message, profile_manager)
    await callback.answer("✅ Задания обновлены")


@quests_router.callback_query(F.data == "quests_stats")
async def show_quests_stats(callback: types.CallbackQuery):
    """Показывает статистику заданий"""
    user_id = callback.from_user.id
    stats = await get_quest_statistics(user_id)
    
    text = f"📊 {hbold('Статистика заданий')}\n\n"
    text += f"✅ Всего выполнено: {stats['total_completed']}\n\n"
    
    for quest_type, count in stats['quests_by_type'].items():
        type_name = "Ежедневные" if quest_type == "daily" else "Еженедельные"
        text += f"{type_name}: {count} выполнено\n"
    
    await callback.message.answer(text, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()

@quests_router.callback_query(F.data.startswith("claim_quest:"))
async def claim_quest_callback(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Обработка получения награды за задание"""
    user_id = callback.from_user.id
    _, quest_type, user_quest_id = callback.data.split(":")
    
    rewards = await claim_quest_reward(user_id, quest_type, user_quest_id, profile_manager)
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

# Универсальная команда для статистики
@quests_router.message(F.text.lower().startswith(("статистика", "/stats")))
async def cmd_stats(message: types.Message):
    """Показывает различную статистику"""
    parts = message.text.lower().split()
    
    if len(parts) > 1:
        # Статистика по конкретной команде
        command_name = parts[1]
        stats = await get_global_command_stats(command_name)
        
        if stats and len(stats) > 0:
            stat = stats[0]
            text = f"📊 Статистика команды '{command_name}':\n"
            text += f"🔄 Использований: {stat['usage_count']}\n"
            text += f"👥 Уникальных пользователей: {stat['unique_users']}\n"
        else:
            text = f"❌ Статистика для команды '{command_name}' не найдена"
    else:
        # Общая статистика
        stats = await get_global_command_stats()
        text = "📊 Общая статистика команд:\n\n"
        
        for stat in stats:
            text += f"🔹 {stat['command_name']}:\n"
            text += f"   Использований: {stat['usage_count']}\n"
            text += f"   Уникальных пользователей: {stat['unique_users']}\n\n"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

# Функции для обновления прогресса заданий из других модулей
async def update_message_quests(user_id: int, message_count: int, bot: Bot = None):
    """Обновляет задания связанные с сообщениями"""
    quests = await get_user_quests(user_id)
    
    for quest_type in ['daily', 'weekly']:
        for quest in quests[quest_type]:
            if quest['type'] == 'message_count' and not quest['completed']:
                await update_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 
                    message_count, bot
                )

async def update_work_quests(user_id: int, work_count: int, bot: Bot = None):
    """Обновляет задания связанные с работой"""
    quests = await get_user_quests(user_id)
    
    for quest_type in ['daily', 'weekly']:
        for quest in quests[quest_type]:
            if quest['type'] == 'work' and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 
                    work_count, bot
                )

async def update_exp_quests(user_id: int, exp_gained: int, bot: Bot = None):
    """Обновляет задания связанные с получением опыта"""
    quests = await get_user_quests(user_id)
    
    for quest_type in ['daily', 'weekly']:
        for quest in quests[quest_type]:
            if quest['type'] == 'exp_gain' and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 
                    exp_gained, bot
                )

async def update_casino_quests(user_id: int, game_type: str, won: bool = False, win_amount: int = 0, bot: Bot = None):
    """Обновляет задания связанные с казино"""
    logger.info(f"Обновление заданий казино: user={user_id}, game={game_type}, won={won}, amount={win_amount}")
    
    quests = await get_user_quests(user_id)
    
    for quest_type in ['daily', 'weekly']:
        for quest in quests[quest_type]:
            # Для игр в казино
            if quest['type'] == 'casino_games' and not quest['completed']:
                logger.info(f"Обновление casino_games: {quest['name']}")
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )
            
            # Для выигрышей в казино
            if quest['type'] == 'casino_wins' and won and not quest['completed']:
                logger.info(f"Обновление casino_wins: {quest['name']}")
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )
            
            # Для прибыли в казино (еженедельные)
            if quest['type'] == 'casino_profit' and won and not quest['completed']:
                logger.info(f"Обновление casino_profit: {quest['name']}")
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], win_amount, bot
                )

async def update_rp_quests(user_id: int, action_type: str, unique_action: bool = False, bot: Bot = None):
    """Обновляет задания связанные с RP-действиями"""
    logger.info(f"Обновление RP заданий: user={user_id}, action={action_type}, unique={unique_action}")
    
    quests = await get_user_quests(user_id)
    
    for quest_type in ['daily', 'weekly']:
        for quest in quests[quest_type]:
            # Обычные RP-действия
            if quest['type'] == 'rp_actions' and action_type == 'rp' and not quest['completed']:
                logger.info(f"Обновление rp_actions: {quest['name']}")
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )
            
            # Уникальные RP-действия
            if quest['type'] == 'unique_rp_actions' and action_type == 'unique_rp' and unique_action and not quest['completed']:
                logger.info(f"Обновление unique_rp_actions: {quest['name']}")
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )
            
            # Общее количество уникальных RP-действий (еженедельные)
            if quest['type'] == 'unique_rp_actions_total' and action_type == 'unique_rp' and unique_action and not quest['completed']:
                logger.info(f"Обновление unique_rp_actions_total: {quest['name']}")
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )

async def update_market_quests(user_id: int, action_type: str, count: int = 1, profit: int = 0, bot: Bot = None):
    """Обновляет задания связанные с рынком"""
    quests = await get_user_quests(user_id)
    
    for quest_type in ['daily', 'weekly']:
        for quest in quests[quest_type]:
            # Выставление предметов на рынок
            if quest['type'] == 'market_listings' and action_type == 'list' and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], count, bot
                )
            
            # Покупки на рынке
            if quest['type'] == 'market_purchases' and action_type == 'buy' and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], count, bot
                )
            
            # Прибыль с рынка (еженедельные)
            if quest['type'] == 'market_profit' and action_type == 'profit' and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], profit, bot
                )

async def update_rp_quests(user_id: int, action_type: str, unique_action: bool = False, bot: Bot = None):
    """Обновляет задания связанные с RP-действиями"""
    quests = await get_user_quests(user_id)
    
    for quest_type in ['daily', 'weekly']:
        for quest in quests[quest_type]:
            # Обычные RP-действия
            if quest['type'] == 'rp_actions' and action_type == 'rp' and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )
            
            # Уникальные RP-действия
            if quest['type'] == 'unique_rp_actions' and action_type == 'unique_rp' and unique_action and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )
            
            # Общее количество уникальных RP-действий (еженедельные)
            if quest['type'] == 'unique_rp_actions_total' and action_type == 'unique_rp' and unique_action and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )

async def update_crafting_quests(user_id: int, item_rarity: str = 'common', bot: Bot = None):
    """Обновляет задания связанные с крафтом"""
    quests = await get_user_quests(user_id)
    
    for quest_type in ['daily', 'weekly']:
        for quest in quests[quest_type]:
            # Обычный крафт
            if quest['type'] == 'crafting' and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )
            
            # Крафт редких/эпических предметов
            if quest['type'] == 'rare_crafting' and item_rarity in ['rare', 'epic'] and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], 1, bot
                )

async def update_activity_quests(user_id: int, activity_score: int, bot: Bot = None):
    """Обновляет задания связанные с активностью"""
    quests = await get_user_quests(user_id)
    
    for quest_type in ['daily', 'weekly']:
        for quest in quests[quest_type]:
            if quest['type'] == 'activity_score' and not quest['completed']:
                await increment_quest_progress(
                    user_id, quest_type, quest['user_quest_id'], activity_score, bot
                )
