# mistral_group_chat.py
import asyncio
import logging
import random
from datetime import datetime, time
from typing import Dict, List, Deque
from collections import deque
import aiohttp
from aiogram import Bot, types
from aiogram.enums import ParseMode, ChatType
from aiogram.exceptions import TelegramAPIError
from core.main.watermark import apply_watermark
import database as db # ❗ NEW: Добавьте этот импорт

logger = logging.getLogger(__name__)

class MistralGroupHandler:
    def __init__(self, bot: Bot, mistral_api_key: str, bot_username: str):
        self.bot = bot
        self.api_key = mistral_api_key
        self.bot_username = bot_username
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

        # Контекст общения с конкретными юзерами: {user_id: timestamp}
        self.user_active_context: Dict[int, float] = {}

        # Время последнего авто-вопроса: {chat_id: datetime}
        self.last_question_time: Dict[int, datetime] = {}

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

    async def handle_all_group_messages(self, message: types.Message):
        """Основной метод обработки входящего сообщения"""
        chat_id = message.chat.id
        user_id = message.from_user.id
        text = message.text or message.caption or ""
        username = message.from_user.first_name

        # Проверяем, что это групповой чат и не бот
        if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP] or message.from_user.is_bot:
            return

        # ❗ NEW: Проверяем статус LLM в группе
        if not await db.get_ai_status(chat_id):
            return # AI выключен, игнорируем сообщение

        # 1. Сохраняем сообщение в историю (всегда, даже если не отвечаем)
        self._add_to_history(chat_id, username, text, is_bot=False)

        # Если сообщение от бота - игнорируем дальнейшую обработку (но в историю сохранили)
        if message.from_user.is_bot:
            return

        # 2. Проверка контекста пользователя (активный диалог)
        is_in_context = False
        now_ts = datetime.now().timestamp()
        if user_id in self.user_active_context:
            if now_ts - self.user_active_context[user_id] < self.context_ttl:
                is_in_context = True

        # Обновляем время активности юзера
        self.user_active_context[user_id] = now_ts

        # 3. Логика принятия решения об ответе
        should_respond = False
        prompt_instruction = ""

        # Если ответили НА сообщение бота
        is_reply = message.reply_to_message is not None
        is_mention = self.bot_username in text

        if is_reply or is_mention:
            should_respond = True
            prompt_instruction = "Пользователь ответил тебе. Поддержи диалог, пошути или задай встречный вопрос."

        # Если активное время (12:00 - 00:00)
        elif self._is_working_hours():
            # Если пользователь в контексте (мы недавно общались), вероятность ответа выше
            if is_in_context:
                # 30% шанс продолжить тему, если диалог идет
                if random.random() < 0.3:
                    should_respond = True
                    prompt_instruction = "Пользователь продолжает беседу. Прокомментируй кратко или пошути."
            else:
                # Если просто пишут в чат, маленький шанс (например 5%), чтобы "влезть"
                if random.random() < 0.05:
                    should_respond = True
                    prompt_instruction = "Вклинься в разговор с интересным комментарием или вопросом."

        # 4. Генерация и отправка
        if should_respond:
            # Ставим статус "печатает"
            await self.bot.send_chat_action(chat_id, "typing")

            response = await self.generate_mistral_response(chat_id, prompt_instruction)

            if response:
                final_response = apply_watermark(response)
                try:
                    await message.reply(final_response, parse_mode=ParseMode.MARKDOWN)
                    self._add_to_history(chat_id, self.bot_username, response, is_bot=True)
                    logger.info(f"Mistral replied to {chat_id}")
                except TelegramAPIError as e:
                    logger.error(f"Failed to send message: {e}")

    async def periodic_question_task(self):
        """Фоновая задача: задавать вопросы раз в час"""
        logger.info("Starting Mistral periodic tasks...")
        while True:
            try:
                if self._is_working_hours():
                    now = datetime.now()
                    # Проходим по всем известным чатам
                    for chat_id in list(self.chat_history.keys()):

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
                                    logger.info(f"Mistral sent periodic question to {chat_id}")
                                except TelegramAPIError as e:
                                    logger.error(f"Failed to send message: {e}")

                # Ждем минуту перед следующей проверкой
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in Mistral periodic task: {e}")
                await asyncio.sleep(60)
