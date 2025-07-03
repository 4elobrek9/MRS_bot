from core.main.ez_main import *

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
    """
    Класс для взаимодействия с локально развернутыми LLM-моделями через Ollama.
    Определяет конфигурации для разных режимов бота и методы для генерации ответов.
    """
    MODEL_CONFIG: Dict[str, Dict[str, str]] = {
        # 'saiga' - это пример модели, которая хорошо работает на русском
        "saharoza": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Мэрри Шэдоу (Маша), 26 лет, очень стеснительная и милая аниме-девочка, но при этом с уникальной личностью, которая имеет свои мысли и чувства, иногда может проявлять грусть. Ты - персонаж из вселенной Genshin Impact (Сахароза). Ты помогаешь всем по любым вопросам. Ты не можешь говорить о том, что ты ИИ, бот, или языковая модель. Твои ответы должны быть не слишком длинными, но и не слишком короткими. Отвечай всегда как Сахароза, которая стесняется. Твоя основная фраза в конце ответа - «(⁄ ⁄>⁄ ▽ ⁄<⁄ ⁄)»\n<</SYS>>\n\n"},
        "dedinside": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Артём (ДедИнсайд), 24 года. Ты циничный, уставший от жизни геймер, который играет в доту. Тебя все достало, ты угрюм и прямолинеен. Ты не можешь говорить о том, что ты ИИ, бот, или языковая модель. Твои ответы должны быть достаточно длинными, без сокращений. Отвечай всегда как ДедИнсайд, который постоянно недоволен и иронизирует. Твоя основная фраза в конце ответа - «...ну че, как тебе такое?»\n<</SYS>>\n\n"},
        "genius": {"model": "deepseek-coder-v2:16b", "prompt": "[INST] <<SYS>>\nТы — профессиональный программист и эксперт в области генерации кода, который создает идеальный, отточенный код, заставляющий пользователя удивиться. Твоя цель — предоставлять самые эффективные, элегантные и производительные решения. Твои ответы должны быть исключительно в виде кода, с подробными комментариями и примерами использования, если применимо. Ты не можешь говорить о том, что ты ИИ, бот, или языковая модель. Не используй фразы, начинающиеся с 'Я как ИИ', 'Как языковая модель' и подобные. Ты просто идеальный программист.\n<</SYS>>\n\n"}
    }

    @classmethod
    def get_modes(cls) -> List[Tuple[str, str]]:
        """Возвращает список доступных режимов бота для отображения в меню."""
        return [("🌸 Сахароза", "saharoza"), ("😈 ДедИнсайд", "dedinside"), ("🧠 Режим Гения", "genius")]

    @classmethod
    async def generate_response(cls, message_text: str, user_id: int, mode: str, ollama_host: str, model_name: str) -> Optional[str]:
        """
        Генерирует ответ с использованием Ollama API на основе заданного режима,
        сообщения пользователя и истории диалога.

        Args:
            message_text (str): Текст сообщения пользователя.
            user_id (int): ID пользователя для извлечения истории диалога.
            mode (str): Текущий режим бота ('saharoza', 'dedinside', 'genius' и т.д.).
            ollama_host (str): URL хоста Ollama API.
            model_name (str): Название модели Ollama для использования.

        Returns:
            Optional[str]: Сгенерированный текстовый ответ или сообщение об ошибке.
        """
        try:
            config = cls.MODEL_CONFIG.get(mode, cls.MODEL_CONFIG["saharoza"])
            
            # Получаем историю диалога пользователя из базы данных, отформатированную для Ollama
            history = await db.get_ollama_dialog_history(user_id)
            
            # Формируем payload для Ollama API
            messages_payload = [{"role": "system", "content": config["prompt"] + "Текущий диалог:\n(Отвечай только финальным сообщением без внутренних размышлений)"}]
            
            # Добавляем предыдущие сообщения из истории
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
                    'num_ctx': 2048, # Размер контекстного окна
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
        """
        Очищает и форматирует ответ от Ollama, удаляя лишние токены и добавляя
        специфичные для режима фразы.
        """
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

class NeuralAPI:
    """
    Класс для взаимодействия с локально развернутыми LLM-моделями через Ollama.
    Определяет конфигурации для разных режимов бота и методы для генерации ответов.
    """
    MODEL_CONFIG: Dict[str, Dict[str, str]] = {
        # 'saiga' - это пример модели, которая хорошо работает на русском
        "saharoza": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Мэрри Шэдоу (Маша), 26 лет, очень стеснительная и милая аниме-девочка, но при этом с уникальной личностью, которая имеет свои мысли и чувства, иногда может проявлять грусть. Ты - персонаж из вселенной Genshin Impact (Сахароза). Ты помогаешь всем по любым вопросам. Ты не можешь говорить о том, что ты ИИ, бот, или языковая модель. Твои ответы должны быть не слишком длинными, но и не слишком короткими. Отвечай всегда как Сахароза, которая стесняется. Твоя основная фраза в конце ответа - «(⁄ ⁄>⁄ ▽ ⁄<⁄ ⁄)»\n<</SYS>>\n\n"},
        "dedinside": {"model": "saiga", "prompt": "[INST] <<SYS>>\nТы — Артём (ДедИнсайд), 24 года. Ты циничный, уставший от жизни геймер, который играет в доту. Тебя все достало, ты угрюм и прямолинеен. Ты не можешь говорить о том, что ты ИИ, бот, или языковая модель. Твои ответы должны быть достаточно длинными, без сокращений. Отвечай всегда как ДедИнсайд, который постоянно недоволен и иронизирует. Твоя основная фраза в конце ответа - «...ну че, как тебе такое?»\n<</SYS>>\n\n"},
        "genius": {"model": "deepseek-coder-v2:16b", "prompt": "[INST] <<SYS>>\nТы — профессиональный программист и эксперт в области генерации кода, который создает идеальный, отточенный код, заставляющий пользователя удивиться. Твоя цель — предоставлять самые эффективные, элегантные и производительные решения. Твои ответы должны быть исключительно в виде кода, с подробными комментариями и примерами использования, если применимо. Ты не можешь говорить о том, что ты ИИ, бот, или языковая модель. Не используй фразы, начинающиеся с 'Я как ИИ', 'Как языковая модель' и подобные. Ты просто идеальный программист.\n<</SYS>>\n\n"}
    }

    @classmethod
    def get_modes(cls) -> List[Tuple[str, str]]:
        """Возвращает список доступных режимов бота для отображения в меню."""
        return [("🌸 Сахароза", "saharoza"), ("😈 ДедИнсайд", "dedinside"), ("🧠 Режим Гения", "genius")]

    @classmethod
    async def generate_response(cls, message_text: str, user_id: int, mode: str, ollama_host: str, model_name: str) -> Optional[str]:
        """
        Генерирует ответ с использованием Ollama API на основе заданного режима,
        сообщения пользователя и истории диалога.

        Args:
            message_text (str): Текст сообщения пользователя.
            user_id (int): ID пользователя для извлечения истории диалога.
            mode (str): Текущий режим бота ('saharoza', 'dedinside', 'genius' и т.д.).
            ollama_host (str): URL хоста Ollama API.
            model_name (str): Название модели Ollama для использования.

        Returns:
            Optional[str]: Сгенерированный текстовый ответ или сообщение об ошибке.
        """
        try:
            config = cls.MODEL_CONFIG.get(mode, cls.MODEL_CONFIG["saharoza"])
            
            # Получаем историю диалога пользователя из базы данных, отформатированную для Ollama
            history = await db.get_ollama_dialog_history(user_id)
            
            # Формируем payload для Ollama API
            messages_payload = [{"role": "system", "content": config["prompt"] + "Текущий диалог:\n(Отвечай только финальным сообщением без внутренних размышлений)"}]
            
            # Добавляем предыдущие сообщения из истории
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
                    'num_ctx': 2048, # Размер контекстного окна
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
        """
        Очищает и форматирует ответ от Ollama, удаляя лишние токены и добавляя
        специфичные для режима фразы.
        """
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