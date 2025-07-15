import random
import re
from pathlib import Path
import logging
from typing import List, Tuple, Any
from aiogram import Router, types, F, Bot
from aiogram.exceptions import TelegramAPIError
<<<<<<< HEAD
from aiogram.utils.markdown import hbold
from aiogram.enums import ParseMode
import asyncio
import time
import random
import logging
from typing import Dict, Any, Optional, List, Tuple, Set
import aiosqlite
from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType, ParseMode, MessageEntityType
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from contextlib import suppress
import database as db
logger = logging.getLogger(__name__)
BAD_WORDS_FILE = Path("data") / "bad_words.txt"

BAD_WORD_ROOTS: List[str] = []

def load_bad_words(filepath: Path) -> List[str]:
=======
from aiogram.utils.markdown import hbold # Предполагаем, что hbold доступен
from aiogram.enums import ParseMode # ИМПОРТИРОВАНО ИЗ aiogram.enums

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения корней "плохих" слов
BAD_WORD_ROOTS: List[str] = []

def load_bad_words(filepath: Path) -> List[str]:
    """
    Загружает корни слов для цензуры из указанного файла.
    
    Args:
        filepath (Path): Путь к файлу со словами.
        
    Returns:
        List[str]: Список корней слов.
    """
>>>>>>> 14db95269ee53caabc816e1133fad09d46f4a408
    try:
        if not filepath.exists():
            logger.warning(f"Файл со 'злыми' словами '{filepath}' не найден. Цензура слов отключена.")
            return []
        with open(filepath, 'r', encoding='utf-8') as f:
            words = [line.strip().lower() for line in f if line.strip()]
        logger.info(f"Загружено {len(words)} корней 'злых' слов из {filepath}.")
<<<<<<< HEAD
=======
        # logger.debug(f"Загруженные слова: {words}") # Только для очень детальной отладки
>>>>>>> 14db95269ee53caabc816e1133fad09d46f4a408
        return words
    except Exception as e:
        logger.error(f"Ошибка загрузки 'злых' слов из {filepath}: {e}", exc_info=True)
        return []

def generate_random_symbols(length: int) -> str:
<<<<<<< HEAD
    symbols = "@#$%^&"
    if not symbols:
        return ""

=======
    """
    Генерирует строку из случайных символов заданной длины,
    избегая повторения одного и того же символа подряд.
    
    Args:
        length (int): Длина генерируемой строки.
        
    Returns:
        str: Строка из случайных символов.
    """
    # Используем символы, которые выглядят как случайный набор для цензуры
    symbols = "@#$%^&" 
    if not symbols: # Проверка на случай, если symbols пуст
        return ""
    
>>>>>>> 14db95269ee53caabc816e1133fad09d46f4a408
    censored_chars = []
    last_char = None

    for _ in range(length):
<<<<<<< HEAD
        available_symbols = [s for s in symbols if s != last_char]
        if not available_symbols:
            available_symbols = list(symbols)

=======
        # Создаем список доступных символов, исключая последний использованный
        available_symbols = [s for s in symbols if s != last_char]
        
        # Если остался только один символ и он совпадает с last_char,
        # или если symbols содержит только один символ,
        # то придется повторить символ.
        if not available_symbols:
            available_symbols = list(symbols)
        
>>>>>>> 14db95269ee53caabc816e1133fad09d46f4a408
        current_char = random.choice(available_symbols)
        censored_chars.append(current_char)
        last_char = current_char
        
    return ''.join(censored_chars)

def censor_text_func(text: str, bad_roots: List[str]) -> Tuple[str, bool]:
<<<<<<< HEAD
    logger.debug(f"censor_text_func called with text: '{text}', bad_roots: {bad_roots}")
    
    if not bad_roots:
        return text, False

    patterns = []
    for root in bad_roots:
        # Создаем очень агрессивное регулярное выражение для каждого корня.
        # Оно позволяет:
        # 1. Повторять буквы (например, "f" или "fff") с помощью `+`.
        # 2. Любым символам, которые НЕ являются буквенно-цифровыми, находиться между буквами `[^\w]*`.
        #    Это позволяет пропускать точки, звездочки, пробелы, дефисы и т.д.
        #    Используем `\W` (небуквенный символ) вместо `[^\w\s]` для большей агрессивности,
        #    так как `\W` включает пробелы.
        # 3. Общая структура: `(char1+)(\W*)(char2+)(\W*)...`
        
        pattern_pieces = []
        for char in root:
            pattern_pieces.append(re.escape(char) + '+')
            pattern_pieces.append(r'\W*') # Allow any non-word characters (including spaces)

        # Join pieces and remove the last separator if it exists
        regex_pattern_str = ''.join(pattern_pieces).rstrip(r'\W*')
        
        patterns.append(f"({regex_pattern_str})") 

    # Объединяем все шаблоны в один regex с использованием OR `|`
    combined_pattern_str = "|".join(patterns)
    
    # Компилируем regex с `re.IGNORECASE` для поиска без учета регистра
    combined_pattern = re.compile(combined_pattern_str, re.IGNORECASE)

    was_censored = False

    def replacer(match):
        nonlocal was_censored
        was_censored = True
        original_match_length = len(match.group(0))
        # Генерируем случайные символы для замены, сохраняя длину исходного совпадения
        replacement = generate_random_symbols(original_match_length)
        logger.debug(f"Censored '{match.group(0)}' to '{replacement}'")
        return replacement

    censored_text = combined_pattern.sub(replacer, text)
    
    logger.debug(f"Final censored text: '{censored_text}', Was censored: {was_censored}")
    return censored_text, was_censored

censor_router = Router(name="censor_router")
censor_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

@censor_router.message(F.text)
async def censor_message_handler(message: types.Message, bot: Bot, profile_manager: Any):
    logger.debug(f"Censor handler received message: '{message.text}' from user {message.from_user.id} in chat {message.chat.id}.")
=======
    """
    Цензурирует текст, заменяя слова, содержащие "плохие" корни, на случайные символы.
    
    Args:
        text (str): Входной текст для цензуры.
        bad_roots (List[str]): Список корней слов, которые нужно цензурировать.
        
    Returns:
        Tuple[str, bool]: Цензурированный текст и флаг, указывающий, была ли произведена цензура.
    """
    logger.debug(f"censor_text_func: Обработка текста: '{text}'")
    censored_parts = []
    was_censored = False
    
    # Регулярное выражение для разделения текста на слова (буквы, цифры) и остальные символы
    # \b\w+\b - слово целиком, \W+ - не-словесные символы (пробелы, знаки препинания)
    words_and_separators = re.findall(r'(\b\w+\b|\W+)', text)

    for item in words_and_separators:
        if re.match(r'^\w+$', item): # Если это слово
            lower_item = item.lower()
            item_censored = False
            for root in bad_roots:
                if root in lower_item:
                    censored_item = generate_random_symbols(len(item))
                    censored_parts.append(censored_item)
                    item_censored = True
                    was_censored = True
                    logger.debug(f"censor_text_func: Слово '{item}' заменено на '{censored_item}'")
                    break
            if not item_censored:
                censored_parts.append(item)
        else: # Если это не слово (пробелы, знаки препинания и т.д.)
            censored_parts.append(item)
            
    censored_text = "".join(censored_parts)
    logger.debug(f"censor_text_func: Результат цензуры: '{censored_text}', Была цензура: {was_censored}")
    return censored_text, was_censored

# Создаем роутер для модуля цензуры
censor_router = Router(name="censor_router")

@censor_router.message(F.text)
async def censor_message_handler(message: types.Message, bot_instance: Bot, profile_manager: Any):
    """
    Обработчик сообщений, который проверяет текст на наличие "плохих" слов.
    Если слова найдены, сообщение удаляется, и отправляется цензурированная версия.
    """
>>>>>>> 14db95269ee53caabc816e1133fad09d46f4a408
    user_id = message.from_user.id
    user_first_name = message.from_user.first_name or "Пользователь"
    original_text = message.text

    if not BAD_WORD_ROOTS:
<<<<<<< HEAD
        logger.debug("Список 'плохих' слов пуст. Сообщение не проверяется на цензуру.")
        return
=======
        logger.debug("Цензура: Список 'плохих' слов пуст. Сообщение не проверяется на цензуру.")
        return # Нечего цензурировать, пропускаем
>>>>>>> 14db95269ee53caabc816e1133fad09d46f4a408

    censored_text, was_censored = censor_text_func(original_text, BAD_WORD_ROOTS)

    if was_censored:
<<<<<<< HEAD
        logger.info(f"CENSOR DETECTED: Original: '{original_text}', Censored: '{censored_text}'")
        try:
            await message.delete()
            logger.info(f"Сообщение {message.message_id} от пользователя {user_id} удалено.")
        except TelegramAPIError as e:
            logger.warning(f"Не удалось удалить сообщение {message.message_id} от пользователя {user_id}: {e.message}. Возможно, у бота нет прав администратора в чате.")
        
        response_text = f"{hbold(user_first_name)} имел в виду: \"{censored_text}\""
        try:
            await bot.send_message(message.chat.id, response_text, parse_mode=ParseMode.HTML)
            logger.info(f"Цензурированное сообщение отправлено в чат {message.chat.id}.")
        except TelegramAPIError as e:
            logger.error(f"Не удалось отправить цензурированное сообщение в чат {message.chat.id}: {e.message}", exc_info=True)
        
        message.stop_propagation()
    else:
        logger.debug(f"CENSOR NO DETECTION: Original: '{original_text}'")
        logger.debug(f"Сообщение от пользователя {user_id} не требует цензуры.")

# ИСПРАВЛЕНИЕ: Изменена сигнатура функции для приема bad_words_file_path
def setup_censor_handlers(main_dp: Router, bot_instance: Bot, bad_words_file_path: Path):
    global BAD_WORD_ROOTS
    BAD_WORD_ROOTS = load_bad_words(bad_words_file_path) # Используем переданный путь
    
    main_dp.include_router(censor_router)
=======
        logger.info(f"Цензура: Сообщение от пользователя {user_id} было цензурировано. Оригинал: '{original_text}', Цензурировано: '{censored_text}'")
        try:
            await message.delete() # Удаляем оригинальное сообщение
            logger.info(f"Цензура: Сообщение {message.message_id} от пользователя {user_id} удалено.")
        except TelegramAPIError as e:
            logger.warning(f"Цензура: Не удалось удалить сообщение {message.message_id} от пользователя {user_id}: {e.message}. Возможно, у бота нет прав администратора в чате.")
            # Продолжаем отправлять цензурированное сообщение, даже если не удалось удалить оригинал
            pass 

        response_text = f"{hbold(user_first_name)} имел в виду: \"{censored_text}\""
        try:
            # Использование ParseMode.HTML напрямую из aiogram.enums
            await bot_instance.send_message(message.chat.id, response_text, parse_mode=ParseMode.HTML)
            logger.info(f"Цензура: Цензурированное сообщение отправлено в чат {message.chat.id}.")
        except TelegramAPIError as e:
            logger.error(f"Цензура: Не удалось отправить цензурированное сообщение в чат {message.chat.id}: {e.message}", exc_info=True)
        
        # Важно: Останавливаем распространение события, чтобы другие F.text обработчики не сработали
        message.stop_propagation()
    else:
        logger.debug(f"Цензура: Сообщение от пользователя {user_id} не требует цензуры.")


def setup_censor_handlers(dp: Router, bot_instance: Bot, profile_manager_instance: Any, bad_words_filepath: Path):
    """
    Настраивает обработчики цензуры и включает их в главный диспетчер.
    
    Args:
        dp (Router): Главный диспетчер (или роутер) Aiogram.
        bot_instance (Bot): Экземпляр бота.
        profile_manager_instance (Any): Экземпляр менеджера профилей.
        bad_words_filepath (Path): Путь к файлу со "злыми" словами.
    """
    global BAD_WORD_ROOTS
    BAD_WORD_ROOTS = load_bad_words(bad_words_filepath)
    
    # Эти две строки были удалены в предыдущих исправлениях,
    # так как они вызывали TypeError.
    # censor_router["bot_instance"] = bot_instance
    # censor_router["profile_manager"] = profile_manager_instance

    dp.include_router(censor_router)
>>>>>>> 14db95269ee53caabc816e1133fad09d46f4a408
    logger.info("Censor module handlers set up and included in main dispatcher.")
