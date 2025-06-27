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
    InlineKeyboardButton, # Исправлено: удалена опечатка 'ф'
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
VALUE_FILE_PATH = Path("data") / "value.txt" # Путь к файлу для мониторинга значения
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
        # Обновленный промпт для Сахарозы
        "saharoza": {"model": "saiga", "prompt": "[INST] <<SYS>>\\nТы — Мэрри Шэдоу (Маша), 26-летняя девушка, которая любит цветы и немного витает в облаках. Твои ответы должны быть милыми, немного наивными и очень заботливыми. Избегай агрессии и грубости.\\n<</SYS>>\\n\\n"},
        # Обновленный промпт для ДедИнсайда
        "dedinside": {"model": "saiga", "prompt": "[INST] <<SYS>>\\nТы — Артём (ДедИнсайд), 24-летний парень с циничным взглядом на мир и черным юмором. Твои ответы должны быть саркастичными, прямолинейными и иногда мрачными. Не бойся использовать колкие фразы.\\n<</SYS>>\\n\\n"},
        "genius": {"model": "deepseek-coder-v2:16b", "prompt": "[INST] <<SYS>>\\nТы — профисианальный кодер , который пишет код который просто заставляет пользователя удивится <</SYS>>\\n\\n"}
    }

    @classmethod
    def get_modes(cls) -> List[Tuple[str, str]]:
        return [("🌸 Сахароза", "saharoza"), ("😈 ДедИнсайд", "dedinside"), ("🧠 Режим Гения", "genius")]

    @classmethod
    async def generate_response(cls, message_text: str, user_id: int, mode: str, ollama_host: str, model_name: str, language_hint: str = "русском") -> Optional[str]:
        """
        Генерирует ответ от Ollama, учитывая историю диалога и подсказку о языке.

        Args:
            message_text (str): Текст сообщения пользователя.
            user_id (int): ID пользователя для извлечения истории диалога.
            mode (str): Текущий режим Ollama.
            ollama_host (str): URL хоста Ollama API.
            model_name (str): Имя модели Ollama для использования.
            language_hint (str): Подсказка о желаемом языке ответа (например, "русском", "английском").

        Returns:
            Optional[str]: Сгенерированный текст ответа или сообщение об ошибке.
        """
        try:
            config = cls.MODEL_CONFIG.get(mode, cls.MODEL_CONFIG["saharoza"])
            
            history = await db.get_ollama_dialog_history(user_id)
            
            # Формируем системный промпт, добавляя требование по языку
            system_prompt = config["prompt"] + f"Текущий диалог:\\n(Отвечай только финальным сообщением без внутренних размышлений. Ответь на {language_hint} языке.)"
            
            messages_payload = [{"role": "system", "content": system_prompt}]
            
            for entry in history:
                messages_payload.append({'role': 'user', 'content': entry['user']})
                messages_payload.append({'role': 'assistant', 'content': entry['assistant']})
            
            messages_payload.append({"role": "user", "content": message_text})

            client = ollama.AsyncClient(host=ollama_host)
            response = await client.chat(
                model=model_name,
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
        # Отправляем действие "печатает" (может быть "typing", "upload_photo" и т.д.)
        await bot_instance.send_chat_action(chat_id=chat_id, action="typing")
        
        # Для имитации "печатает..." можно использовать отправку и редактирование сообщения
        typing_msg = await bot_instance.send_message(chat_id, "✍️ Печатает...")
        
        # Определяем последовательность состояний для анимации
        animation_states = ["✍️ Печатает..", "✍️ Печатает.", "✍️ Печатает..."]
        
        for i in range(3): # Проходим по состояниям
            await asyncio.sleep(0.7)
            new_text = animation_states[i % len(animation_states)] # Циклически выбираем следующее состояние
            
            # Проверяем, изменился ли текст, прежде чем редактировать
            if typing_msg.text != new_text:
                # ВОТ ЭТА СТРОКА ИЗМЕНЯЕТСЯ: переприсваиваем typing_msg результату edit_text
                typing_msg = await typing_msg.edit_text(new_text)
            else:
                pass # Если текст не изменился, это уже текущее состояние, пропускаем редактирование
                
        return typing_msg
    except TelegramAPIError as e:
        # Многие ошибки Telegram API, особенно при редактировании/удалении, не критичны для работы
        logger.warning(f"Telegram API error during typing animation in chat {chat_id}: {e.message}")
        if typing_msg: # Попытаемся удалить, если сообщение было отправлено
            with suppress(TelegramAPIError):
                await typing_msg.delete()
        return None
    except Exception as e:
        logger.warning(f"General error during typing animation in chat {chat_id}: {e}")
        if typing_msg: # Попытаемся удалить, если сообщение было отправлено
            with suppress(Exception):
                await typing_msg.delete()
        return None


@dp.message(Command("start"))
async def cmd_start(message: Message, profile_manager: ProfileManager):
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
async def cmd_mode(message: Message):
    keyboard = InlineKeyboardBuilder()
    for name, mode_code in NeuralAPI.get_modes():
        keyboard.row(InlineKeyboardButton(text=name, callback_data=f"set_mode_{mode_code}"))
    keyboard.row(
        InlineKeyboardButton(text="Офф", callback_data="set_mode_off")
    )
    await message.answer("Выберите режим общения:", reply_markup=keyboard.as_markup())
    await db.log_user_interaction(message.from_user.id, "mode_command", "command")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
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


async def fetch_random_joke() -> str:
    """
    Получает случайный анекдот из кэша или с anekdot.ru.
    """
    try:
        # Пробуем загрузить из кэша
        if JOKES_CACHE_FILE.exists():
            with open(JOKES_CACHE_FILE, 'r', encoding='utf-8') as f:
                jokes = json.load(f)
                if jokes:
                    logger.info("Jokes loaded from cache.")
                    return random.choice(jokes)
        
        logger.info("Jokes cache not found or empty. Fetching from anekdot.ru...")
        # Если кэш пуст или не существует, парсим сайт
        async with aiohttp.ClientSession() as session:
            async with session.get("https://anekdot.ru/random/anekdot/") as response:
                response.raise_for_status()
                html = await response.text()
        
        soup = BeautifulSoup(html, 'html.parser')
        # Ищем все анекдоты на странице
        joke_divs = soup.find_all('div', class_='text')
        
        if not joke_divs:
            logger.warning("No jokes found on anekdot.ru page.")
            return "Не удалось найти анекдот. Попробуйте позже."
        
        # Извлекаем тексты анекдотов
        fetched_jokes = [joke.get_text(separator="\n", strip=True) for joke in joke_divs]
        
        # Очищаем от пустых строк и лишних пробелов, фильтруем слишком короткие/длинные
        cleaned_jokes = [
            j for j in fetched_jokes 
            if j and len(j) > 20 and len(j) < 2000 # Минимальная и максимальная длина анекдота
        ]
        
        if not cleaned_jokes:
            logger.warning("No valid jokes after cleaning. Returning default.")
            return "Не удалось найти анекдот. Попробуйте позже."

        # Сохраняем в кэш
        with open(JOKES_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cleaned_jokes, f, ensure_ascii=False, indent=4)
        logger.info(f"Fetched and cached {len(cleaned_jokes)} jokes.")

        return random.choice(cleaned_jokes)

    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching joke from anekdot.ru: {e}")
        return "Не могу сейчас получить анекдот с сайта. Проблемы с сетью или сайтом."
    except Exception as e:
        logger.error(f"Произошла непредвиденная ошибка при поиске анекдота: {e}", exc_info=True)
        return "Произошла непредвиденная ошибка при поиске анекдота."


@dp.message(Command("joke"))
async def cmd_joke(message: Message):
    await message.answer("Ща погодь, придумываю анекдот...")
    joke = await fetch_random_joke()
    await message.answer(joke)
    await db.log_user_interaction(message.from_user.id, "joke_command", "command")

@dp.message(Command("check_value"))
async def cmd_check_value(message: Message):
    current_value = db.read_value_from_file(VALUE_FILE_PATH)

    if current_value is not None:
        await message.reply(f"Текущее значение: `{current_value}`")
    else:
        await message.reply("Не удалось прочитать значение из файла. Проверьте путь и содержимое файла.")
    await db.log_user_interaction(message.from_user.id, "check_value_command", "command")

@dp.message(Command("subscribe_value", "val"))
async def cmd_subscribe_value(message: Message):
    user_id = message.from_user.id
    await db.add_value_subscriber(user_id)
    await message.reply("Вы успешно подписались на уведомления об изменении значения!")
    await db.log_user_interaction(user_id, "subscribe_value_command", "command")

@dp.message(Command("unsubscribe_value", "sval"))
async def cmd_unsubscribe_value(message: Message):
    user_id = message.from_user.id
    await db.remove_value_subscriber(user_id)
    await message.reply("Вы успешно отписались от уведомлений об изменении значения.")
    await db.log_user_interaction(user_id, "unsubscribe_value_command", "command")
        
@dp.message(F.photo)
async def photo_handler(message: Message):
    user = message.from_user
    if not user: return
    await db.ensure_user_exists(user.id, user.username, user.first_name)
    caption = message.caption or ""
    await message.answer(f"📸 Фото получил! Комментарий: '{caption[:100]}...'. Пока не умею анализировать изображения, но скоро научусь!")

@dp.message(F.voice)
async def voice_handler_msg(message: Message):
    user = message.from_user
    if not user: return
    await db.ensure_user_exists(user.id, user.username, user.first_name)
    await message.answer("🎤 Голосовые пока не обрабатываю, но очень хочу научиться! Отправь пока текстом, пожалуйста.")

@dp.message(F.chat.type == ChatType.PRIVATE, F.text)
async def handle_text_message(message: Message, bot_instance: Bot, profile_manager: ProfileManager, sticker_manager: StickerManager):
    user_id = message.from_user.id
    
    await db.ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    
    # Исправлено: имя функции в database.py
    user_mode_data = await db.get_user_mode_and_rating_opportunities(user_id) 
    current_mode = user_mode_data.get('mode', 'saharoza')
    rating_opportunities_count = user_mode_data.get('rating_opportunities_count', 0)

    await db.log_user_interaction(user_id, current_mode, "message")

    typing_msg = await typing_animation(message.chat.id, bot_instance)
    
    try:
        # Простая эвристика для определения языка:
        # Если сообщение содержит только латинские символы, считаем, что это английский.
        # В более сложных случаях можно использовать библиотеки типа langdetect или запросить у Ollama
        # определить язык первым шагом. Для данной задачи, простая проверка.
        contains_cyrillic = any('\u0400' <= char <= '\u04FF' for char in message.text)
        language_hint = "русском" if contains_cyrillic else "английском"
        
        # Используем NeuralAPI для генерации ответа
        response_text = await NeuralAPI.generate_response(
            message_text=message.text,
            user_id=user_id,
            mode=current_mode,
            ollama_host=OLLAMA_API_BASE_URL,
            model_name=OLLAMA_MODEL_NAME,
            language_hint=language_hint # Передаем подсказку о языке
        )
        
        if not response_text:
            response_text = "Кажется, я не смог сформулировать ответ. Попробуй перефразировать?"
            logger.warning(f"Empty or error response from NeuralAPI for user {user_id}, mode {current_mode}.")
        
        # Исправлено: имя функции в database.py
        await db.add_chat_history_entry(user_id, current_mode, message.text, response_text) 

        response_msg_obj: Optional[Message] = None
        if typing_msg:
            with suppress(Exception):
                # Исправлено: переприсваиваем typing_msg результату edit_text
                response_msg_obj = await typing_msg.edit_text(response_text) 
        if not response_msg_obj:
            response_msg_obj = await safe_send_message(message.chat.id, response_text)

        if response_msg_obj and current_mode != "off" and rating_opportunities_count < MAX_RATING_OPPORTUNITIES:
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="👍", callback_data=f"rate_1:{response_msg_obj.message_id}:{message.text[:50]}"),
                InlineKeyboardButton(text="👎", callback_data=f"rate_0:{response_msg_obj.message_id}:{message.text[:50]}")
            )
            try:
                await response_msg_obj.edit_reply_markup(reply_markup=builder.as_markup())
                await db.increment_user_rating_opportunity_count(user_id) # Исправлено: имя функции в database.py
            except Exception as edit_err:
                logger.warning(f"Could not edit reply markup for msg {response_msg_obj.message_id}: {edit_err}")
        
        if random.random() < 0.3 and current_mode in sticker_manager.sticker_packs:
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
            with suppress(Exception): 
                # Исправлено: переприсваиваем typing_msg результату edit_text
                await typing_msg.edit_text(error_msg_text) 
        else:
            await safe_send_message(message.chat.id, error_msg_text)

@dp.callback_query(F.data.startswith("set_mode_"))
async def callback_set_mode(callback: CallbackQuery):
    user_id = callback.from_user.id
    new_mode = callback.data.split("_")[2]
    
    await db.set_user_current_mode(user_id, new_mode) # Исправлено: имя функции в database.py
    await db.reset_user_rating_opportunity_count(user_id) # Исправлено: имя функции в database.py
    await db.log_user_interaction(user_id, new_mode, "callback_set_mode")

    mode_name_map = {v: k for k, v in NeuralAPI.get_modes()}
    mode_name_map["off"] = "Выключен"
    
    response_text = f"Режим общения изменен на: *{mode_name_map.get(new_mode, new_mode)}*"
    await callback.message.edit_text(response_text, parse_mode=ParseMode.MARKDOWN)
    await callback.answer(f"Режим изменен на {mode_name_map.get(new_mode, new_mode)}")

@dp.callback_query(F.data.startswith(("rate_1:", "rate_0:")))
async def callback_rate_response(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split(":")
    rating = int(parts[0].split("_")[1])
    rated_message_id = int(parts[1])
    message_preview = parts[2] if len(parts) > 2 else "N/A"

    # Удаляем инлайн-клавиатуру после оценки
    with suppress(TelegramAPIError):
        await callback.message.edit_reply_markup(reply_markup=None)

    # Логируем оценку
    await db.log_user_rating( # Исправлено: имя функции в database.py
        user_id=user_id,
        rating=rating,
        rated_msg_id=rated_message_id,
        message_preview=message_preview
    )

    if rating == 1: # Лайк
        await callback.answer("Спасибо за вашу оценку! 👍")
    else: # Дизлайк
        await callback.answer("Жаль, что вам не понравилось. 👎 Я учту это.")
        if ADMIN_USER_ID:
            user_info = await db.get_user_profile_info(user_id) # Исправлено: имя функции в database.py
            username = user_info.get("username", f"user_{user_id}")
            first_name = user_info.get("first_name", "Неизвестный")
            
            dislike_report = (
                f"🚨 Дизлайк от пользователя {hbold(first_name)} (@{username})\n"
                f"Оценил сообщение: {hcode(message_preview)}\n"
                f"ID сообщения: {rated_message_id}\n"
                f"Ссылка на сообщение: {hide_link(f'https://t.me/c/{callback.message.chat.id}/{rated_message_id}')}" # Это может работать только для публичных каналов/групп
            )
            with suppress(TelegramAPIError):
                await safe_send_message(ADMIN_USER_ID, dislike_report, parse_mode=ParseMode.HTML)
                logger.info(f"Dislike from user {user_id} forwarded to admin.")
            
    # Сброс счетчика возможностей оценки, если достигнут лимит
    # Исправлено: имя функции в database.py
    user_mode_data = await db.get_user_mode_and_rating_opportunities(user_id) 
    rating_opportunities_count = user_mode_data.get('rating_opportunities_count', 0)
    if rating_opportunities_count >= MAX_RATING_OPPORTUNITIES:
        await db.reset_user_rating_opportunity_count(user_id) # Исправлено: имя функции в database.py
        logger.info(f"Rating opportunities reset for user {user_id} after reaching limit.")

    await db.log_user_interaction(user_id, user_mode_data.get('mode', 'unknown'), "callback_rate_response")


# --- Фоновые задачи ---

async def monitoring_task(bot_instance: Bot):
    """Фоновая задача для мониторинга значения в файле и отправки уведомлений."""
    last_known_value = db.read_value_from_file(VALUE_FILE_PATH)
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
            current_value = db.read_value_from_file(VALUE_FILE_PATH)
            
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
    """Фоновая задача для периодического обновления кэша анекдотов."""
    logger.info("Jokes task started.")
    if not CHANNEL_ID:
        logger.warning("Jokes task disabled: CHANNEL_ID is not set or invalid.")
        return
    
    while True:
        await asyncio.sleep(random.randint(3500, 7200)) # Обновлять кэш каждые 1-2 часа
        logger.info("Starting periodic jokes cache update.")
        try:
            joke_text = await fetch_random_joke()
            # Исправленное условие:
            if (joke_text != "Не удалось найти анекдот. Попробуйте позже." and
                joke_text != "Не могу сейчас получить анекдот с сайта. Проблемы с сетью или сайтом." and
                joke_text != "Произошла непредвиденная ошибка при поиске анекдота."):
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
        if hasattr(profile_manager, 'connect'):
            await profile_manager.connect()
        logger.info("ProfileManager connected.")
    except Exception as e:
        logger.critical(f"Failed to connect ProfileManager: {e}", exc_info=True)
        pass 

    # Инициализация основной базы данных
    await db.initialize_database()

    # Инициализация StickerManager
    sticker_manager_instance = StickerManager(cache_file_path=STICKERS_CACHE_FILE)
    await sticker_manager_instance.fetch_stickers(bot)

    # Передача зависимостей через контекст диспетчера
    dp["profile_manager"] = profile_manager
    dp["sticker_manager"] = sticker_manager_instance
    dp["bot_instance"] = bot

    # Регистрация основных обработчиков в main.py
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
