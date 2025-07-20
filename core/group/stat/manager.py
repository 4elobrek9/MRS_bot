from core.group.stat.smain import *
from core.group.stat.config import ProfileConfig
# from core.group.stat.manager import * # Циклический импорт
# from group_stat import * # Циклический импорт

# Прямые импорты, чтобы избежать цикличности
from database import get_user_rp_stats, add_item_to_inventory, get_user_inventory, set_user_active_background, get_user_profile_info
import aiosqlite
from PIL import Image, ImageDraw, ImageFont, ImageOps
import aiohttp
from io import BytesIO
from aiogram import types, Bot
from typing import Optional, Dict, Any, List
import logging
import os
import sqlite3 # Импортируем для синхронной инициализации

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
        # Используем get_user_profile_info из database.py для получения полной информации
        return await get_user_profile_info(user.id)

    async def record_message(self, user: types.User) -> None:
        if self._conn is None: raise RuntimeError("DB not connected")
        user_id = user.id
        current_time = time.time()

        # Ensure user exists in 'users' table
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
            last_active_ts_cursor = await self._conn.execute(
                'SELECT last_active_ts FROM users WHERE user_id = ?', (user_id,)
            )
            last_active_ts_row = await last_active_ts_cursor.fetchone()
            last_active_ts = last_active_ts_row[0] if last_active_ts_row else 0

            last_active_date = datetime.fromtimestamp(last_active_ts).date()
            current_date = datetime.fromtimestamp(current_time).date()

            if current_date > last_active_date:
                daily_messages = 0

            # Update stats
            exp += ProfileConfig.EXP_PER_MESSAGE
            total_messages += 1
            daily_messages += 1

            # Level up logic
            new_level = level
            while exp >= ProfileConfig.LEVEL_UP_EXP_REQUIREMENT(new_level):
                exp -= ProfileConfig.LEVEL_UP_EXP_REQUIREMENT(new_level)
                new_level += 1
                lumcoins += ProfileConfig.LUMCOINS_PER_LEVEL_UP

            await self._conn.execute(
                '''
                UPDATE user_profiles
                SET level = ?, exp = ?, lumcoins = ?, daily_messages = ?, total_messages = ?
                WHERE user_id = ?
                ''',
                (new_level, exp, lumcoins, daily_messages, total_messages, user_id)
            )
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
                (user_id, 1, ProfileConfig.EXP_PER_MESSAGE, 0, 1, 1, 0, 'default') # Default active background
            )
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
        return [dict(zip(columns, row)) for row in rows]

    async def get_top_users_by_lumcoins(self, limit: int = 10) -> List[Dict[str, Any]]:
        if self._conn is None: raise RuntimeError("DB not connected")
        cursor = await self._conn.execute('''
            SELECT u.username, u.first_name, up.lumcoins
            FROM user_profiles up JOIN users u ON up.user_id = u.user_id
            ORDER BY up.lumcoins DESC LIMIT ?
        ''', (limit,))
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

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
        font_hp = get_font(20)

        # Аватар пользователя
        avatar_url = user.photo.big_file_id if user.photo else ProfileConfig.DEFAULT_AVATAR_URL
        avatar_image = None
        if avatar_url and isinstance(avatar_url, str) and avatar_url.startswith("http"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(avatar_url) as resp:
                        if resp.status == 200:
                            avatar_bytes = await resp.read()
                            avatar_image = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
                            logger.debug(f"Loaded remote avatar: {avatar_url}")
                        else:
                            logger.warning(f"Failed to load remote avatar {avatar_url}: Status {resp.status}. Using default.")
                except Exception as e:
                    logger.error(f"Error loading remote avatar {avatar_url}: {e}. Using default.", exc_info=True)
        elif avatar_url and not isinstance(avatar_url, str): # Assume it's a file_id from Telegram
            try:
                file = await bot.get_file(avatar_url)
                file_path = file.file_path
                avatar_bytes = await bot.download_file(file_path)
                avatar_image = Image.open(BytesIO(avatar_bytes.getvalue())).convert("RGBA")
                logger.debug(f"Loaded Telegram avatar for user {user.id}.")
            except Exception as e:
                logger.error(f"Error downloading Telegram avatar for user {user.id}: {e}. Using default.", exc_info=True)
        
        if not avatar_image:
            avatar_image = Image.open(ProfileConfig.DEFAULT_AVATAR_URL.split('?')[0]).convert("RGBA") # Remove query params for local load

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

        # HP Bar
        hp_current = profile_data.get('hp', 100)
        hp_max = ProfileConfig.MAX_HP
        hp_percentage = hp_current / hp_max

        hp_bar_width = ProfileConfig.EXP_BAR_WIDTH
        hp_bar_height = ProfileConfig.EXP_BAR_HEIGHT
        hp_bar_x = ProfileConfig.TEXT_BLOCK_LEFT_X
        hp_bar_y = ProfileConfig.USERNAME_Y + font_username.getbbox(username_text)[3] + 10 # Отступ от имени пользователя

        # Выбор цвета HP бара
        if hp_percentage >= 0.75:
            hp_color = ProfileConfig.HP_COLORS["full"]
        elif hp_percentage >= 0.5:
            hp_color = ProfileConfig.HP_COLORS["high"]
        elif hp_percentage >= 0.25:
            hp_color = ProfileConfig.HP_COLORS["medium"]
        elif hp_percentage > 0:
            hp_color = ProfileConfig.HP_COLORS["low"]
        else:
            hp_color = ProfileConfig.HP_COLORS["empty"]

        # Фон HP бара (серый)
        draw.rounded_rectangle(
            [(hp_bar_x, hp_bar_y), (hp_bar_x + hp_bar_width, hp_bar_y + hp_bar_height)],
            radius=hp_bar_height // 2,
            fill=(100, 100, 100, ProfileConfig.EXP_BAR_ALPHA)
        )
        # Заполненная часть HP бара
        draw.rounded_rectangle(
            [(hp_bar_x, hp_bar_y), (hp_bar_x + hp_bar_width * hp_percentage, hp_bar_y + hp_bar_height)],
            radius=hp_bar_height // 2,
            fill=hp_color + (ProfileConfig.EXP_BAR_ALPHA,)
        )
        # Текст HP
        hp_text = f"HP: {hp_current}/{hp_max}"
        text_width, text_height = draw.textbbox((0,0), hp_text, font=font_hp)[2:]
        hp_text_x = hp_bar_x + (hp_bar_width - text_width) // 2
        hp_text_y = hp_bar_y + (hp_bar_height - text_height) // 2
        draw.text((hp_text_x, hp_text_y), hp_text, fill=ProfileConfig.TEXT_COLOR, font=font_hp,
                  stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)

        # EXP Bar
        level = profile_data.get('level', 1)
        exp = profile_data.get('exp', 0)
        exp_needed_for_next_level = ProfileConfig.LEVEL_UP_EXP_REQUIREMENT(level)
        exp_percentage = exp / exp_needed_for_next_level if exp_needed_for_next_level > 0 else 0

        exp_bar_x = ProfileConfig.EXP_BAR_X
        exp_bar_y = ProfileConfig.EXP_BAR_Y
        exp_bar_width = ProfileConfig.EXP_BAR_WIDTH
        exp_bar_height = ProfileConfig.EXP_BAR_HEIGHT

        # Фон EXP бара (серый)
        draw.rounded_rectangle(
            [(exp_bar_x, exp_bar_y), (exp_bar_x + exp_bar_width, exp_bar_y + exp_bar_height)],
            radius=exp_bar_height // 2,
            fill=(100, 100, 100, ProfileConfig.EXP_BAR_ALPHA)
        )

        # Заполненная часть EXP бара (градиент)
        for i in range(int(exp_bar_width * exp_percentage)):
            r = int(ProfileConfig.EXP_GRADIENT_START[0] + (ProfileConfig.EXP_GRADIENT_END[0] - ProfileConfig.EXP_GRADIENT_START[0]) * (i / (exp_bar_width * exp_percentage + 1e-6)))
            g = int(ProfileConfig.EXP_GRADIENT_START[1] + (ProfileConfig.EXP_GRADIENT_END[1] - ProfileConfig.EXP_GRADIENT_START[1]) * (i / (exp_bar_width * exp_percentage + 1e-6)))
            b = int(ProfileConfig.EXP_GRADIENT_START[2] + (ProfileConfig.EXP_GRADIENT_END[2] - ProfileConfig.EXP_GRADIENT_START[2]) * (i / (exp_bar_width * exp_percentage + 1e-6)))
            draw.line([(exp_bar_x + i, exp_bar_y), (exp_bar_x + i, exp_bar_y + exp_bar_height)], fill=(r, g, b, ProfileConfig.EXP_BAR_ALPHA))

        # Текст EXP
        exp_text = f"Уровень: {level} | EXP: {exp}/{exp_needed_for_next_level}"
        text_width, text_height = draw.textbbox((0,0), exp_text, font=font_level_exp)[2:]
        exp_text_x = exp_bar_x + (exp_bar_width - text_width) // 2
        exp_text_y = exp_bar_y + (exp_bar_height - text_height) // 2
        draw.text((exp_text_x, exp_text_y), exp_text, fill=ProfileConfig.TEXT_COLOR, font=font_level_exp,
                  stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)

        # Статистика справа
        stats = [
            ("Lumcoins:", f"{profile_data.get('lumcoins', 0)} LUM"),
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

