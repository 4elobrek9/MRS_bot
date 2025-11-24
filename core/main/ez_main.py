import os
import json
import random
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from contextlib import suppress
import logging
import logging.handlers # Импортируем модуль для обработчиков логирования
import aiosqlite
import dotenv
import ollama # Для взаимодействия с Ollama API
import aiohttp # Для асинхронных HTTP запросов (например, для анекдотов, фонов)
from bs4 import BeautifulSoup # Для парсинга HTML (анекдоты)
from aiogram import Bot, Dispatcher, F, types, Router # <--- ИЗМЕНЕНИЕ: Добавлен импорт Router
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
# Загрузка переменных окружения из .env файла
dotenv.load_dotenv()

# Получение токена бота из переменных окружения
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    # Используем print, так как логирование еще не настроено
    print("CRITICAL: Bot token not found in environment variables. Please set the TOKEN variable.")
    exit(1)

# Конфигурация для Ollama
OLLAMA_API_BASE_URL = os.getenv("OLLAMA_API_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "llama3")

# Определение базовой директории скрипта
# Это гарантирует, что пути к файлам данных будут корректными независимо от того,
# из какой директории запускается скрипт.
# core/main/ez_main.py -> core/main/ -> core/ -> MRS_bot/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Пути к файлам данных, теперь относительно BASE_DIR
JOKES_CACHE_FILE = BASE_DIR / "data" / "jokes_cache.json"
VALUE_FILE_PATH = BASE_DIR / "data" / "value.txt"
STICKERS_CACHE_FILE = BASE_DIR / "data" / "stickers_cache.json"
BAD_WORDS_FILE = BASE_DIR / "data" / "bad_words.txt"

# *** ИЗМЕНЕНИЕ: Настройка логирования в файл ***
LOGS_DIR = BASE_DIR / "logs"
LOG_FILE_PATH = LOGS_DIR / "bot.log" # Имя файла логов

# Создаем директорию для логов, если она не существует
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Настройка базового логирования
logging.basicConfig(
    level=logging.DEBUG, # Устанавливаем уровень DEBUG для подробных логов
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(), # Вывод логов в консоль
        logging.handlers.RotatingFileHandler( # Вывод логов в файл с ротацией
            filename=LOG_FILE_PATH,
            maxBytes=10485760, # 10 MB
            backupCount=5,     # Хранить до 5 старых файлов логов
            encoding='utf-8'
        )
    ]
)
logger = logging.getLogger(__name__) # Получаем логгер после настройки basicConfig

# Глобальные переменные для админа и канала анекдотов
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID")
ADMIN_USER_ID: Optional[int] = None
if ADMIN_USER_ID_STR and ADMIN_USER_ID_STR.isdigit():
    ADMIN_USER_ID = int(ADMIN_USER_ID_STR)
else:
    logger.warning("ADMIN_USER_ID is not set or invalid. Dislike forwarding will be disabled.")

CHANNEL_ID_STR = os.getenv("CHANNEL_ID")
CHANNEL_ID: Optional[int] = None
if CHANNEL_ID_STR:
    try:
        CHANNEL_ID = int(CHANNEL_ID_STR)
    except ValueError:
        logger.warning("CHANNEL_ID is not set or invalid. Jokes task will be disabled.")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
