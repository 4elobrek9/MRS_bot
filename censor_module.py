import random
import re
from pathlib import Path
import logging
from typing import List, Tuple, Any, Dict, Callable, Awaitable # Добавлены Callable, Awaitable
import asyncio
from contextlib import suppress
from aiogram import Router, types, F, Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.utils.markdown import hbold
from aiogram.enums import ParseMode, ChatType

# Настройка логгера для модуля цензуры
logger = logging.getLogger(__name__)

# Глобальная переменная для хранения корней "плохих" слов
BAD_WORD_ROOTS: List[str] = []

# Глобальная переменная для хранения списка команд, которые должны игнорироваться цензором
NON_SLASH_COMMAND_PREFIXES: List[str] = []

# Глобальные переменные для прямого вызова обработчиков
DIRECT_DISPATCH_HANDLERS: Dict[str, Tuple[Callable[..., Awaitable[Any]], List[str]]] = {}
GLOBAL_PROFILE_MANAGER: Any = None
GLOBAL_BOT: Any = None


def load_bad_words(filepath: Path) -> List[str]:
    """
    Загружает список "плохих" слов из указанного файла.
    """
    logger.debug(f"censor_module.load_bad_words: Попытка загрузить слова из файла: {filepath}")
    try:
        if not filepath.exists():
            logger.warning(f"censor_module.load_bad_words: Файл со 'злыми' словами '{filepath}' не найден. Цензура слов отключена.")
            return []
        
        with open(filepath, 'r', encoding='utf-8') as f:
            words = [line.strip().lower() for line in f if line.strip()]
        
        logger.info(f"censor_module.load_bad_words: Успешно загружено {len(words)} корней 'злых' слов из {filepath}.")
        return words
    except Exception as e:
        logger.error(f"censor_module.load_bad_words: Ошибка при загрузке 'злых' слов из {filepath}: {e}", exc_info=True)
        return []

def generate_random_symbols(length: int) -> str:
    """
    Генерирует случайную строку из спецсимволов заданной длины.
    """
    symbols = "@#$%^&"
    if not symbols:
        logger.warning("censor_module.generate_random_symbols: Список доступных символов для цензуры пуст. Возвращена пустая строка.")
        return ""

    censored_chars = []
    last_char = None

    for _ in range(length):
        available_symbols = [s for s in symbols if s != last_char]
        if not available_symbols:
            available_symbols = list(symbols)

        current_char = random.choice(available_symbols)
        censored_chars.append(current_char)
        last_char = current_char
        
    result = ''.join(censored_chars)
    logger.debug(f"censor_module.generate_random_symbols: Сгенерированы случайные символы длиной {length}: '{result}'")
    return result

def censor_text_func(text: str, bad_roots: List[str]) -> Tuple[str, bool, List[str]]:
    """
    Основная функция цензуры текста. Ищет "плохие" корни слов в тексте
    и заменяет их случайными символами.
    Изменена логика для цензурирования ВСЕГО слова, содержащего корень.
    """
    logger.debug(f"censor_module.censor_text_func: Начата обработка текста: '{text}' с корнями: {bad_roots}")
    
    if not bad_roots:
        logger.debug("censor_module.censor_text_func: Список 'плохих' слов пуст. Цензура не выполняется.")
        return text, False, []

    patterns = []
    for root in bad_roots:
        # Строим агрессивное регулярное выражение для каждого корня.
        # Пример: для корня "шлю" будет создан паттерн "ш+\W*л+\W*ю+"
        root_pattern_inner = ""
        for char in root:
            # Экранируем спецсимволы в корне и добавляем '+' для повторений символа
            root_pattern_inner += re.escape(char) + '+'
            # Добавляем \W* для игнорирования небуквенных символов между буквами корня (например, "м@т")
            root_pattern_inner += r'\W*' 
        # Удаляем лишний \W* в конце, если он есть
        root_pattern_inner = root_pattern_inner.rstrip(r'\W*')

        # Паттерн для захвата ВСЕГО слова, содержащего корень
        # \b - граница слова (гарантирует, что мы ищем целое слово)
        # (?:\w*{root_pattern_inner}\w*) - не-захватывающая группа, которая ищет
        #   \w* - ноль или более "буквенных" символов до корня
        #   {root_pattern_inner} - сам агрессивный паттерн корня
        #   \w* - ноль или более "буквенных" символов после корня
        full_word_pattern = rf"\b(?:\w*{root_pattern_inner}\w*)\b"
        patterns.append(full_word_pattern)

    combined_pattern_str = "|".join(patterns)
    logger.debug(f"censor_module.censor_text_func: Сформировано объединенное регулярное выражение: '{combined_pattern_str}'")
    
    # Компилируем регулярное выражение для повышения производительности
    # re.IGNORECASE - игнорировать регистр
    # re.UNICODE - для корректной работы с Юникод-символами (русский язык)
    combined_pattern = re.compile(combined_pattern_str, re.IGNORECASE | re.UNICODE)

    was_censored = False
    found_words = []

    def replacer(match):
        """
        Функция-заменитель для `re.sub()`. Вызывается для каждого найденного совпадения.
        """
        nonlocal was_censored
        was_censored = True
        matched_word = match.group(0) 
        found_words.append(matched_word)
        # Генерируем замену той же длины, что и найденное слово
        replacement = generate_random_symbols(len(matched_word)) 
        logger.debug(f"censor_module.censor_text_func: Обнаружено совпадение '{matched_word}', заменено на '{replacement}'")
        return replacement

    censored_text = combined_pattern.sub(replacer, text)
    
    logger.debug(f"censor_module.censor_text_func: Конечный цензурированный текст: '{censored_text}', Было ли цензурировано: {was_censored}")
    return censored_text, was_censored, found_words

# Создаем роутер для модуля цензуры
censor_router = Router(name="censor_router")
# Фильтр для работы ТОЛЬКО в групповых и супергрупповых чатах
censor_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})) 
logger.debug("censor_router: Настроен фильтр для работы ТОЛЬКО в групповых и супергрупповых чатах.")


@censor_router.message(F.text)
async def censor_message_handler(message: types.Message, bot: Bot):
    """
    Обработчик входящих текстовых сообщений.
    Проверяет сообщение на наличие "плохих" слов. Если найдены,
    удаляет оригинальное сообщение и отправляет цензурированную версию.
    Если сообщение является командой (начинается с '/' или является известной не-слеш командой),
    оно пропускается.
    """
    logger.debug(f"censor_message_handler: Получено сообщение: '{message.text}' от пользователя {message.from_user.id} в чате {message.chat.id}.")
    
    # Проверяем, что сообщение не от самого бота, чтобы избежать цикла
    if not message.from_user or message.from_user.id == bot.id:
        logger.debug("censor_message_handler: Сообщение от бота или без пользователя. Пропускаем.")
        return

    user = message.from_user
    original_text = message.text
    original_text_lower = original_text.lower()

    # Пропускаем сообщения, начинающиеся с "/" (команды)
    if original_text.startswith('/'):
        logger.debug(f"censor_message_handler: Сообщение '{original_text}' является командой со слешем. Пропускаем цензуру.")
        # Важно: если это команда, мы просто возвращаемся, позволяя Aiogram передать ее дальше
        # по цепочке обработчиков, где ее подхватит соответствующий Command-обработчик.
        return 

    # Проверяем, является ли сообщение известной не-слеш командой для прямого вызова
    for cmd_prefix in NON_SLASH_COMMAND_PREFIXES:
        if original_text_lower.startswith(cmd_prefix):
            # Дополнительная проверка, чтобы убедиться, что это именно команда, а не часть другого слова
            # Например, "профиль" должен сработать, но "профилька" - нет.
            # Проверяем, что после команды идет пробел, или это конец строки
            if len(original_text_lower) == len(cmd_prefix) or \
               (len(original_text_lower) > len(cmd_prefix) and original_text_lower[len(cmd_prefix)].isspace()):
                
                logger.debug(f"censor_message_handler: Сообщение '{original_text}' является известной не-слеш командой '{cmd_prefix}'. Попытка прямого вызова обработчика.")
                
                if cmd_prefix in DIRECT_DISPATCH_HANDLERS:
                    handler_func, required_args_names = DIRECT_DISPATCH_HANDLERS[cmd_prefix]
                    
                    # Подготавливаем аргументы для обработчика
                    handler_args = {}
                    if "message" in required_args_names:
                        handler_args["message"] = message
                    if "bot" in required_args_names and GLOBAL_BOT:
                        handler_args["bot"] = GLOBAL_BOT
                    if "profile_manager" in required_args_names and GLOBAL_PROFILE_MANAGER:
                        handler_args["profile_manager"] = GLOBAL_PROFILE_MANAGER
                    if "command_text_payload" in required_args_names:
                        handler_args["command_text_payload"] = original_text # Передаем полный текст как payload

                    try:
                        await handler_func(**handler_args)
                        logger.info(f"censor_message_handler: Прямой вызов обработчика для '{cmd_prefix}' успешно выполнен. Завершение обработки сообщения.")
                        return # Останавливаем дальнейшую обработку после прямого вызова
                    except Exception as e:
                        logger.error(f"censor_message_handler: Ошибка при прямом вызове обработчика для '{cmd_prefix}': {e}", exc_info=True)
                        await message.reply(f"❌ Произошла ошибка при обработке команды '{cmd_prefix}'.")
                        return # Возвращаемся после ошибки, чтобы избежать дальнейшей обработки

    if not BAD_WORD_ROOTS:
        logger.debug("censor_message_handler: Список 'плохих' слов пуст. Сообщение не проверяется на цензуру. Пропускаем обработку.")
        return # Выходим, если нет слов для цензуры

    logger.debug(f"censor_message_handler: Вызов censor_text_func для текста: '{original_text}'")
    censored_text, was_censored, found_words = censor_text_func(original_text, BAD_WORD_ROOTS)
    logger.debug(f"censor_message_handler: Результат censor_text_func: was_censored={was_censored}")

    if was_censored:
        logger.info(f"censor_message_handler: ЦЕНЗУРА ОБНАРУЖЕНА: Оригинал: '{original_text}', Цензурировано: '{censored_text}'. Найденные слова: {found_words}")
        
        # Попытка удалить оригинальное сообщение
        logger.debug(f"censor_message_handler: Попытка удалить сообщение {message.message_id} от пользователя {user.id}.")
        try:
            await message.delete()
            logger.info(f"censor_message_handler: Сообщение {message.message_id} от пользователя {user.id} УСПЕШНО удалено.")
        except TelegramAPIError as e:
            logger.warning(f"censor_message_handler: НЕ УДАЛОСЬ удалить сообщение {message.message_id} от пользователя {user.id}: {e.message}. Возможно, у бота нет прав администратора в чате.")
        except Exception as e:
            logger.error(f"censor_message_handler: Непредвиденная ошибка при попытке удаления сообщения {message.message_id}: {e}", exc_info=True)
        
        # Формирование и отправка цензурированного сообщения
        response_text = f"{hbold(user.first_name or 'Пользователь')} имел в виду: \"{censored_text}\""
        logger.debug(f"censor_message_handler: Попытка отправить цензурированное сообщение в чат {message.chat.id}: '{response_text}'")
        try:
            await bot.send_message(message.chat.id, response_text, parse_mode=ParseMode.HTML)
            logger.info(f"censor_message_handler: Цензурированное сообщение УСПЕШНО отправлено в чат {message.chat.id}.")
        except TelegramAPIError as e:
            logger.error(f"censor_message_handler: НЕ УДАЛОСЬ отправить цензурированное сообщение в чат {message.chat.id}: {e.message}", exc_info=True)
        except Exception as e:
            logger.error(f"censor_message_handler: Непредвиденная ошибка при попытке отправки цензурированного сообщения: {e}", exc_info=True)
        
        # Если цензура сработала, мы полностью обработали сообщение.
        # Возвращение чего-либо (или ничего) после await message.delete() и await bot.send_message()
        # обычно приводит к тому, что Aiogram не передает сообщение дальше.
        return 

    else:
        logger.debug(f"censor_message_handler: ЦЕНЗУРА НЕ ОБНАРУЖЕНА: Оригинал: '{original_text}'")
        logger.debug(f"censor_message_handler: Сообщение от пользователя {user.id} не требует цензуры. Сообщение будет передано для дальнейшей обработки.")
        return # Если цензура не сработала, возвращаем None, чтобы сообщение продолжило распространение
               # к другим обработчикам (например, F.text.lower().startswith("профиль") в stat_router).

def setup_censor_handlers(
    main_dp: Router, 
    bad_words_file_path: Path, 
    non_slash_command_prefixes: List[str],
    direct_dispatch_handlers: Dict[str, Tuple[Callable[..., Awaitable[Any]], List[str]]],
    profile_manager_instance: Any,
    bot_instance: Any
):
    """
    Настраивает модуль цензуры: загружает "плохие" слова и включает
    роутер цензуры в главный диспетчер Aiogram.
    Также принимает список не-слеш команд, которые цензор должен игнорировать
    и словарь для прямого вызова обработчиков.
    """
    logger.debug(f"setup_censor_handlers: Начата настройка модуля цензуры.")
    global BAD_WORD_ROOTS
    BAD_WORD_ROOTS = load_bad_words(bad_words_file_path) # Загружаем слова при инициализации
    
    global NON_SLASH_COMMAND_PREFIXES
    # Сортируем по длине в убывающем порядке, чтобы более длинные команды проверялись первыми (например, "моё хп" раньше "хп")
    NON_SLASH_COMMAND_PREFIXES = sorted([cmd.lower() for cmd in non_slash_command_prefixes], key=len, reverse=True) 
    logger.debug(f"setup_censor_handlers: Загружены не-слеш команды для игнорирования цензором: {NON_SLASH_COMMAND_PREFIXES}")

    global DIRECT_DISPATCH_HANDLERS
    DIRECT_DISPATCH_HANDLERS = direct_dispatch_handlers
    
    global GLOBAL_PROFILE_MANAGER
    GLOBAL_PROFILE_MANAGER = profile_manager_instance

    global GLOBAL_BOT
    GLOBAL_BOT = bot_instance

    logger.debug("setup_censor_handlers: Включение censor_router в главный диспетчер.")
    main_dp.include_router(censor_router)
    logger.info("setup_censor_handlers: Обработчики модуля цензуры успешно настроены и включены в главный диспетчер.")
