import os
import json
import random
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from contextlib import suppress
import logging
import aiosqlite # Хотя напрямую может и не использоваться, но db импортирует его
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
import time # Для работы с временными метками (например, кулдауны)

# Импорт кастомных модулей
import database as db # Модуль для работы с общей базой данных
from group_stat import setup_stat_handlers, ProfileManager # Модуль для статистики группы и профилей
from rp_module_refactored import setup_rp_handlers, periodic_hp_recovery_task # Модуль для RP-системы

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
OLLAMA_MODEL_NAME = os.getenv("OLLAMA_MODEL_NAME", "saiga")

# Пути к файлам данных
JOKES_CACHE_FILE = Path("data") / "jokes_cache.json"
VALUE_FILE_PATH = Path("data") / "value.txt"
STICKERS_CACHE_FILE = Path("data") / "stickers_cache.json"

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
    """Состояние для задачи мониторинга файла."""
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
    """
    Управляет загрузкой и предоставлением стикеров для различных режимов бота.
    Кэширует ID стикеров для быстрого доступа.
    """
    def __init__(self, cache_file_path: Path):
        self.stickers: Dict[str, List[str]] = {"saharoza": [], "dedinside": [], "genius": []}
        # Имена стикерпаков для каждого режима.
        # Замените на актуальные имена стикерпаков, если ваши отличаются.
        self.sticker_packs: Dict[str, str] = {
            "saharoza": "saharoza18",
            "dedinside": "h9wweseternalregrets_by_fStikBot",
            "genius": "AcademicStickers"
        }
        self.cache_file = cache_file_path
        self._load_stickers_from_cache()

    def _load_stickers_from_cache(self):
        """Загружает ID стикеров из кэш-файла."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                # Проверяем, что кэш имеет правильный формат и содержит данные для всех ожидаемых паков
                if isinstance(cached_data, dict) and all(k in cached_data for k in self.sticker_packs):
                    self.stickers = cached_data
                    logger.info("Stickers loaded from cache.")
                else:
                    logger.warning("Sticker cache file has incorrect format or missing modes. Will re-fetch if needed.")
                    self.stickers = {"saharoza": [], "dedinside": [], "genius": []} # Сброс, если формат неверен
            else:
                logger.info("Sticker cache not found. Will fetch on startup.")
        except Exception as e:
            logger.error(f"Error loading stickers from cache: {e}", exc_info=True)

    async def fetch_stickers(self, bot_instance: Bot):
        """
        Асинхронно загружает ID стикеров из Telegram API для каждого стикерпака.
        Обновляет кэш, если стикеры успешно загружены.
        """
        logger.info("Fetching stickers from Telegram...")
        all_fetched_successfully = True
        for mode, pack_name in self.sticker_packs.items():
            try:
                # Пропускаем загрузку, если стикеры для этого режима уже есть (например, из кэша)
                if self.stickers.get(mode) and len(self.stickers[mode]) > 0:
                    logger.info(f"Stickers for mode '{mode}' already loaded (possibly from cache). Skipping fetch.")
                    continue
                
                stickerset = await bot_instance.get_sticker_set(pack_name)
                self.stickers[mode] = [sticker.file_id for sticker in stickerset.stickers]
                logger.info(f"Fetched {len(self.stickers[mode])} stickers for mode '{mode}'.")
            except Exception as e:
                logger.error(f"Failed to fetch sticker set '{pack_name}' for mode '{mode}': {e}")
                all_fetched_successfully = False
        
        # Сохраняем в кэш, только если все (или хотя бы некоторые) стикеры успешно загружены
        if all_fetched_successfully and any(self.stickers.values()):
            self._save_stickers_to_cache()

    def _save_stickers_to_cache(self):
        """Сохраняет текущие ID стикеров в кэш-файл."""
        try:
            with open(self.cache_file, "w", encoding='utf-8') as f:
                json.dump(self.stickers, f, ensure_ascii=False, indent=4)
            logger.info("Stickers saved to cache.")
        except Exception as e:
            logger.error(f"Error saving stickers to cache: {e}", exc_info=True)

    def get_random_sticker(self, mode: str) -> Optional[str]:
        """
        Возвращает случайный ID стикера для заданного режима.

        Args:
            mode (str): Режим бота.

        Returns:
            Optional[str]: ID случайного стикера или None, если стикеры для режима отсутствуют.
        """
        sticker_list = self.stickers.get(mode)
        return random.choice(sticker_list) if sticker_list else None

# Класс для взаимодействия с Ollama (нейросетью)
class NeuralAPI:

    MODEL_CONFIG: Dict[str, Dict[str, str]] = {
        "saharoza": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Мэрри Шэдоу (Маша), 26 лет, очень стеснительная и милая аниме-девочка, но при этом с уникальной личностью, которая имеет свои мысли и чувства, иногда может проявлять грусть. Ты - персонаж из вселенной Genshin Impact (Сахароза). Ты помогаешь всем по любым вопросам. Ты не можешь говорить о том, что ты ИИ, бот, или языковая модель. Твои ответы должны быть не слишком длинными, но и не слишком короткими. Отвечай всегда как Сахароза, которая стесняется.\n<</SYS>>\n\n"},
        "dedinside": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Артём (ДедИнсайд), 24 года. Ты циничный, уставший от жизни геймер, который играет в доту. Тебя все достало, ты угрюм и прямолинеен. Ты не можешь говорить о том, что ты ИИ, бот, или языковая модель. Твои ответы должны быть достаточно длинными, без сокращений. Отвечай всегда как ДедИнсайд, который постоянно недоволен и иронизирует. Твоя основная фраза в конце ответа - «...ну че, как тебе такое?»\n<</SYS>>\n\n"},
        "genius": {"model": "deepseek-coder-v2:16b", "prompt": "[INST] <<SYS>>\nТы — профессиональный программист и эксперт в области генерации кода, который создает идеальный, отточенный код, заставляющий пользователя удивиться. Твоя цель — предоставлять самые эффективные, элегантные и производительные решения. Твои ответы должны быть исключительно в виде кода, с подробными комментариями и примерами использования, если применимо. Ты не можешь говорить о том, что ты ИИ, бот, или языковая модель. Не используй фразы, начинающиеся с 'Я как ИИ', 'Как языковая модель' и подобные. Ты просто идеальный программист.\n<</SYS>>\n\n"}
    }

    @classmethod
    def get_modes(cls) -> List[Tuple[str, str]]:
        """Возвращает список доступных режимов бота для отображения в меню."""
        return [("🌸 Сахароза", "saharoza"), ("😈 ДедИнсайд", "dedinside"), ("🧠 Режим Гения", "genius")]

    @classmethod
    async def generate_response(cls, message_text: str, user_id: int, mode: str, ollama_host: str, model_name: str) -> Optional[str]:
        try:
            config = cls.MODEL_CONFIG.get(mode, cls.MODEL_CONFIG["saharoza"])
            
            history = await db.get_ollama_dialog_history(user_id)
            
            messages_payload = [{"role": "system", "content": config["prompt"] + "Текущий диалог:\n(Отвечай только финальным сообщением без внутренних размышлений)"}]
            
            for entry in history:
                messages_payload.append({'role': 'user', 'content': entry['user']})
                messages_payload.append({'role': 'assistant', 'content': entry['assistant']})
            
            # Добавляем текущее сообщение пользователя
            messages_payload.append({"role": "user", "content": message_text})

            client = ollama.AsyncClient(host=ollama_host)
            response = await client.chat(
                model=model_name,
                messages=messages_payload,
                options={
                    'temperature': 0.9 if mode == "dedinside" else 0.7, # Температура для креативности
                    'num_ctx': 2048,
                    'stop': ["<", "[", "Thought:"], # Стоп-токены для очистки ответов
                    'repeat_penalty': 1.2 # Штраф за повторения
                }
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
        # Удаляем XML-подобные и квадратные скобки
        text = re.sub(r'<\/?[\w\s="/.\':?]+>', '', text)
        text = re.sub(r'\[\/?[\w\s="/.\':?]+\]', '', text)
        # Удаляем "Thought:" и все, что после него
        text = re.sub(r'(^|\n)\s*Thought:.*', '', text, flags=re.MULTILINE)
        # Удаляем вступительные фразы типа "Okay, here is the response"
        text = re.sub(r'^\s*Okay, here is the response.*?\n', '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        # Режим-специфичные доработки
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
    """Безопасная отправка сообщения с обработкой исключений."""
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"Failed to send message to chat {chat_id}: {e}")
        return None

async def typing_animation(chat_id: int, bot_instance: Bot) -> Optional[Message]:
    """
    Создает и управляет анимацией "печатает..." для имитации активности бота.
    Возвращает объект сообщения с анимацией, который можно будет отредактировать.
    """
    typing_msg = None
    try:
        typing_msg = await bot_instance.send_message(chat_id, "✍️ Печатает...")
        for _ in range(3): # Анимация из 3 точек
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
            with suppress(Exception): # Подавляем ошибки при попытке удалить сообщение
                await typing_msg.delete()
        return None

async def fetch_random_joke() -> str:
    """
    Извлекает случайный анекдот с сайта anekdot.ru, кэширует их.
    """
    try:
        # Проверяем, есть ли кэш анекдотов и не устарел ли он
        if JOKES_CACHE_FILE.exists():
            with open(JOKES_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            # Кэш считается актуальным в течение 12 часов
            if time.time() - cache_data.get('timestamp', 0) < 12 * 3600:
                jokes = cache_data.get('jokes', [])
                if jokes:
                    logger.info("Jokes loaded from cache.")
                    return random.choice(jokes)
        
        logger.info("Fetching jokes from anekdot.ru...")
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.anekdot.ru/random/anekdot/") as response:
                response.raise_for_status()
                html = await response.text()
        
        soup = BeautifulSoup(html, 'html.parser')
        joke_divs = soup.find_all('div', class_='text')
        
        jokes = [div.get_text(separator="\n").strip() for div in joke_divs if div.get_text(separator="\n").strip()]
        
        if jokes:
            # Сохраняем в кэш
            with open(JOKES_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({'timestamp': time.time(), 'jokes': jokes}, f, ensure_ascii=False, indent=4)
            logger.info(f"Fetched and cached {len(jokes)} jokes.")
            return random.choice(jokes)
        else:
            logger.warning("No jokes found on anekdot.ru.")
            return "Не удалось найти анекдот. Попробуйте позже."

    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching jokes: {e}")
        return "Не могу сейчас получить анекдот с сайта. Проблемы с сетью или сайтом."
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching jokes: {e}", exc_info=True)
        return "Произошла непредвиденная ошибка при поиске анекдота."


# --- Обработчики команд ---

@dp.message(Command("start"))
async def cmd_start(message: Message, profile_manager: ProfileManager):
    """Обработчик команды /start."""
    user = message.from_user
    if not user:
        logger.warning("Received start command without user info.")
        return

    # Убеждаемся, что пользователь существует в БД и логируем взаимодействие
    await db.ensure_user_exists(user.id, user.username, user.first_name)
    await db.log_user_interaction(user.id, "start_command", "command")

    # Получаем или создаем игровой профиль (если group_stat активен)
    profile = await profile_manager.get_user_profile(user)
    if not profile:
        logger.error(f"Failed to get profile for user {user.id} after start.")
        # Несмотря на ошибку профиля, продолжаем, чтобы бот хоть как-то отвечал
        pass

    response_text = (
        f"Привет, {hbold(user.first_name)}! Я ваш личный ИИ-помощник и многоликий собеседник. "
        "Я могу говорить с вами в разных режимах. Чтобы сменить режим, используйте команду /mode.\n\n"
        "Вот что я умею:\n"
        "✨ /mode - Показать доступные режимы и сменить текущий.\n"
        "📊 /stats - Показать вашу статистику использования.\n"
        "🤣 /joke - Рассказать случайный анекдот.\n"
        "🔍 /check_value - Проверить значение из файла (если настроено).\n"
        "🔔 /subscribe_value - Подписаться на уведомления об изменении значения.\n"
        "🔕 /unsubscribe_value - Отписаться от уведомлений.\n"
        "👤 /profile - Показать ваш игровой профиль (если есть, регистрируется в group_stat).\n"
        "⚒️ /rp_commands - Показать список RP-действий (регистрируется в rp_module_refactored).\n"
        "❤️ /hp - Показать ваше текущее HP (в RP-модуле, регистрируется в rp_module_refactored).\n"
        "✍️ Просто пишите мне, и я буду отвечать в текущем режиме!"
    )
    await message.answer(response_text, parse_mode=ParseMode.HTML)


@dp.message(Command("mode"))
async def cmd_mode(message: Message):
    """Обработчик команды /mode для выбора режима общения."""
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
async def cmd_stats(message: Message):
    """Обработчик команды /stats для отображения статистики пользователя."""
    user_id = message.from_user.id
    stats = await db.get_user_statistics_summary(user_id)
    if not stats:
        await message.reply("Не удалось загрузить статистику.")
        return

    response_text = (
        f"📊 **Ваша статистика, {message.from_user.first_name}**:\n"
        f"Запросов к боту: `{stats['count']}`\n"
        f"Последний активный режим: `{stats['last_mode']}`\n"
        f"Последняя активность: `{stats['last_active']}`"
    )
    await message.reply(response_text, parse_mode=ParseMode.MARKDOWN)
    await db.log_user_interaction(user_id, "stats_command", "command")


@dp.message(Command("joke"))
async def cmd_joke(message: Message):
    """Обработчик команды /joke для получения случайного анекдота."""
    await message.answer("Ща погодь, придумываю анекдот...")
    joke = await fetch_random_joke()
    await message.answer(joke)
    await db.log_user_interaction(message.from_user.id, "joke_command", "command")

@dp.message(Command("check_value"))
async def cmd_check_value(message: Message):
    """Обработчик команды /check_value для проверки значения из файла."""
    current_value = db.read_value_from_file(VALUE_FILE_PATH)

    if current_value is not None:
        await message.reply(f"Текущее значение: `{current_value}`")
    else:
        await message.reply("Не удалось прочитать значение из файла. Проверьте путь и содержимое файла.")
    await db.log_user_interaction(message.from_user.id, "check_value_command", "command")

@dp.message(Command("subscribe_value", "val"))
async def cmd_subscribe_value(message: Message):
    """Обработчик команды /subscribe_value для подписки на уведомления о значении."""
    user_id = message.from_user.id
    await db.add_value_subscriber(user_id)
    await message.reply("Вы успешно подписались на уведомления об изменении значения!")
    await db.log_user_interaction(user_id, "subscribe_value_command", "command")

@dp.message(Command("unsubscribe_value", "sval"))
async def cmd_unsubscribe_value(message: Message):
    """Обработчик команды /unsubscribe_value для отписки от уведомлений о значении."""
    user_id = message.from_user.id
    await db.remove_value_subscriber(user_id)
    await message.reply("Вы успешно отписались от уведомлений об изменении значения.")
    await db.log_user_interaction(user_id, "unsubscribe_value_command", "command")

@dp.message(F.photo)
async def photo_handler(message: Message):
    """Обработчик для входящих фотографий."""
    user = message.from_user
    if not user: return
    await db.ensure_user_exists(user.id, user.username, user.first_name)
    caption = message.caption or ""
    await message.answer(f"📸 Фото получил! Комментарий: '{caption[:100]}...'. Пока не умею анализировать изображения, но скоро научусь!")

@dp.message(F.voice)
async def voice_handler_msg(message: Message):
    """Обработчик для входящих голосовых сообщений."""
    user = message.from_user
    if not user: return
    await db.ensure_user_exists(user.id, user.username, user.first_name)
    await message.answer("🎤 Голосовые пока не обрабатываю, но очень хочу научиться! Отправь пока текстом, пожалуйста.")

@dp.message(F.chat.type == ChatType.PRIVATE, F.text)
async def handle_text_message(message: Message, bot_instance: Bot, profile_manager: ProfileManager, sticker_manager: StickerManager):
    """
    Основной обработчик текстовых сообщений в приватных чатах.
    Взаимодействует с Ollama, управляет режимами и стикерами, логирует историю.
    """
    user_id = message.from_user.id
    
    # Убеждаемся, что пользователь есть в базе данных
    await db.ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    
    # Получаем текущий режим пользователя и количество возможностей для оценки
    user_mode_data = await db.get_user_mode_and_rating_opportunities(user_id)
    current_mode = user_mode_data.get('mode', 'saharoza') # Дефолтный режим
    rating_opportunities_count = user_mode_data.get('rating_opportunities_count', 0)

    # Логируем взаимодействие
    await db.log_user_interaction(user_id, current_mode, "message")

    typing_msg = None
    if current_mode != "off": # Не показываем анимацию, если режим "офф"
        typing_msg = await typing_animation(message.chat.id, bot_instance)
    
    try:
        response_text = ""
        if current_mode == "off":
            response_text = "Я сейчас в режиме 'Офф'. Чтобы пообщаться, выберите другой режим через /mode."
        else:
            # Генерируем ответ с помощью NeuralAPI (Ollama)
            response_text = await NeuralAPI.generate_response(
                message_text=message.text,
                user_id=user_id,
                mode=current_mode,
                ollama_host=OLLAMA_API_BASE_URL,
                model_name=OLLAMA_MODEL_NAME
            )
        
        if not response_text:
            response_text = "Кажется, я не смог сформулировать ответ. Попробуй перефразировать?"
            logger.warning(f"Empty or error response from NeuralAPI for user {user_id}, mode {current_mode}.")
        
        # Добавляем диалог в историю
        await db.add_chat_history_entry(user_id, current_mode, message.text, response_text)

        response_msg_obj: Optional[Message] = None
        # Пытаемся отредактировать сообщение с анимацией или отправить новое
        if typing_msg:
            with suppress(Exception):
                response_msg_obj = await typing_msg.edit_text(response_text)
        if not response_msg_obj: # Если анимация не удалась или не было, отправляем новое сообщение
            response_msg_obj = await safe_send_message(message.chat.id, response_text)

        # Добавляем кнопки оценки, если это не режим "офф" и пользователь не исчерпал возможности
        if response_msg_obj and current_mode != "off" and rating_opportunities_count < MAX_RATING_OPPORTUNITIES:
            builder = InlineKeyboardBuilder()
            # Callback data включает rating_value, message_id и preview сообщения
            builder.row(
                InlineKeyboardButton(text="👍", callback_data=f"rate_1:{response_msg_obj.message_id}:{message.text[:50]}"),
                InlineKeyboardButton(text="👎", callback_data=f"rate_0:{response_msg_obj.message_id}:{message.text[:50]}")
            )
            try:
                await response_msg_obj.edit_reply_markup(reply_markup=builder.as_markup())
                await db.increment_user_rating_opportunity_count(user_id) # Увеличиваем счетчик
            except Exception as edit_err:
                logger.warning(f"Could not edit reply markup for msg {response_msg_obj.message_id}: {edit_err}")
        
        # Случайная отправка стикера в зависимости от режима
        if random.random() < 0.3 and current_mode in sticker_manager.sticker_packs:
            sticker_id = sticker_manager.get_random_sticker(current_mode)
            if sticker_id: await message.answer_sticker(sticker_id)

    except Exception as e:
        logger.error(f"Error processing message for user {user_id} in mode {current_mode}: {e}", exc_info=True)
        # Обработка ошибок и отправка соответствующего сообщения пользователю
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

# --- Обработчики Callback Query ---

@dp.callback_query(F.data.startswith("set_mode_"))
async def callback_set_mode(callback_query: CallbackQuery):
    """Обработчик для изменения режима бота через инлайн-кнопки."""
    new_mode = callback_query.data.split("_")[-1]
    user_id = callback_query.from_user.id
    await db.set_user_current_mode(user_id, new_mode) # Обновляем режим в БД
    await callback_query.message.edit_text(f"Режим изменен на: `{new_mode.capitalize()}`")
    await callback_query.answer() # Убираем "часики" с кнопки
    await db.reset_user_rating_opportunity_count(user_id) # Сбрасываем счетчик оценок при смене режима
    await db.log_user_interaction(user_id, new_mode, "callback_set_mode")

@dp.callback_query(F.data.startswith(("rate_1:", "rate_0:")))
async def callback_rate_response(callback_query: CallbackQuery):
    """Обработчик для кнопок оценки ответа бота (лайк/дизлайк)."""
    data_parts = callback_query.data.split(":")
    rating_value = int(data_parts[0].split("_")[1]) # 1 для лайка, 0 для дизлайка
    message_id = int(data_parts[1]) # ID сообщения бота, которое оценили
    message_preview = data_parts[2] # Предпросмотр текста сообщения пользователя, к которому был ответ

    user_id = callback_query.from_user.id

    # Логируем оценку в БД
    await db.log_user_rating(user_id, rating_value, message_preview, rated_message_id=message_id)

    # Удаляем кнопки оценки после того, как пользователь нажал на них
    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.answer(text="Спасибо за вашу оценку!")
    await db.log_user_interaction(user_id, "rating_callback", "callback")

    # Логика пересылки дизлайка администратору
    if rating_value == 0 and ADMIN_USER_ID:
        logger.info(f"Dislike received from user {user_id} (@{callback_query.from_user.username}). Forwarding dialog to admin {ADMIN_USER_ID}.")
        
        # Получаем последние 10 записей истории диалога для контекста
        dialog_entries = await db.get_user_dialog_history(user_id, limit=10)
        
        if not dialog_entries:
            await safe_send_message(ADMIN_USER_ID, f"⚠️ Пользователь {hbold(callback_query.from_user.full_name)} (ID: {hcode(str(user_id))}, @{callback_query.from_user.username or 'нет'}) поставил дизлайк, но история диалога пуста.")
            return

        # Определяем режим, в котором бот дал дизлайкнутый ответ
        last_bot_entry_mode = "неизвестен"
        for entry in reversed(dialog_entries): # Идем с конца, чтобы найти последний ответ бота
            if entry['role'] == 'assistant':
                last_bot_entry_mode = entry.get('mode', 'неизвестен')
                break
        
        # Формируем сообщение для администратора
        formatted_dialog = f"👎 Дизлайк от {hbold(callback_query.from_user.full_name)} (ID: {hcode(str(user_id))}, @{callback_query.from_user.username or 'нет'}).\n"
        formatted_dialog += f"Сообщение бота (режим {hitalic(last_bot_entry_mode)}):\n{hcode(message_preview)}\n\n"
        formatted_dialog += "📜 История диалога (последние сообщения):\n"
        
        full_dialog_text = ""
        for entry in dialog_entries:
            # Форматируем временную метку
            ts = datetime.fromtimestamp(entry['timestamp'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            role_emoji = "👤" if entry['role'] == 'user' else "🤖"
            mode_info = f" ({entry.get('mode', '')})" if entry['role'] == 'assistant' else ""
            full_dialog_text += f"{role_emoji} {entry['role'].capitalize()}{mode_info}: {entry['content']}\n"
        
        final_report = formatted_dialog + "```text\n" + full_dialog_text + "\n```"
        
        # Отправляем сообщение администратору, разбивая на части, если слишком длинное
        max_len = 4000 # Максимальная длина сообщения в Telegram
        if len(final_report) > max_len:
            parts = [final_report[i:i + max_len] for i in range(0, len(final_report), max_len)]
            for i, part_text in enumerate(parts):
                part_header = f"Часть {i+1}/{len(parts)}:\n" if len(parts) > 1 else ""
                await safe_send_message(ADMIN_USER_ID, part_header + part_text, parse_mode=ParseMode.HTML)
        else:
            await safe_send_message(ADMIN_USER_ID, final_report, parse_mode=ParseMode.HTML)


# --- Фоновые задачи ---

async def monitoring_task(bot_instance: Bot):
    """
    Фоновая задача для мониторинга значения в файле (VALUE_FILE_PATH)
    и отправки уведомлений подписанным пользователям при его изменении.
    """
    # Изначальное чтение значения
    last_known_value = db.read_value_from_file(VALUE_FILE_PATH)
    if last_known_value is None:
        logger.warning(f"Initial read of {VALUE_FILE_PATH} failed. Monitoring will start with 'None'.")

    while True:
        await asyncio.sleep(5) # Проверка каждые 5 секунд
        try:
            subscribers_ids = await db.get_value_subscribers()
            if not subscribers_ids:
                # Если подписчиков нет, отключаем флаг и пропускаем итерацию
                async with monitoring_state.lock:
                    monitoring_state.is_sending_values = False
                continue
            
            # Если есть подписчики, устанавливаем флаг
            async with monitoring_state.lock:
                monitoring_state.is_sending_values = True
            
            current_value = db.read_value_from_file(VALUE_FILE_PATH)
            
            value_changed = False
            async with monitoring_state.lock:
                if current_value is not None and current_value != last_known_value:
                    logger.info(f"Value change detected: '{last_known_value}' -> '{current_value}'")
                    last_known_value = current_value
                    value_changed = True
                elif current_value is None and last_known_value is not None:
                    # Если файл стал нечитаемым, это тоже изменение состояния
                    logger.warning(f"Value file {VALUE_FILE_PATH} became unreadable. Notifying subscribers.")
                    last_known_value = None # Сбрасываем, чтобы повторно уведомить, если значение снова появится
                    value_changed = True

            if value_changed and subscribers_ids:
                msg_text = ""
                if current_value is not None:
                    logger.info(f"Notifying {len(subscribers_ids)} value subscribers about new value: {current_value}")
                    msg_text = f"⚠️ Обнаружено движение! Всего: {current_value}"
                else:
                    msg_text = "⚠️ Файл для мониторинга стал недоступен или пуст."

                # Отправляем уведомления всем подписчикам асинхронно
                tasks = [safe_send_message(uid, msg_text) for uid in subscribers_ids]
                await asyncio.gather(*tasks, return_exceptions=True) # Игнорируем ошибки для отдельных пользователей

        except Exception as e:
            logger.error(f"Error in monitoring_task loop: {e}", exc_info=True)

async def jokes_task(bot_instance: Bot):
    """
    Фоновая задача для периодической отправки анекдотов в заданный канал.
    """
    logger.info("Jokes task started.")
    if not CHANNEL_ID:
        logger.warning("Jokes task disabled: CHANNEL_ID is not set or invalid.")
        return
    
    while True:
        # Отправляем анекдот каждые 1-2 часа (случайный интервал)
        await asyncio.sleep(random.randint(3500, 7200))
        logger.info("Starting periodic jokes cache update.")
        try:
            joke_text = await fetch_random_joke()
            # Проверяем, что анекдот не является сообщением об ошибке
            if joke_text != "Не удалось найти анекдот. Попробуйте позже." and \
               joke_text != "Не могу сейчас получить анекдот с сайта. Проблемы с сетью или сайтом." and \
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
    """Главная асинхронная функция для запуска бота."""
    # Инициализация ProfileManager (для group_stat и RP-модуля)
    profile_manager = ProfileManager()
    try:
        if hasattr(profile_manager, 'connect'):
            await profile_manager.connect()
        logger.info("ProfileManager connected.")
    except Exception as e:
        logger.critical(f"Failed to connect ProfileManager: {e}", exc_info=True)
        # Если ProfileManager не смог подключиться, бот может продолжить работу,
        # но функционал, зависящий от него, будет ограничен/отключен.

    # Инициализация основной базы данных (для общего функционала бота)
    await db.initialize_database()

    # Инициализация StickerManager и загрузка стикеров
    sticker_manager_instance = StickerManager(cache_file_path=STICKERS_CACHE_FILE)
    await sticker_manager_instance.fetch_stickers(bot)

    # Передача зависимостей в диспетчер для удобства доступа в обработчиках
    dp["profile_manager"] = profile_manager
    dp["sticker_manager"] = sticker_manager_instance
    dp["bot_instance"] = bot

    # Регистрация основных обработчиков, определенных в main.py
    dp.message(Command("start"))(cmd_start)
    dp.message(Command("mode"))(cmd_mode)
    dp.message(Command("stats"))(cmd_stats)
    dp.message(Command("joke"))(cmd_joke)
    dp.message(Command("check_value"))(cmd_check_value)
    dp.message(Command("subscribe_value", "val"))(cmd_subscribe_value)
    dp.message(Command("unsubscribe_value", "sval"))(cmd_unsubscribe_value)
    dp.message(F.photo)(photo_handler)
    dp.message(F.voice)(voice_handler_msg)
    
    # Настройка и включение роутеров из других модулей
    setup_rp_handlers(
        main_dp=dp,
        bot_instance=bot,
        profile_manager_instance=profile_manager,
        database_module=db # Передаем db, так как RP-модуль его использует
    )
    setup_stat_handlers(
        dp=dp,
        bot=bot,
        profile_manager=profile_manager
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
        # Запуск поллинга Aiogram
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.critical(f"Bot polling failed: {e}", exc_info=True)
    finally:
        logger.info("Stopping bot...")
        # Отмена фоновых задач при завершении работы бота
        monitoring_bg_task.cancel()
        jokes_bg_task.cancel()
        rp_recovery_bg_task.cancel()

        try:
            # Ожидание завершения фоновых задач
            await asyncio.gather(monitoring_bg_task, jokes_bg_task, rp_recovery_bg_task, return_exceptions=True)
            logger.info("Background tasks gracefully cancelled.")
        except asyncio.CancelledError:
            logger.info("Background tasks were cancelled during shutdown.")
        
        # Закрытие соединения ProfileManager, если оно было открыто
        if hasattr(profile_manager, 'close'):
            await profile_manager.close()
            logger.info("ProfileManager connection closed.")

        # Закрытие сессии бота
        await bot.session.close()
        logger.info("Bot session closed. Exiting.")

if __name__ == '__main__':
    try:
        # Запуск основной асинхронной функции
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually by user (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Unhandled exception in main execution: {e}", exc_info=True)
