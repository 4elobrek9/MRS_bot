import os
import aiosqlite
import string
import sqlite3
import time
from datetime import datetime, date, timedelta
from io import BytesIO
from typing import Optional, Dict, Any, List, Tuple
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
    FONT_PATH = "Hlobus.ttf" # Убедитесь, что этот файл шрифта присутствует в корневой директории
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
    # Константы для расчета очков топа
    POINTS_PER_10_LUMCOINS = 100
    POINTS_PER_LEVEL = 100
    POINTS_PER_HP = 0 # HP не дает очков

# Синхронная инициализация базы данных для ProfileManager
# Управляет profiles.db, который хранит данные профилей пользователей (XP, Lumcoins, сообщения и т.д.)
def init_db_sync():
    """Инициализирует базу данных profiles.db, если она не существует."""
    db_file = 'profiles.db'
    if not os.path.exists(db_file):
        conn = sqlite3.connect(db_file)
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
        logger.info(f"Database {db_file} initialized (sync).")
    else:
        logger.info(f"Database {db_file} already exists (sync check).")

# Вызываем синхронную инициализацию при импорте модуля
init_db_sync()

class ProfileManager:
    """Управляет профилями пользователей, их статистикой и генерацией изображений."""
    def __init__(self):
        self._conn = None
        self.font_cache = {}
        logger.info("ProfileManager instance created.")

    async def connect(self):
        """Устанавливает асинхронное соединение с базой данных."""
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
        """Закрывает асинхронное соединение с базой данных."""
        if self._conn is not None:
            logger.info("Closing database connection...")
            try:
                await self._conn.close()
                self._conn = None
                logger.info("Database connection closed.")
            except Exception as e:
                logger.exception("Error closing database connection:")

    async def _init_db_async(self):
        """Асинхронно инициализирует таблицы базы данных, если они не существуют."""
        if self._conn is None:
            logger.error("Cannot perform async DB init: connection is None.")
            return
        cursor = await self._conn.cursor()
        # В этой функции повторяется логика init_db_sync, но через aiosqlite,
        # что полезно для гарантии схемы при асинхронном доступе.
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

    async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
        """
        Получает профиль пользователя, создавая его, если не существует.
        Обновляет информацию о пользователе в таблице users.
        """
        if self._conn is None:
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()

        # Обновляем или вставляем данные пользователя
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
        # Вставляем или игнорируем профиль пользователя
        await cursor.execute('''
        INSERT OR IGNORE INTO user_profiles (user_id, background_url)
        VALUES (?, ?)
        ''', (user_id, ProfileConfig.DEFAULT_BG_URL))
        await self._conn.commit()

        # Получаем данные профиля
        await cursor.execute('''
        SELECT * FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        profile = await cursor.fetchone()

        if not profile:
            logger.error(f"Profile not found for user_id {user_id} after creation attempt.")
            return None

        columns = [column[0] for column in cursor.description]
        profile_data = dict(zip(columns, profile))

        # Добавляем имя пользователя из таблицы users
        await cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
        user_data = await cursor.fetchone()
        if user_data:
             profile_data['username'] = f"@{user_data[0]}" if user_data[0] else user_data[1]
        else:
             profile_data['username'] = user.first_name # Fallback, если по каким-то причинам нет данных в users

        # Применяем кастомный фон, если установлен
        await cursor.execute('SELECT background_url FROM backgrounds WHERE user_id = ?', (user_id,))
        custom_bg = await cursor.fetchone()
        if custom_bg:
            profile_data['background_url'] = custom_bg[0]
        # Если custom_bg нет, background_url уже будет ProfileConfig.DEFAULT_BG_URL из INSERT OR IGNORE

        return profile_data

    async def record_message(self, user: types.User) -> None:
        """
        Записывает отправку сообщения пользователем, обновляет EXP, уровень и Lumcoins.
        """
        if self._conn is None:
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

        total_messages += 1
        daily_messages_increment = 1 # Предполагается, что daily_messages будет сбрасываться внешней задачей

        exp_added = 0
        if total_messages > 0 and total_messages % ProfileConfig.EXP_PER_MESSAGE_INTERVAL == 0:
             exp_added = ProfileConfig.EXP_AMOUNT_PER_INTERVAL

        new_exp = exp + exp_added
        new_level = level
        new_lumcoins = lumcoins

        # Логика повышения уровня
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
        """Рассчитывает количество опыта, необходимое для перехода на следующий уровень."""
        if level < 1:
            return 0
        base_exp = 100
        coefficient = 2
        multiplier = 5
        return base_exp + (level ** coefficient) * multiplier

    def _get_lumcoins_for_level(self, level: int) -> int:
        """Определяет количество Lumcoins, получаемых за достижение уровня."""
        for lvl, coins in sorted(ProfileConfig.LUMCOINS_PER_LEVEL.items(), reverse=True):
            if level >= lvl:
                return coins
        return 1 # По умолчанию 1 Lumcoin за уровень

    async def generate_profile_image(self, user: types.User, profile: Dict[str, Any]) -> BytesIO:
        """Генерирует изображение профиля пользователя."""
        exp_bar_width = 250
        exp_bar_height = 30

        # Загрузка шрифтов
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

        # Загрузка фонового изображения
        bg_url = profile.get('background_url', ProfileConfig.DEFAULT_BG_URL)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(bg_url) as resp:
                    resp.raise_for_status() # Вызывает исключение для HTTP ошибок
                    bg_image_data = await resp.read()
            bg_image = Image.open(BytesIO(bg_image_data)).convert("RGBA")
            bg_image = bg_image.resize((600, 200)) # Фиксированный размер для профиля
            overlay = Image.new('RGBA', bg_image.size, (0, 0, 0, 0)) # Прозрачный слой для текста
            draw = ImageDraw.Draw(overlay)

            # Получение данных профиля
            level = profile.get('level', 1)
            exp = profile.get('exp', 0)
            lumcoins = profile.get('lumcoins', 0)
            hp = profile.get('hp', 100) # HP берется из профиля, но оно не обновляется этим модулем
            total_messages = profile.get('total_messages', 0)
            flames = profile.get('flames', 0)
            username = profile.get('username', user.first_name) # Имя пользователя для отображения

            # Форматирование текста
            user_info_text = f"{username}"
            level_text = f"Уровень: {level}"
            needed_exp_for_next_level = self._get_exp_for_level(level)
            if level < ProfileConfig.MAX_LEVEL:
                display_exp = min(exp, needed_exp_for_next_level) if needed_exp_for_next_level > 0 else exp
                exp_text = f"Опыт: {display_exp} / {needed_exp_for_next_level}"
            else:
                exp_text = f"Опыт: {exp} (МАКС)"
            money_text = f"💎 {lumcoins}"
            hp_text = f"❤️ HP: {hp}/{ProfileConfig.MAX_HP}"
            flames_text = f"🔥 {flames}"
            messages_text = f"✉️ {total_messages}"

            def draw_text_with_shadow(draw_obj, position, text, font, text_color, shadow_color, shadow_offset=(1, 1)):
                """Вспомогательная функция для рисования текста с тенью."""
                shadow_pos = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
                draw_obj.text(shadow_pos, text, font=font, fill=shadow_color)
                draw_obj.text(position, text, font=font, fill=text_color)

            # Позиционирование и отрисовка текста
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
                hp_color = ProfileConfig.HP_COLORS.get("low", (128, 0, 0)) # Особый цвет для 0 HP
            draw_text_with_shadow(draw, hp_pos, hp_text, font_medium, hp_color, ProfileConfig.TEXT_SHADOW)

            # Отрисовка полосы опыта
            exp_bar_pos = ProfileConfig.EXP_BAR_OFFSET
            current_exp_percentage = 0.0
            if level < ProfileConfig.MAX_LEVEL and needed_exp_for_next_level > 0:
                current_exp_percentage = min(exp / needed_exp_for_next_level, 1.0)
            elif level == ProfileConfig.MAX_LEVEL:
                current_exp_percentage = 1.0
            exp_bar_fill_width = int(exp_bar_width * current_exp_percentage)

            draw.rectangle([exp_bar_pos, (exp_bar_pos[0] + exp_bar_width, exp_bar_pos[1] + exp_bar_height)], fill=(50, 50, 50, 128)) # Фон полосы
            if exp_bar_fill_width > 0:
                draw.rectangle([exp_bar_pos, (exp_bar_pos[0] + exp_bar_fill_width, exp_bar_pos[1] + exp_bar_height)], fill=(0, 255, 0, 192)) # Заполнение полосы

            exp_text_bbox = draw.textbbox((0,0), exp_text, font=font_small)
            exp_text_height = exp_text_bbox[3] - exp_text_bbox[1]
            exp_text_pos_x = exp_bar_pos[0]
            exp_text_pos_y = exp_bar_pos[1] - exp_text_height - 2
            draw_text_with_shadow(draw, (exp_text_pos_x, exp_text_pos_y), exp_text, font_small, ProfileConfig.TEXT_COLOR, ProfileConfig.TEXT_SHADOW)

            # Отрисовка Lumcoins, Flames, Messages (справа)
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
            # Fallback для генерации изображения с ошибкой
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
        """Обновляет количество Lumcoins пользователя."""
        if self._conn is None:
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        UPDATE user_profiles
        SET lumcoins = lumcoins + ?
        WHERE user_id = ?
        ''', (amount, user_id))
        await self._conn.commit()

    async def get_lumcoins(self, user_id: int) -> int:
        """Получает текущее количество Lumcoins пользователя."""
        if self._conn is None:
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        SELECT lumcoins FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

    async def set_background(self, user_id: int, background_url: str):
        """Устанавливает фоновое изображение профиля пользователя."""
        if self._conn is None:
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        INSERT OR REPLACE INTO backgrounds (user_id, background_url)
        VALUES (?, ?)
        ''', (user_id, background_url))
        await self._conn.commit()

    def get_available_backgrounds(self) -> Dict[str, Dict[str, Any]]:
        """Возвращает список доступных фонов для покупки."""
        return ProfileConfig.BACKGROUND_SHOP

    async def get_last_work_time(self, user_id: int) -> float:
        """Получает время последнего выполнения работы пользователем."""
        if self._conn is None:
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        SELECT last_work_time FROM user_profiles WHERE user_id = ?
        ''', (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0.0

    async def update_last_work_time(self, user_id: int, timestamp: float):
        """Обновляет время последнего выполнения работы пользователем."""
        if self._conn is None:
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()
        await cursor.execute('''
        UPDATE user_profiles
        SET last_work_time = ?
        WHERE user_id = ?
        ''', (timestamp, user_id))
        await self._conn.commit()

    # --- Методы для работы с топами ---

    async def get_top_users_by_score(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получает топ пользователей по комплексной системе очков.
        Очки: (Lumcoins / 10 * 100) + (Уровень * 100) + (HP * 0).
        """
        if self._conn is None:
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()

        # Выбираем необходимые поля и вычисляем score прямо в запросе
        query = f"""
            SELECT
                up.user_id,
                u.username,
                u.first_name,
                up.level,
                up.lumcoins,
                (CAST(up.lumcoins AS REAL) / 10 * {ProfileConfig.POINTS_PER_10_LUMCOINS}) +
                (up.level * {ProfileConfig.POINTS_PER_LEVEL}) AS score
            FROM user_profiles up
            JOIN users u ON up.user_id = u.user_id
            ORDER BY score DESC
            LIMIT ?
        """
        await cursor.execute(query, (limit,))
        rows = await cursor.fetchall()
        
        columns = [description[0] for description in cursor.description]
        top_users = []
        for row in rows:
            user_data = dict(zip(columns, row))
            user_data['display_name'] = f"@{user_data['username']}" if user_data['username'] else user_data['first_name']
            top_users.append(user_data)
        return top_users

    async def get_top_users_by_total_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получает топ пользователей по общему количеству отправленных сообщений.
        """
        if self._conn is None:
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()

        query = """
            SELECT
                up.user_id,
                u.username,
                u.first_name,
                up.total_messages
            FROM user_profiles up
            JOIN users u ON up.user_id = u.user_id
            ORDER BY up.total_messages DESC
            LIMIT ?
        """
        await cursor.execute(query, (limit,))
        rows = await cursor.fetchall()

        columns = [description[0] for description in cursor.description]
        top_users = []
        for row in rows:
            user_data = dict(zip(columns, row))
            user_data['display_name'] = f"@{user_data['username']}" if user_data['username'] else user_data['first_name']
            top_users.append(user_data)
        return top_users

    async def get_top_users_by_daily_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Получает топ пользователей по количеству сообщений за текущий день.
        Важно: для корректной работы 'daily_messages' должно сбрасываться ежедневно.
        """
        if self._conn is None:
            raise RuntimeError("Database connection is not established.")
        cursor = await self._conn.cursor()

        query = """
            SELECT
                up.user_id,
                u.username,
                u.first_name,
                up.daily_messages
            FROM user_profiles up
            JOIN users u ON up.user_id = u.user_id
            ORDER BY up.daily_messages DESC
            LIMIT ?
        """
        await cursor.execute(query, (limit,))
        rows = await cursor.fetchall()

        columns = [description[0] for description in cursor.description]
        top_users = []
        for row in rows:
            user_data = dict(zip(columns, row))
            user_data['display_name'] = f"@{user_data['username']}" if user_data['username'] else user_data['first_name']
            top_users.append(user_data)
        return top_users


@stat_router.message(F.text.lower().startswith(("профиль", "/профиль")))
async def show_profile(message: types.Message, profile_manager: ProfileManager):
    """Обработчик команды для показа профиля пользователя."""
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
    """Обработчик команды 'работать' для получения Lumcoins."""
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
    """Обработчик команды 'магазин' для отображения доступных фонов."""
    shop_items = profile_manager.get_available_backgrounds()
    text = "🛍️ **Магазин фонов** 🛍️\n\n"
    text += "Напишите название фона из списка, чтобы купить его:\n\n"
    for key, item in shop_items.items():
        text += f"- `{key}`: {item['name']} ({item['cost']} LUMcoins)\n"
    await message.reply(text, parse_mode="Markdown")

@stat_router.message(F.text.lower().in_(ProfileConfig.BACKGROUND_SHOP.keys()))
async def buy_background(message: types.Message, profile_manager: ProfileManager):
    """Обработчик для покупки фонового изображения."""
    user_id = message.from_user.id
    command = message.text.lower()
    shop_items = profile_manager.get_available_backgrounds()

    if command in shop_items:
        item = shop_items[command]
        user_coins = await profile_manager.get_lumcoins(user_id)
        if user_coins >= item['cost']:
            await profile_manager.update_lumcoins(user_id, -item['cost']) # Снимаем стоимость
            await profile_manager.set_background(user_id, item['url']) # Устанавливаем новый фон
            await message.reply(f"✅ Вы успешно приобрели фон '{item['name']}' за {item['cost']} LUMcoins!")
        else:
            await message.reply(f"❌ Недостаточно LUMcoins! Цена фона '{item['name']}': {item['cost']}, у вас: {user_coins}.")

@stat_router.message()
async def track_message_activity(message: types.Message, profile_manager: ProfileManager):
    """
    Отслеживает активность сообщений пользователя и обновляет его профиль.
    Уведомляет пользователя о повышении уровня.
    """
    # Игнорируем сообщения от самого бота и нетекстовые сообщения
    if message.from_user.id == message.bot.id or message.content_type != types.ContentType.TEXT:
         return

    user_id = message.from_user.id
    
    # Получаем старый профиль для сравнения уровня
    old_profile = await profile_manager.get_user_profile(message.from_user)
    if not old_profile:
         logger.error(f"Failed to get old profile for user_id {user_id} in track_message_activity.")
         return

    old_level = old_profile.get('level', 1)
    old_lumcoins = old_profile.get('lumcoins', 0)

    # Записываем сообщение в профиль
    await profile_manager.record_message(message.from_user)

    # Получаем обновленный профиль
    new_profile = await profile_manager.get_user_profile(message.from_user)
    if not new_profile:
        logger.error(f"Failed to get new profile for user_id {user_id} after record_message.")
        return

    new_level = new_profile.get('level', 1)
    new_lumcoins = new_profile.get('lumcoins', 0)

    # Вычисляем Lumcoins, заработанные за повышение уровня
    lumcoins_earned_from_level = new_lumcoins - old_lumcoins

    # Если уровень повысился и были заработаны Lumcoins за уровень, отправляем уведомление
    if new_level > old_level and lumcoins_earned_from_level > 0:
        await message.reply(
            f"🎉 Поздравляю, {message.from_user.first_name}! Ты достиг(ла) Уровня {new_level}! "
            f"Награда: {lumcoins_earned_from_level} LUMcoins."
        )

# --- НОВЫЕ ОБРАБОТЧИКИ ТОПОВ ---

@stat_router.message(Command("top", "лидеры"))
async def show_top_score(message: types.Message, profile_manager: ProfileManager):
    """
    Показывает топ пользователей по общей системе очков.
    Очки: Lumcoins / 10 * 100 + Уровень * 100.
    """
    top_users = await profile_manager.get_top_users_by_score(limit=10)
    
    if not top_users:
        await message.reply("Пока нет данных для топа по очкам.")
        return

    response_text = "🏆 **Топ по очкам** 🏆\n\n"
    for i, user_data in enumerate(top_users):
        username = user_data['display_name']
        score = int(user_data['score']) # Очки могут быть float, округляем для вывода
        level = user_data['level']
        lumcoins = user_data['lumcoins']
        response_text += (
            f"**{i+1}. {username}**\n"
            f"   Очки: `{score}` | Уровень: `{level}` | Lumcoins: `{lumcoins}`\n"
        )
    
    await message.reply(response_text, parse_mode="Markdown")

@stat_router.message(Command("top_messages", "топ_сообщений"))
async def show_top_total_messages(message: types.Message, profile_manager: ProfileManager):
    """
    Показывает топ пользователей по общему количеству отправленных сообщений.
    """
    top_users = await profile_manager.get_top_users_by_total_messages(limit=10)

    if not top_users:
        await message.reply("Пока нет данных для топа по сообщениям.")
        return

    response_text = "✉️ **Топ по сообщениям (общее)** ✉️\n\n"
    for i, user_data in enumerate(top_users):
        username = user_data['display_name']
        total_messages = user_data['total_messages']
        response_text += (
            f"**{i+1}. {username}**: `{total_messages}` сообщений\n"
        )
    
    await message.reply(response_text, parse_mode="Markdown")

@stat_router.message(Command("top_daily_messages", "топ_сообщений_за_день"))
async def show_top_daily_messages(message: types.Message, profile_manager: ProfileManager):
    """
    Показывает топ пользователей по количеству сообщений за текущий день.
    Напоминание: daily_messages должен сбрасываться ежедневно внешней задачей.
    """
    top_users = await profile_manager.get_top_users_by_daily_messages(limit=10)

    if not top_users:
        await message.reply("Пока нет данных для топа по сообщениям за день.")
        return

    response_text = "🗓️ **Топ по сообщениям за день** 🗓️\n\n"
    for i, user_data in enumerate(top_users):
        username = user_data['display_name']
        daily_messages = user_data['daily_messages']
        response_text += (
            f"**{i+1}. {username}**: `{daily_messages}` сообщений\n"
        )
    
    await message.reply(response_text, parse_mode="Markdown")


def setup_stat_handlers(dp: Dispatcher, bot: Bot, profile_manager: ProfileManager):
    """
    Настраивает обработчики группы статистики, включая их в главный диспетчер.
    """
    dp.include_router(stat_router)
    logger.info("Stat router included.")
    # profile_manager.bot = bot # Если ProfileManager требует доступа к боту, можно передать так
    return dp
