from core.group.stat.smain import *
from core.group.stat.config import ProfileConfig
# from core.group.stat.manager import * # Циклический импорт
# from group_stat import * # Циклический импорт

# Прямые импорты, чтобы избежать цикличности
# Удален get_user_profile_info, так как ProfileManager теперь сам получает данные профиля
from database import get_user_rp_stats, add_item_to_inventory, get_user_inventory, set_user_active_background 
import aiosqlite
from PIL import Image, ImageDraw, ImageFont, ImageOps
import aiohttp
from io import BytesIO
from aiogram import types, Bot
from typing import Optional, Dict, Any, List
import logging
import os
import sqlite3 # Импортируем для синхронной инициализации
from pathlib import Path # Импортируем Path для работы с путями к файлам

# Импорт ShopConfig для доступа к товарам магазина
from core.group.stat.shop_config import ShopConfig

logger = logging.getLogger(__name__)

class ProfileManager:
    def __init__(self):
        logger.info("ProfileManager instance initialized.")
        self._conn = None
        self.font_cache = {}

    async def connect(self):
        logger.debug("Attempting to connect to profiles database asynchronously.")
        if self._conn is not None:
            logger.warning("Profiles database connection already exists, skipping reconnection.")
            return
        try:
            self._conn = await aiosqlite.connect('profiles.db')
            logger.info("Profiles database connected asynchronously.")
            await self._init_db_async()
            logger.info("Asynchronous profiles database schema check/initialization completed.")
        except Exception as e:
            logger.critical(f"Failed to connect or initialize profiles database: {e}", exc_info=True)
            raise

    async def close(self):
        logger.debug("Attempting to close profiles database connection.")
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Profiles database connection closed.")

    async def _init_db_async(self):
        if self._conn is None: raise RuntimeError("DB not connected")
        await self._conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        await self._conn.execute('''
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
            last_work_time REAL DEFAULT 0,
            active_background TEXT DEFAULT 'default', -- Добавлено поле для активного фона
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        await self._conn.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)')
        await self._conn.commit()

    async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
        """
        Получает полную информацию о профиле пользователя из profiles.db.
        """
        if self._conn is None:
            logger.error("Profiles database connection is not established.")
            return None
        
        user_id = user.id
        cursor = await self._conn.execute('''
            SELECT 
                up.hp, up.level, up.exp, up.lumcoins, up.daily_messages, 
                up.total_messages, up.flames, up.last_work_time, up.active_background,
                u.username, u.first_name, u.last_name
            FROM user_profiles up
            JOIN users u ON up.user_id = u.user_id
            WHERE up.user_id = ?
        ''', (user_id,))
        
        row = await cursor.fetchone()
        if row:
            columns = [
                'hp', 'level', 'exp', 'lumcoins', 'daily_messages', 
                'total_messages', 'flames', 'last_work_time', 'active_background',
                'username', 'first_name', 'last_name'
            ]
            profile_data = dict(zip(columns, row))
            return profile_data
        return None

    async def record_message(self, user: types.User) -> None:
        if self._conn is None: raise RuntimeError("DB not connected")
        user_id = user.id
        current_time = time.time()

        # Ensure user exists in 'users' table in profiles.db
        await self._conn.execute(
            'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
            (user_id, user.username, user.first_name)
        )
        await self._conn.commit()

        # Get current profile data
        cursor = await self._conn.execute(
            'SELECT level, exp, lumcoins, daily_messages, total_messages FROM user_profiles WHERE user_id = ?',
            (user_id,)
        )
        profile_data = await cursor.fetchone()

        if profile_data:
            level, exp, lumcoins, daily_messages, total_messages = profile_data
            # Reset daily messages if new day
            # Note: last_active_ts is in the 'users' table of the main bot database,
            # but for profile stats, we should use a timestamp within profiles.db
            # For simplicity, we'll assume current_time comparison is sufficient for daily reset for now.
            # A more robust solution might involve storing last_daily_reset_date in user_profiles.
            
            # For now, let's just update based on message count and level up
            
            # Update stats
            exp += ProfileConfig.EXP_PER_MESSAGE_INTERVAL # Use correct constant
            total_messages += 1
            daily_messages += 1

            # Level up logic
            new_level = level
            while exp >= ProfileConfig.LEVEL_UP_EXP_REQUIREMENT(new_level):
                exp -= ProfileConfig.LEVEL_UP_EXP_REQUIREMENT(new_level)
                new_level += 1
                # Lumcoins awarded per level up, if defined in config
                lumcoins += ProfileConfig.LUMCOINS_PER_LEVEL.get(new_level, 0) # Get lumcoins for specific level, default 0
                logger.info(f"User {user_id} leveled up to {new_level}, earned {ProfileConfig.LUMCOINS_PER_LEVEL.get(new_level, 0)} Lumcoins.")


            await self._conn.execute(
                '''
                UPDATE user_profiles
                SET level = ?, exp = ?, lumcoins = ?, daily_messages = ?, total_messages = ?
                WHERE user_id = ?
                ''',
                (new_level, exp, lumcoins, daily_messages, total_messages, user_id)
            )
            # Update last_active_ts in the 'users' table of profiles.db as well
            await self._conn.execute(
                'UPDATE users SET last_active_ts = ? WHERE user_id = ?',
                (current_time, user_id)
            )
            await self._conn.commit()
            logger.debug(f"User {user_id} profile updated: level={new_level}, exp={exp}, lumcoins={lumcoins}.")
        else:
            # Insert new profile if not exists
            await self._conn.execute(
                '''
                INSERT INTO user_profiles (user_id, level, exp, lumcoins, daily_messages, total_messages, last_work_time, active_background)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (user_id, 1, ProfileConfig.EXP_PER_MESSAGE_INTERVAL, 0, 1, 1, 0, 'default') # Default active background
            )
            # Update last_active_ts in the 'users' table of profiles.db
            await self._conn.execute(
                'UPDATE users SET last_active_ts = ? WHERE user_id = ?',
                (current_time, user_id)
            )
            await self._conn.commit()
            logger.debug(f"New profile created for user {user_id}.")

    async def update_lumcoins(self, user_id: int, amount: int) -> None:
        if self._conn is None: raise RuntimeError("DB not connected")
        await self._conn.execute('UPDATE user_profiles SET lumcoins = lumcoins + ? WHERE user_id = ?', (amount, user_id))
        await self._conn.commit()
        logger.info(f"User {user_id} Lumcoins updated by {amount}.")

    async def get_lumcoins(self, user_id: int) -> int:
        if self._conn is None: raise RuntimeError("DB not connected")
        cursor = await self._conn.execute('SELECT lumcoins FROM user_profiles WHERE user_id = ?', (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

    async def set_user_background(self, user_id: int, background_key: str) -> None:
        """Устанавливает активный фон для пользователя и добавляет его в инвентарь."""
        if self._conn is None: raise RuntimeError("DB not connected")
        await self._conn.execute('UPDATE user_profiles SET active_background = ? WHERE user_id = ?', (background_key, user_id))
        await self._conn.commit()
        await add_item_to_inventory(user_id, background_key, 'background') # Добавляем в инвентарь при покупке
        logger.info(f"User {user_id} active background set to '{background_key}' and added to inventory.")

    async def get_last_work_time(self, user_id: int) -> float:
        if self._conn is None: raise RuntimeError("DB not connected")
        cursor = await self._conn.execute('SELECT last_work_time FROM user_profiles WHERE user_id = ?', (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0.0

    async def update_last_work_time(self, user_id: int, timestamp: float):
        if self._conn is None: raise RuntimeError("DB not connected")
        await self._conn.execute('UPDATE user_profiles SET last_work_time = ? WHERE user_id = ?', (timestamp, user_id))
        await self._conn.commit()

    async def get_top_users_by_level(self, limit: int = 10) -> List[Dict[str, Any]]:
        if self._conn is None: raise RuntimeError("DB not connected")
        cursor = await self._conn.execute('''
            SELECT u.username, u.first_name, up.level, up.exp
            FROM user_profiles up JOIN users u ON up.user_id = u.user_id
            ORDER BY up.level DESC, up.exp DESC LIMIT ?
        ''', (limit,))
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        # Map columns to dictionary keys for each row
        # Add 'display_name' for compatibility with existing code that expects it
        return [{columns[i]: row[i] for i in range(len(columns)) | {'display_name': row[1] if row[0] is None else row[0]}} for row in rows]


    async def get_top_users_by_lumcoins(self, limit: int = 10) -> List[Dict[str, Any]]:
        if self._conn is None: raise RuntimeError("DB not connected")
        cursor = await self._conn.execute('''
            SELECT u.username, u.first_name, up.lumcoins
            FROM user_profiles up JOIN users u ON up.user_id = u.user_id
            ORDER BY up.lumcoins DESC LIMIT ?
        ''', (limit,))
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        # Map columns to dictionary keys for each row
        # Add 'display_name' for compatibility with existing code that expects it
        return [{columns[i]: row[i] for i in range(len(columns)) | {'display_name': row[1] if row[0] is None else row[0]}} for row in rows]


    def get_available_backgrounds(self) -> Dict[str, Any]:
        """Возвращает список доступных фонов из ShopConfig."""
        return ShopConfig.SHOP_BACKGROUNDS

    async def get_user_backgrounds_inventory(self, user_id: int) -> List[str]:
        """Получает список ключей фонов из инвентаря пользователя."""
        return await get_user_inventory(user_id, 'background')

    async def generate_profile_image(self, user: types.User, profile_data: Dict[str, Any], bot: Bot) -> BytesIO:
        """
        Генерирует изображение профиля пользователя с учетом всех данных.
        """
        logger.debug(f"Starting profile image generation for user {user.id}.")

        # Загрузка фона
        active_background_key = profile_data.get('active_background', 'default')
        background_info = ShopConfig.SHOP_BACKGROUNDS.get(active_background_key)
        if background_info and background_info.get('url'):
            background_url = background_info['url']
            if background_url.startswith("background/"): # Локальный файл
                background_path = Path(__file__).parent.parent.parent / background_url
                if background_path.exists():
                    background_image = Image.open(background_path).convert("RGBA")
                    logger.debug(f"Loaded local background: {background_path}")
                else:
                    logger.warning(f"Local background file not found: {background_path}. Using default.")
                    background_image = Image.open(ProfileConfig.DEFAULT_LOCAL_BG_PATH).convert("RGBA")
            else: # Удаленный URL
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(background_url) as resp:
                            if resp.status == 200:
                                bg_bytes = await resp.read()
                                background_image = Image.open(BytesIO(bg_bytes)).convert("RGBA")
                                logger.debug(f"Loaded remote background: {background_url}")
                            else:
                                logger.warning(f"Failed to load remote background {background_url}: Status {resp.status}. Using default.")
                                background_image = Image.open(ProfileConfig.DEFAULT_LOCAL_BG_PATH).convert("RGBA")
                except Exception as e:
                    logger.error(f"Error loading remote background {background_url}: {e}. Using default.", exc_info=True)
                    background_image = Image.open(ProfileConfig.DEFAULT_LOCAL_BG_PATH).convert("RGBA")
        else:
            logger.debug(f"No specific background or URL found for '{active_background_key}'. Using default.")
            background_image = Image.open(ProfileConfig.DEFAULT_LOCAL_BG_PATH).convert("RGBA")

        # Изменение размера фона под размер карточки
        background_image = background_image.resize((ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT))

        # Создание основного изображения с закругленными углами
        card = Image.new("RGBA", (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), (0, 0, 0, 0))
        mask = Image.new("L", (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.rounded_rectangle([(0, 0), (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT)],
                                    radius=ProfileConfig.CARD_RADIUS, fill=255)
        
        # Наложение фона на карточку с маской
        card.paste(background_image, (0, 0), mask)

        draw = ImageDraw.Draw(card)

        # Загрузка шрифтов
        def get_font(size, font_path=ProfileConfig.FONT_PATH):
            if (font_path, size) not in self.font_cache:
                try:
                    font = ImageFont.truetype(font_path, size)
                except IOError:
                    logger.warning(f"Font '{font_path}' not found, using default PIL font.")
                    font = ImageFont.load_default()
                self.font_cache[(font_path, size)] = font
            return self.font_cache[(font_path, size)]

        font_username = get_font(30)
        font_stats_label = get_font(20)
        font_stats_value = get_font(22)
        font_level_exp = get_font(18)
        font_hp_lum = get_font(22) # Новый шрифт для HP и Lumcoins

        # Аватар пользователя
        avatar_image = None
        
        # Безопасно получаем URL/file_id аватара
        current_avatar_source = None
        if hasattr(user, 'photo') and user.photo: # Проверяем, существует ли атрибут 'photo' и не равен ли он None
            current_avatar_source = user.photo.big_file_id # Это file_id, а не прямой URL
        
        if current_avatar_source: # Если доступен file_id Telegram
            try:
                file = await bot.get_file(current_avatar_source)
                file_path = file.file_path
                avatar_bytes = await bot.download_file(file_path)
                avatar_image = Image.open(BytesIO(avatar_bytes.getvalue())).convert("RGBA")
                logger.debug(f"Loaded Telegram avatar for user {user.id}.")
            except Exception as e:
                logger.error(f"Error downloading Telegram avatar for user {user.id}: {e}. Falling back to default avatar.", exc_info=True)
        
        if not avatar_image: # Если аватар Telegram не был загружен (нет фото или произошла ошибка)
            # Пытаемся загрузить аватар по умолчанию по URL или локальному пути
            default_avatar_url_or_path = ProfileConfig.DEFAULT_AVATAR_URL
            if default_avatar_url_or_path.startswith("http"): # Это удаленный URL
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(default_avatar_url_or_path) as resp:
                            if resp.status == 200:
                                default_avatar_bytes = await resp.read()
                                avatar_image = Image.open(BytesIO(default_avatar_bytes)).convert("RGBA")
                                logger.debug("Loaded default remote avatar.")
                            else:
                                logger.warning(f"Failed to load default remote avatar {default_avatar_url_or_path}: Status {resp.status}. Using hardcoded local fallback if available.")
                                # Заглушка на локальный файл, если удаленный недоступен
                                local_fallback_path = Path(__file__).parent.parent.parent / "background" / "default_avatar_local.png" # Предполагается, что локальный аватар по умолчанию существует
                                if local_fallback_path.exists():
                                    avatar_image = Image.open(local_fallback_path).convert("RGBA")
                                else:
                                    logger.error(f"Hardcoded local default avatar not found at {local_fallback_path}. Profile image generation might fail or be incomplete.")
                                    # В крайнем случае, создаем пустое изображение или используем очень простой плейсхолдер
                                    avatar_image = Image.new("RGBA", (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), (200, 200, 200, 255)) # Серый квадрат
                except Exception as e:
                    logger.error(f"Error loading default remote avatar {default_avatar_url_or_path}: {e}. Using hardcoded local fallback if available.", exc_info=True)
                    local_fallback_path = Path(__file__).parent.parent.parent / "background" / "default_avatar_local.png"
                    if local_fallback_path.exists():
                        avatar_image = Image.open(local_fallback_path).convert("RGBA")
                    else:
                        logger.error(f"Hardcoded local default avatar not found at {local_fallback_path}. Profile image generation might fail or be incomplete.")
                        avatar_image = Image.new("RGBA", (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), (200, 200, 200, 255))
            else: # Предполагаем, что это локальный путь, если не http/https
                try:
                    avatar_image = Image.open(default_avatar_url_or_path).convert("RGBA")
                    logger.debug(f"Loaded default local avatar: {default_avatar_url_or_path}")
                except Exception as e:
                    logger.error(f"Error loading default local avatar {default_avatar_url_or_path}: {e}. Creating blank image.", exc_info=True)
                    avatar_image = Image.new("RGBA", (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), (200, 200, 200, 255)) # Серый квадрат

        # Убедимся, что avatar_image не None перед изменением размера
        if avatar_image is None:
            logger.critical("Avatar image is still None after all attempts. Creating a blank placeholder.")
            avatar_image = Image.new("RGBA", (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), (200, 200, 200, 255)) # Окончательная заглушка

        avatar_image = avatar_image.resize((ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE))

        # Создание круглой маски для аватара
        avatar_mask = Image.new("L", (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), 0)
        draw_avatar_mask = ImageDraw.Draw(avatar_mask)
        draw_avatar_mask.ellipse([(0, 0), (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE)], fill=255)
        
        # Вставка аватара
        card.paste(avatar_image, ProfileConfig.AVATAR_OFFSET, avatar_mask)

        # Текст: Имя пользователя
        username_text = user.first_name
        draw.text((ProfileConfig.TEXT_BLOCK_LEFT_X, ProfileConfig.USERNAME_Y), username_text,
                  fill=ProfileConfig.TEXT_COLOR, font=font_username,
                  stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)

        # HP и Lumcoins рядом с аватаркой (числовые значения)
        hp_current = profile_data.get('hp', 100)
        hp_max = ProfileConfig.MAX_HP
        lumcoins = profile_data.get('lumcoins', 0)

        # Позиционирование HP
        hp_text = f"HP: {hp_current}/{hp_max}"
        # Отступ от правой границы аватарки
        hp_x = ProfileConfig.AVATAR_X + ProfileConfig.AVATAR_SIZE + ProfileConfig.MARGIN // 2
        hp_y = ProfileConfig.AVATAR_Y # Выравнивание по верхнему краю аватарки
        draw.text((hp_x, hp_y), hp_text, fill=ProfileConfig.TEXT_COLOR, font=font_hp_lum,
                  stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)

        # Позиционирование Lumcoins под HP
        lumcoins_text = f"LUM: {lumcoins}"
        # Отступ под HP, с тем же X-координатой
        lumcoins_y = hp_y + font_hp_lum.getbbox(hp_text)[3] + 5 # 5 пикселей отступа
        draw.text((hp_x, lumcoins_y), lumcoins_text, fill=ProfileConfig.TEXT_COLOR, font=font_hp_lum,
                  stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)

        # Удаление старых HP и EXP баров, так как они теперь не нужны
        # HP Bar (удален)
        # EXP Bar (удален)
        # Текст EXP (перемещен и изменен)

        # Текст EXP (теперь без бара, просто числовое значение)
        level = profile_data.get('level', 1)
        exp = profile_data.get('exp', 0)
        exp_needed_for_next_level = ProfileConfig.LEVEL_UP_EXP_REQUIREMENT(level) if hasattr(ProfileConfig, 'LEVEL_UP_EXP_REQUIREMENT') else 100 # Fallback
        
        exp_text = f"Уровень: {level} | EXP: {exp}/{exp_needed_for_next_level}"
        # Позиционирование EXP под Lumcoins, с тем же X-координатой
        exp_y = lumcoins_y + font_hp_lum.getbbox(lumcoins_text)[3] + 5 # 5 пикселей отступа
        draw.text((hp_x, exp_y), exp_text, fill=ProfileConfig.TEXT_COLOR, font=font_level_exp,
                  stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)


        # Статистика справа (остается без изменений)
        stats = [
            ("Сообщения (день):", profile_data.get('daily_messages', 0)),
            ("Сообщения (всего):", profile_data.get('total_messages', 0)),
            ("Пламя:", profile_data.get('flames', 0))
        ]

        current_y = ProfileConfig.RIGHT_COLUMN_TOP_Y
        for label, value in stats:
            # Метка
            label_text_width, label_text_height = draw.textbbox((0,0), label, font=font_stats_label)[2:]
            draw.text((ProfileConfig.RIGHT_COLUMN_X - label_text_width, current_y), label,
                      fill=ProfileConfig.TEXT_COLOR, font=font_stats_label,
                      stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)
            
            # Значение
            value_text = str(value)
            value_text_width, value_text_height = draw.textbbox((0,0), value_text, font=font_stats_value)[2:]
            draw.text((ProfileConfig.RIGHT_COLUMN_X - value_text_width, current_y + label_text_height + 5), value_text,
                      fill=ProfileConfig.TEXT_COLOR, font=font_stats_value,
                      stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)
            
            current_y += ProfileConfig.ITEM_SPACING_Y

        # Сохранение изображения в байтовый поток
        img_byte_arr = BytesIO()
        card.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        logger.debug(f"Profile image generated for user {user.id}.")
        return img_byte_arr
