import os
from pathlib import Path
import json
import textwrap
import time # Добавлен импорт time для использования в некоторых файлах

def create_project_files():
    """
    Создает все необходимые файлы и директории для проекта Telegram бота.
    """
    print("Создание директории 'data/'...")
    Path("data").mkdir(exist_ok=True)

    print("Создание database.py...")
    database_content = textwrap.dedent("""\
        import aiosqlite
        import asyncio
        import logging
        from datetime import datetime
        from pathlib import Path
        from typing import Any, Dict, List, Optional, Tuple
        import time

        # Настройка логирования для модуля базы данных
        logger = logging.getLogger(__name__)

        # Определение пути к файлу базы данных
        DB_FILE = Path("data") / "bot_database.db"
        # Создание директории 'data', если она не существует
        DB_FILE.parent.mkdir(exist_ok=True)

        async def initialize_database() -> None:
            \"\"\"
            Инициализирует базу данных, создавая все необходимые таблицы и индексы,
            если они еще не существуют.

            Этот асинхронный метод устанавливает соединение с базой данных SQLite
            и выполняет SQL-скрипты для создания таблиц пользователей, подписок,
            истории диалогов, режимов пользователей, аналитики взаимодействий,
            рейтингов и статистики RP-пользователей.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT NOT NULL,
                        last_active_ts REAL DEFAULT 0
                    )
                ''')
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS value_subscriptions (
                        user_id INTEGER PRIMARY KEY,
                        subscribed_ts REAL NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS dialog_history (
                        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        timestamp REAL NOT NULL,
                        mode TEXT NOT NULL,
                        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                        content TEXT NOT NULL,
                        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')
                # Индекс для быстрого доступа к истории диалогов по пользователю и времени
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS idx_dialog_history_user_ts ON dialog_history (user_id, timestamp DESC)
                ''')
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS user_modes (
                        user_id INTEGER PRIMARY KEY,
                        mode TEXT NOT NULL DEFAULT 'saharoza',
                        rating_opportunities_count INTEGER DEFAULT 0,
                        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS analytics_interactions (
                        interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        timestamp REAL NOT NULL,
                        mode TEXT NOT NULL,
                        action_type TEXT NOT NULL DEFAULT 'message',
                        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')
                # Индекс для быстрого доступа к аналитике взаимодействий
                await db.execute('''
                    CREATE INDEX IF NOT EXISTS idx_interactions_user_ts_mode ON analytics_interactions (user_id, timestamp DESC, mode)
                ''')
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS analytics_ratings (
                        rating_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        rated_message_id INTEGER,
                        dialog_history_id INTEGER,
                        timestamp REAL NOT NULL,
                        rating INTEGER NOT NULL CHECK(rating IN (0, 1)),
                        message_preview TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY(dialog_history_id) REFERENCES dialog_history(history_id) ON DELETE SET NULL
                    )
                ''')
                await db.execute('''
                    CREATE TABLE IF NOT EXISTS rp_user_stats (
                        user_id INTEGER PRIMARY KEY,
                        hp INTEGER NOT NULL DEFAULT 100,
                        heal_cooldown_ts REAL NOT NULL DEFAULT 0,
                        recovery_end_ts REAL NOT NULL DEFAULT 0,
                        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')
                await db.commit()
            logger.info("Database initialized successfully.")

        async def ensure_user_exists(user_id: int, username: Optional[str], first_name: str) -> None:
            \"\"\"
            Гарантирует, что пользователь существует в базе данных, или обновляет его информацию.
            Также создает записи по умолчанию в user_modes и rp_user_stats, если их нет.

            Args:
                user_id (int): Уникальный идентификатор пользователя Telegram.
                username (Optional[str]): Имя пользователя Telegram (может быть None).
                first_name (str): Имя пользователя Telegram.
            \"\"\"
            current_timestamp = datetime.now().timestamp()
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('''
                    INSERT INTO users (user_id, username, first_name, last_active_ts)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        last_active_ts = excluded.last_active_ts
                ''', (user_id, username, first_name, current_timestamp))
                await db.execute('''
                    INSERT OR IGNORE INTO user_modes (user_id, mode, rating_opportunities_count)
                    VALUES (?, 'saharoza', 0)
                ''', (user_id,))
                await db.execute('''
                    INSERT OR IGNORE INTO rp_user_stats (user_id) VALUES (?)
                ''', (user_id,))
                await db.commit()

        async def get_user_profile_info(user_id: int) -> Optional[Dict[str, Any]]:
            \"\"\"
            Получает базовую информацию о пользователе из таблицы users.

            Args:
                user_id (int): Уникальный идентификатор пользователя.

            Returns:
                Optional[Dict[str, Any]]: Словарь с информацией о пользователе
                                        (user_id, username, first_name, last_active)
                                        или None, если пользователь не найден.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute('SELECT user_id, username, first_name, last_active_ts FROM users WHERE user_id = ?', (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        last_active_formatted = datetime.fromtimestamp(row[3]).isoformat() if row[3] and row[3] > 0 else 'N/A'
                        return {
                            "user_id": row[0],
                            "username": row[1],
                            "first_name": row[2],
                            "last_active": last_active_formatted
                        }
                    return None

        async def add_value_subscriber(user_id: int) -> None:
            \"\"\"
            Добавляет пользователя в список подписчиков для мониторинга значения.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('''
                    INSERT OR IGNORE INTO value_subscriptions (user_id, subscribed_ts) VALUES (?, ?)
                ''', (user_id, datetime.now().timestamp()))
                await db.commit()

        async def remove_value_subscriber(user_id: int) -> None:
            \"\"\"
            Удаляет пользователя из списка подписчиков для мониторинга значения.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('DELETE FROM value_subscriptions WHERE user_id = ?', (user_id,))
                await db.commit()

        async def get_value_subscribers() -> List[int]:
            \"\"\"
            Получает список ID всех пользователей, подписанных на мониторинг значения.

            Returns:
                List[int]: Список уникальных идентификаторов пользователей.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute('SELECT user_id FROM value_subscriptions') as cursor:
                    rows = await cursor.fetchall()
                    return [row[0] for row in rows]

        async def check_value_subscriber_status(user_id: int) -> bool:
            \"\"\"
            Проверяет, подписан ли пользователь на мониторинг значения.

            Args:
                user_id (int): Уникальный идентификатор пользователя.

            Returns:
                bool: True, если пользователь подписан, иначе False.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute('SELECT 1 FROM value_subscriptions WHERE user_id = ?', (user_id,)) as cursor:
                    return await cursor.fetchone() is not None

        async def add_chat_history_entry(user_id: int, mode: str, user_message_content: str, bot_response_content: str) -> None:
            \"\"\"
            Добавляет записи в историю диалога для пользователя (сообщение пользователя и ответ бота).
            Ограничивает историю до последних 20 записей для каждого пользователя.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
                mode (str): Активный режим бота во время диалога.
                user_message_content (str): Текст сообщения от пользователя.
                bot_response_content (str): Текст ответа от бота.
            \"\"\"
            current_timestamp = datetime.now().timestamp()
            async with aiosqlite.connect(DB_FILE) as db:
                # Добавляем сообщение пользователя
                await db.execute('''
                    INSERT INTO dialog_history (user_id, timestamp, mode, role, content)
                    VALUES (?, ?, ?, 'user', ?)
                ''', (user_id, current_timestamp - 0.001, mode, user_message_content)) # Небольшая задержка для порядка
                # Добавляем ответ бота
                await db.execute('''
                    INSERT INTO dialog_history (user_id, timestamp, mode, role, content)
                    VALUES (?, ?, ?, 'assistant', ?)
                ''', (user_id, current_timestamp, mode, bot_response_content))
                # Удаляем старые записи, оставляя только последние 20 (10 пар "пользователь-ассистент")
                await db.execute('''
                    DELETE FROM dialog_history
                    WHERE history_id NOT IN (
                        SELECT history_id FROM dialog_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20
                    ) AND user_id = ?
                ''', (user_id, user_id))
                await db.commit()

        async def get_user_dialog_history(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
            \"\"\"
            Получает историю диалога для заданного пользователя.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
                limit (int): Максимальное количество записей для извлечения.

            Returns:
                List[Dict[str, Any]]: Список словарей, где каждый словарь представляет
                                    запись в истории диалога (роль, контент, режим, метка времени).
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute('''
                    SELECT role, content, mode, timestamp FROM dialog_history
                    WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?
                ''', (user_id, limit)) as cursor:
                    rows = await cursor.fetchall()
                    # Возвращаем историю в хронологическом порядке
                    history = [{"role": row[0], "content": row[1], "mode": row[2], "timestamp": row[3]} for row in reversed(rows)]
                    return history

        async def get_ollama_dialog_history(user_id: int, limit_turns: int = 5) -> List[Dict[str, str]]:
            \"\"\"
            Формирует историю диалога для использования с Ollama API.
            Обеспечивает корректное чередование ролей "user" и "assistant".

            Args:
                user_id (int): Уникальный идентификатор пользователя.
                limit_turns (int): Максимальное количество "ходов" (пар вопрос-ответ) для включения.

            Returns:
                List[Dict[str, str]]: Список словарей, отформатированных для Ollama,
                                    например, [{"user": "...", "assistant": "..."}].
            \"\"\"
            # Получаем в два раза больше записей, так как каждый ход состоит из двух записей (user и assistant)
            raw_history = await get_user_dialog_history(user_id, limit=limit_turns * 2)
            ollama_history = []
            user_message_buffer = None

            for entry in raw_history:
                if entry["role"] == "user":
                    user_message_buffer = entry["content"]
                elif entry["role"] == "assistant" and user_message_buffer is not None:
                    # Если есть сообщение пользователя в буфере и текущее сообщение от ассистента,
                    # формируем пару и добавляем в историю Ollama
                    ollama_history.append({"user": user_message_buffer, "assistant": entry["content"]})
                    user_message_buffer = None  # Сбрасываем буфер
                elif entry["role"] == "assistant" and user_message_buffer is None:
                    # Если сообщение от ассистента пришло без предыдущего сообщения пользователя,
                    # это аномалия (например, первое сообщение в истории от бота).
                    # Логируем и пропускаем, чтобы не нарушать структуру для Ollama.
                    logger.warning(f"Orphan assistant message in history for user {user_id}, skipping for Ollama.")

            return ollama_history

        async def set_user_current_mode(user_id: int, mode: str) -> None:
            \"\"\"
            Устанавливает текущий режим для пользователя.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
                mode (str): Название режима.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('''
                    INSERT INTO user_modes (user_id, mode) VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET mode = excluded.mode
                ''', (user_id, mode))
                await db.commit()

        async def get_user_mode_and_rating_opportunities(user_id: int) -> Dict[str, Any]:
            \"\"\"
            Получает текущий режим пользователя и количество оставшихся возможностей для оценки.

            Args:
                user_id (int): Уникальный идентификатор пользователя.

            Returns:
                Dict[str, Any]: Словарь с ключами 'mode' (текущий режим) и
                                'rating_opportunities_count' (количество оценок, уже сделанных).
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                # Гарантируем наличие записи для пользователя перед попыткой чтения
                await db.execute('''
                    INSERT OR IGNORE INTO user_modes (user_id, mode, rating_opportunities_count)
                    VALUES (?, 'saharoza', 0)
                ''', (user_id,))
                async with db.execute('SELECT mode, rating_opportunities_count FROM user_modes WHERE user_id = ?', (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    # Должен всегда найтись, так как мы только что его вставили/игнорировали
                    return {"mode": row[0], "rating_opportunities_count": row[1]}

        async def increment_user_rating_opportunity_count(user_id: int) -> None:
            \"\"\"
            Увеличивает счетчик использованных возможностей для оценки для пользователя.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('''
                    UPDATE user_modes
                    SET rating_opportunities_count = rating_opportunities_count + 1
                    WHERE user_id = ?
                ''', (user_id,))
                await db.commit()

        async def reset_user_rating_opportunity_count(user_id: int) -> None:
            \"\"\"
            Сбрасывает счетчик использованных возможностей для оценки для пользователя до нуля.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('UPDATE user_modes SET rating_opportunities_count = 0 WHERE user_id = ?', (user_id,))
                await db.commit()

        async def log_user_interaction(user_id: int, mode: str, action_type: str = "message") -> None:
            \"\"\"
            Записывает взаимодействие пользователя с ботом для аналитики.
            Также обновляет метку времени последней активности пользователя.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
                mode (str): Режим бота, который был активен во время взаимодействия.
                action_type (str): Тип действия (например, 'message', 'command', 'callback').
            \"\"\"
            current_timestamp = datetime.now().timestamp()
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('''
                    INSERT INTO analytics_interactions (user_id, timestamp, mode, action_type) VALUES (?, ?, ?, ?)
                ''', (user_id, current_timestamp, mode, action_type))
                await db.execute('UPDATE users SET last_active_ts = ? WHERE user_id = ?', (current_timestamp, user_id))
                await db.commit()

        async def log_user_rating(user_id: int, rating: int, message_preview: str,
                                rated_message_id: Optional[int] = None, dialog_history_id: Optional[int] = None) -> None:
            \"\"\"
            Записывает оценку пользователя в базу данных.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
                rating (int): Оценка (0 для дизлайка, 1 для лайка).
                message_preview (str): Краткий предпросмотр сообщения, к которому относится оценка.
                rated_message_id (Optional[int]): ID сообщения бота, которое было оценено (опционально).
                dialog_history_id (Optional[int]): ID записи в dialog_history, связанной с оценкой (опционально).
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute('''
                    INSERT INTO analytics_ratings (user_id, timestamp, rating, message_preview, rated_message_id, dialog_history_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, datetime.now().timestamp(), rating, message_preview[:500], rated_message_id, dialog_history_id))
                await db.commit()

        async def get_user_statistics_summary(user_id: int) -> Dict[str, Any]:
            \"\"\"
            Получает сводную статистику для пользователя.

            Args:
                user_id (int): Уникальный идентификатор пользователя.

            Returns:
                Dict[str, Any]: Словарь с количеством запросов, последним активным режимом и временем последней активности.
            \"\"\"
            stats = {"count": 0, "last_mode": "N/A", "last_active": "N/A"}
            async with aiosqlite.connect(DB_FILE) as db:
                # Получаем общее количество взаимодействий
                async with db.execute('SELECT COUNT(*) FROM analytics_interactions WHERE user_id = ?', (user_id,)) as cursor:
                    count_row = await cursor.fetchone()
                    if count_row:
                        stats["count"] = count_row[0]

                # Получаем информацию о последней активности пользователя
                user_info = await get_user_profile_info(user_id)
                if user_info:
                    stats["last_active"] = user_info["last_active"]

                # Пытаемся получить последний использованный режим из взаимодействий
                async with db.execute('SELECT mode FROM analytics_interactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1', (user_id,)) as cursor:
                    last_interaction_mode = await cursor.fetchone()
                    if last_interaction_mode:
                        stats["last_mode"] = last_interaction_mode[0]
                    else:
                        # Если взаимодействий нет, берем текущий режим из user_modes
                        async with db.execute('SELECT mode FROM user_modes WHERE user_id = ?', (user_id,)) as mode_cursor:
                            current_mode = await mode_cursor.fetchone()
                            if current_mode:
                                stats["last_mode"] = current_mode[0]
            return stats

        async def get_user_rp_stats(user_id: int) -> Dict[str, Any]:
            \"\"\"
            Получает RP-статистику пользователя (HP, таймеры кулдаунов).

            Args:
                user_id (int): Уникальный идентификатор пользователя.

            Returns:
                Dict[str, Any]: Словарь с HP, heal_cooldown_ts и recovery_end_ts.
                                Возвращает значения по умолчанию, если запись не найдена,
                                и логирует ошибку.
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                # Гарантируем, что запись существует
                await db.execute('INSERT OR IGNORE INTO rp_user_stats (user_id) VALUES (?)', (user_id,))
                async with db.execute('SELECT hp, heal_cooldown_ts, recovery_end_ts FROM rp_user_stats WHERE user_id = ?', (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {"hp": row[0], "heal_cooldown_ts": row[1], "recovery_end_ts": row[2]}
                    else:
                        logger.error(f"CRITICAL: RP stats row not found for user_id {user_id} after INSERT OR IGNORE. Schema defaults might be missing or DB error.")
                        return {"hp": 100, "heal_cooldown_ts": 0, "recovery_end_ts": 0}

        async def update_user_rp_stats(user_id: int, **kwargs: Optional[Any]) -> None:
            \"\"\"
            Обновляет указанные поля RP-статистики для пользователя.

            Args:
                user_id (int): Уникальный идентификатор пользователя.
                **kwargs: Пары ключ=значение для обновления (например, hp=120, heal_cooldown_ts=...).
            \"\"\"
            updates = []
            params: List[Any] = []

            # Динамическое формирование SQL-запроса на основе переданных аргументов
            if 'hp' in kwargs and kwargs['hp'] is not None:
                updates.append("hp = ?")
                params.append(kwargs['hp'])
            if 'heal_cooldown_ts' in kwargs and kwargs['heal_cooldown_ts'] is not None:
                updates.append("heal_cooldown_ts = ?")
                params.append(kwargs['heal_cooldown_ts'])
            if 'recovery_end_ts' in kwargs and kwargs['recovery_end_ts'] is not None:
                updates.append("recovery_end_ts = ?")
                params.append(kwargs['recovery_end_ts'])

            if not updates: # Если нет полей для обновления, просто выходим
                return

            query = f"UPDATE rp_user_stats SET {', '.join(updates)} WHERE user_id = ?"
            params.append(user_id)

            async with aiosqlite.connect(DB_FILE) as db:
                # Гарантируем, что запись существует перед обновлением
                await db.execute('INSERT OR IGNORE INTO rp_user_stats (user_id) VALUES (?)', (user_id,))
                await db.execute(query, tuple(params))
                await db.commit()

        def read_value_from_file(file_path: Path) -> Optional[str]:
            \"\"\"
            Читает значение из текстового файла, ища строку "check = <value>".

            Args:
                file_path (Path): Путь к файлу.

            Returns:
                Optional[str]: Извлеченное значение или None, если файл не найден,
                            произошла ошибка или значение не найдено.
            \"\"\"
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    for line in file:
                        stripped_line = line.strip()
                        if stripped_line.startswith("check = "):
                            value = stripped_line[len("check = "):].strip()
                            return value
            except FileNotFoundError:
                logger.warning(f"File for value monitoring not found: {file_path}")
            except Exception as e:
                logger.error(f"Error reading value file ({file_path}): {e}", exc_info=True)
            return None

        async def get_users_for_hp_recovery(current_timestamp: float, min_hp_level_inclusive: int) -> List[Tuple[int, int]]:
            \"\"\"
            Получает список пользователей, чье HP равно или ниже указанного уровня
            и чей таймер восстановления истек.

            Args:
                current_timestamp (float): Текущая метка времени для сравнения с recovery_end_ts.
                min_hp_level_inclusive (int): Максимальный уровень HP (включительно), при котором
                                            пользователь нуждается в восстановлении.

            Returns:
                List[Tuple[int, int]]: Список кортежей, где каждый кортеж содержит (user_id, current_hp).
            \"\"\"
            query = \"\"\"
                SELECT user_id, hp
                FROM rp_user_stats
                WHERE hp <= ? AND recovery_end_ts > 0 AND recovery_end_ts <= ?
            \"\"\"
            async with aiosqlite.connect(DB_FILE) as db:
                async with db.execute(query, (min_hp_level_inclusive, current_timestamp)) as cursor:
                    rows = await cursor.fetchall()
                    return [(row[0], row[1]) for row in rows]
        """)
    with open("database.py", "w", encoding="utf-8") as f:
        f.write(database_content)
    print("Файл database.py успешно создан.")

    print("Создание group_stat.py...")
    group_stat_content = textwrap.dedent("""\
        import os
        import aiosqlite
        import string
        import sqlite3
        import time
        from datetime import datetime, date, timedelta
        from io import BytesIO
        from typing import Optional, Dict, Any
        from aiogram import Dispatcher, types, Bot
        from aiogram.filters import Command
        import logging
        logger = logging.getLogger(__name__)
        from PIL import Image, ImageDraw, ImageFont
        import requests
        from aiogram import Router, types, F
        from aiogram.enums import ChatType
        from aiogram.types import BufferedInputFile
        import random
        import aiohttp

        formatter = string.Formatter()

        stat_router = Router(name="stat_router")

        class ProfileConfig:
            DEFAULT_BG_URL = "https://images.steamusercontent.com/ugc/2109432979738958246/80A8B1D46BC2434A53C634DE9721205228BEA966/"
            FONT_PATH = "Hlobus.ttf"
            TEXT_COLOR = (255, 255, 255)
            TEXT_SHADOW = (0, 0, 0)
            MARGIN = 15
            AVATAR_SIZE = 50
            AVATAR_OFFSET = (MARGIN, MARGIN)
            USER_ID_OFFSET = (MARGIN + AVATAR_SIZE + 10, MARGIN + 5)
            EXP_BAR_OFFSET = (MARGIN, MARGIN + AVATAR_SIZE + 10)
            MONEY_OFFSET_RIGHT = 15
            HP_OFFSET = (MARGIN, MARGIN + AVATAR_SIZE + 35)
            FLAMES_OFFSET_X = -70
            FLAMES_OFFSET_Y = MARGIN
            MESSAGES_OFFSET_X = -100
            MESSAGES_OFFSET_Y = MARGIN + 25
            HP_COLORS = {
                "high": (0, 128, 0),
                "medium": (255, 165, 0),
                "low": (255, 0, 0),
                "very_high": (255, 69, 0)
            }
            MAX_HP = 150
            MAX_LEVEL = 169
            EXP_PER_MESSAGE_INTERVAL = 10
            EXP_AMOUNT_PER_INTERVAL = 1
            LUMCOINS_PER_LEVEL = {
                1: 1, 10: 2, 20: 3, 30: 5,
                50: 8, 100: 15, 150: 25, 169: 50
            }
            WORK_REWARD_MIN = 5
            WORK_REWARD_MAX = 20
            WORK_COOLDOWN_SECONDS = 15 * 60
            WORK_TASKS = [
                "чистил(а) ботинки",
                "поливал(а) цветы",
                "ловил(а) бабочек",
                "собирал(а) ягоды",
                "помогал(а) старушке перейти дорогу",
                "писал(а) стихи",
                "играл(а) на гитаре",
                "готовил(а) обед",
                "читал(а) книгу",
                "смотрел(а) в окно"
            ]
            FONT_SIZE_LARGE = 24
            FONT_SIZE_MEDIUM = 20
            FONT_SIZE_SMALL = 16
            BACKGROUND_SHOP = {
                "forest": {"name": "Лес", "cost": 50, "url": "https://images.unsplash.com/photo-1511497584788-d14a01452277?q=80&w=1974&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D"},
                "mountain": {"name": "Горы", "cost": 100, "url": "https://images.unsplash.com/photo-1549880338-65ddcdfd017b?q=80&w=2070&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D"},
                "city": {"name": "Город", "cost": 150, "url": "https://images.unsplash.com/photo-1596701072172-88c97351659f?q=80&w=2070&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D"}
            }

        def init_db_sync(): # Переименовано для ясности, что это синхронная функция
            if not os.path.exists('profiles.db'):
                conn = sqlite3.connect('profiles.db')
                cursor = conn.cursor()
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    hp INTEGER DEFAULT 100 CHECK(hp >= 0 AND hp <= 150),
                    level INTEGER DEFAULT 1 CHECK(level >= 1 AND level <= 169),
                    exp INTEGER DEFAULT 0,
                    lumcoins INTEGER DEFAULT 0,
                    daily_messages INTEGER DEFAULT 0,
                    total_messages INTEGER DEFAULT 0,
                    flames INTEGER DEFAULT 0,
                    background_url TEXT,
                    last_work_time REAL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                ''')
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS backgrounds (
                    user_id INTEGER PRIMARY KEY,
                    background_url TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)')
                conn.commit()
                conn.close()
                logger.info("Database initialized (sync).")
            else:
                logger.info("Database already exists (sync check).")

        # Вызываем синхронную инициализацию при импорте модуля
        init_db_sync()

        class ProfileManager:
            def __init__(self):
                self._conn = None
                self.font_cache = {}
                logger.info("ProfileManager instance created.")

            async def connect(self):
                if self._conn is not None:
                    logger.warning("Database connection already exists.")
                    return
                logger.info("Connecting to database...")
                try:
                    self._conn = await aiosqlite.connect('profiles.db')
                    logger.info("Database connected asynchronously.")
                    await self._init_db_async()
                    logger.info("Database schema checked/initialized asynchronously.")
                except Exception as e:
                    logger.exception("Failed to connect to database or initialize schema:")
                    raise

            async def close(self):
                if self._conn is not None:
                    logger.info("Closing database connection...")
                    try:
                        await self._conn.close()
                        self._conn = None
                        logger.info("Database connection closed.")
                    except Exception as e:
                        logger.exception("Error closing database connection:")

            async def _init_db_async(self):
                if self._conn is None: logger.error("Cannot perform async DB init: connection is None.")
                cursor = await self._conn.cursor()
                await cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                await cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    hp INTEGER DEFAULT 100 CHECK(hp >= 0 AND hp <= 150),
                    level INTEGER DEFAULT 1 CHECK(level >= 1 AND level <= 169),
                    exp INTEGER DEFAULT 0,
                    lumcoins INTEGER DEFAULT 0,
                    daily_messages INTEGER DEFAULT 0,
                    total_messages INTEGER DEFAULT 0,
                    flames INTEGER DEFAULT 0,
                    background_url TEXT,
                    last_work_time REAL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                ''')
                await cursor.execute('''
                CREATE TABLE IF NOT EXISTS backgrounds (
                    user_id INTEGER PRIMARY KEY,
                    background_url TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                ''')
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)')
                await self._conn.commit()

            async def _get_or_create_user(self, user: types.User) -> int:
                if self._conn is None: raise RuntimeError("Database connection is not established.")
                cursor = await self._conn.cursor()
                await cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                ''', (user.id, user.username, user.first_name, user.last_name))
                await self._conn.commit()
                return user.id

            async def _get_or_create_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
                if self._conn is None: raise RuntimeError("Database connection is not established.")
                cursor = await self._conn.cursor()
                await cursor.execute('''
                INSERT OR IGNORE INTO user_profiles (user_id, background_url)
                VALUES (?, ?)
                ''', (user_id, ProfileConfig.DEFAULT_BG_URL))
                await self._conn.commit()
                await cursor.execute('''
                SELECT * FROM user_profiles WHERE user_id = ?
                ''', (user_id,))
                profile = await cursor.fetchone()
                if not profile:
                    return None
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, profile))

            async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
                if self._conn is None: raise RuntimeError("Database connection is not established.")
                cursor = await self._conn.cursor()
                await cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        last_name = excluded.last_name
                ''', (user.id, user.username, user.first_name, user.last_name))
                await self._conn.commit()
                user_id = user.id
                await cursor.execute('''
                INSERT OR IGNORE INTO user_profiles (user_id, background_url)
                VALUES (?, ?)
                ''', (user_id, ProfileConfig.DEFAULT_BG_URL))
                await self._conn.commit()
                await cursor.execute('''
                SELECT * FROM user_profiles WHERE user_id = ?
                ''', (user_id,))
                profile = await cursor.fetchone()
                if not profile:
                    logger.error(f"Profile not found for user_id {user_id} after creation attempt.")
                    return None
                columns = [column[0] for column in cursor.description]
                profile_data = dict(zip(columns, profile))
                await cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
                user_data = await cursor.fetchone()
                if user_data:
                     profile_data['username'] = f"@{user_data[0]}" if user_data[0] else user_data[1]
                else:
                     profile_data['username'] = user.first_name
                await cursor.execute('SELECT background_url FROM backgrounds WHERE user_id = ?', (user_id,))
                custom_bg = await cursor.fetchone()
                if custom_bg:
                    profile_data['background_url'] = custom_bg[0]
                else:
                    pass
                return profile_data

            async def record_message(self, user: types.User) -> None:
                if self._conn is None: raise RuntimeError("Database connection is not established.")
                cursor = await self._conn.cursor()
                user_id = user.id
                await cursor.execute('''
                SELECT total_messages, level, exp, lumcoins
                FROM user_profiles WHERE user_id = ?
                ''', (user_id,))
                profile_data = await cursor.fetchone()
                if not profile_data:
                     logger.error(f"Profile not found for user_id: {user_id} in record_message. Skipping message count.")
                     return
                total_messages, level, exp, lumcoins = profile_data
                total_messages += 1
                daily_messages_increment = 1
                exp_added = 0
                if total_messages > 0 and total_messages % ProfileConfig.EXP_PER_MESSAGE_INTERVAL == 0:
                     exp_added = ProfileConfig.EXP_AMOUNT_PER_INTERVAL
                new_exp = exp + exp_added
                new_level = level
                new_lumcoins = lumcoins
                while new_exp >= self._get_exp_for_level(new_level) and new_level < ProfileConfig.MAX_LEVEL:
                     needed_for_current = self._get_exp_for_level(new_level)
                     new_exp -= needed_for_current
                     new_level += 1
                     coins_this_level = self._get_lumcoins_for_level(new_level)
                     new_lumcoins += coins_this_level
                await cursor.execute('''
                UPDATE user_profiles
                SET daily_messages = daily_messages + ?,
                    total_messages = ?,
                    exp = ?,
                    level = ?,
                    lumcoins = ?
                WHERE user_id = ?
                ''', (daily_messages_increment, total_messages, new_exp, new_level, new_lumcoins, user_id))
                await self._conn.commit()

            def _get_exp_for_level(self, level: int) -> int:
                if level < 1:
                    return 0
                base_exp = 100
                coefficient = 2
                multiplier = 5
                return base_exp + (level ** coefficient) * multiplier

            def _get_lumcoins_for_level(self, level: int) -> int:
                for lvl, coins in sorted(ProfileConfig.LUMCOINS_PER_LEVEL.items(), reverse=True):
                    if level >= lvl:
                        return coins
                return 1

            async def generate_profile_image(self, user: types.User, profile: Dict[str, Any]) -> BytesIO:
                    exp_bar_width = 250
                    exp_bar_height = 30
                    if not os.path.exists(ProfileConfig.FONT_PATH):
                        logger.error(f"Font file not found: {ProfileConfig.FONT_PATH}. Using default font.")
                        font_large = ImageFont.load_default()
                        font_medium = ImageFont.load_default()
                        font_small = ImageFont.load_default()
                    else:
                        if ProfileConfig.FONT_PATH not in self.font_cache:
                            try:
                                self.font_cache[ProfileConfig.FONT_PATH] = {
                                        'large': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_LARGE),
                                        'medium': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_MEDIUM),
                                        'small': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_SMALL)
                                }
                                logger.info(f"Font '{ProfileConfig.FONT_PATH}' loaded successfully.")
                            except Exception as e:
                                logger.exception(f"Failed to load font '{ProfileConfig.FONT_PATH}':")
                                font_large = ImageFont.load_default()
                                font_medium = ImageFont.load_default()
                                font_small = ImageFont.load_default()
                        font_large = self.font_cache[ProfileConfig.FONT_PATH].get('large', ImageFont.load_default())
                        font_medium = self.font_cache[ProfileConfig.FONT_PATH].get('medium', ImageFont.load_default())
                        font_small = self.font_cache[ProfileConfig.FONT_PATH].get('small', ImageFont.load_default())
                    bg_url = profile.get('background_url', ProfileConfig.DEFAULT_BG_URL)
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(bg_url) as resp:
                                resp.raise_for_status()
                                bg_image_data = await resp.read()
                        bg_image = Image.open(BytesIO(bg_image_data)).convert("RGBA")
                        bg_image = bg_image.resize((600, 200))
                        overlay = Image.new('RGBA', bg_image.size, (0, 0, 0, 0))
                        draw = ImageDraw.Draw(overlay)
                        level = profile.get('level', 1)
                        exp = profile.get('exp', 0)
                        lumcoins = profile.get('lumcoins', 0)
                        hp = profile.get('hp', 100)
                        total_messages = profile.get('total_messages', 0)
                        flames = profile.get('flames', 0)
                        username = profile.get('username', user.first_name)
                        user_info_text = f"{username}"
                        level_text = f"Уровень: {level}"
                        needed_exp_for_next_level = self._get_exp_for_level(level)
                        if level < ProfileConfig.MAX_LEVEL:
                            display_exp = min(exp, needed_exp_for_next_level) if needed_exp_for_next_level > 0 else exp # Убрано деление, чтобы отображать опыт в числах, а не процентах
                            exp_text = f"Опыт: {display_exp} / {needed_exp_for_next_level}"
                        else:
                            exp_text = f"Опыт: {exp} (МАКС)"
                        money_text = f"💎 {lumcoins}"
                        hp_text = f"❤️ HP: {hp}/{ProfileConfig.MAX_HP}"
                        flames_text = f"🔥 {flames}"
                        messages_text = f"✉️ {total_messages}"

                        def draw_text_with_shadow(draw_obj, position, text, font, text_color, shadow_color, shadow_offset=(1, 1)):
                            shadow_pos = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
                            draw_obj.text(shadow_pos, text, font=font, fill=shadow_color)
                            draw_obj.text(position, text, font=font, fill=text_color)

                        username_pos = (ProfileConfig.AVATAR_OFFSET[0] + ProfileConfig.AVATAR_SIZE + 10, ProfileConfig.AVATAR_OFFSET[1] + 5)
                        draw_text_with_shadow(draw, username_pos, user_info_text, font_large, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)
                        username_bbox = draw.textbbox((0,0), user_info_text, font=font_large)
                        username_height = username_bbox[3] - username_bbox[1]
                        level_pos_y = username_pos[1] + username_height + 5
                        level_pos = (username_pos[0], level_pos_y)
                        draw_text_with_shadow(draw, level_pos, level_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)
                        hp_pos_y = ProfileConfig.EXP_BAR_OFFSET[1] + exp_bar_height + 5
                        hp_pos = (ProfileConfig.EXP_BAR_OFFSET[0], hp_pos_y)
                        hp_color = ProfileConfig.HP_COLORS.get("high")
                        if hp < ProfileConfig.MAX_HP * 0.2 and hp > 0:
                            hp_color = ProfileConfig.HP_COLORS.get("low", hp_color)
                        elif hp < ProfileConfig.MAX_HP * 0.5 and hp > 0:
                            hp_color = ProfileConfig.HP_COLORS.get("medium", hp_color)
                        elif hp == 0:
                            hp_color = ProfileConfig.HP_COLORS.get("low", (128, 0, 0))
                        draw_text_with_shadow(draw, hp_pos, hp_text, font_medium, hp_color, ProfileConfig.TEXT_SHADOW)
                        exp_bar_pos = ProfileConfig.EXP_BAR_OFFSET
                        needed_exp_for_next_level = self._get_exp_for_level(level)
                        current_exp_percentage = 0.0
                        if level < ProfileConfig.MAX_LEVEL and needed_exp_for_next_level > 0:
                            current_exp_percentage = min(exp / needed_exp_for_next_level, 1.0)
                        elif level == ProfileConfig.MAX_LEVEL:
                            current_exp_percentage = 1.0
                        exp_bar_fill_width = int(exp_bar_width * current_exp_percentage)
                        draw.rectangle([exp_bar_pos, (exp_bar_pos[0] + exp_bar_width, exp_bar_pos[1] + exp_bar_height)], fill=(50, 50, 50, 128))
                        if exp_bar_fill_width > 0:
                            draw.rectangle([exp_bar_pos, (exp_bar_pos[0] + exp_bar_fill_width, exp_bar_pos[1] + exp_bar_height)], fill=(0, 255, 0, 192))
                        exp_text_bbox = draw.textbbox((0,0), exp_text, font=font_small)
                        exp_text_height = exp_text_bbox[3] - exp_text_bbox[1]
                        exp_text_pos_x = exp_bar_pos[0]
                        exp_text_pos_y = exp_bar_pos[1] - exp_text_height - 2
                        draw_text_with_shadow(draw, (exp_text_pos_x, exp_text_pos_y), exp_text, font_small, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)
                        money_text_bbox = draw.textbbox((0,0), money_text, font=font_medium)
                        money_text_width = money_text_bbox[2] - money_text_bbox[0]
                        money_pos_x = bg_image.size[0] - ProfileConfig.MONEY_OFFSET_RIGHT - money_text_width
                        money_pos_y = ProfileConfig.MARGIN
                        draw_text_with_shadow(draw, (money_pos_x, money_pos_y), money_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)
                        flames_text_bbox = draw.textbbox((0,0), flames_text, font=font_medium)
                        flames_text_width = flames_text_bbox[2] - flames_text_bbox[0]
                        flames_text_height = flames_text_bbox[3] - flames_text_bbox[1]
                        flames_pos_x = bg_image.size[0] + ProfileConfig.FLAMES_OFFSET_X - flames_text_width
                        flames_pos_y = ProfileConfig.FLAMES_OFFSET_Y + (money_text_bbox[3] - money_text_bbox[1]) + 5
                        draw_text_with_shadow(draw, (flames_pos_x, flames_pos_y), flames_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)
                        messages_text_bbox = draw.textbbox((0,0), messages_text, font=font_medium)
                        messages_text_width = messages_text_bbox[2] - messages_text_bbox[0]
                        messages_pos_x = bg_image.size[0] + ProfileConfig.MESSAGES_OFFSET_X - messages_text_width
                        messages_pos_y = ProfileConfig.MESSAGES_OFFSET_Y + flames_text_height + 5
                        draw_text_with_shadow(draw, (messages_pos_x, messages_pos_y), messages_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)
                        composite = Image.alpha_composite(bg_image, overlay)
                        byte_io = BytesIO()
                        composite.save(byte_io, format='PNG')
                        byte_io.seek(0)
                        return byte_io
                    except Exception as e:
                        logger.exception("Error generating profile image:")
                        try:
                            error_img = Image.new('RGB', (600, 200), color = (255, 0, 0))
                            d = ImageDraw.Draw(error_img)
                            try:
                                error_font = ImageFont.truetype(ProfileConfig.FONT_PATH, 30)
                            except:
                                error_font = ImageFont.load_default()
                            text = "Ошибка при загрузке/генерации профиля"
                            text_bbox = d.textbbox((0,0), text, font=error_font)
                            text_width = text_bbox[2] - text_bbox[0]
                            text_height = text_bbox[3] - text_bbox[1]
                            text_x = (600 - text_width) // 2
                            text_y = (200 - text_height) // 2
                            d.text((text_x, text_y), text, fill=(255,255,255), font=error_font)
                            byte_io = BytesIO()
                            error_img.save(byte_io, format='PNG')
                            byte_io.seek(0)
                            return byte_io
                        except Exception as fallback_e:
                            logger.exception("Failed to generate error image fallback:")
                            return BytesIO()

            async def update_lumcoins(self, user_id: int, amount: int):
                if self._conn is None: raise RuntimeError("Database connection is not established.")
                cursor = await self._conn.cursor()
                await cursor.execute('''
                UPDATE user_profiles
                SET lumcoins = lumcoins + ?
                WHERE user_id = ?
                ''', (amount, user_id))
                await self._conn.commit()

            async def get_lumcoins(self, user_id: int) -> int:
                if self._conn is None: raise RuntimeError("Database connection is not established.")
                cursor = await self._conn.cursor()
                await cursor.execute('''
                SELECT lumcoins FROM user_profiles WHERE user_id = ?
                ''', (user_id,))
                result = await cursor.fetchone()
                return result[0] if result else 0

            async def set_background(self, user_id: int, background_url: str):
                if self._conn is None: raise RuntimeError("Database connection is not established.")
                cursor = await self._conn.cursor()
                await cursor.execute('''
                INSERT OR REPLACE INTO backgrounds (user_id, background_url)
                VALUES (?, ?)
                ''', (user_id, background_url))
                await self._conn.commit()

            def get_available_backgrounds(self) -> Dict[str, Dict[str, Any]]:
                return ProfileConfig.BACKGROUND_SHOP

            async def get_last_work_time(self, user_id: int) -> float:
                if self._conn is None: raise RuntimeError("Database connection is not established.")
                cursor = await self._conn.cursor()
                await cursor.execute('''
                SELECT last_work_time FROM user_profiles WHERE user_id = ?
                ''', (user_id,))
                result = await cursor.fetchone()
                return result[0] if result else 0.0

            async def update_last_work_time(self, user_id: int, timestamp: float):
                if self._conn is None: raise RuntimeError("Database connection is not established.")
                cursor = await self._conn.cursor()
                await cursor.execute('''
                UPDATE user_profiles
                SET last_work_time = ?
                WHERE user_id = ?
                ''', (timestamp, user_id))
                await self._conn.commit()

        @stat_router.message(F.text.lower().startswith(("профиль", "/профиль")))
        async def show_profile(message: types.Message, profile_manager: ProfileManager):
            profile = await profile_manager.get_user_profile(message.from_user)
            if not profile:
                await message.reply("❌ Не удалось загрузить профиль!")
                return
            image_bytes = await profile_manager.generate_profile_image(message.from_user, profile)
            input_file = BufferedInputFile(image_bytes.getvalue(), filename="profile.png")
            await message.answer_photo(
                photo=input_file,
                caption=f"Профиль пользователя {message.from_user.first_name}"
            )

        @stat_router.message(F.text.lower() == "работать")
        async def do_work(message: types.Message, profile_manager: ProfileManager):
            user_id = message.from_user.id
            current_time = time.time()
            last_work_time = await profile_manager.get_last_work_time(user_id)
            time_elapsed = current_time - last_work_time
            time_left = ProfileConfig.WORK_COOLDOWN_SECONDS - time_elapsed
            if time_elapsed < ProfileConfig.WORK_COOLDOWN_SECONDS:
                minutes_left = int(time_left // 60)
                seconds_left = int(time_left % 60)
                await message.reply(f"⏳ Работать можно будет через {minutes_left} мин {seconds_left} сек.")
            else:
                reward = random.randint(ProfileConfig.WORK_REWARD_MIN, ProfileConfig.WORK_REWARD_MAX)
                task = random.choice(ProfileConfig.WORK_TASKS)
                await profile_manager.update_lumcoins(user_id, reward)
                await profile_manager.update_last_work_time(user_id, current_time)
                await message.reply(f"{message.from_user.first_name} {task} и заработал(а) {reward} LUMcoins!")

        @stat_router.message(F.text.lower() == "магазин")
        async def show_shop(message: types.Message, profile_manager: ProfileManager):
            shop_items = profile_manager.get_available_backgrounds()
            text = "🛍️ **Магазин фонов** 🛍️\\n\\n"
            text += "Напишите название фона из списка, чтобы купить его:\\n\\n"
            for key, item in shop_items.items():
                text += f"- `{key}`: {item['name']} ({item['cost']} LUMcoins)\\n"
            await message.reply(text, parse_mode="Markdown")

        @stat_router.message(F.text.lower().in_(ProfileConfig.BACKGROUND_SHOP.keys()))
        async def buy_background(message: types.Message, profile_manager: ProfileManager):
            user_id = message.from_user.id
            command = message.text.lower()
            shop_items = profile_manager.get_available_backgrounds()
            if command in shop_items:
                item = shop_items[command]
                user_coins = await profile_manager.get_lumcoins(user_id)
                if user_coins >= item['cost']:
                    await profile_manager.update_lumcoins(user_id, -item['cost'])
                    await profile_manager.set_background(user_id, item['url'])
                    await message.reply(f"✅ Вы успешно приобрели фон '{item['name']}' за {item['cost']} LUMcoins!")
                else:
                    await message.reply(f"❌ Недостаточно LUMcoins! Цена фона '{item['name']}': {item['cost']}, у вас: {user_coins}.")

        @stat_router.message()
        async def track_message_activity(message: types.Message, profile_manager: ProfileManager):
            if message.from_user.id == message.bot.id or message.content_type != types.ContentType.TEXT:
                 return
            user_id = message.from_user.id
            old_profile = await profile_manager.get_user_profile(message.from_user)
            if not old_profile:
                 logger.error(f"Failed to get old profile for user_id {user_id} in track_message_activity.")
                 return
            old_level = old_profile.get('level', 1)
            old_lumcoins = old_profile.get('lumcoins', 0)
            await profile_manager.record_message(message.from_user)
            new_profile = await profile_manager.get_user_profile(message.from_user)
            if not new_profile:
                logger.error(f"Failed to get new profile for user_id {user_id} after record_message.")
                return
            new_level = new_profile.get('level', 1)
            new_lumcoins = new_profile.get('lumcoins', 0)
            lumcoins_earned_from_level = new_lumcoins - old_lumcoins
            if new_level > old_level and lumcoins_earned_from_level > 0:
                await message.reply(
                    f"🎉 Поздравляю, {message.from_user.first_name}! Ты достиг(ла) Уровня {new_level}! "
                    f"Награда: {lumcoins_earned_from_level} LUMcoins."
                )

        def setup_stat_handlers(dp: Dispatcher, bot: Bot, profile_manager: ProfileManager): # Добавлены bot и profile_manager
            dp.include_router(stat_router)
            logger.info("Stat router included.")
            # profile_manager.bot = bot # Если ProfileManager требует доступа к боту, можно передать так
            return dp
        """)
    with open("group_stat.py", "w", encoding="utf-8") as f:
        f.write(group_stat_content)
    print("Файл group_stat.py успешно создан.")

    print("Создание rp_module_refactored.py...")
    rp_module_content = textwrap.dedent("""\
        import asyncio
        import time
        import random
        import logging
        from typing import Dict, Any, Optional, List, Tuple, Set
        import aiosqlite
        from aiogram import Router, types, F, Bot
        from aiogram.enums import ChatType, ParseMode, MessageEntityType
        from aiogram.filters import Command
        from aiogram.exceptions import TelegramAPIError
        from contextlib import suppress
        import database as db

        try:
            from group_stat import ProfileManager as RealProfileManager # Импортируем с алиасом
            HAS_PROFILE_MANAGER = True
        except ImportError:
            logging.critical("CRITICAL: Module 'group_stat' or 'ProfileManager' not found. RP functionality will be severely impaired or non-functional.")
            HAS_PROFILE_MANAGER = False
            # Заглушка ProfileManager, которая соответствует интерфейсу RealProfileManager
            class RealProfileManager:
                async def get_user_rp_stats(self, user_id: int) -> Dict[str, Any]: # Изменено с get_rp_stats
                    return {'hp': 100, 'recovery_end_ts': 0.0, 'heal_cooldown_ts': 0.0}
                async def update_user_rp_stats(self, user_id: int, **kwargs: Any) -> None:
                    pass
                async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
                    return None
                async def connect(self) -> None:
                    pass
                async def close(self) -> None:
                    pass

        ProfileManager = RealProfileManager

        logger = logging.getLogger(__name__)

        rp_router = Router(name="rp_module")
        rp_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

        class RPConfig:
            \"\"\"Конфигурационные параметры для RP-системы.\"\"\"
            DEFAULT_HP: int = 100
            MAX_HP: int = 150
            MIN_HP: int = 0
            HEAL_COOLDOWN_SECONDS: int = 1800  # 30 минут
            HP_RECOVERY_TIME_SECONDS: int = 600 # 10 минут
            HP_RECOVERY_AMOUNT: int = 25

        class RPActions:
            \"\"\"Определения RP-действий и их эффектов на HP.\"\"\"
            INTIMATE_ACTIONS: Dict[str, Dict[str, Dict[str, int]]] = {
                "добрые": {
                    "поцеловать": {"hp_change_target": +10, "hp_change_sender": +1},
                    "обнять": {"hp_change_target": +15, "hp_change_sender": +5},
                    "погладить": {"hp_change_target": +5, "hp_change_sender": +2},
                    "романтический поцелуй": {"hp_change_target": +20, "hp_change_sender": +10},
                    "трахнуть": {"hp_change_target": +30, "hp_change_sender": +15},
                    "поцеловать в щёчку": {"hp_change_target": +7, "hp_change_sender": +3},
                    "прижать к себе": {"hp_change_target": +12, "hp_change_sender": +6},
                    "покормить": {"hp_change_target": +9, "hp_change_sender": -2},
                    "напоить": {"hp_change_target": +6, "hp_change_sender": -1},
                    "сделать массаж": {"hp_change_target": +15, "hp_change_sender": +3},
                    "спеть песню": {"hp_change_target": +5, "hp_change_sender": +1},
                    "подарить цветы": {"hp_change_target": +12, "hp_change_sender": 0},
                    "подрочить": {"hp_change_target": +12, "hp_change_sender": +6},
                    "полечить": {"hp_change_target": +25, "hp_change_sender": -5},
                },
                "нейтральные": {
                    "толкнуть": {"hp_change_target": 0, "hp_change_sender": 0},
                    "схватить": {"hp_change_target": 0, "hp_change_sender": 0},
                    "помахать": {"hp_change_target": 0, "hp_change_sender": 0},
                    "кивнуть": {"hp_change_target": 0, "hp_change_sender": 0},
                    "похлопать": {"hp_change_target": 0, "hp_change_sender": 0},
                    "постучать": {"hp_change_target": 0, "hp_change_sender": 0},
                    "попрощаться": {"hp_change_target": 0, "hp_change_sender": 0},
                    "шепнуть": {"hp_change_target": 0, "hp_change_sender": 0},
                    "почесать спинку": {"hp_change_target": +5, "hp_change_sender": 0},
                    "успокоить": {"hp_change_target": +5, "hp_change_sender": +1},
                    "заплакать": {}, "засмеяться": {}, "удивиться": {}, "подмигнуть": {},
                },
                "злые": {
                    "уебать": {"hp_change_target": -20, "hp_change_sender": -2},
                    "схватить за шею": {"hp_change_target": -25, "hp_change_sender": -3},
                    "ударить": {"hp_change_target": -10, "hp_change_sender": -1},
                    "укусить": {"hp_change_target": -15, "hp_change_sender": 0},
                    "шлепнуть": {"hp_change_target": -8, "hp_change_sender": 0},
                    "пощечина": {"hp_change_target": -12, "hp_change_sender": -1},
                    "пнуть": {"hp_change_target": -10, "hp_change_sender": 0},
                    "ущипнуть": {"hp_change_target": -7, "hp_change_sender": 0},
                    "толкнуть сильно": {"hp_change_target": -9, "hp_change_sender": -1},
                    "обозвать": {"hp_change_target": -5, "hp_change_sender": 0},
                    "плюнуть": {"hp_change_target": -6, "hp_change_sender": 0},
                    "превратить": {"hp_change_target": -80, "hp_change_sender": -10},
                    "обидеть": {"hp_change_target": -7, "hp_change_sender": 0},
                    "разозлиться": {"hp_change_target": -2, "hp_change_sender": -1},
                    "испугаться": {"hp_change_target": -1, "hp_change_sender": 0},
                    "издеваться": {"hp_change_target": -10, "hp_change_sender": -1},
                }
            }
            # Объединение всех действий в один словарь для удобного доступа
            ALL_ACTION_DATA: Dict[str, Dict[str, int]] = {
                action: data if data else {}
                for category_actions in INTIMATE_ACTIONS.values()
                for action, data in category_actions.items()
            }
            # Список команд, отсортированных по длине для правильного парсинга (длинные команды первыми)
            SORTED_COMMANDS_FOR_PARSING: List[str] = sorted(
                ALL_ACTION_DATA.keys(), key=len, reverse=True
            )
            # Действия, сгруппированные по категориям для отображения в списке команд
            ALL_ACTIONS_LIST_BY_CATEGORY: Dict[str, List[str]] = {
                "Добрые действия ❤️": list(INTIMATE_ACTIONS["добрые"].keys()),
                "Нейтральные действия 😐": list(INTIMATE_ACTIONS["нейтральные"].keys()),
                "Злые действия 💀": list(INTIMATE_ACTIONS["злые"].keys())
            }

        def get_user_display_name(user: types.User) -> str:
            \"\"\"Формирует отображаемое имя пользователя.\"\"\"
            name = f"@{user.username}" if user.username else user.full_name
            return name

        async def _update_user_hp(
            profile_manager: ProfileManager,
            user_id: int,
            hp_change: int
        ) -> Tuple[int, bool]:
            \"\"\"
            Обновляет HP пользователя и проверяет, потерял ли он сознание.

            Args:
                profile_manager (ProfileManager): Менеджер профилей для доступа к RP-статистике.
                user_id (int): ID пользователя.
                hp_change (int): Изменение HP (может быть положительным или отрицательным).

            Returns:
                Tuple[int, bool]: Новое значение HP и флаг, указывающий, потерял ли пользователь сознание.
            \"\"\"
            stats = await profile_manager.get_user_rp_stats(user_id) # Исправлено
            current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
            new_hp = max(RPConfig.MIN_HP, min(RPConfig.MAX_HP, current_hp + hp_change))
            knocked_out_this_time = False
            update_fields = {'hp': new_hp}

            # Если HP упало до или ниже нуля, и это не было так ранее
            if new_hp <= RPConfig.MIN_HP and current_hp > RPConfig.MIN_HP:
                recovery_ts = time.time() + RPConfig.HP_RECOVERY_TIME_SECONDS
                update_fields['recovery_end_ts'] = recovery_ts
                knocked_out_this_time = True
                logger.info(f"User {user_id} HP dropped to {new_hp}. Recovery timer set for {RPConfig.HP_RECOVERY_TIME_SECONDS}s.")
            # Если HP восстановилось выше нуля
            elif new_hp > RPConfig.MIN_HP and stats.get('recovery_end_ts', 0.0) > 0 :
                update_fields['recovery_end_ts'] = 0.0
                logger.info(f"User {user_id} HP recovered above {RPConfig.MIN_HP}. Recovery timer reset.")

            await profile_manager.update_user_rp_stats(user_id, **update_fields) # Исправлено
            return new_hp, knocked_out_this_time

        def get_command_from_text(text: Optional[str]) -> Tuple[Optional[str], str]:
            \"\"\"
            Извлекает RP-команду из текстового сообщения.

            Args:
                text (Optional[str]): Входной текст сообщения.

            Returns:
                Tuple[Optional[str], str]: Найденная команда (или None) и остальной текст.
            \"\"\"
            if not text:
                return None, ""
            text_lower = text.lower()
            for cmd in RPActions.SORTED_COMMANDS_FOR_PARSING:
                # Проверяем, что команда либо является полным сообщением, либо за ней идет пробел
                if text_lower.startswith(cmd) and \\
                   (len(text_lower) == len(cmd) or text_lower[len(cmd)].isspace()):
                    additional_text = text[len(cmd):].strip()
                    return cmd, additional_text
            return None, ""

        def format_timedelta(seconds: float) -> str:
            \"\"\"Форматирует количество секунд в читаемый формат (мин/сек).\"\"\"
            if seconds <= 0:
                return "уже можно"
            total_seconds = int(seconds)
            minutes = total_seconds // 60
            secs = total_seconds % 60
            if minutes > 0 and secs > 0:
                return f"{minutes} мин {secs} сек"
            elif minutes > 0:
                return f"{minutes} мин"
            return f"{secs} сек"

        async def check_and_notify_rp_state(
            user: types.User,
            bot: Bot,
            profile_manager: ProfileManager,
            message_to_delete_on_block: Optional[types.Message] = None
        ) -> bool:
            \"\"\"
            Проверяет состояние HP пользователя и уведомляет его, если он не может выполнять RP-действия.

            Args:
                user (types.User): Объект пользователя, который пытается выполнить действие.
                bot (Bot): Экземпляр бота.
                profile_manager (ProfileManager): Менеджер профилей.
                message_to_delete_on_block (Optional[types.Message]): Сообщение, которое нужно удалить,
                                                                      если действие заблокировано (например, RP-команда).

            Returns:
                bool: True, если действие заблокировано (пользователь без HP), False иначе.
            \"\"\"
            if not HAS_PROFILE_MANAGER:
                logger.error(f"Cannot check RP state for user {user.id} due to missing ProfileManager.")
                try:
                    await bot.send_message(user.id, "⚠️ Произошла ошибка с модулем профилей, RP-действия временно недоступны.")
                except TelegramAPIError:
                    pass
                if message_to_delete_on_block:
                     with suppress(TelegramAPIError): await message_to_delete_on_block.delete()
                return True

            stats = await profile_manager.get_user_rp_stats(user.id) # Исправлено
            current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
            recovery_ts = stats.get('recovery_end_ts', 0.0)
            now = time.time()

            if current_hp <= RPConfig.MIN_HP:
                if recovery_ts > 0.0 and now < recovery_ts:
                    remaining_recovery = recovery_ts - now
                    time_str = format_timedelta(remaining_recovery)
                    try:
                        await bot.send_message(
                            user.id,
                            f"Вы сейчас не можете совершать RP-действия (HP: {current_hp}).\\n"
                            f"Автоматическое восстановление {RPConfig.HP_RECOVERY_AMOUNT} HP через: {time_str}."
                        )
                    except TelegramAPIError as e:
                        logger.warning(f"Could not send RP state PM to user {user.id}: {e}")
                        if message_to_delete_on_block:
                            await message_to_delete_on_block.reply(
                                f"{get_user_display_name(user)}, вы пока не можете действовать (HP: {current_hp}). "
                                f"Восстановление через {time_str}."
                            )
                    if message_to_delete_on_block:
                        with suppress(TelegramAPIError): await message_to_delete_on_block.delete()
                    return True
                elif recovery_ts == 0.0 or now >= recovery_ts:
                    recovered_hp, _ = await _update_user_hp(profile_manager, user.id, RPConfig.HP_RECOVERY_AMOUNT)
                    logger.info(f"User {user.id} HP auto-recovered to {recovered_hp} upon action attempt.")
                    try:
                        await bot.send_message(user.id, f"Ваше HP восстановлено до {recovered_hp}! Теперь вы можете совершать RP-действия.")
                    except TelegramAPIError:
                        pass
                    return False
            return False

        async def _process_rp_action(
            message: types.Message,
            bot: Bot,
            profile_manager: ProfileManager,
            command_text_payload: str
        ):
            \"\"\"
            Обрабатывает RP-действие, инициированное пользователем.

            Args:
                message (types.Message): Объект сообщения Telegram.
                bot (Bot): Экземпляр бота.
                profile_manager (ProfileManager): Менеджер профилей.
                command_text_payload (str): Текст команды RP (например, "поцеловать @username").
            \"\"\"
            if not HAS_PROFILE_MANAGER:
                await message.reply("⚠️ RP-модуль временно недоступен из-за внутренней ошибки конфигурации.")
                return
            sender_user = message.from_user
            if not sender_user:
                logger.warning("Cannot identify sender for an RP action.")
                return

            if await check_and_notify_rp_state(sender_user, bot, profile_manager, message_to_delete_on_block=message):
                return

            target_user: Optional[types.User] = None
            if message.reply_to_message and message.reply_to_message.from_user:
                target_user = message.reply_to_message.from_user
            else:
                entities = message.entities or []
                for entity in entities:
                    if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                        target_user = entity.user
                        break

            if not target_user:
                await message.reply(
                    "⚠️ Укажите цель: ответьте на сообщение пользователя или упомяните его (@ИмяПользователя так, чтобы он был кликабелен)."
                )
                return

            command, additional_text = get_command_from_text(command_text_payload)
            if not command:
                return

            if target_user.id == sender_user.id:
                await message.reply("🤦 Вы не можете использовать RP-команды на себе!")
                with suppress(TelegramAPIError): await message.delete()
                return
            if target_user.id == bot.id:
                await message.reply(f"🤖 Нельзя применять RP-действия ко мне, {sender_user.first_name}!")
                with suppress(TelegramAPIError): await message.delete()
                return
            if target_user.is_bot:
                await message.reply("👻 Действия на других ботов не имеют смысла.")
                with suppress(TelegramAPIError): await message.delete()
                return

            sender_name = get_user_display_name(sender_user)
            target_name = get_user_display_name(target_user)

            action_data = RPActions.ALL_ACTION_DATA.get(command, {})
            action_category = next((cat for cat, cmds in RPActions.INTIMATE_ACTIONS.items() if command in cmds), None)

            if action_category == "добрые" and action_data.get("hp_change_target", 0) > 0:
                sender_stats = await profile_manager.get_user_rp_stats(sender_user.id) # Исправлено
                heal_cd_ts = sender_stats.get('heal_cooldown_ts', 0.0)
                now = time.time()
                if now < heal_cd_ts:
                    remaining_cd_str = format_timedelta(heal_cd_ts - now)
                    await message.reply(
                        f"{sender_name}, вы сможете снова использовать лечащие команды через {remaining_cd_str}."
                    )
                    with suppress(TelegramAPIError): await message.delete()
                    return
                else:
                    await profile_manager.update_user_rp_stats( # Исправлено
                        sender_user.id, heal_cooldown_ts=now + RPConfig.HEAL_COOLDOWN_SECONDS
                    )

            hp_change_target_val = action_data.get("hp_change_target", 0)
            hp_change_sender_val = action_data.get("hp_change_sender", 0)

            target_initial_stats = await profile_manager.get_user_rp_stats(target_user.id) # Исправлено
            target_current_hp_before_action = target_initial_stats.get('hp', RPConfig.DEFAULT_HP)
            if target_current_hp_before_action <= RPConfig.MIN_HP and \\
               hp_change_target_val < 0 and \\
               command != "превратить":
                await message.reply(f"{target_name} уже без сознания. Зачем же его мучить еще больше?", parse_mode=ParseMode.HTML)
                with suppress(TelegramAPIError): await message.delete()
                return

            new_target_hp, target_knocked_out = (target_current_hp_before_action, False)
            if hp_change_target_val != 0:
                new_target_hp, target_knocked_out = await _update_user_hp(profile_manager, target_user.id, hp_change_target_val)
            new_sender_hp, sender_knocked_out = await _update_user_hp(profile_manager, sender_user.id, hp_change_sender_val)

            command_past = command
            verb_ending_map = {"ть": "л", "ться": "лся"}
            for infinitive_ending, past_ending_male in verb_ending_map.items():
                if command.endswith(infinitive_ending):
                    base = command[:-len(infinitive_ending)]
                    command_past = base + random.choice([past_ending_male, base + "ла"])
                    break

            response_text = f"{sender_name} {command_past} {target_name}"
            if additional_text:
                response_text += f" {additional_text}"

            hp_report_parts = []
            if hp_change_target_val > 0: hp_report_parts.append(f"{target_name} <b style='color:green;'>+{hp_change_target_val} HP</b>")
            elif hp_change_target_val < 0: hp_report_parts.append(f"{target_name} <b style='color:red;'>{hp_change_target_val} HP</b>")
            if hp_change_sender_val > 0: hp_report_parts.append(f"{sender_name} <b style='color:green;'>+{hp_change_sender_val} HP</b>")
            elif hp_change_sender_val < 0: hp_report_parts.append(f"{sender_name} <b style='color:red;'>{hp_change_sender_val} HP</b>")

            if hp_report_parts:
                response_text += f"\\n({', '.join(hp_report_parts)})"

            status_lines = []
            if target_knocked_out:
                status_lines.append(f"😵 {target_name} теряет сознание! (Восстановление через {format_timedelta(RPConfig.HP_RECOVERY_TIME_SECONDS)})")
            elif hp_change_target_val != 0 :
                status_lines.append(f"HP {target_name}: {new_target_hp}/{RPConfig.MAX_HP}")

            if hp_change_sender_val != 0 or new_sender_hp < RPConfig.MAX_HP :
                status_lines.append(f"HP {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP}")

            if sender_knocked_out:
                 status_lines.append(f"😵 {sender_name} перестарался и теряет сознание! (Восстановление через {format_timedelta(RPConfig.HP_RECOVERY_TIME_SECONDS)})")

            if status_lines:
                response_text += "\\n\\n" + "\\n".join(status_lines)

            await message.reply(response_text, parse_mode=ParseMode.HTML)
            with suppress(TelegramAPIError):
                await message.delete()

        @rp_router.message(F.text, lambda msg: get_command_from_text(msg.text)[0] is not None)
        async def handle_rp_action_via_text(message: types.Message, bot: Bot, profile_manager: ProfileManager):
            command_text = message.text
            await _process_rp_action(message, bot, profile_manager, command_text)

        @rp_router.message(Command("rp"))
        async def handle_rp_action_via_command(message: types.Message, bot: Bot, profile_manager: ProfileManager):
            command_payload = message.text[len("/rp"):].strip()
            if not command_payload or get_command_from_text(command_payload)[0] is None:
                await message.reply(
                    "⚠️ Укажите действие после <code>/rp</code>. Например: <code>/rp поцеловать</code>\\n"
                    "И не забудьте ответить на сообщение цели или упомянуть её.\\n"
                    "Список действий: /rp_commands", parse_mode=ParseMode.HTML
                )
                return
            await _process_rp_action(message, bot, profile_manager, command_payload)

        @rp_router.message(F.text.lower().startswith((
            "моё хп", "мое хп", "моё здоровье", "мое здоровье", "хп", "здоровье"
        )))
        @rp_router.message(Command("myhp", "hp"))
        async def cmd_check_self_hp(message: types.Message, bot: Bot, profile_manager: ProfileManager):
            if not message.from_user: return
            if not HAS_PROFILE_MANAGER:
                await message.reply("⚠️ RP-модуль временно недоступен.")
                return
            
            user = message.from_user
            if await check_and_notify_rp_state(user, bot, profile_manager, message_to_delete_on_block=message):
                return

            stats = await profile_manager.get_user_rp_stats(user.id) # Исправлено
            current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
            recovery_ts = stats.get('recovery_end_ts', 0.0)
            heal_cd_ts = stats.get('heal_cooldown_ts', 0.0)
            now = time.time()

            user_display_name = get_user_display_name(user)
            response_lines = [f"{user_display_name}, ваше состояние:"]
            response_lines.append(f"❤️ Здоровье: <b>{current_hp}/{RPConfig.MAX_HP}</b>")

            if current_hp <= RPConfig.MIN_HP and recovery_ts > now:
                response_lines.append(
                    f"😵 Вы без сознания. Восстановление через: {format_timedelta(recovery_ts - now)}"
                )
            elif recovery_ts > 0.0 and recovery_ts <= now and current_hp <= RPConfig.MIN_HP:
                response_lines.append(f"⏳ HP должно было восстановиться, попробуйте еще раз или подождите немного.")

            if heal_cd_ts > now:
                response_lines.append(f"🕒 Кулдаун лечащих действий: {format_timedelta(heal_cd_ts - now)}")
            else:
                response_lines.append("✅ Лечащие действия: готовы!")

            await message.reply("\\n".join(response_lines), parse_mode=ParseMode.HTML)

        @rp_router.message(Command("rp_commands", "rphelp"))
        @rp_router.message(F.text.lower().startswith(("список действий", "рп действия", "список рп", "команды рп")))
        async def cmd_show_rp_actions_list(message: types.Message, bot: Bot):
            response_parts = ["<b>📋 Доступные RP-действия:</b>\\n"]
            for category_name, actions in RPActions.ALL_ACTIONS_LIST_BY_CATEGORY.items():
                response_parts.append(f"<b>{category_name}:</b>")
                action_lines = [f"  • <code>{action}</code> (или <code>/rp {action}</code>)" for action in actions]
                response_parts.append("\\n".join(action_lines))
                response_parts.append("")

            response_parts.append(
                "<i>Использование: ответьте на сообщение цели и напишите команду (<code>обнять</code>) "
                "или используйте <code>/rp обнять</code>, также отвечая или упоминая цель (@ник).</i>"
            )
            await message.reply("\\n".join(response_parts), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

        @rp_router.message(F.text.lower().contains("спасибо"))
        async def reaction_thanks(message: types.Message, bot: Bot, profile_manager: ProfileManager):
            if not message.from_user: return
            if await check_and_notify_rp_state(message.from_user, bot, profile_manager, message): return
            await message.reply("Всегда пожалуйста! 😊")

        @rp_router.message(F.text.lower().contains("люблю"))
        async def reaction_love(message: types.Message, bot: Bot, profile_manager: ProfileManager):
            if not message.from_user: return
            if await check_and_notify_rp_state(message.from_user, bot, profile_manager, message): return
            await message.reply("И я вас люблю! ❤️🤡")

        async def periodic_hp_recovery_task(bot: Bot, profile_manager: ProfileManager, db_module: Any):
            \"\"\"
            Периодическая фоновая задача для восстановления HP пользователей.
            Сканирует базу данных на предмет пользователей, которым требуется восстановление HP.
            \"\"\"
            if not HAS_PROFILE_MANAGER:
                logger.error("Periodic HP recovery task cannot start: ProfileManager is missing.")
                return
            logger.info("Periodic HP recovery task started.")
            while True:
                await asyncio.sleep(60) # Проверка каждую минуту
                now = time.time()
                try:
                    if not hasattr(db_module, 'get_users_for_hp_recovery'):
                        logger.error("Periodic HP recovery: db_module.get_users_for_hp_recovery function is missing!")
                        continue
                    
                    users_to_recover: List[Tuple[int, int]] = await db_module.get_users_for_hp_recovery(now, RPConfig.MIN_HP)

                    if users_to_recover:
                        logger.info(f"Periodic recovery: Found {len(users_to_recover)} users for HP recovery.")
                        for user_id, current_hp_val in users_to_recover:
                            new_hp, _ = await _update_user_hp(profile_manager, user_id, RPConfig.HP_RECOVERY_AMOUNT)
                            logger.info(f"Periodic recovery: User {user_id} HP auto-recovered from {current_hp_val} to {new_hp}.")
                            try:
                                await bot.send_message(
                                    user_id,
                                    f"✅ Ваше HP автоматически восстановлено до {new_hp}/{RPConfig.MAX_HP}! Вы снова в строю."
                                )
                            except TelegramAPIError as e:
                                logger.warning(f"Periodic recovery: Could not send PM to user {user_id}: {e.message}")
                except Exception as e:
                    logger.error(f"Error in periodic_hp_recovery_task: {e}", exc_info=True)

        def setup_rp_handlers(main_dp: Router, bot_instance: Bot, profile_manager_instance: ProfileManager, database_module: Any):
            \"\"\"
            Настраивает RP-обработчики, включая их в главный диспетчер.
            \"\"\"
            if not HAS_PROFILE_MANAGER:
                logging.error("Not setting up RP handlers because ProfileManager is missing.")
                return
            main_dp.include_router(rp_router)
            logger.info("RP router included and configured.")

        def setup_all_handlers(dp: Router, bot: Bot, profile_manager: ProfileManager, db_module: Any):
            \"\"\"
            Централизованная функция для настройки всех обработчиков (RP и статистики групп).
            \"\"\"
            setup_rp_handlers(dp, bot, profile_manager, db_module)
            try:
                from group_stat import setup_stat_handlers as setup_gs_handlers
                setup_gs_handlers(dp, bot=bot, profile_manager=profile_manager)
                logger.info("Group_stat handlers also configured.")
            except ImportError:
                logger.warning("group_stat.setup_stat_handlers not found, skipping its setup.")
        """)
    with open("rp_module_refactored.py", "w", encoding="utf-8") as f:
        f.write(rp_module_content)
    print("Файл rp_module_refactored.py успешно создан.")

    print("Создание main.py...")
    main_content = textwrap.dedent("""\
        import os
        import json
        import random
        import asyncio
        from datetime import datetime, timezone
        from pathlib import Path
        from typing import Optional, List, Tuple, Dict, Any
        from contextlib import suppress
        import logging
        import aiosqlite
        import dotenv
        import ollama
        import aiohttp
        from bs4 import BeautifulSoup
        from aiogram import Bot, Dispatcher, F, types
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode, ChatType
        from aiogram.filters import Command
        from aiogram.types import (
            Message,
            CallbackQuery,
            InlineKeyboardButton,
        )
        from aiogram.exceptions import TelegramAPIError
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.utils.markdown import hide_link, hbold, hitalic, hcode
        import time

        import database as db
        from group_stat import setup_stat_handlers, ProfileManager
        from rp_module_refactored import setup_rp_handlers, periodic_hp_recovery_task

        # Настройка базового логирования
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )
        logger = logging.getLogger(__name__)

        # Загрузка переменных окружения из .env файла
        dotenv.load_dotenv()

        # Получение токена бота из переменных окружения
        TOKEN = os.getenv("TOKEN")
        if not TOKEN:
            logger.critical("Bot token not found in environment variables. Please set the TOKEN variable.")
            exit(1)

        # Конфигурация для Ollama
        OLLAMA_API_BASE_URL = os.getenv("OLLAMA_API_BASE_URL", "http://localhost:11434")
        OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3")

        # Пути к файлам данных
        JOKES_CACHE_FILE = Path("data") / "jokes_cache.json"
        VALUE_FILE_PATH = Path("data") / "value.txt" # Исправлено: использование VALUE_FILE_PATH
        STICKERS_CACHE_FILE = Path("data") / "stickers_cache.json" # Добавлено для StickerManager

        # Глобальные переменные для админа и канала анекдотов
        ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID")
        ADMIN_USER_ID: Optional[int] = None
        if ADMIN_USER_ID_STR and ADMIN_USER_ID_STR.isdigit():
            ADMIN_USER_ID = int(ADMIN_USER_ID_STR)
        else:
            logger.warning("ADMIN_USER_ID is not set or invalid. Dislike forwarding will be disabled.")

        CHANNEL_ID_STR = os.getenv("CHANNEL_ID")
        CHANNEL_ID: Optional[int] = None
        if CHANNEL_ID_STR and CHANNEL_ID_STR.isdigit():
            CHANNEL_ID = int(CHANNEL_ID_STR)
        else:
            logger.warning("CHANNEL_ID is not set or invalid. Jokes task will be disabled.")

        MAX_RATING_OPPORTUNITIES = 3 # Максимальное количество оценок до сброса (для /help)

        class MonitoringState:
            def __init__(self):
                self.is_sending_values = False
                self.last_value: Optional[str] = None
                self.lock = asyncio.Lock()

        monitoring_state = MonitoringState()

        # Создаем экземпляры бота и диспетчера глобально
        bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()

        # Класс для управления стикерами
        class StickerManager:
            def __init__(self, cache_file_path: Path):
                self.stickers: Dict[str, List[str]] = {"saharoza": [], "dedinside": [], "genius": []}
                self.sticker_packs: Dict[str, str] = {
                    "saharoza": "saharoza18",
                    "dedinside": "h9wweseternalregrets_by_fStikBot",
                    "genius": "AcademicStickers"
                }
                self.cache_file = cache_file_path
                self._load_stickers_from_cache()

            def _load_stickers_from_cache(self):
                try:
                    if self.cache_file.exists():
                        with open(self.cache_file, 'r', encoding='utf-8') as f:
                            cached_data = json.load(f)
                        if isinstance(cached_data, dict) and all(k in cached_data for k in self.sticker_packs):
                            self.stickers = cached_data
                            logger.info("Stickers loaded from cache.")
                        else:
                            logger.warning("Sticker cache file has incorrect format. Will re-fetch if needed.")
                    else:
                        logger.info("Sticker cache not found. Will fetch on startup.")
                except Exception as e:
                    logger.error(f"Error loading stickers from cache: {e}", exc_info=True)

            async def fetch_stickers(self, bot_instance: Bot):
                logger.info("Fetching stickers from Telegram...")
                all_fetched_successfully = True
                for mode, pack_name in self.sticker_packs.items():
                    try:
                        if self.stickers.get(mode) and len(self.stickers[mode]) > 0:
                            logger.info(f"Stickers for mode '{mode}' already loaded (possibly from cache). Skipping fetch.")
                            continue
                        
                        stickerset = await bot_instance.get_sticker_set(pack_name)
                        self.stickers[mode] = [sticker.file_id for sticker in stickerset.stickers]
                        logger.info(f"Fetched {len(self.stickers[mode])} stickers for mode '{mode}'.")
                    except Exception as e:
                        logger.error(f"Failed to fetch sticker set '{pack_name}' for mode '{mode}': {e}")
                        all_fetched_successfully = False
                
                if all_fetched_successfully and any(self.stickers.values()):
                    self._save_stickers_to_cache()

            def _save_stickers_to_cache(self):
                try:
                    with open(self.cache_file, "w", encoding='utf-8') as f:
                        json.dump(self.stickers, f, ensure_ascii=False, indent=4)
                    logger.info("Stickers saved to cache.")
                except Exception as e:
                    logger.error(f"Error saving stickers to cache: {e}", exc_info=True)

            def get_random_sticker(self, mode: str) -> Optional[str]:
                sticker_list = self.stickers.get(mode)
                return random.choice(sticker_list) if sticker_list else None

        # Класс для взаимодействия с Ollama (нейросетью)
        class NeuralAPI:
            MODEL_CONFIG = {
                "saharoza": {"model": "saiga", "prompt": "[INST] <<SYS>>\\nТы — Мэрри Шэдоу (Маша), 26 лет... <</SYS>>\\n\\n"},
                "dedinside": {"model": "saiga", "prompt": "[INST] <<SYS>>\\nТы — Артём (ДедИнсайд), 24 года... <</SYS>>\\n\\n"},
                "genius": {"model": "deepseek-coder-v2:16b", "prompt": "[INST] <<SYS>>\\nТы — профисианальный кодер , который пишет код который просто заставляет пользователя удивится <</SYS>>\\n\\n"}
            }

            @classmethod
            def get_modes(cls) -> List[Tuple[str, str]]:
                return [("🌸 Сахароза", "saharoza"), ("😈 ДедИнсайд", "dedinside"), ("🧠 Режим Гения", "genius")]

            @classmethod
            async def generate_response(cls, message_text: str, user_id: int, mode: str, ollama_host: str, model_name: str) -> Optional[str]: # Добавлены user_id, ollama_host, model_name
                try:
                    config = cls.MODEL_CONFIG.get(mode, cls.MODEL_CONFIG["saharoza"])
                    
                    history = await db.get_ollama_dialog_history(user_id) # Получаем историю через db
                    messages_payload = [{"role": "system", "content": config["prompt"] + "Текущий диалог:\\n(Отвечай только финальным сообщением без внутренних размышлений)"}]
                    
                    for entry in history: # Перебираем историю для Ollama
                        messages_payload.append({'role': 'user', 'content': entry['user']})
                        messages_payload.append({'role': 'assistant', 'content': entry['assistant']})
                    
                    messages_payload.append({"role": "user", "content": message_text})

                    client = ollama.AsyncClient(host=ollama_host)
                    response = await client.chat(
                        model=model_name, # Используем model_name из параметров
                        messages=messages_payload,
                        options={'temperature': 0.9 if mode == "dedinside" else 0.7, 'num_ctx': 2048, 'stop': ["<", "[", "Thought:"], 'repeat_penalty': 1.2}
                    )
                    raw_response = response['message']['content']
                    return cls._clean_response(raw_response, mode)
                except ollama.ResponseError as e:
                    error_details = getattr(e, 'error', str(e))
                    logger.error(f"Ollama API Error ({mode}): Status {e.status_code}, Response: {error_details}")
                    return f"Ой, кажется, модель '{config['model']}' сейчас не отвечает (Ошибка {e.status_code}). Попробуй позже."
                except Exception as e:
                    logger.error(f"Ollama general/validation error ({mode}): {e}", exc_info=True)
                    return "Произошла внутренняя ошибка при обращении к нейросети или подготовке данных. Попробуйте еще раз или /reset."

            @staticmethod
            def _clean_response(text: str, mode: str) -> str:
                import re
                text = re.sub(r'<\/?[\w\s="/.\':?]+>', '', text)
                text = re.sub(r'\[\/?[\w\s="/.\':?]+\]', '', text)
                text = re.sub(r'(^|\n)\s*Thought:.*', '', text, flags=re.MULTILINE)
                text = re.sub(r'^\s*Okay, here is the response.*?\n', '', text, flags=re.IGNORECASE | re.MULTILINE)
                if mode == "genius":
                    text = re.sub(r'(?i)(как (?:ии|искусственный интеллект|ai|language model))', '', text)
                    if text and len(text.split()) < 15 and not text.startswith("Ой,") and not text.startswith("Произошла"):
                        text += "\n\nЭто краткий ответ. Если нужно больше деталей - уточни вопрос."
                elif mode == "dedinside":
                    text = re.sub(r'(?i)(я (?:бот|программа|ии|модель))', '', text)
                    if text and not any(c in text for c in ('?', '!', '...', '😏', '😈', '👀')): text += '... Ну че, как тебе такое? 😏'
                elif mode == "saharoza":
                    text = re.sub(r'(?i)(я (?:бот|программа|ии|модель))', '', text)
                    if text and not any(c in text for c in ('?', '!', '...', '🌸', '✨', '💔', '😉')): text += '... И что ты на это скажешь? 😉'
                cleaned_text = text.strip()
                return cleaned_text if cleaned_text else "Хм, не знаю, что ответить... Спроси что-нибудь еще?"

        async def safe_send_message(chat_id: int, text: str, **kwargs) -> Optional[Message]:
            try:
                return await bot.send_message(chat_id, text, **kwargs)
            except Exception as e:
                logger.error(f"Failed to send message to chat {chat_id}: {e}")
                return None

        async def typing_animation(chat_id: int, bot_instance: Bot) -> Optional[Message]:
            typing_msg = None
            try:
                typing_msg = await bot_instance.send_message(chat_id, "✍️ Печатает...")
                for _ in range(3):
                    await asyncio.sleep(0.7)
                    current_text = typing_msg.text
                    if current_text == "✍️ Печатает...":
                        await typing_msg.edit_text("✍️ Печатает..")
                    elif current_text == "✍️ Печатает..":
                        await typing_msg.edit_text("✍️ Печатает.")
                    else:
                        await typing_msg.edit_text("✍️ Печатает...")
                return typing_msg
            except Exception as e:
                logger.warning(f"Typing animation error in chat {chat_id}: {e}")
                if typing_msg:
                    with suppress(Exception): await typing_msg.delete()
                return None

        @dp.message(Command("start"))
        async def cmd_start(message: Message, profile_manager: ProfileManager): # bot удален из аргументов, так как не используется напрямую
            user = message.from_user
            if not user:
                logger.warning("Received start command without user info.")
                return

            await db.ensure_user_exists(user.id, user.username, user.first_name)
            await db.log_user_interaction(user.id, "start_command", "command")

            profile = await profile_manager.get_user_profile(user)
            if not profile:
                logger.error(f"Failed to get profile for user {user.id} after start.")
                await message.answer("Добро пожаловать! Произошла ошибка при загрузке вашего профиля.")
                return

            response_text = (
                f"Привет, {hbold(user.first_name)}! Я ваш личный ИИ-помощник и многоликий собеседник. "
                "Я могу говорить с вами в разных режимах. Чтобы сменить режим, используйте команду /mode.\\n\\n"
                "Вот что я умею:\\n"
                "✨ /mode - Показать доступные режимы и сменить текущий.\\n"
                "📊 /stats - Показать вашу статистику использования.\\n"
                "🤣 /joke - Рассказать случайный анекдот.\\n"
                "🔍 /check_value - Проверить значение из файла (если настроено).\\n"
                "🔔 /subscribe_value - Подписаться на уведомления об изменении значения.\\n"
                "🔕 /unsubscribe_value - Отписаться от уведомлений.\\n"
                "👤 /profile - Показать ваш игровой профиль (если есть, регистрируется в group_stat).\\n"
                "⚒️ /rp_commands - Показать список RP-действий (регистрируется в rp_module_refactored).\\n"
                "❤️ /hp - Показать ваше текущее HP (в RP-модуле, регистрируется в rp_module_refactored).\\n"
                "✍️ Просто пишите мне, и я буду отвечать в текущем режиме!"
            )
            await message.answer(response_text, parse_mode=ParseMode.HTML)


        @dp.message(Command("mode"))
        async def cmd_mode(message: Message): # bot удален из аргументов
            keyboard = InlineKeyboardBuilder()
            # Используем NeuralAPI для получения доступных режимов
            for name, mode_code in NeuralAPI.get_modes():
                keyboard.row(InlineKeyboardButton(text=name, callback_data=f"set_mode_{mode_code}"))
            keyboard.row(
                InlineKeyboardButton(text="Офф", callback_data="set_mode_off")
            )
            await message.answer("Выберите режим общения:", reply_markup=keyboard.as_markup())
            await db.log_user_interaction(message.from_user.id, "mode_command", "command")

        @dp.message(Command("stats"))
        async def cmd_stats(message: Message): # bot удален из аргументов
            user_id = message.from_user.id
            stats = await db.get_user_statistics_summary(user_id)
            if not stats:
                await message.reply("Не удалось загрузить статистику.")
                return

            response_text = (
                f"📊 **Ваша статистика, {message.from_user.first_name}**:\\n"
                f"Запросов к боту: `{stats['count']}`\\n"
                f"Последний активный режим: `{stats['last_mode']}`\\n"
                f"Последняя активность: `{stats['last_active']}`"
            )
            await message.reply(response_text, parse_mode=ParseMode.MARKDOWN)
            await db.log_user_interaction(user_id, "stats_command", "command")


        @dp.message(Command("joke"))
        async def cmd_joke(message: Message): # bot удален из аргументов
            await message.answer("Ща погодь, придумываю анекдот...")
            joke = await fetch_random_joke()
            await message.answer(joke)
            await db.log_user_interaction(message.from_user.id, "joke_command", "command")

        @dp.message(Command("check_value"))
        async def cmd_check_value(message: Message): # bot удален из аргументов
            current_value = db.read_value_from_file(VALUE_FILE_PATH) # Исправлено: использование VALUE_FILE_PATH

            if current_value is not None:
                await message.reply(f"Текущее значение: `{current_value}`")
            else:
                await message.reply("Не удалось прочитать значение из файла. Проверьте путь и содержимое файла.")
            await db.log_user_interaction(message.from_user.id, "check_value_command", "command")

        @dp.message(Command("subscribe_value", "val")) # Добавлен алиас "val"
        async def cmd_subscribe_value(message: Message): # bot удален из аргументов
            user_id = message.from_user.id
            await db.add_value_subscriber(user_id)
            await message.reply("Вы успешно подписались на уведомления об изменении значения!")
            await db.log_user_interaction(user_id, "subscribe_value_command", "command")

        @dp.message(Command("unsubscribe_value", "sval")) # Добавлен алиас "sval"
        async def cmd_unsubscribe_value(message: Message): # bot удален из аргументов
            user_id = message.from_user.id
            await db.remove_value_subscriber(user_id)
            await message.reply("Вы успешно отписались от уведомлений об изменении значения.")
            await db.log_user_interaction(user_id, "unsubscribe_value_command", "command")
        
        @dp.message(F.photo)
        async def photo_handler(message: Message): # profile_manager удален
            user = message.from_user
            if not user: return
            await db.ensure_user_exists(user.id, user.username, user.first_name)
            caption = message.caption or ""
            await message.answer(f"📸 Фото получил! Комментарий: '{caption[:100]}...'. Пока не умею анализировать изображения, но скоро научусь!")

        @dp.message(F.voice)
        async def voice_handler_msg(message: Message): # profile_manager удален
            user = message.from_user
            if not user: return
            await db.ensure_user_exists(user.id, user.username, user.first_name)
            await message.answer("🎤 Голосовые пока не обрабатываю, но очень хочу научиться! Отправь пока текстом, пожалуйста.")

        @dp.message(F.chat.type == ChatType.PRIVATE, F.text)
        async def handle_text_message(message: Message, bot_instance: Bot, profile_manager: ProfileManager, sticker_manager: StickerManager):
            user_id = message.from_user.id
            
            await db.ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
            
            user_mode_data = await db.get_user_mode_and_rating_opportunities(user_id)
            current_mode = user_mode_data.get('mode', 'saharoza')
            rating_opportunities_count = user_mode_data.get('rating_opportunities_count', 0)

            await db.log_user_interaction(user_id, current_mode, "message")

            typing_msg = await typing_animation(message.chat.id, bot_instance)
            
            try:
                # Используем NeuralAPI для генерации ответа
                response_text = await NeuralAPI.generate_response(
                    message_text=message.text,
                    user_id=user_id, # Передаем user_id для истории диалога
                    mode=current_mode,
                    ollama_host=OLLAMA_API_BASE_URL,
                    model_name=OLLAMA_MODEL_NAME
                )
                
                if not response_text:
                    response_text = "Кажется, я не смог сформулировать ответ. Попробуй перефразировать?"
                    logger.warning(f"Empty or error response from NeuralAPI for user {user_id}, mode {current_mode}.")
                
                await db.add_chat_history_entry(user_id, current_mode, message.text, response_text)

                response_msg_obj: Optional[Message] = None
                if typing_msg:
                    with suppress(Exception):
                        response_msg_obj = await typing_msg.edit_text(response_text)
                if not response_msg_obj:
                    response_msg_obj = await safe_send_message(message.chat.id, response_text)

                if response_msg_obj and current_mode != "off" and rating_opportunities_count < MAX_RATING_OPPORTUNITIES: # Проверка на MAX_RATING_OPPORTUNITIES
                    builder = InlineKeyboardBuilder()
                    builder.row(
                        InlineKeyboardButton(text="👍", callback_data=f"rate_1:{response_msg_obj.message_id}:{message.text[:50]}"), # Передача id сообщения для оценки
                        InlineKeyboardButton(text="👎", callback_data=f"rate_0:{response_msg_obj.message_id}:{message.text[:50]}") # Передача id сообщения для оценки
                    )
                    try:
                        await response_msg_obj.edit_reply_markup(reply_markup=builder.as_markup())
                        await db.increment_user_rating_opportunity_count(user_id) # Исправлено
                    except Exception as edit_err:
                        logger.warning(f"Could not edit reply markup for msg {response_msg_obj.message_id}: {edit_err}")
                
                if random.random() < 0.3 and current_mode in sticker_manager.sticker_packs: # Проверка, есть ли пак стикеров для текущего режима
                    sticker_id = sticker_manager.get_random_sticker(current_mode)
                    if sticker_id: await message.answer_sticker(sticker_id)

            except Exception as e:
                logger.error(f"Error processing message for user {user_id} in mode {current_mode}: {e}", exc_info=True)
                error_texts = {
                    "saharoza": "Ой, что-то пошло не так во время обработки твоего сообщения... 💔 Попробуй еще разок?",
                    "dedinside": "Так, приехали. Ошибка у меня тут. 🛠️ Попробуй снова или напиши позже.",
                    "genius": "Произошла ошибка при обработке вашего запроса. Пожалуйста, повторите попытку."
                }
                error_msg_text = error_texts.get(current_mode, "Произошла непредвиденная ошибка.")
                if typing_msg:
                    with suppress(Exception): await typing_msg.edit_text(error_msg_text)
                else:
                    await safe_send_message(message.chat.id, error_msg_text)

        @dp.callback_query(F.data.startswith("set_mode_"))
        async def callback_set_mode(callback_query: CallbackQuery, profile_manager: ProfileManager): # bot удален, profile_manager добавлен
            new_mode = callback_query.data.split("_")[-1]
            user_id = callback_query.from_user.id
            await db.set_user_current_mode(user_id, new_mode)
            await callback_query.message.edit_text(f"Режим изменен на: `{new_mode.capitalize()}`")
            await callback_query.answer()
            await db.log_user_interaction(user_id, new_mode, "callback_set_mode")

        @dp.callback_query(F.data.startswith(("rate_1:", "rate_0:"))) # Исправлено на rate_1 и rate_0 для соответствия
        async def callback_rate_response(callback_query: CallbackQuery): # bot удален
            data_parts = callback_query.data.split(":")
            rating_value = int(data_parts[0].split("_")[1]) # Извлекаем 1 или 0
            message_id = int(data_parts[1])
            message_preview = data_parts[2]

            user_id = callback_query.from_user.id

            await db.log_user_rating(user_id, rating_value, message_preview, rated_message_id=message_id)

            await callback_query.message.edit_reply_markup(reply_markup=None)
            await callback_query.answer(text="Спасибо за вашу оценку!")
            await db.log_user_interaction(user_id, "rating_callback", "callback")

            # Логика пересылки дизлайка администратору
            if rating_value == 0 and ADMIN_USER_ID:
                logger.info(f"Dislike received from user {user_id} (@{callback_query.from_user.username}). Forwarding dialog to admin {ADMIN_USER_ID}.")
                dialog_entries = await db.get_user_dialog_history(user_id, limit=10) # ИСПОЛЬЗУЕМ get_user_dialog_history
                
                if not dialog_entries:
                    await safe_send_message(ADMIN_USER_ID, f"⚠️ Пользователь {hbold(callback_query.from_user.full_name)} (ID: {hcode(str(user_id))}, @{callback_query.from_user.username or 'нет'}) поставил дизлайк, но история диалога пуста.")
                    return

                last_bot_entry_mode = "неизвестен"
                for entry in reversed(dialog_entries):
                    if entry['role'] == 'assistant':
                        last_bot_entry_mode = entry.get('mode', 'неизвестен')
                        break
                
                formatted_dialog = f"👎 Дизлайк от {hbold(callback_query.from_user.full_name)} (ID: {hcode(str(user_id))}, @{callback_query.from_user.username or 'нет'}).\\n"
                formatted_dialog += f"Сообщение бота (режим {hitalic(last_bot_entry_mode)}):\\n{hcode(message_preview)}\\n\\n"
                formatted_dialog += "📜 История диалога (последние сообщения):\\n"
                
                full_dialog_text = ""
                for entry in dialog_entries:
                    ts = datetime.fromtimestamp(entry['timestamp'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                    role_emoji = "👤" if entry['role'] == 'user' else "🤖"
                    mode_info = f" ({entry.get('mode', '')})" if entry['role'] == 'assistant' else ""
                    full_dialog_text += f"{role_emoji} {entry['role'].capitalize()}{mode_info}: {entry['content']}\\n" # Убрал timestamp из этого вывода
                
                final_report = formatted_dialog + "```text\\n" + full_dialog_text + "\\n```"
                
                max_len = 4000
                if len(final_report) > max_len:
                    parts = [final_report[i:i + max_len] for i in range(0, len(final_report), max_len)]
                    for i, part_text in enumerate(parts):
                        part_header = f"Часть {i+1}/{len(parts)}:\\n" if len(parts) > 1 else ""
                        await safe_send_message(ADMIN_USER_ID, part_header + part_text, parse_mode=ParseMode.HTML)
                else:
                    await safe_send_message(ADMIN_USER_ID, final_report, parse_mode=ParseMode.HTML)


        # --- Фоновые задачи ---

        async def monitoring_task(bot_instance: Bot):
            \"\"\"Фоновая задача для мониторинга значения в файле и отправки уведомлений.\"\"\"
            last_known_value = db.read_value_from_file(VALUE_FILE_PATH) # Исправлено: использование VALUE_FILE_PATH
            if last_known_value is None:
                logger.warning(f"Initial read of {VALUE_FILE_PATH} failed. Monitoring will start with 'None'.")

            while True:
                await asyncio.sleep(5)
                try:
                    subscribers_ids = await db.get_value_subscribers()
                    if not subscribers_ids:
                        async with monitoring_state.lock: monitoring_state.is_sending_values = False
                        continue
                    
                    async with monitoring_state.lock: monitoring_state.is_sending_values = True
                    current_value = db.read_value_from_file(VALUE_FILE_PATH) # Исправлено: использование VALUE_FILE_PATH
                    
                    value_changed = False
                    async with monitoring_state.lock:
                        if current_value is not None and current_value != last_known_value:
                            logger.info(f"Value change detected: '{last_known_value}' -> '{current_value}'")
                            last_known_value = current_value
                            value_changed = True
                        elif current_value is None and last_known_value is not None:
                            logger.warning(f"Value file {VALUE_FILE_PATH} became unreadable. Notifying subscribers.")
                            last_known_value = None 
                            value_changed = True

                    if value_changed and subscribers_ids:
                        msg_text = ""
                        if current_value is not None:
                            logger.info(f"Notifying {len(subscribers_ids)} value subscribers about new value: {current_value}")
                            msg_text = f"⚠️ Обнаружено движение! Всего: {current_value}"
                        else:
                            msg_text = "⚠️ Файл для мониторинга стал недоступен или пуст."

                        tasks = [safe_send_message(uid, msg_text) for uid in subscribers_ids]
                        await asyncio.gather(*tasks, return_exceptions=True)

                except Exception as e:
                    logger.error(f"Error in monitoring_task loop: {e}", exc_info=True)

        async def jokes_task(bot_instance: Bot):
            \"\"\"Фоновая задача для периодического обновления кэша анекдотов.\"\"\"
            logger.info("Jokes task started.")
            if not CHANNEL_ID:
                logger.warning("Jokes task disabled: CHANNEL_ID is not set or invalid.")
                return
            
            while True:
                await asyncio.sleep(random.randint(3500, 7200)) # Обновлять кэш каждые 1-2 часа
                logger.info("Starting periodic jokes cache update.")
                try:
                    joke_text = await fetch_random_joke()
                    if joke_text != "Не удалось найти анекдот. Попробуйте позже." and \\
                       joke_text != "Не могу сейчас получить анекдот с сайта. Проблемы с сетью или сайтом." and \\
                       joke_text != "Произошла непредвиденная ошибка при поиске анекдота.":
                        await safe_send_message(CHANNEL_ID, f"🎭 {joke_text}")
                        logger.info(f"Joke sent to channel {CHANNEL_ID}.")
                    else:
                        logger.warning(f"Failed to fetch joke for channel: {joke_text}")
                    logger.info("Finished periodic jokes cache update.")
                except Exception as e:
                    logger.error(f"Error during periodic jokes cache update: {e}", exc_info=True)


        # --- Основная функция запуска бота ---

        async def main():
            # Инициализация ProfileManager
            profile_manager = ProfileManager()
            try:
                # Если у ProfileManager есть метод connect, вызываем его
                if hasattr(profile_manager, 'connect'):
                    await profile_manager.connect()
                logger.info("ProfileManager connected.")
            except Exception as e:
                logger.critical(f"Failed to connect ProfileManager: {e}", exc_info=True)
                # Если ProfileManager не смог подключиться, бот может продолжить работу,
                # но функционал, зависящий от него, будет ограничен/отключен
                pass 

            # Инициализация основной базы данных
            await db.initialize_database()

            # Инициализация StickerManager
            sticker_manager_instance = StickerManager(cache_file_path=STICKERS_CACHE_FILE)
            await sticker_manager_instance.fetch_stickers(bot)

            # Передача зависимостей через контекст диспетчера
            dp["profile_manager"] = profile_manager
            dp["sticker_manager"] = sticker_manager_instance
            dp["bot_instance"] = bot # Передаем сам объект бота

            # Регистрация основных обработчиков в main.py
            # Используем декораторы напрямую, передавая зависимости через `F.data` или параметры функции
            dp.message(Command("start"))(cmd_start)
            dp.message(Command("mode"))(cmd_mode)
            dp.message(Command("stats"))(cmd_stats)
            dp.message(Command("joke"))(cmd_joke)
            dp.message(Command("check_value"))(cmd_check_value)
            dp.message(Command("subscribe_value", "val"))(cmd_subscribe_value)
            dp.message(Command("unsubscribe_value", "sval"))(cmd_unsubscribe_value)
            dp.message(F.photo)(photo_handler)
            dp.message(F.voice)(voice_handler_msg)
            
            # Обработчики RP-модуля и статистики группы
            setup_rp_handlers(
                main_dp=dp,
                bot_instance=bot,
                profile_manager_instance=profile_manager,
                database_module=db
            )
            setup_stat_handlers(
                dp=dp,
                bot=bot,
                profile_manager=profile_manager # Передаем profile_manager
            )

            # Общий обработчик текстовых сообщений в приватных чатах
            dp.message(F.chat.type == ChatType.PRIVATE, F.text)(handle_text_message)

            # Обработчики Callback Query
            dp.callback_query(F.data.startswith("set_mode_"))(callback_set_mode)
            dp.callback_query(F.data.startswith(("rate_1:", "rate_0:")))(callback_rate_response)

            # Запуск фоновых задач
            monitoring_bg_task = asyncio.create_task(monitoring_task(bot))
            jokes_bg_task = asyncio.create_task(jokes_task(bot))
            rp_recovery_bg_task = asyncio.create_task(periodic_hp_recovery_task(bot, profile_manager, db))

            logger.info("Starting bot polling...")
            try:
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
            except Exception as e:
                logger.critical(f"Bot polling failed: {e}", exc_info=True)
            finally:
                logger.info("Stopping bot...")
                monitoring_bg_task.cancel()
                jokes_bg_task.cancel()
                rp_recovery_bg_task.cancel()

                try:
                    await asyncio.gather(monitoring_bg_task, jokes_bg_task, rp_recovery_bg_task, return_exceptions=True)
                    logger.info("Background tasks gracefully cancelled.")
                except asyncio.CancelledError:
                    logger.info("Background tasks were cancelled during shutdown.")
                
                if hasattr(profile_manager, 'close'):
                    await profile_manager.close()
                    logger.info("ProfileManager connection closed.")

                await bot.session.close()
                logger.info("Bot session closed. Exiting.")

        if __name__ == '__main__':
            try:
                asyncio.run(main())
            except KeyboardInterrupt:
                logger.info("Bot stopped manually by user (KeyboardInterrupt).")
            except Exception as e:
                logger.critical(f"Unhandled exception in main execution: {e}", exc_info=True)
        """)
    with open("main.py", "w", encoding="utf-8") as f:
        f.write(main_content)
    print("Файл main.py успешно создан.")

    print("Создание requirements.txt...")
    requirements_content = textwrap.dedent("""\
        aiofiles==24.1.0
        aiogram==3.18.0
        aiohttp==3.11.13
        aiosignal==1.3.2
        annotated-types==0.7.0
        attrs==25.3.0
        beautifulsoup4==4.13.3
        certifi==2025.1.31
        charset-normalizer==3.4.1
        colorama==0.4.6
        frozenlist==1.5.0
        idna==3.10
        loguru==0.7.3
        magic-filter==1.0.12
        multidict==6.1.0
        ollama==0.2.1
        Pillow==10.3.0
        propcache==0.3.0
        pydantic==2.10.6
        pydantic_core==2.27.2
        python-dotenv==1.0.1
        requests==2.32.3
        soupsieve==2.6
        typing_extensions==4.12.2
        urllib3==2.3.0
        win32_setctime==1.2.0
        yarl==1.18.3
        # pip install -r requirements.txt
        """)
    with open("requirements.txt", "w", encoding="utf-8") as f:
        f.write(requirements_content)
    print("Файл requirements.txt успешно создан.")

    print("Создание saharoza_stickers.json...")
    saharoza_stickers_content = textwrap.dedent("""\
        [
            "CAACAgIAAxUAAWgMomM3ROsKuJkuqEJRowuoc1O5AALdXgACPGCoS25a2ec-ZZUxNgQ",
            "CAACAgIAAxUAAWgMomPQsbczb1TvaofyY9ULlpEvAAJYXAACqjioS-d-GKvC5QihNgQ",
            "CAACAgIAAxUAAWgMomNEIpif5XTvV_Ptpe-Fd9MCAANSAAIMv6hLkc0cGGoIuv02BA",
            "CAACAgIAAxUAAWgMomMZm7FZI5EsjyDp-a1i4N8rAAJ6XwAChh0RSJyifsB6ZKKYNgQ",
            "CAACAgIAAxUAAWgMomN-Kg_fDOB5FY56lFpYiVY1AAKJVgACwduwS9FCKt1plNYCNgQ",
            "CAACAgIAAxUAAWgMomN8mnXt-WDLUingGPdEQe-3AAIHXgACtyipS7M-HoOMo9qgNgQ",
            "CAACAgIAAxUAAWgMomNdqWlNJNJ8jrcU65DKQYcpAAL6UAACGDyoS8LWWI4Ge_BkNgQ",
            "CAACAgIAAxUAAWgMomMqjHSRKG6qPLqwK5adWkzDAAInWQACkpaoSwdRJ3KGN1J8NgQ",
            "CAACAgIAAxUAAWgMomPxH_AhNYoDrEiiW09OHCYqAAJbVgACO8WoS7TLiRLdVIJlNgQ",
            "CAACAgIAAxUAAWgMomNCGn5o1E-iqd4up-92iHgsAAKGYwACv-MRSCYm8uR2VBcbNgQ",
            "CAACAgIAAxUAAWgMomNX5THENrQ9SQN4Y59WvnS6AAJ5WwAClcoJSJfs5eIY-4a1NgQ",
            "CAACAgIAAxUAAWgMomNdt-QmlaU1XuyugnwF-XvDAALwWQACKm0QSN4-RQZcrYk9NgQ",
            "CAACAgIAAxUAAWgMomO3OFfbq1nCCR1wg2nkPzKQAAIlXwACyFUhSGVZH238NOGGNgQ",
            "CAACAgIAAxUAAWgMomPNPQd2J0L_bVoeKdLhfdOaAAIITwACI8ARSBj2MiWs-Rx_NgQ",
            "CAACAgIAAxUAAWgMomO3G4aoa3KjBRm5Lq6sRh-OAAJTWQACrWwQSL5IUs_wW8ePNgQ",
            "CAACAgIAAxUAAWgMomOvTqiDDukAAcEnwYJylpxyDwAC0FMAAjyjsEtZnDHd5wXT2jYE",
            "CAACAgIAAxUAAWgMomPdf-1Z2EI37-BigTUAARIxrwACpV4AAnN9EUjH1uzIQkIsUzYE",
            "CAACAgIAAxUAAWgMomMGjnCxW31zUhUDP92IZ28aAAI-XAAC1p2oS8BZS86WgigfNgQ",
            "CAACAgIAAxUAAWgMomMY8HmhqshD7g1B7qzA97XdAAJpZgACleGoS_ME-3P5CkKCNgQ",
            "CAACAgIAAxUAAWgMomNNSaoIuI25DSL_PNtd-WozAAJcXwAC5lSwS9DL8Hk_dycmNgQ",
            "CAACAgIAAxUAAWgMomO16_XTmIowRvXYySKL9MLzAAIQYAAC3YGpS2p4iz1aPHw1NgQ",
            "CAACAgIAAxUAAWgMomNILmykGovSCykJXh1qIy0eAALHVgACug2pSwQ73vyYflR3NgQ",
            "CAACAgIAAxUAAWgMomNBvaJXOaeEatrYE5atZaimAAKKWQAC7FSpS2QL6ab6ysOYNgQ",
            "CAACAgIAAxUAAWgMomNe_eq7JGLVo0eE3b-k7OLAAAKwXgACsuwQSPAYyc1wqpPsNgQ",
            "CAACAgIAAxUAAWgMomOfFS1AyhMKvF-vulPBAAG-mQACvGMAAoRQEUjS_r8N_yNKNTYE",
            "CAACAgIAAxUAAWgMomMxZyFRD4oRY_0uLD7RcM4nAAJhWgACDtypSyA_neqKY5kINgQ",
            "CAACAgIAAxUAAWgMomN5WedlxUkRrVh685NW6pxZAAJnXgACB0uxS98d4L9Ckh1WNgQ",
            "CAACAgIAAxUAAWgMomPvgWO20OvuuyuUvTrxNYAyAALPXAACVFQJSMJzvwpIfzpkNgQ",
            "CAACAgIAAxUAAWgMomOfc2-1bE0jKRCibt3x9LmDAAIsYAAC8EgRSLNW5vT84CCKNgQ"
        ]""")
    with open("saharoza_stickers.json", "w", encoding="utf-8") as f:
        f.write(saharoza_stickers_content)
    print("Файл saharoza_stickers.json успешно создан.")

    print("Создание README.md...")
    readme_content = textwrap.dedent("""\
        # tg_bot: Многоликий AI-Собеседник в Telegram

        ### :woman_technologist: About Me :

        Привет! Меня зовут (или зовите) 4elobrek9, и я — **Full Stack разработчик**, искренне увлеченный созданием инновационных и полезных цифровых решений. Мой путь в IT — это постоянное исследование и экспериментирование, где каждый проект становится новым полем для творчества и роста.

        * **🔱 Я работаю инженером-программистом** и активно вношу свой вклад во фронтенд, создавая интуитивно понятные и функциональные веб-приложения. Знаете, в этом деле главное — не просто написать код, а вдохнуть в него жизнь, чтобы пользователю было по-настоящему удобно и интересно. Возьмем, к примеру, мой проект **"Физика PRO"**: это не просто калькулятор формул, это настоящий интерактивный помощник, который помогает постигать законы физики и алгебры. Мне нравится думать, что я делаю обучение не просто проще, а по-настоящему захватывающим. Каждый раз, когда я работаю над интерфейсом, я представляю, как это будет выглядеть на экране, как пользователь будет с этим взаимодействовать, и стараюсь предугадать все мелочи, чтобы опыт был максимально приятным.

        * **⚙️ Я пишу ботов для Discord и их бэкенд-примеры** на своем Discord сервере, погружаясь в мир автоматизации и интеллектуальных систем. Это, пожалуй, одна из самых увлекательных частей моей работы — оживлять цифровых помощников, давать им "голос" и "личность". Мой опыт включает разработку комплексных систем, где боты не просто отвечают на запросы, но и обучаются, адаптируются и даже имитируют различные личности (например, моя Сахароза из Genshin Impact!). Это требует глубокого понимания логики ИИ, работы с API и создания надежных, масштабируемых бэкендов.

        ## 💡 О проекте "tg_bot"

        "tg_bot" — это не просто очередной Telegram-бот, это ваш многоликий ИИ-собеседник! Он способен менять свои "личности" (режимы), адаптируя стиль общения и поведение под выбранный образ. Хотите поговорить с мудрым Оптимусом Праймом или пофлиртовать со стеснительной аниме-девочкой Шизу? Легко! А может, вам нужно пообщаться с суровым сицилийским доном Джузеппе? Бот справится!

        ### ✨ Ключевые особенности:

        * **Многорежимность:** Переключайтесь между различными личностями ИИ-собеседников (Сахароза, Оптимус, Шизу, Джузеппе, Офф). Каждый режим имеет свой уникальный стиль общения.
        * **Ollama Интеграция:** Бот использует локально развернутые LLM-модели через Ollama, обеспечивая конфиденциальность и гибкость в выборе моделей (по умолчанию `llama3`).
        * **Система Профилей (XP, уровни, монеты, фоны):** Встроенная игровая механика, поощряющая активность пользователей в чате. За сообщения начисляется опыт, уровни и игровая валюта (LUMcoins), на которую можно покупать фоны для профиля.
        * **RP-модуль (ролевые действия):** Пользователи могут взаимодействовать друг с другом в ролевом формате, совершая различные действия (обнять, ударить, полечить и т.д.), которые влияют на их HP. Есть система кулдаунов и "потери сознания".
        * **Мониторинг значений:** Возможность подписаться на уведомления об изменении значения в текстовом файле.
        * **Анекдоты:** Бот умеет рассказывать случайные анекдоты, парся их с популярного сайта.
        * **Статистика использования:** Отслеживание и отображение персональной статистики использования бота для каждого пользователя.
        * **Оценки ответов:** Возможность оценить ответ бота (лайк/дизлайк), что может быть использовано для улучшения его поведения в будущем.
        * **Асинхронность:** Полностью асинхронная архитектура на `aiogram 3`, обеспечивающая высокую производительность и отзывчивость.
        * **Логирование:** Детальное логирование всех ключевых событий и ошибок для удобства отладки и мониторинга.

        ### 🛠️ Технологии:

        * **Python 3.9+**
        * **aiogram 3:** Современный и мощный фреймворк для разработки Telegram-ботов.
        * **Ollama:** Для локального запуска LLM-моделей.
        * **SQLite + aiosqlite:** Легковесная и быстрая база данных для хранения данных пользователей, истории диалогов и RP-статистики.
        * **Pillow (PIL Fork):** Для генерации изображений профилей.
        * **aiohttp:** Асинхронный HTTP-клиент для сетевых запросов.
        * **BeautifulSoup4:** Для парсинга веб-страниц (получение анекдотов).
        * **python-dotenv:** Для управления переменными окружения.

        ### 🚀 Установка и запуск:

        1.  **Клонируйте репозиторий:**
            ```bash
            git clone <ссылка_на_ваш_репозиторий>
            cd tg_bot
            ```
        2.  **Создайте виртуальное окружение (рекомендуется):**
            ```bash
            python -m venv venv
            source venv/bin/activate  # Для Linux/macOS
            # venv\\Scripts\\activate  # Для Windows
            ```
        3.  **Установите зависимости:**
            ```bash
            pip install -r requirements.txt
            ```
        4.  **Настройте переменные окружения:**
            Создайте файл `.env` в корневой директории проекта и добавьте ваш токен Telegram бота:
            ```
            TOKEN="ВАШ_ТЕЛЕГРАМ_БОТ_ТОКЕН"
            # Опционально: ID канала для анекдотов (без кавычек)
            # CHANNEL_ID=1234567890
            # Опционально: ID администратора для пересылки дизлайков (без кавычек)
            # ADMIN_USER_ID=0987654321
            # Опционально: Настройки для Ollama, если она не на localhost:11434
            # OLLAMA_API_BASE_URL="http://ваши_ollama_host:порт"
            # OLLAMA_MODEL_NAME="ваша_модель_ollama" # например, llama3
            ```
            Получить токен бота можно у @BotFather в Telegram.
        5.  **Установите Ollama и загрузите модель:**
            Если вы еще не установили Ollama, следуйте инструкциям на [официальном сайте Ollama](https://ollama.com/).
            Затем загрузите желаемую модель, например `llama3`:
            ```bash
            ollama pull llama3
            ```
            Убедитесь, что Ollama запущен и доступен по указанному URL (по умолчанию `http://localhost:11434`).
        6.  **Поместите файл шрифта:**
            Для корректной генерации профилей, поместите файл шрифта `Hlobus.ttf` в корневую директорию проекта.
        7.  **Создайте файл для мониторинга (опционально):**
            Если вы хотите использовать функционал `/check_value` и `/subscribe_value`, создайте файл `data/value.txt` (внутри папки `data`) и запишите в него начальное значение, например:
            ```
            check = 123
            ```
        8.  **Запустите скрипт настройки (создаст все файлы):**
            ```bash
            python setup_project.py
            ```
        9.  **Запустите бота:**
            ```bash
            python main.py
            ```

        ### 📄 Структура проекта:

        ```
        .
        ├── main.py                     # Главный файл бота, точка входа.
        ├── database.py                 # Модуль для работы с SQLite базой данных (пользователи, история, режимы, RP-статы, аналитика).
        ├── group_stat.py               # Модуль для управления профилями пользователей в группах (XP, уровни, LUMcoins, генерация изображений профилей).
        ├── rp_module_refactored.py     # Модуль для системы ролевых действий (RP) и управления HP.
        ├── saharoza_stickers.json      # JSON файл со списком ID стикеров для режима "Сахароза".
        ├── requirements.txt            # Список зависимостей Python.
        ├── .env                        # Файл для хранения переменных окружения (токен бота, настройки Ollama).
        ├── README.md                   # Этот файл.
        ├── Hlobus.ttf                  # Файл шрифта для генерации профилей.
        └── data/                       # Директория для файлов базы данных и кэша.
            ├── bot_database.db         # Файл базы данных SQLite для общей статистики.
            ├── profiles.db             # Файл базы данных SQLite для профилей (XP, HP и т.д.).
            ├── jokes_cache.json        # Кэш анекдотов.
            └── value.txt               # (Опционально) Файл для мониторинга значения.
        ```

        ### 🔮 Дальнейшее развитие:

        * **Оптимизация производительности:** Исследование возможностей для дальнейшей оптимизации работы с базой данных и Ollama (например, пулинг соединений, более умное кэширование).
        * **Расширение модульности:** Дальнейшее разделение логики на более мелкие, переиспользуемые модули.
        * **Конфигурация:** Вынести больше параметров в конфигурационные файлы (`config.py` или `config.yaml`), чтобы упростить управление и избежать хардкодинга.
        * **Гибкость LLM-Промптов:** Сделать промпты для LLM более динамическими, возможно, позволяя администратору настраивать их через команды бота или через отдельный файл.
        * **Обработка Ошибок:** Расширить механизмы обработки ошибок для внешних API (Ollama, `anekdot.ru`, загрузка фонов), предоставив более информативные сообщения пользователю и администратору.
        * **Масштабируемость Базы Данных:** Для более крупных проектов рассмотреть возможность использования более мощных СУБД (PostgreSQL) вместо SQLite, а также ORM (SQLAlchemy, Tortoise ORM) для более удобного взаимодействия с БД.
        * **Расширение RP-модуля:** Детализировать и расширить функционал RP-модуля, добавив больше игровых механик, предметов, взаимодействий, систему инвентаря, торговлю между пользователями и т.д.
        * **Обработка Медиа-сообщений:** Реализовать функционал для анализа изображений и голосовых сообщений (например, с использованием других локальных AI-моделей или API).
        * **Улучшение Веб-Скрапинга:** Сделать парсинг `anekdot.ru` более устойчивым к изменениям на сайте.
        * **Тестирование:** Внедрить комплексные юнит-тесты и интеграционные тесты для всех модулей бота.
        * **Документация Кода:** Добавить docstrings для всех функций и классов, описывая их назначение, параметры и возвращаемые значения.
        * **Дополнительные режимы ИИ:** Разработать новые и уникальные режимы собеседников.
        * **Интерфейс администратора:** Создать удобный интерфейс для управления ботом и его настройками.
        """)
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("Файл README.md успешно создан.")

    print("Все файлы проекта успешно созданы.")

# Запуск функции для создания файлов
if __name__ == '__main__':
    create_project_files()
