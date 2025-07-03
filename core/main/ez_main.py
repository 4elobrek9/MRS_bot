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
import ollama # Для взаимодействия с Ollama API
import aiohttp # Для асинхронных HTTP запросов (например, для анекдотов, фонов)
from bs4 import BeautifulSoup # Для парсинга HTML (анекдоты)
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

# Импорт кастомных модулей
import database as db # Модуль для работы с общей базой данных
from group_stat import setup_stat_handlers, ProfileManager # Модуль для статистики группы и профилей
from rp_module_refactored import setup_rp_handlers, periodic_hp_recovery_task # Модуль для RP-системы
import censor_module

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
VALUE_FILE_PATH = Path("data") / "value.txt"
STICKERS_CACHE_FILE = Path("data") / "stickers_cache.json"
BAD_WORDS_FILE = Path("data") / "bad_words.txt"


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

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
