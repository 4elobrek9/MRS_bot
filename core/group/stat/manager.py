import asyncio
import time
import random
import logging
import os
import sqlite3
from pathlib import Path
from io import BytesIO
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

import aiosqlite
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps
from aiogram import types, Bot

from core.group.stat.config import ProfileConfig
from core.group.stat.shop_config import ShopConfig
from database import get_user_rp_stats, add_item_to_inventory, get_user_inventory
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
        if self._conn is None: 
            raise RuntimeError("DB not connected")
        
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
                active_background TEXT DEFAULT 'default',
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        await self._conn.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)')
        
        await self._conn.execute('''
            CREATE TABLE IF NOT EXISTS user_activity_log (
                user_id INTEGER,
                date TEXT,
                exp_gained INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date),
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
            )
        ''')
        
        try:
            await self._conn.execute('SELECT last_activity_date FROM user_profiles LIMIT 1')
            logger.debug("Column last_activity_date already exists in user_profiles table.")
        except Exception:
            logger.debug("Adding last_activity_date column to user_profiles table.")
            await self._conn.execute('ALTER TABLE user_profiles ADD COLUMN last_activity_date TEXT')
        
        await self._conn.commit()

    async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
        if self._conn is None:
            logger.error("Profiles database connection is not established.")
            return None
        
        user_id = user.id
        try:
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
                logger.debug(f"Retrieved profile for user {user_id}, active_background: {profile_data.get('active_background')}")
                return profile_data
            return None
        except Exception as e:
            logger.error(f"Error getting user profile for {user_id}: {e}")
            return None

    async def record_message(self, user: types.User) -> None:
        if self._conn is None: 
            raise RuntimeError("DB not connected")
        
        user_id = user.id
        current_time = time.time()
        current_date = datetime.now().date().isoformat()

        # Ensure user exists
        await self._conn.execute(
            'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
            (user_id, user.username, user.first_name)
        )
        await self._conn.commit()

        # Get current profile data
        cursor = await self._conn.execute(
            'SELECT level, exp, lumcoins, daily_messages, total_messages, flames, last_activity_date FROM user_profiles WHERE user_id = ?',
            (user_id,)
        )
        profile_data = await cursor.fetchone()

        if profile_data:    
            level, exp, lumcoins, daily_messages, total_messages, flames, last_activity_date = profile_data
            
            # Reset daily messages and handle flames logic if it's a new day
            if last_activity_date != current_date:
                daily_messages = 0
                
                # Calculate yesterday's date
                yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
                
                # If user was active yesterday, increase flames
                if last_activity_date == yesterday:
                    flames += 1
                else:
                    # If missed a day, reset flames to 1 (for today's activity)
                    flames = 1
            
            # Add XP and increment message counters
            total_messages += 1
            daily_messages += 1
            
            # Начисляем EXP только за каждое 10-е сообщение
            if total_messages % ProfileConfig.EXP_PER_MESSAGES_COUNT == 0:
                exp_gained = ProfileConfig.EXP_PER_MESSAGE_INTERVAL
                exp += exp_gained
                
                # Логика повышения уровня
                new_level = level
                while exp >= ProfileConfig.LEVEL_UP_EXP_REQUIREMENT(new_level):
                    exp -= ProfileConfig.LEVEL_UP_EXP_REQUIREMENT(new_level)
                    new_level += 1
                    lumcoins += ProfileConfig.LUMCOINS_PER_LEVEL.get(new_level, 0)
                
                # Обновляем уровень и EXP
                level = new_level
                
                # Логируем начисление EXP
                await self._conn.execute(
                    'INSERT OR REPLACE INTO user_activity_log (user_id, date, exp_gained) VALUES (?, ?, ?)',
                    (user_id, current_date, exp_gained)
                )
            
            # Обновляем профиль
            await self._conn.execute(
                '''UPDATE user_profiles 
                SET level = ?, exp = ?, lumcoins = ?, daily_messages = ?, total_messages = ?, flames = ?, last_activity_date = ?
                WHERE user_id = ?''',
                (level, exp, lumcoins, daily_messages, total_messages, flames, current_date, user_id)
            )
        else:
            # Создаем новый профиль
            await self._conn.execute(
                '''INSERT INTO user_profiles 
                (user_id, level, exp, lumcoins, daily_messages, total_messages, flames, last_work_time, active_background, last_activity_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (user_id, 1, 0, 0, 1, 1, 1, 0, 'default', current_date)  # EXP начинается с 0
            )
        
        await self._conn.commit()



    async def update_lumcoins(self, user_id: int, amount: int) -> None:
        if self._conn is None: 
            raise RuntimeError("DB not connected")
        await self._conn.execute('UPDATE user_profiles SET lumcoins = lumcoins + ? WHERE user_id = ?', (amount, user_id))
        await self._conn.commit()
        logger.info(f"User {user_id} Lumcoins updated by {amount}.")

    async def get_lumcoins(self, user_id: int) -> int:
        if self._conn is None: 
            raise RuntimeError("DB not connected")
        cursor = await self._conn.execute('SELECT lumcoins FROM user_profiles WHERE user_id = ?', (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0

    async def set_user_background(self, user_id: int, background_key: str) -> None:
        """Устанавливает активный фон для пользователя."""
        if self._conn is None: 
            raise RuntimeError("DB not connected")
        
        # Проверяем, что фон существует в магазине или это фон по умолчанию
        available_backgrounds = self.get_available_backgrounds()
        if background_key != 'default' and background_key not in available_backgrounds:
            logger.warning(f"Background '{background_key}' not found in available backgrounds.")
            return
        
        try:
            # Обновляем активный фон в базе профилей
            await self._conn.execute(
                'UPDATE user_profiles SET active_background = ? WHERE user_id = ?',
                (background_key, user_id)
            )
            await self._conn.commit()
            logger.info(f"User {user_id} active background set to '{background_key}' in profiles database.")
            
            # Также обновляем в основной базе данных
            await set_user_active_background(user_id, background_key)
            
        except Exception as e:
            logger.error(f"Error setting background for user {user_id}: {e}")

    async def get_last_work_time(self, user_id: int) -> float:
        if self._conn is None: 
            raise RuntimeError("DB not connected")
        cursor = await self._conn.execute('SELECT last_work_time FROM user_profiles WHERE user_id = ?', (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 0.0

    async def update_last_work_time(self, user_id: int, timestamp: float):
        if self._conn is None: 
            raise RuntimeError("DB not connected")
        await self._conn.execute('UPDATE user_profiles SET last_work_time = ? WHERE user_id = ?', (timestamp, user_id))
        await self._conn.commit()

    async def get_top_users_by_level(self, limit: int = 10) -> List[Dict[str, Any]]:
        if self._conn is None: 
            raise RuntimeError("DB not connected")
        cursor = await self._conn.execute('''
            SELECT u.username, u.first_name, up.level, up.exp
            FROM user_profiles up JOIN users u ON up.user_id = u.user_id
            ORDER BY up.level DESC, up.exp DESC LIMIT ?
        ''', (limit,))
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        
        results = []
        for row in rows:
            user_data = {columns[i]: row[i] for i in range(len(columns))}
            user_data['display_name'] = user_data.get('username') or user_data.get('first_name')
            results.append(user_data)
        return results

    async def get_top_users_by_lumcoins(self, limit: int = 10) -> List[Dict[str, Any]]:
        if self._conn is None: 
            raise RuntimeError("DB not connected")
        cursor = await self._conn.execute('''
            SELECT u.username, u.first_name, up.lumcoins
            FROM user_profiles up JOIN users u ON up.user_id = u.user_id
            ORDER BY up.lumcoins DESC LIMIT ?
        ''', (limit,))
        rows = await cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        
        results = []
        for row in rows:
            user_data = {columns[i]: row[i] for i in range(len(columns))}
            user_data['display_name'] = user_data.get('username') or user_data.get('first_name')
            results.append(user_data)
        return results

    def get_available_backgrounds(self) -> Dict[str, Any]:
        return ShopConfig.SHOP_BACKGROUNDS

    async def get_user_backgrounds_inventory(self, user_id: int) -> List[str]:
        return await get_user_inventory(user_id, 'background')

    async def generate_profile_image(self, user: types.User, profile_data: Dict[str, Any], bot: Bot) -> BytesIO:
        logger.debug(f"Starting profile image generation for user {user.id}.")

        active_background_key = profile_data.get('active_background', 'default')
        logger.debug(f"Active background key: {active_background_key}")
        
        background_info = ShopConfig.SHOP_BACKGROUNDS.get(active_background_key)
        logger.debug(f"Background info: {background_info}")
        
        background_image = None
        
# Замените этот блок кода:
        if background_info and background_info.get('url'):
            background_url = background_info['url']
            try:
                # Пробуем разные возможные пути
                possible_paths = [
                    Path(__file__).parent.parent.parent / background_url,  # MRS_bot-4/background/
                    Path(__file__).parent / background_url,  # core/group/stat/background/
                    Path("background") / background_url.split("/")[-1]  # просто папка background/
                ]
                
                background_path = None
                for path in possible_paths:
                    if path.exists():
                        background_path = path
                        break
                
                if background_path and background_path.exists():
                    background_image = Image.open(background_path).convert("RGBA")
                    logger.debug(f"Loaded background from local file: {background_path}")
                else:
                    logger.warning(f"Background file not found at any path: {background_url}")
                    background_image = Image.open(ProfileConfig.DEFAULT_LOCAL_BG_PATH).convert("RGBA")
                    
            except Exception as e:
                logger.error(f"Error loading background image: {e}")
                background_image = Image.open(ProfileConfig.DEFAULT_LOCAL_BG_PATH).convert("RGBA")

            background_image = background_image.resize((ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT))
            card = Image.new("RGBA", (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), (0, 0, 0, 0))
            mask = Image.new("L", (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.rounded_rectangle([(0, 0), (ProfileConfig.CARD_WIDTH, ProfileConfig.CARD_HEIGHT)],
                                        radius=ProfileConfig.CARD_RADIUS, fill=255)
            card.paste(background_image, (0, 0), mask)
            draw = ImageDraw.Draw(card)

            def get_font(size, font_path=ProfileConfig.FONT_PATH):
                if (font_path, size) not in self.font_cache:
                    try:
                        font = ImageFont.truetype(font_path, size)
                    except IOError:
                        font = ImageFont.load_default()
                    self.font_cache[(font_path, size)] = font
                return self.font_cache[(font_path, size)]

            font_username = get_font(30)
            font_stats_label = get_font(20)
            font_stats_value = get_font(22)
            font_level_exp = get_font(18)
            font_hp_lum = get_font(22)

            avatar_image = None
            
            try:
                user_profile_photos = await bot.get_user_profile_photos(user.id, limit=1)
                if user_profile_photos.total_count > 0:
                    photo = user_profile_photos.photos[0][-1]
                    file = await bot.get_file(photo.file_id)
                    avatar_bytes = await bot.download_file(file.file_path)
                    avatar_image = Image.open(BytesIO(avatar_bytes.getvalue())).convert("RGBA")
                else:
                    raise Exception("No profile photo")
            except Exception:
                default_avatar_path = Path(__file__).parent.parent.parent / "background" / "default_avatar.png"
                if default_avatar_path.exists():
                    avatar_image = Image.open(default_avatar_path).convert("RGBA")
                else:
                    avatar_image = Image.new("RGBA", (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), (200, 200, 200, 255))
                    draw_avatar = ImageDraw.Draw(avatar_image)
                    try:
                        font = ImageFont.truetype(ProfileConfig.FONT_PATH, 40)
                    except:
                        font = ImageFont.load_default()
                    initial = user.first_name[0].upper() if user.first_name else "U"
                    draw_avatar.text((ProfileConfig.AVATAR_SIZE//2, ProfileConfig.AVATAR_SIZE//2), 
                                initial, fill=(0, 0, 0, 255), font=font, anchor="mm")

            avatar_image = avatar_image.resize((ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE))
            avatar_mask = Image.new("L", (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE), 0)
            draw_avatar_mask = ImageDraw.Draw(avatar_mask)
            draw_avatar_mask.ellipse([(0, 0), (ProfileConfig.AVATAR_SIZE, ProfileConfig.AVATAR_SIZE)], fill=255)
            card.paste(avatar_image, ProfileConfig.AVATAR_OFFSET, avatar_mask)

            username_text = f"@{user.username}" if user.username else user.first_name
            draw.text((ProfileConfig.TEXT_BLOCK_LEFT_X, ProfileConfig.USERNAME_Y), username_text,
                    fill=ProfileConfig.TEXT_COLOR, font=font_username,
                    stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)

            hp_current = profile_data.get('hp', 100)
            hp_max = ProfileConfig.MAX_HP
            lumcoins = profile_data.get('lumcoins', 0)

            hp_text = f"HP: {hp_current}/{hp_max}"
            hp_x = ProfileConfig.AVATAR_X + ProfileConfig.AVATAR_SIZE + ProfileConfig.MARGIN // 2
            hp_y = ProfileConfig.USERNAME_Y + 40
            draw.text((hp_x, hp_y), hp_text, fill=ProfileConfig.TEXT_COLOR, font=font_hp_lum,
                    stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)

            lumcoins_text = f"LUM: {lumcoins}"
            lumcoins_y = hp_y + 30
            draw.text((hp_x, lumcoins_y), lumcoins_text, fill=ProfileConfig.TEXT_COLOR, font=font_hp_lum,
                    stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)

            level = profile_data.get('level', 1)
            exp = profile_data.get('exp', 0)
            exp_needed_for_next_level = 100
            exp_percentage = exp / exp_needed_for_next_level if exp_needed_for_next_level > 0 else 0

            exp_bar_x = ProfileConfig.MARGIN
            exp_bar_y = ProfileConfig.CARD_HEIGHT - ProfileConfig.MARGIN - ProfileConfig.EXP_BAR_HEIGHT
            exp_bar_width = ProfileConfig.CARD_WIDTH - (ProfileConfig.MARGIN * 2) - 80
            exp_bar_height = ProfileConfig.EXP_BAR_HEIGHT

            draw.rounded_rectangle(
                [(exp_bar_x, exp_bar_y), (exp_bar_x + exp_bar_width, exp_bar_y + exp_bar_height)],
                radius=exp_bar_height // 2,
                fill=(100, 100, 100, ProfileConfig.EXP_BAR_ALPHA)
            )

            for i in range(int(exp_bar_width * exp_percentage)):
                r = int(ProfileConfig.EXP_GRADIENT_START[0] + (ProfileConfig.EXP_GRADIENT_END[0] - ProfileConfig.EXP_GRADIENT_START[0]) * (i / (exp_bar_width * exp_percentage + 1e-6)))
                g = int(ProfileConfig.EXP_GRADIENT_START[1] + (ProfileConfig.EXP_GRADIENT_END[1] - ProfileConfig.EXP_GRADIENT_START[1]) * (i / (exp_bar_width * exp_percentage + 1e-6)))
                b = int(ProfileConfig.EXP_GRADIENT_START[2] + (ProfileConfig.EXP_GRADIENT_END[2] - ProfileConfig.EXP_GRADIENT_START[2]) * (i / (exp_bar_width * exp_percentage + 1e-6)))
                draw.line([(exp_bar_x + i, exp_bar_y), (exp_bar_x + i, exp_bar_y + exp_bar_height)], fill=(r, g, b, ProfileConfig.EXP_BAR_ALPHA))

            exp_text = f"Уровень: {level} | EXP: {exp}/{exp_needed_for_next_level}"
            bbox = draw.textbbox((0, 0), exp_text, font=font_level_exp)
            text_width = bbox[2] - bbox[0]
            exp_text_x = exp_bar_x + (exp_bar_width - text_width) // 2
            exp_text_y = exp_bar_y + (exp_bar_height - (bbox[3] - bbox[1])) // 2
            draw.text((exp_text_x, exp_text_y), exp_text, fill=ProfileConfig.TEXT_COLOR, font=font_level_exp,
                    stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)

            stats = [
                ("Сообщения (день):", profile_data.get('daily_messages', 0)),
                ("Сообщения (всего):", profile_data.get('total_messages', 0)),
                ("Пламя:", profile_data.get('flames', 0)),
                # ("Уровень:", profile_data.get('level', 1)),
                # ("Опыт:", f"{profile_data.get('exp', 0)}/{ProfileConfig.LEVEL_UP_EXP_REQUIREMENT(profile_data.get('level', 1))}"),
                ("Lumcoins:", profile_data.get('lumcoins', 0))
            ]

            current_y = ProfileConfig.RIGHT_COLUMN_TOP_Y
            for label, value in stats:
                bbox = draw.textbbox((0, 0), label, font=font_stats_label)
                label_text_width = bbox[2] - bbox[0]
                draw.text((ProfileConfig.RIGHT_COLUMN_X - label_text_width, current_y), label,
                        fill=ProfileConfig.TEXT_COLOR, font=font_stats_label,
                        stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)
                
                value_text = str(value)
                bbox = draw.textbbox((0, 0), value_text, font=font_stats_value)
                value_text_width = bbox[2] - bbox[0]
                draw.text((ProfileConfig.RIGHT_COLUMN_X - value_text_width, current_y + 25), value_text,
                        fill=ProfileConfig.TEXT_COLOR, font=font_stats_value,
                        stroke_width=1, stroke_fill=ProfileConfig.TEXT_SHADOW_COLOR)
                
                current_y += ProfileConfig.ITEM_SPACING_Y

            img_byte_arr = BytesIO()
            card.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            logger.debug(f"Profile image generated for user {user.id}.")
            return img_byte_arr
    
    async def sync_profiles_with_main_db(self):
            if self._conn is None:
                return
                
            try:
                cursor = await self._conn.execute('SELECT user_id, active_background FROM user_profiles')
                profiles = await cursor.fetchall()
                
                for user_id, active_background in profiles:
                    await set_user_active_background(user_id, active_background)
                    
                logger.info(f"Synced {len(profiles)} profiles with main database")
            except Exception as e:
                logger.error(f"Error syncing profiles with main database: {e}")

# Оставьте эту функцию вне класса
async def set_user_active_background(user_id: int, background_key: str) -> None:
    """Устанавливает активный фон для пользователя в основной базе данных."""
    from database import set_user_active_background as set_bg_main_db
    await set_bg_main_db(user_id, background_key)


async def set_user_active_background(user_id: int, background_key: str) -> None:
    """Устанавливает активный фон для пользователя в основной базе данных."""
    # Импортируем здесь, чтобы избежать циклического импорта
    from database import set_user_active_background as set_bg_main_db
    await set_bg_main_db(user_id, background_key)