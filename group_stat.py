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
from PIL import Image, ImageDraw, ImageFont, ImageOps
import requests
from aiogram import Router, types, F
from aiogram.enums import ChatType
from aiogram.types import BufferedInputFile
import random
import aiohttp

formatter = string.Formatter()

stat_router = Router(name="stat_router")

class ProfileConfig:
    DEFAULT_BG_URL = "https://images.unsplash.com/photo-1506318137072-291786a88698?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8M3x8c3BhY2VlbnwwfHwwfHww&auto=format&fit=crop&w=600&q=80"
    DEFAULT_AVATAR_URL = "https://placehold.co/120x120/CCCCCC/FFFFFF/png?text=AV"

    FONT_PATH = "Hlobus.ttf"
    TEXT_COLOR = (255, 255, 255)
    TEXT_SHADOW_COLOR = (0, 0, 0)
    
    CARD_WIDTH = 700
    CARD_HEIGHT = 280
    CARD_RADIUS = 20

    MARGIN = 30

    AVATAR_SIZE = 120
    AVATAR_X = MARGIN
    AVATAR_Y = (CARD_HEIGHT - AVATAR_SIZE) // 2
    AVATAR_OFFSET = (AVATAR_X, AVATAR_Y)

    TEXT_BLOCK_LEFT_X = AVATAR_X + AVATAR_SIZE + MARGIN // 2
    USERNAME_Y = AVATAR_Y - 10
    TELEGRAM_NICKNAME_Y = USERNAME_Y + 30 # This constant remains, but the text drawing is removed
    # LEFT_LUMCOINS_Y = TELEGRAM_NICKNAME_Y + 30 # Removed as Lumcoins move back to right

    EXPERIENCE_LABEL_Y = CARD_HEIGHT - MARGIN - 20 - 25
    EXP_BAR_Y = EXPERIENCE_LABEL_Y + 25
    EXP_BAR_X = MARGIN
    EXP_BAR_HEIGHT = 20
    EXP_BAR_WIDTH = int( (CARD_WIDTH - EXP_BAR_X - MARGIN - 70) ) # Около 70% ширины с учетом текста справа

    RIGHT_COLUMN_X = CARD_WIDTH - MARGIN
    RIGHT_COLUMN_TOP_Y = MARGIN + 20 # Общая начальная Y-позиция для правого столбца
    ITEM_SPACING_Y = 70 # Расстояние между HP и Lumcoins
    
    HP_COLORS = {
        "full": (0, 200, 0),
        "high": (50, 150, 0),
        "medium": (255, 165, 0),
        "low": (255, 0, 0),
        "empty": (128, 0, 0)
    }
    
    EXP_GRADIENT_START = (0, 128, 0) # Зеленый цвет
    EXP_GRADIENT_END = (0, 255, 0) # Ярко-зеленый цвет
    EXP_BAR_ALPHA = 200 # Прозрачность для шкалы опыта (0-255)

    MAX_HP = 150
    MIN_HP = 0
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
    BACKGROUND_SHOP = {
        "space": {"name": "Космос", "url": "https://images.unsplash.com/photo-1506318137072-291786a88698?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8M3x8c3BhY2VlbnwwfHwwfHww&auto=format&fit=crop&w=600&q=80", "cost": 50},
        "nature": {"name": "Природа", "url": "https://images.unsplash.com/photo-1440330559787-852571c1c71a?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxzZWFyY2h8MTB8fG5hdHVyZXxlbnwwfHwwfHww&auto=format&fit=crop&w=600&q=80", "cost": 40},
        "city": {"name": "Город", "url": "https://images.unsplash.com/photo-1519013876546-8858ba07e532?ixlib=rb-4.0.3&ixid=M3wxMjA3fDF8fGNpdHl8ZW58MHx8MHx8fDA%3D&auto=format&fit=crop&w=600&q=80", "cost": 60},
        "abstract": {"name": "Абстракция", "url": "https://images.unsplash.com/photo-1508768787810-6adc1f09aeda?ixlib=rb-4.0.3&ixid=M3wxMjA3fDdzfHxhYnN0cmFjdHxlbnwwfHwwfHww&auto=format&fit=crop&w=600&q=80", "cost": 30}
    }
    FONT_SIZE_XLARGE = 36
    FONT_SIZE_LARGE = 28
    FONT_SIZE_MEDIUM = 20
    FONT_SIZE_SMALL = 16


def init_db():
    logger.info("Attempting to initialize database (sync).")
    if not os.path.exists('profiles.db'):
        logger.info("profiles.db not found, creating new database.")
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
        logger.info("Database initialized successfully (sync).")
    else:
        logger.info("Database profiles.db already exists, skipping sync initialization.")

init_db()

class ProfileManager:
    def __init__(self):
        logger.info("ProfileManager instance initialized.")
        self._conn = None
        self.font_cache = {}

    async def connect(self):
        logger.debug("Attempting to connect to database asynchronously.")
        if self._conn is not None:
            logger.warning("Database connection already exists, skipping reconnection.")
            return
        try:
            self._conn = await aiosqlite.connect('profiles.db')
            logger.info("Database connected asynchronously.")
            await self._init_db_async()
            logger.info("Asynchronous database schema check/initialization completed.")
        except Exception as e:
            logger.exception("Failed to establish database connection or initialize schema asynchronously:")
            raise

    async def close(self):
        logger.debug("Attempting to close database connection.")
        if self._conn is not None:
            try:
                await self._conn.close()
                self._conn = None
                logger.info("Database connection closed successfully.")
            except Exception as e:
                logger.exception("Error occurred while closing database connection:")
        else:
            logger.info("Database connection was already closed or not established.")

    async def _init_db_async(self):
        logger.debug("Starting asynchronous database schema initialization.")
        if self._conn is None:
            logger.error("Cannot perform async DB init: connection is None. Aborting.")
            return
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
        logger.info("Asynchronous database tables checked/created.")

    async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
        logger.debug(f"Fetching or creating profile for user_id: {user.id}")
        if self._conn is None:
            logger.error("Database connection is not established when trying to get user profile.")
            raise RuntimeError("Database connection is not established.")
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
        logger.debug(f"User {user.id} information updated/inserted in 'users' table.")
        user_id = user.id

        await cursor.execute('''
        INSERT OR IGNORE INTO user_profiles (user_id, background_url)
        VALUES (?, ?)
        ''', (user_id, ProfileConfig.DEFAULT_BG_URL))
        await self._conn.commit()
        logger.debug(f"User profile for {user_id} ensured existence in 'user_profiles' table.")

        await cursor.execute('''
        SELECT * FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        profile = await cursor.fetchone()

        if not profile:
            logger.error(f"Profile not found for user_id {user.id} after creation attempt. This should not happen.")
            return None

        columns = [column[0] for column in cursor.description]
        profile_data = dict(zip(columns, profile))
        logger.debug(f"Profile data retrieved for user_id {user.id}.")
        
        profile_data['display_name'] = f"@{user.username}" if user.username else user.full_name 
        logger.debug(f"Display name set to: {profile_data['display_name']} for user {user.id}.")
        
        await cursor.execute('SELECT background_url FROM backgrounds WHERE user_id = ?', (user_id,))
        custom_bg = await cursor.fetchone()
        if custom_bg:
            profile_data['background_url'] = custom_bg[0]
            logger.debug(f"Custom background found and set for user {user.id}: {custom_bg[0]}.")
        else:
            profile_data['background_url'] = ProfileConfig.DEFAULT_BG_URL
            logger.debug(f"No custom background found for user {user.id}, setting default: {ProfileConfig.DEFAULT_BG_URL}.")
        
        logger.info(f"Successfully retrieved/created profile for user {user.id}.")
        return profile_data

    async def record_message(self, user: types.User) -> None:
        logger.debug(f"Recording message activity for user_id: {user.id}.")
        if self._conn is None:
            logger.error("Database connection is not established when trying to record message.")
            raise RuntimeError("Database connection is not established.")
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
        old_total_messages = total_messages
        total_messages += 1
        logger.debug(f"User {user_id}: Total messages updated from {old_total_messages} to {total_messages}.")
        
        exp_added = 0
        if total_messages > 0 and total_messages % ProfileConfig.EXP_PER_MESSAGE_INTERVAL == 0:
            exp_added = ProfileConfig.EXP_AMOUNT_PER_INTERVAL
            logger.debug(f"User {user_id}: {exp_added} EXP added due to message interval.")
        
        new_exp = exp + exp_added
        new_level = level
        new_lumcoins = lumcoins
        logger.debug(f"User {user_id}: Current EXP: {exp}, New EXP: {new_exp}, Current Level: {level}, Current Lumcoins: {lumcoins}.")

        while new_exp >= self._get_exp_for_level(new_level) and new_level < ProfileConfig.MAX_LEVEL:
            needed_for_current = self._get_exp_for_level(new_level)
            new_exp -= needed_for_current
            new_level += 1
            coins_this_level = self._get_lumcoins_for_level(new_level)
            new_lumcoins += coins_this_level
            logger.info(f"User {user_id} leveled up to {new_level}! Earned {coins_this_level} Lumcoins. Remaining EXP: {new_exp}.")

        await cursor.execute('''
        UPDATE user_profiles
        SET daily_messages = daily_messages + 1,
            total_messages = ?,
            exp = ?,
            level = ?,
            lumcoins = ?
        WHERE user_id = ?
        ''', (total_messages, new_exp, new_level, new_lumcoins, user_id))
        await self._conn.commit()
        logger.info(f"User {user_id} profile updated: Total messages: {total_messages}, Level: {new_level}, EXP: {new_exp}, Lumcoins: {new_lumcoins}.")

    def _get_exp_for_level(self, level: int) -> int:
        logger.debug(f"Calculating required EXP for level {level}.")
        if level < 1:
            logger.warning(f"Invalid level {level} provided for EXP calculation, returning 0.")
            return 0
        base_exp = 100
        coefficient = 2
        multiplier = 5
        required_exp = base_exp + (level ** coefficient) * multiplier
        logger.debug(f"Required EXP for level {level}: {required_exp}.")
        return required_exp

    def _get_lumcoins_for_level(self, level: int) -> int:
        logger.debug(f"Determining Lumcoins reward for level {level}.")
        for lvl, coins in sorted(ProfileConfig.LUMCOINS_PER_LEVEL.items(), reverse=True):
            if level >= lvl:
                logger.debug(f"Lumcoins for level {level}: {coins} (from level {lvl} threshold).")
                return coins
        logger.debug(f"No specific Lumcoins reward found for level {level}, returning default 1.")
        return 1

    async def generate_profile_image(self, user: types.User, profile: Dict[str, Any], bot_instance: Bot) -> BytesIO:
        logger.info(f"Starting profile image generation for user {user.id}.")
        font_xlarge, font_large, font_medium, font_small = None, None, None, None
        try:
            if ProfileConfig.FONT_PATH not in self.font_cache:
                if os.path.exists(ProfileConfig.FONT_PATH):
                    self.font_cache[ProfileConfig.FONT_PATH] = {
                            'xlarge': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_XLARGE, encoding="UTF-8"),
                            'large': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_LARGE, encoding="UTF-8"),
                            'medium': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_MEDIUM, encoding="UTF-8"),
                            'small': ImageFont.truetype(ProfileConfig.FONT_PATH, ProfileConfig.FONT_SIZE_SMALL, encoding="UTF-8")
                    }
                    logger.info(f"Font '{ProfileConfig.FONT_PATH}' loaded successfully and cached.")
                else:
                    logger.error(f"Font file not found: {ProfileConfig.FONT_PATH}. Raising FileNotFoundError.")
                    raise FileNotFoundError(f"Font file not found: {ProfileConfig.FONT_PATH}")
            
            font_xlarge = self.font_cache[ProfileConfig.FONT_PATH]['xlarge']
            font_large = self.font_cache[ProfileConfig.FONT_PATH]['large']
            font_medium = self.font_cache[ProfileConfig.FONT_PATH]['medium']
            font_small = self.font_cache[ProfileConfig.FONT_PATH]['small']
            logger.debug("Fonts retrieved from cache.")

        except (FileNotFoundError, OSError, Exception) as e:
            logger.error(f"Failed to load custom font '{ProfileConfig.FONT_PATH}': {e}. Using default Pillow font.", exc_info=True)
            font_xlarge = ImageFont.load_default(size=ProfileConfig.FONT_SIZE_XLARGE + 4)
            font_large = ImageFont.load_default(size=ProfileConfig.FONT_SIZE_LARGE + 4)
            font_medium = ImageFont.load_default(size=ProfileConfig.FONT_SIZE_MEDIUM + 4)
            font_small = ImageFont.load_default(size=ProfileConfig.FONT_SIZE_SMALL + 4)
            logger.info("Default Pillow fonts loaded.")

        # Создаем базовое изображение и объект для рисования
        base_image = Image.new('RGBA', (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), (0, 0, 0, 0))
        draw_base = ImageDraw.Draw(base_image)
        logger.debug("Base image and draw object created.")

        # Нарисовать фон карточки
        card_fill_color = (36, 38, 50, 255)
        shadow_offset_x = 5
        shadow_offset_y = 5
        shadow_color = (0, 0, 0, 100)
        draw_base.rounded_rectangle(
            (shadow_offset_x, shadow_offset_y, ProfileConfig.CARD_WIDTH + shadow_offset_x, ProfileConfig.CARD_HEIGHT + shadow_offset_y),
            radius=ProfileConfig.CARD_RADIUS,
            fill=shadow_color
        )
        draw_base.rounded_rectangle(
            (0, 0, ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT),
            radius=ProfileConfig.CARD_RADIUS,
            fill=card_fill_color
        )
        logger.debug("Card background and shadow drawn.")

        # Обработка аватара
        avatar_image = None
        try:
            logger.debug(f"Attempting to get avatar for user ID: {user.id} from Telegram.")
            photos = await bot_instance.get_user_profile_photos(user.id, limit=1)
            if photos.photos and photos.photos[0]:
                file_id = photos.photos[0][-1].file_id
                file = await bot_instance.get_file(file_id)
                file_path = file.file_path
                if file_path:
                    avatar_bytes = BytesIO()
                    await bot_instance.download_file(file_path, destination=avatar_bytes)
                    avatar_bytes.seek(0)
                    avatar_image = Image.open(avatar_bytes).convert("RGBA")
                    avatar_image = avatar_image.resize((ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE))
                    mask = Image.new("L", avatar_image.size, 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), fill=255)
                    avatar_image = ImageOps.fit(avatar_image, mask.size, centering=(0.5, 0.5))
                    avatar_image.putalpha(mask)
                    logger.info(f"User avatar loaded and processed successfully for user {user.id}.")
                else:
                    logger.warning(f"File path not found for avatar of user {user.id}. Falling back to default placeholder.")
                    raise ValueError("File path not available")
            else:
                logger.info(f"No profile photos found for user {user.id}. Falling back to default placeholder.")
                raise ValueError("No profile photos") 
        except Exception as e:
            logger.warning(f"Failed to get user avatar {user.id}: {e}. Attempting to load default placeholder from URL.", exc_info=True)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(ProfileConfig.DEFAULT_AVATAR_URL) as resp: 
                        resp.raise_for_status()
                        avatar_placeholder_data = await resp.read()
                avatar_image = Image.open(BytesIO(avatar_placeholder_data)).convert("RGBA")
                avatar_image = avatar_image.resize((ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE))
                mask = Image.new("L", avatar_image.size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), fill=255)
                avatar_image = ImageOps.fit(avatar_image, mask.size, centering=(0.5, 0.5))
                avatar_image.putalpha(mask)
                logger.info("Default avatar placeholder loaded successfully from URL.")
            except Exception as e_fallback:
                logger.error(f"Failed to load default avatar placeholder from URL '{ProfileConfig.DEFAULT_AVATAR_URL}': {e_fallback}. Using solid gray fallback.", exc_info=True)
                avatar_image = Image.new('RGBA', (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), (100, 100, 100, 255)) 

        if avatar_image:
            base_image.paste(avatar_image, ProfileConfig.AVATAR_OFFSET, avatar_image)
            logger.debug("Avatar pasted onto base image.")

        # Иконка монетки на аватаре
        coin_icon_offset_x = ProfileConfig.AVATAR_X + ProfileConfig.AVATAR_SIZE - 25
        coin_icon_offset_y = ProfileConfig.AVATAR_Y + ProfileConfig.AVATAR_SIZE - 25
        draw_base.ellipse((coin_icon_offset_x, coin_icon_offset_y, 
                        coin_icon_offset_x + 20, coin_icon_offset_y + 20), 
                        fill=(255, 215, 0))
        draw_base.text((coin_icon_offset_x + 5, coin_icon_offset_y + 2), "$", font=font_small, fill=(0,0,0))
        logger.debug("Coin icon drawn on avatar.")

        def draw_text_with_shadow(draw_obj, position, text, font, text_color, shadow_color, shadow_offset=(1, 1)):
            shadow_pos = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
            draw_obj.text(shadow_pos, text, font=font, fill=shadow_color)
            draw_obj.text(position, text, font=font, fill=text_color)
            logger.debug(f"Text '{text}' drawn with shadow at {position}.")
        
        display_name = profile.get('display_name', user.first_name) 
        level = profile.get('level', 1)
        exp = profile.get('exp', 0)
        lumcoins = profile.get('lumcoins', 0)
        hp = profile.get('hp', 100)
        total_messages = profile.get('total_messages', 0)
        flames = profile.get('flames', 0)
        logger.debug(f"Profile data for image: Display Name: {display_name}, Level: {level}, EXP: {exp}, Lumcoins: {lumcoins}, HP: {hp}.")

        username_text = f"{display_name}" 
        # telegram_nickname_text = "⟟ Telegram nickname" # Удален комментарий по запросу

        # Левый центральный блок текста
        draw_text_with_shadow(draw_base, (ProfileConfig.TEXT_BLOCK_LEFT_X, ProfileConfig.USERNAME_Y), 
                            username_text, font_large, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        
        # Удален "⟟ Telegram nickname"
        # draw_text_with_shadow(draw_base, (ProfileConfig.TEXT_BLOCK_LEFT_X, ProfileConfig.TELEGRAM_NICKNAME_Y), 
        #                     telegram_nickname_text, font_small, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        
        # Lumcoins теперь снова только справа, поэтому код для левых Lumcoins удален
        # draw_text_with_shadow(draw_base, (ProfileConfig.TEXT_BLOCK_LEFT_X, ProfileConfig.LEFT_LUMCOINS_Y), 
        #                     left_lumcoins_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug("Left-central text block drawn.")

        needed_exp_for_next_level = self._get_exp_for_level(level)

        # Секция опыта
        draw_text_with_shadow(draw_base, (ProfileConfig.EXP_BAR_X, ProfileConfig.EXPERIENCE_LABEL_Y),
                            "Experience", font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug("Experience label drawn.")

        exp_bar_rect = (ProfileConfig.EXP_BAR_X, ProfileConfig.EXP_BAR_Y,
                        ProfileConfig.EXP_BAR_X + ProfileConfig.EXP_BAR_WIDTH, ProfileConfig.EXP_BAR_Y + ProfileConfig.EXP_BAR_HEIGHT)
        current_exp_percentage = exp / needed_exp_for_next_level if needed_exp_for_next_level > 0 and level < ProfileConfig.MAX_LEVEL else (1.0 if level == ProfileConfig.MAX_LEVEL else 0.0)
        exp_bar_fill_width = int(ProfileConfig.EXP_BAR_WIDTH * current_exp_percentage)
        logger.debug(f"EXP Bar: current_exp_percentage={current_exp_percentage}, fill_width={exp_bar_fill_width}.")
        
        draw_base.rounded_rectangle(
            exp_bar_rect,
            radius=ProfileConfig.EXP_BAR_HEIGHT // 2, 
            fill=(50, 50, 50, 128)
        )
        logger.debug("EXP bar background drawn.")

        # Заполнение шкалы опыта градиентом (зеленая прозрачная полоса)
        for i in range(exp_bar_fill_width):
            r = int(ProfileConfig.EXP_GRADIENT_START[0] + (ProfileConfig.EXP_GRADIENT_END[0] - ProfileConfig.EXP_GRADIENT_START[0]) * (i / ProfileConfig.EXP_BAR_WIDTH))
            g = int(ProfileConfig.EXP_GRADIENT_START[1] + (ProfileConfig.EXP_GRADIENT_END[1] - ProfileConfig.EXP_GRADIENT_START[1]) * (i / ProfileConfig.EXP_BAR_WIDTH))
            b = int(ProfileConfig.EXP_GRADIENT_START[2] + (ProfileConfig.EXP_GRADIENT_END[2] - ProfileConfig.EXP_GRADIENT_START[2]) * (i / ProfileConfig.EXP_BAR_WIDTH))
            draw_base.line([(exp_bar_rect[0] + i, exp_bar_rect[1]),
                            (exp_bar_rect[0] + i, exp_bar_rect[3])],
                        fill=(r, g, b, ProfileConfig.EXP_BAR_ALPHA), width=1) # Применена прозрачность
        logger.debug("EXP bar filled with green gradient with transparency.")
        
        # Текст прогресса шкалы опыта (например, "0/100" или "1/100")
        exp_progress_text = f"{exp}/{needed_exp_for_next_level}"
        exp_progress_text_bbox = draw_base.textbbox((0,0), exp_progress_text, font=font_medium)
        # exp_progress_text_width = exp_progress_text_bbox[2] - exp_progress_text_bbox[0] # Not used
        exp_progress_pos_x = ProfileConfig.EXP_BAR_X + ProfileConfig.EXP_BAR_WIDTH + (ProfileConfig.MARGIN // 2)
        exp_progress_pos_y = ProfileConfig.EXP_BAR_Y + (ProfileConfig.EXP_BAR_HEIGHT - (exp_progress_text_bbox[3] - exp_progress_text_bbox[1])) // 2
        draw_text_with_shadow(draw_base, (exp_progress_pos_x, exp_progress_pos_y),
                            exp_progress_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug(f"Experience progress text '{exp_progress_text}' drawn.")


        # Правый столбец (HP и Lumcoins)
        # HP
        hp_right_text = "HP"
        hp_value_text = f"❤️ {hp}"
        
        hp_right_text_bbox = draw_base.textbbox((0,0), hp_right_text, font=font_medium)
        hp_right_text_width = hp_right_text_bbox[2] - hp_right_text_bbox[0]
        hp_right_x = ProfileConfig.RIGHT_COLUMN_X - hp_right_text_width
        draw_text_with_shadow(draw_base, (hp_right_x, ProfileConfig.RIGHT_COLUMN_TOP_Y), 
                            hp_right_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        
        hp_value_text_bbox = draw_base.textbbox((0,0), hp_value_text, font=font_xlarge)
        hp_value_text_width = hp_value_text_bbox[2] - hp_value_text_bbox[0]
        hp_value_x = ProfileConfig.RIGHT_COLUMN_X - hp_value_text_width
        draw_text_with_shadow(draw_base, (hp_value_x, ProfileConfig.RIGHT_COLUMN_TOP_Y + 25),
                            hp_value_text, font_xlarge, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug("Right column HP text drawn.")

        # Lumcoins (возвращены в правый столбец, под HP)
        lumcoins_right_text = "LumCoins"
        lumcoins_value_text = f"₽ {lumcoins}" # Валютный символ возвращен
        
        lumcoins_right_text_bbox = draw_base.textbbox((0,0), lumcoins_right_text, font=font_medium)
        lumcoins_right_text_width = lumcoins_right_text_bbox[2] - lumcoins_right_text_bbox[0]
        lumcoins_right_x = ProfileConfig.RIGHT_COLUMN_X - lumcoins_right_text_width
        lumcoins_y = ProfileConfig.RIGHT_COLUMN_TOP_Y + ProfileConfig.ITEM_SPACING_Y # Отступ от HP
        draw_text_with_shadow(draw_base, (lumcoins_right_x, lumcoins_y), 
                            lumcoins_right_text, font_medium, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        
        lumcoins_value_text_bbox = draw_base.textbbox((0,0), lumcoins_value_text, font=font_xlarge)
        lumcoins_value_text_width = lumcoins_value_text_bbox[2] - lumcoins_value_text_bbox[0]
        lumcoins_value_x = ProfileConfig.RIGHT_COLUMN_X - lumcoins_value_text_width
        draw_text_with_shadow(draw_base, (lumcoins_value_x, lumcoins_y + 25),
                            lumcoins_value_text, font_xlarge, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW_COLOR)
        logger.debug("Right column Lumcoins text drawn.")


        byte_io = BytesIO()
        base_image.save(byte_io, format='PNG')
        byte_io.seek(0)
        logger.info(f"Profile image generation completed for user {user.id}.")
        return byte_io

    async def update_lumcoins(self, user_id: int, amount: int):
        logger.debug(f"Updating Lumcoins for user {user_id} by amount {amount}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to update Lumcoins.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        UPDATE user_profiles
        SET lumcoins = lumcoins + ?
        WHERE user_id = ?
        ''', (amount, user_id))
        await self._conn.commit()
        logger.info(f"Lumcoins updated for user {user_id}. Change: {amount}.")

    async def get_lumcoins(self, user_id: int) -> int:
        logger.debug(f"Fetching Lumcoins for user {user_id}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to get Lumcoins.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        SELECT lumcoins FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()
        lumcoins_value = result[0] if result else 0
        logger.info(f"Lumcoins for user {user_id}: {lumcoins_value}.")
        return lumcoins_value

    async def set_background(self, user_id: int, background_url: str):
        logger.debug(f"Setting background for user {user_id} to URL: {background_url}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to set background.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        INSERT OR REPLACE INTO backgrounds (user_id, background_url)
        VALUES (?, ?)
        ''', (user_id, background_url))
        await self._conn.commit()
        logger.info(f"Background set for user {user_id} to {background_url}.")

    def get_available_backgrounds(self) -> Dict[str, Dict[str, Any]]:
        logger.debug("Retrieving available backgrounds from shop configuration.")
        return ProfileConfig.BACKGROUND_SHOP

    async def get_last_work_time(self, user_id: int) -> float:
        logger.debug(f"Fetching last work time for user {user_id}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to get last work time.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        SELECT last_work_time FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()
        last_work = result[0] if result else 0.0
        logger.info(f"Last work time for user {user_id}: {last_work}.")
        return last_work

    async def update_last_work_time(self, user_id: int, timestamp: float):
        logger.debug(f"Updating last work time for user {user_id} to {timestamp}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to update last work time.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        UPDATE user_profiles
        SET last_work_time = ?
        WHERE user_id = ?
        ''', (timestamp, user_id))
        await self._conn.commit()
        logger.info(f"Last work time updated for user {user_id} to {timestamp}.")
    
    async def set_level(self, user_id: int, level: int):
        logger.debug(f"Attempting to set level for user {user_id} to {level}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to set level.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        
        level = max(1, min(level, ProfileConfig.MAX_LEVEL))
        logger.debug(f"Level for user {user_id} adjusted to {level} (within bounds).")
        
        needed_exp = self._get_exp_for_level(level)
        
        await cursor.execute('''
        UPDATE user_profiles
        SET level = ?, exp = ?
        WHERE user_id = ?
        ''', (level, needed_exp, user_id))
        await self._conn.commit()
        logger.info(f"User {user_id} level set to {level} with exp {needed_exp}.")

    async def set_hp(self, user_id: int, hp_value: int):
        logger.debug(f"Attempting to set HP for user {user_id} to {hp_value}.")
        if self._conn is None:
            logger.error("Database connection not established when trying to set HP.")
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        
        hp_value = max(ProfileConfig.MIN_HP, min(hp_value, ProfileConfig.MAX_HP)) 
        logger.debug(f"HP value for user {user_id} adjusted to {hp_value} (within bounds).")
        
        await cursor.execute('''
        UPDATE user_profiles
        SET hp = ?
        WHERE user_id = ?
        ''', (hp_value, user_id))
        await self._conn.commit()
        logger.info(f"User {user_id} HP set to {hp_value}.")


@stat_router.message(F.text.lower().startswith(("профиль", "/профиль")))
async def show_profile(message: types.Message, profile_manager: ProfileManager, bot: Bot):
    logger.info(f"Received /profile command from user {message.from_user.id}.")
    profile = await profile_manager.get_user_profile(message.from_user)
    if not profile:
        logger.error(f"Failed to load profile for user {message.from_user.id} after /profile command.")
        await message.reply("❌ Не удалось загрузить профиль!")
        return
    
    logger.debug(f"Generating profile image for user {message.from_user.id}.")
    image_bytes = await profile_manager.generate_profile_image(message.from_user, profile, bot)
    input_file = BufferedInputFile(image_bytes.getvalue(), filename="profile.png")
    
    logger.info(f"Sending profile image to user {message.from_user.id}.")
    await message.answer_photo(
        photo=input_file,
        caption=f"Профиль пользователя {message.from_user.first_name}"
    )

@stat_router.message(F.text.lower() == "работать")
async def do_work(message: types.Message, profile_manager: ProfileManager):
    logger.info(f"Received 'работать' command from user {message.from_user.id}.")
    user_id = message.from_user.id
    current_time = time.time()
    last_work_time = await profile_manager.get_last_work_time(user_id)
    time_elapsed = current_time - last_work_time
    time_left = ProfileConfig.WORK_COOLDOWN_SECONDS - time_elapsed
    if time_elapsed < ProfileConfig.WORK_COOLDOWN_SECONDS:
        minutes_left = int(time_left // 60)
        seconds_left = int(time_left % 60)
        logger.info(f"User {user_id} tried to work, but still on cooldown. Time left: {minutes_left}m {seconds_left}s.")
        await message.reply(f"⏳ Работать можно будет через {minutes_left} мин {seconds_left} сек.")
    else:
        reward = random.randint(ProfileConfig.WORK_REWARD_MIN, ProfileConfig.WORK_REWARD_MAX)
        task = random.choice(ProfileConfig.WORK_TASKS)
        await profile_manager.update_lumcoins(user_id, reward)
        await profile_manager.update_last_work_time(user_id, current_time)
        logger.info(f"User {user_id} successfully worked, earned {reward} Lumcoins. Task: '{task}'.")
        await message.reply(f"{message.from_user.first_name} {task} и заработал(а) {reward} LUMcoins!")

@stat_router.message(F.text.lower() == "магазин")
async def show_shop(message: types.Message, profile_manager: ProfileManager):
    logger.info(f"Received 'магазин' command from user {message.from_user.id}.")
    shop_items = profile_manager.get_available_backgrounds()
    text = "🛍️ **Магазин фонов** 🛍️\\n\\n"
    text += "Напишите название фона из списка, чтобы купить его:\\n\\n"
    for key, item in shop_items.items():
        text += f"- `{key}`: {item['name']} ({item['cost']} LUMcoins)\\n"
    logger.debug(f"Shop items compiled: {shop_items}.")
    await message.reply(text, parse_mode="Markdown")
    logger.info(f"Shop list sent to user {message.from_user.id}.")

@stat_router.message(F.text.lower().in_(ProfileConfig.BACKGROUND_SHOP.keys()))
async def buy_background(message: types.Message, profile_manager: ProfileManager):
    logger.info(f"User {message.from_user.id} attempted to buy background: '{message.text.lower()}'.")
    user_id = message.from_user.id
    command = message.text.lower()
    shop_items = profile_manager.get_available_backgrounds()
    if command in shop_items:
        item = shop_items[command]
        user_coins = await profile_manager.get_lumcoins(user_id)
        logger.debug(f"User {user_id} has {user_coins} Lumcoins. Item '{item['name']}' costs {item['cost']}.")
        if user_coins >= item['cost']:
            await profile_manager.update_lumcoins(user_id, -item['cost'])
            await profile_manager.set_background(user_id, item['url'])
            logger.info(f"User {user_id} successfully bought background '{item['name']}'. New balance.")
            await message.reply(f"✅ Вы успешно приобрели фон '{item['name']}' за {item['cost']} LUMcoins!")
        else:
            logger.info(f"User {user_id} failed to buy background '{item['name']}' due to insufficient funds.")
            await message.reply(f"❌ Недостаточно LUMcoins! Цена фона '{item['name']}': {item['cost']}, у вас: {user_coins}.")
    else:
        logger.warning(f"Unexpected: User {user_id} tried to buy non-existent background '{command}'.")

@stat_router.message()
async def track_message_activity(message: types.Message, profile_manager: ProfileManager):
    logger.debug(f"Tracking message activity for user {message.from_user.id}.")
    if message.from_user.id == message.bot.id or message.content_type != types.ContentType.TEXT:
        logger.debug(f"Ignoring message from bot or non-text message for user {message.from_user.id}.")
        return
    user_id = message.from_user.id
    old_profile = await profile_manager.get_user_profile(message.from_user)
    if not old_profile:
        logger.error(f"Failed to get old profile for user_id {user_id} in track_message_activity. Aborting.")
        return
    old_level = old_profile.get('level', 1)
    old_lumcoins = old_profile.get('lumcoins', 0)
    logger.debug(f"User {user_id}: Old level {old_level}, old lumcoins {old_lumcoins}.")
    await profile_manager.record_message(message.from_user)
    new_profile = await profile_manager.get_user_profile(message.from_user)
    if not new_profile:
        logger.error(f"Failed to get new profile for user_id {user_id} after record_message. Aborting.")
        return
    new_level = new_profile.get('level', 1)
    new_lumcoins = new_profile.get('lumcoins', 0)
    lumcoins_earned_from_level = new_lumcoins - old_lumcoins
    logger.debug(f"User {user_id}: New level {new_level}, new lumcoins {new_lumcoins}, earned {lumcoins_earned_from_level} from level up.")
    if new_level > old_level and lumcoins_earned_from_level > 0:
        logger.info(f"User {user_id} leveled up to {new_level} and earned {lumcoins_earned_from_level} Lumcoins.")
        await message.reply(
            f"🎉 Поздравляю, {message.from_user.first_name}! Ты достиг(ла) Уровня {new_level}! "
            f"Награда: {lumcoins_earned_from_level} LUMcoins."
        )

def setup_stat_handlers(dp: Dispatcher, bot: Bot, profile_manager: ProfileManager):
    logger.info("Registering stat router handlers.")
    dp.include_router(stat_router)
    logger.info("Stat router included in Dispatcher.")
    return dp
