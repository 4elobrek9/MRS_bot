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
    """
    Инициализирует базу данных, создавая все необходимые таблицы и индексы,
    если они еще не существуют.

    Этот асинхронный метод устанавливает соединение с базой данных SQLite
    и выполняет SQL-скрипты для создания таблиц пользователей, подписок,
    истории диалогов, режимов пользователей, аналитики взаимодействий,
    рейтингов и статистики RP-пользователей.
    """
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
    """
    Гарантирует, что пользователь существует в базе данных, или обновляет его информацию.
    Также создает записи по умолчанию в user_modes и rp_user_stats, если их нет.

    Args:
        user_id (int): Уникальный идентификатор пользователя Telegram.
        username (Optional[str]): Имя пользователя Telegram (может быть None).
        first_name (str): Имя пользователя Telegram.
    """
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
    """
    Получает базовую информацию о пользователе из таблицы users.

    Args:
        user_id (int): Уникальный идентификатор пользователя.

    Returns:
        Optional[Dict[str, Any]]: Словарь с информацией о пользователе
                                (user_id, username, first_name, last_active)
                                или None, если пользователь не найден.
    """
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
    """
    Добавляет пользователя в список подписчиков для мониторинга значения.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT OR IGNORE INTO value_subscriptions (user_id, subscribed_ts) VALUES (?, ?)
        ''', (user_id, datetime.now().timestamp()))
        await db.commit()

async def remove_value_subscriber(user_id: int) -> None:
    """
    Удаляет пользователя из списка подписчиков для мониторинга значения.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('DELETE FROM value_subscriptions WHERE user_id = ?', (user_id,))
        await db.commit()

async def get_value_subscribers() -> List[int]:
    """
    Получает список ID всех пользователей, подписанных на мониторинг значения.

    Returns:
        List[int]: Список уникальных идентификаторов пользователей.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT user_id FROM value_subscriptions') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def check_value_subscriber_status(user_id: int) -> bool:
    """
    Проверяет, подписан ли пользователь на мониторинг значения.

    Args:
        user_id (int): Уникальный идентификатор пользователя.

    Returns:
        bool: True, если пользователь подписан, иначе False.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT 1 FROM value_subscriptions WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def add_chat_history_entry(user_id: int, mode: str, user_message_content: str, bot_response_content: str) -> None:
    """
    Добавляет записи в историю диалога для пользователя (сообщение пользователя и ответ бота).
    Ограничивает историю до последних 20 записей для каждого пользователя.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
        mode (str): Активный режим бота во время диалога.
        user_message_content (str): Текст сообщения от пользователя.
        bot_response_content (str): Текст ответа от бота.
    """
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
    """
    Получает историю диалога для заданного пользователя.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
        limit (int): Максимальное количество записей для извлечения.

    Returns:
        List[Dict[str, Any]]: Список словарей, где каждый словарь представляет
                              запись в истории диалога (роль, контент, режим, метка времени).
    """
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
    """
    Формирует историю диалога для использования с Ollama API.
    Обеспечивает корректное чередование ролей "user" и "assistant".

    Args:
        user_id (int): Уникальный идентификатор пользователя.
        limit_turns (int): Максимальное количество "ходов" (пар вопрос-ответ) для включения.

    Returns:
        List[Dict[str, str]]: Список словарей, отформатированных для Ollama,
                              например, [{"user": "...", "assistant": "..."}].
    """
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
    """
    Устанавливает текущий режим для пользователя.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
        mode (str): Название режима.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO user_modes (user_id, mode) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET mode = excluded.mode
        ''', (user_id, mode))
        await db.commit()

async def get_user_mode_and_rating_opportunities(user_id: int) -> Dict[str, Any]:
    """
    Получает текущий режим пользователя и количество оставшихся возможностей для оценки.

    Args:
        user_id (int): Уникальный идентификатор пользователя.

    Returns:
        Dict[str, Any]: Словарь с ключами 'mode' (текущий режим) и
                        'rating_opportunities_count' (количество оценок, уже сделанных).
    """
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
    """
    Увеличивает счетчик использованных возможностей для оценки для пользователя.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            UPDATE user_modes
            SET rating_opportunities_count = rating_opportunities_count + 1
            WHERE user_id = ?
        ''', (user_id,))
        await db.commit()

async def reset_user_rating_opportunity_count(user_id: int) -> None:
    """
    Сбрасывает счетчик использованных возможностей для оценки для пользователя до нуля.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('UPDATE user_modes SET rating_opportunities_count = 0 WHERE user_id = ?', (user_id,))
        await db.commit()

async def log_user_interaction(user_id: int, mode: str, action_type: str = "message") -> None:
    """
    Записывает взаимодействие пользователя с ботом для аналитики.
    Также обновляет метку времени последней активности пользователя.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
        mode (str): Режим бота, который был активен во время взаимодействия.
        action_type (str): Тип действия (например, 'message', 'command', 'callback').
    """
    current_timestamp = datetime.now().timestamp()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO analytics_interactions (user_id, timestamp, mode, action_type) VALUES (?, ?, ?, ?)
        ''', (user_id, current_timestamp, mode, action_type))
        await db.execute('UPDATE users SET last_active_ts = ? WHERE user_id = ?', (current_timestamp, user_id))
        await db.commit()

async def log_user_rating(user_id: int, rating: int, message_preview: str,
                           rated_message_id: Optional[int] = None, dialog_history_id: Optional[int] = None) -> None:
    """
    Записывает оценку пользователя в базу данных.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
        rating (int): Оценка (0 для дизлайка, 1 для лайка).
        message_preview (str): Краткий предпросмотр сообщения, к которому относится оценка.
        rated_message_id (Optional[int]): ID сообщения бота, которое было оценено (опционально).
        dialog_history_id (Optional[int]): ID записи в dialog_history, связанной с оценкой (опционально).
    """
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            INSERT INTO analytics_ratings (user_id, timestamp, rating, message_preview, rated_message_id, dialog_history_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, datetime.now().timestamp(), rating, message_preview[:500], rated_message_id, dialog_history_id))
        await db.commit()

async def get_user_statistics_summary(user_id: int) -> Dict[str, Any]:
    """
    Получает сводную статистику для пользователя.

    Args:
        user_id (int): Уникальный идентификатор пользователя.

    Returns:
        Dict[str, Any]: Словарь с количеством запросов, последним активным режимом и временем последней активности.
    """
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
    """
    Получает RP-статистику пользователя (HP, таймеры кулдаунов).

    Args:
        user_id (int): Уникальный идентификатор пользователя.

    Returns:
        Dict[str, Any]: Словарь с HP, heal_cooldown_ts и recovery_end_ts.
                        Возвращает значения по умолчанию, если запись не найдена,
                        и логирует ошибку.
    """
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
    """
    Обновляет указанные поля RP-статистики для пользователя.

    Args:
        user_id (int): Уникальный идентификатор пользователя.
        **kwargs: Пары ключ=значение для обновления (например, hp=120, heal_cooldown_ts=...).
    """
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
    """
    Читает значение из текстового файла, ища строку "check = <value>".

    Args:
        file_path (Path): Путь к файлу.

    Returns:
        Optional[str]: Извлеченное значение или None, если файл не найден,
                       произошла ошибка или значение не найдено.
    """
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
    """
    Получает список пользователей, чье HP равно или ниже указанного уровня
    и чей таймер восстановления истек.

    Args:
        current_timestamp (float): Текущая метка времени для сравнения с recovery_end_ts.
        min_hp_level_inclusive (int): Максимальный уровень HP (включительно), при котором
                                      пользователь нуждается в восстановлении.

    Returns:
        List[Tuple[int, int]]: Список кортежей, где каждый кортеж содержит (user_id, current_hp).
    """
    query = """
        SELECT user_id, hp
        FROM rp_user_stats
        WHERE hp <= ? AND recovery_end_ts > 0 AND recovery_end_ts <= ?
    """
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(query, (min_hp_level_inclusive, current_timestamp)) as cursor:
            rows = await cursor.fetchall()
            return [(row[0], row[1]) for row in rows]
