# mistral_group_chat.py
import asyncio
import logging
import random
import re
from contextlib import suppress
from datetime import datetime, time
from typing import Dict, List, Deque, Set
from collections import deque
import aiohttp
from aiogram import Bot, types
from aiogram.enums import ParseMode, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import ReactionTypeEmoji
from aiogram.enums import ReactionTypeType
from core.main.watermark import apply_watermark
import database as db # ❗ NEW: Добавьте этот импорт

logger = logging.getLogger(__name__)

class MistralGroupHandler:
    def __init__(self, bot: Bot, mistral_api_key: str, bot_username: str, sticker_manager=None):
        self.bot = bot
        self.api_key = mistral_api_key
        self.bot_username = bot_username
        self.sticker_manager = sticker_manager
        self.base_url = "https://api.mistral.ai/v1"
        self.model = "mistral-small-latest"  # Или mistral-tiny, mistral-medium

        # --- НАСТРОЙКИ ---
        self.history_limit = 15  # Сколько сообщений помнить для контекста
        self.context_ttl = 600   # Время жизни контекста пользователя (10 мин)
        self.question_interval = 3600  # Интервал авто-вопросов (1 час)

        # Время работы (12:00 - 00:00)
        self.start_time = time(12, 0)
        self.end_time = time(23, 59)

        # --- ПАМЯТЬ ---
        # История чата: {chat_id: deque([msg1, msg2, ...], maxlen=15)}
        self.chat_history: Dict[int, Deque[Dict]] = {}

        # Контекст общения внутри группы: {chat_id: {user_id: timestamp}}
        self.user_active_context: Dict[int, Dict[int, float]] = {}
        # Память участников группы: {chat_id: {user_id: "имя"}}
        self.chat_participants: Dict[int, Dict[int, str]] = {}
        # Недавняя активность для умного ограничения: {chat_id: deque[(ts, user_id)]}
        self.recent_activity: Dict[int, Deque[tuple[float, int]]] = {}

        # Время последнего авто-вопроса: {chat_id: datetime}
        self.last_question_time: Dict[int, datetime] = {}
        # Счетчик входящих сообщений в чате для ответа на каждое N-е
        self.chat_message_counter: Dict[int, int] = {}
        # Счётчик ответов на сообщения бота в чате
        self.reply_message_counter: Dict[int, int] = {}
        self.last_reply_time: Dict[int, float] = {}
        # Все известные чаты, где бот видел сообщения
        self.known_chats: Set[int] = set()
        # Ширина окна активности и лимит одновременных участников
        self.activity_window_seconds = 120
        self.max_active_participants = 4

        # Темы для разговора (можно расширить)
        self.conversation_topics = [
            "последних новостях в мире технологий", "странных привычках людей",
            "будущем нейросетей", "видеоиграх", "кино и сериалах",
            "том, как прошел день", "планах на выходные", "философии жизни"
        ]

    def _is_working_hours(self) -> bool:
        """Проверяет, находится ли текущее время в диапазоне 12:00 - 00:00"""
        now = datetime.now().time()
        # Если start < end (стандартный случай 12:00 - 23:59)
        if self.start_time <= self.end_time:
            return self.start_time <= now <= self.end_time
        # Если интервал переходит через полночь (на всякий случай)
        return self.start_time <= now or now <= self.end_time

    def _add_to_history(self, chat_id: int, username: str, text: str, is_bot: bool = False):
        """Сохраняет сообщение в локальную память бота"""
        if chat_id not in self.chat_history:
            self.chat_history[chat_id] = deque(maxlen=self.history_limit)

        role = "assistant" if is_bot else "user"
        self.chat_history[chat_id].append({
            "role": role,
            "name": username,
            "content": text,
            "timestamp": datetime.now().timestamp()
        })

    @staticmethod
    def _normalize_message_text(text: str) -> str:
        normalized = (text or "").strip().lower()
        return re.sub(r"[\s\.,!?:;]+$", "", normalized)

    def _register_participant(self, chat_id: int, user_id: int, username: str):
        if chat_id not in self.chat_participants:
            self.chat_participants[chat_id] = {}
        self.chat_participants[chat_id][user_id] = username

    def _update_recent_activity(self, chat_id: int, user_id: int) -> int:
        now_ts = datetime.now().timestamp()
        if chat_id not in self.recent_activity:
            self.recent_activity[chat_id] = deque()

        activity = self.recent_activity[chat_id]
        activity.append((now_ts, user_id))
        cutoff = now_ts - self.activity_window_seconds
        while activity and activity[0][0] < cutoff:
            activity.popleft()

        unique_users: Set[int] = {uid for _, uid in activity}
        return len(unique_users)

    async def generate_mistral_response(self, chat_id: int, prompt_instruction: str) -> str:
        """Отправляет запрос в Mistral AI с историей переписки"""
        if chat_id not in self.chat_history or not self.chat_history[chat_id]:
            return ""

        history = list(self.chat_history[chat_id])

        # Формируем сообщения для API
        messages = [
            {"role": "system", "content": (
                "Ты — участник группового чата, дерзкий, но дружелюбный бот. "
                "Твоя цель — разговорить людей, поддерживать беседу. "
                "Не пиши длинные тексты, пиши как живой человек в чате (1-2 предложения). "
                "Используй сленг, если уместно. Не будь душным. "
                f"{prompt_instruction}"
            )}
        ]

        # Добавляем историю
        for msg in history:
            # Mistral API ожидает role 'user' или 'assistant' (или 'system')
            # Мы добавим имя пользователя в контент, чтобы бот понимал, кто пишет
            content = f"{msg['name']}: {msg['content']}" if msg['role'] == 'user' else msg['content']
            messages.append({"role": msg['role'], "content": content})

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.8,
                    "max_tokens": 150
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                async with session.post(f"{self.base_url}/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data['choices'][0]['message']['content']
                    else:
                        logger.error(f"Mistral API Error: {await resp.text()}")
                        return ""
        except Exception as e:
            logger.error(f"Mistral Request Failed: {e}")
            return ""

    async def warmup_ping(self) -> str:
        """Проверочный запрос к Mistral на старте."""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "Ответь коротко и дружелюбно."},
                        {"role": "user", "content": "Привет"}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 40
                }
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                async with session.post(f"{self.base_url}/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        return f"warmup failed status={resp.status}: {await resp.text()}"
                    data = await resp.json()
                    return data['choices'][0]['message']['content']
        except Exception as e:
            return f"warmup exception: {e!r}"

    async def handle_all_group_messages(self, message: types.Message):
        """Основной метод обработки входящего сообщения"""
        chat_id = message.chat.id
        user_id = message.from_user.id
        text = message.text or message.caption or ""
        username = message.from_user.first_name

        # Регистрируем чат сразу, чтобы бот отслеживал все группы, где присутствует.
        self.known_chats.add(chat_id)

        # Проверяем, что это групповой чат и не бот
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP] or message.from_user.is_bot:
            return UNHANDLED

        raw_message_text = message.text or ""
        message_text = self._normalize_message_text(raw_message_text)

        # 1) Сначала отсекаем команды (/команды)
        if raw_message_text.startswith('/'):
            return UNHANDLED

        # 2) Потом отсекаем текстовые игровые/RP/конфиг команды
        text_commands_to_ignore = {
            "профиль", "топ", "работать", "инвентарь", "верстак", "магазин",
            "продать", "обмен", "аукцион", "рынок", "инвестировать",
            "задания", "квесты", "пмагазин", "pshop",
            "доп. функции", "дополнительные функции", "конфиг", "config", "cfg", "настройки", "dop_func",
            "статистика", "stats", "анекдот", "joke",
            "heal", "myhp", "myhealth", "health", "рп действия", "rpactions"
        }

        # Удаляем упоминание бота, если оно есть (например, "профиль @botname")
        if self.bot_username and message_text.endswith(f"@{self.bot_username}".lower()):
             message_text = message_text.replace(f"@{self.bot_username}".lower(), "").strip()

        if message_text in text_commands_to_ignore:
            return UNHANDLED  # Если текст совпадает с командой, LLM игнорирует его.

        # 3) Проверяем статус LLM в группе (в конфиге можно выключить полностью)
        if not await db.get_ai_status(chat_id):
            return UNHANDLED  # AI выключен, игнорируем сообщение

        # 4) Умная активность: если одновременно активно много людей — AI молчит
        active_participants = self._update_recent_activity(chat_id, user_id)
        self._register_participant(chat_id, user_id, username)
        if active_participants >= self.max_active_participants:
            logger.debug("Skipping AI in chat %s due to high activity: %s users", chat_id, active_participants)
            return UNHANDLED

        # 1. Сохраняем сообщение в историю (всегда, даже если не отвечаем)
        self._add_to_history(chat_id, username, text, is_bot=False)

        # Если сообщение от бота - игнорируем дальнейшую обработку (но в историю сохранили)
        if message.from_user.is_bot:
            return UNHANDLED

        # 2. Проверка контекста пользователя (активный диалог)
        is_in_context = False
        now_ts = datetime.now().timestamp()
        chat_context = self.user_active_context.setdefault(chat_id, {})
        if user_id in chat_context:
            if now_ts - chat_context[user_id] < self.context_ttl:
                is_in_context = True

        # Обновляем время активности юзера
        chat_context[user_id] = now_ts

        # 3. Логика принятия решения об ответе
        should_respond = False
        prompt_instruction = ""

        # Если ответили НА сообщение бота
        is_reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == self.bot.id
        )
        is_mention = bool(self.bot_username and f"@{self.bot_username.lower()}" in text.lower())

        # AI отвечает когда ему отвечают (reply/mention), с небольшим антиспам-интервалом.
        if is_reply_to_bot or is_mention:
            now_reply = datetime.now().timestamp()
            last_reply = self.last_reply_time.get(chat_id, 0)
            if self._is_working_hours() and (now_reply - last_reply) >= 12:
                should_respond = True
                member = await self.bot.get_chat_member(chat_id, user_id)
                honorific = ""
                if username.lower() == "rin":
                    honorific = "Обращайся: «госпожа Рин», максимально уважительно."
                elif username.lower() == "ace":
                    honorific = "Обращайся: «господин Ace», максимально уважительно."
                elif member.status in {"administrator", "creator"}:
                    honorific = "Пользователь админ, обращайся уважительно."

                prompt_instruction = "Пользователь ответил тебе. Ответь коротко, дружелюбно и по теме. " + honorific
                self.last_reply_time[chat_id] = now_reply

        # 4. Генерация и отправка
        if should_respond:
            # Ставим статус "печатает"
            await self.bot.send_chat_action(chat_id, "typing")

            response = await self.generate_mistral_response(chat_id, prompt_instruction)

            if response:
                final_response = apply_watermark(response)
                try:
                    # Всегда отвечаем реплаем на сообщение пользователя.
                    reply_target_message_id = message.message_id
                    sent = await self.bot.send_message(
                        chat_id,
                        final_response,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_to_message_id=reply_target_message_id,
                    )
                    # Реакции с шансом 20%
                    if random.random() < 0.2:
                        reaction = random.choice(["🔥", "❤️", "👍", "⚡", "💯"])
                        try:
                            await self.bot.set_message_reaction(
                                chat_id=chat_id,
                                message_id=message.message_id,
                                reaction=[ReactionTypeEmoji(type=ReactionTypeType.EMOJI, emoji=reaction)],
                                is_big=False,
                            )
                        except Exception as react_err:
                            logger.debug("Reaction could not be set in chat %s: %r", chat_id, react_err)
                    # Стикер с шансом 40%
                    if self.sticker_manager is not None and random.random() < 0.4:
                        with suppress(Exception):
                            mode = random.choice(list(self.sticker_manager.sticker_packs.keys()))
                            sticker_id = self.sticker_manager.get_random_sticker(mode)
                            if sticker_id:
                                await self.bot.send_sticker(chat_id, sticker_id, reply_to_message_id=sent.message_id)
                    self._add_to_history(chat_id, self.bot_username, response, is_bot=True)
                    logger.info(f"Mistral replied to {chat_id}")
                except TelegramAPIError as e:
                    logger.error(f"Failed to send message: {e}")
        return UNHANDLED

    async def periodic_question_task(self):
        """Фоновая задача: задавать вопросы раз в час"""
        logger.info("Starting Mistral periodic tasks...")
        while True:
            try:
                if self._is_working_hours():
                    now = datetime.now()
                    # Проходим по всем известным чатам (а не только с уже накопленной историей)
                    for chat_id in list(self.known_chats):

                        # ❗ NEW: Проверяем статус LLM в группе
                        if not await db.get_ai_status(chat_id):
                            continue # AI выключен, пропускаем этот чат

                        last_time = self.last_question_time.get(chat_id)

                        # Если прошло больше часа или вопросов еще не было
                        if not last_time or (now - last_time).total_seconds() > self.question_interval:
                            # Генерируем вопрос
                            topic = random.choice(self.conversation_topics)
                            prompt = f"Придумай интересный, провокационный или философский вопрос для группы людей на тему: {topic}. Вопрос должен побуждать к обсуждению."

                            response = await self.generate_mistral_response(chat_id, prompt)
                            if response:
                                final_response = apply_watermark(response)
                                try:
                                    await self.bot.send_message(chat_id, final_response, parse_mode=ParseMode.MARKDOWN)
                                    self._add_to_history(chat_id, self.bot_username, response, is_bot=True)
                                    self.last_question_time[chat_id] = now
                                    # Системный вопрос тоже считается сообщением AI, на него можно отвечать.
                                    self.reply_message_counter[chat_id] = 0
                                    logger.info(f"Mistral sent periodic question to {chat_id}")
                                except TelegramAPIError as e:
                                    logger.error(f"Failed to send message: {e}")

                # Ждем минуту перед следующей проверкой
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in Mistral periodic task: {e}")
                await asyncio.sleep(60)
