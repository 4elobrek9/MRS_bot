import random
import os
import aiohttp
import asyncio
import importlib
import tempfile
from contextlib import suppress
from typing import Optional

from core.main.ez_main import (
    dp,
    logger,
    VALUE_FILE_PATH,
    OLLAMA_API_BASE_URL,
    OLLAMA_MODEL_NAME,
)
from core.main.ollama import NeuralAPI, safe_send_message, typing_animation, fetch_random_joke, StickerManager
from core.group.stat.manager import ProfileManager
import database as db
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold
from aiogram.filters import Command
from aiogram.types import Message
from aiogram import F
from aiogram.enums import ChatType, ParseMode
from aiogram import Bot
from command import cmd_help

MAX_RATING_OPPORTUNITIES = 5
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
LOCAL_STT_MODEL_NAME = os.getenv("LOCAL_STT_MODEL", "small")
LOCAL_STT_DEVICE = os.getenv("LOCAL_STT_DEVICE", "auto")
LOCAL_STT_COMPUTE_TYPE = os.getenv("LOCAL_STT_COMPUTE_TYPE", "int8")
_LOCAL_STT_MODEL = None


def _local_stt_installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def _get_local_stt_model():
    global _LOCAL_STT_MODEL
    if _LOCAL_STT_MODEL is not None:
        return _LOCAL_STT_MODEL

    if not _local_stt_installed():
        logger.error("Local STT disabled: package 'faster_whisper' is not installed.")
        return None

    faster_whisper = importlib.import_module("faster_whisper")
    _LOCAL_STT_MODEL = faster_whisper.WhisperModel(
        LOCAL_STT_MODEL_NAME,
        device=LOCAL_STT_DEVICE,
        compute_type=LOCAL_STT_COMPUTE_TYPE,
    )
    logger.info("Local STT model loaded: %s (%s/%s)", LOCAL_STT_MODEL_NAME, LOCAL_STT_DEVICE, LOCAL_STT_COMPUTE_TYPE)
    return _LOCAL_STT_MODEL


def _transcribe_file_sync(file_path: str) -> Optional[str]:
    model = _get_local_stt_model()
    if model is None:
        return None

    segments, _ = model.transcribe(
        file_path,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
        without_timestamps=True,
    )
    text = " ".join((segment.text or "").strip() for segment in segments).strip()
    return text or None


async def _transcribe_telegram_media(message: Message, bot: Bot, file_id: str, filename: str) -> Optional[str]:
    """Скачивает медиа из Telegram и расшифровывает локально (без внешних API)."""
    try:
        tg_file = await bot.get_file(file_id)
        file_buffer = await bot.download(tg_file)
        if file_buffer is None:
            return None
        file_bytes = file_buffer.read()
        if not file_bytes:
            return None

        suffix = ".ogg"
        if "." in filename:
            suffix = "." + filename.rsplit(".", 1)[-1]

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_audio:
            temp_audio.write(file_bytes)
            temp_path = temp_audio.name

        try:
            return await asyncio.to_thread(_transcribe_file_sync, temp_path)
        finally:
            with suppress(Exception):
                os.remove(temp_path)
    except Exception as e:
        logger.error("Failed to transcribe media: %s", e, exc_info=True)
        return None

@dp.message(Command("start"))
async def cmd_start(message: Message, profile_manager: ProfileManager):
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


@dp.message(Command("commands"))
@dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.text.func(lambda t: isinstance(t, str) and t.strip().lower() in {"команды", "commands"}))
async def cmd_commands_alias(message: Message):
    await cmd_help(message)
    await db.log_user_interaction(message.from_user.id, "commands_alias", "command")

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
async def voice_handler_msg(message: Message, bot: Bot):
    """Расшифровка голосовых в текст."""
    user = message.from_user
    if not user or not message.voice:
        return
    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        settings = await db.get_group_settings(message.chat.id)
        if not settings.get("stt_enabled", True):
            return
    await db.ensure_user_exists(user.id, user.username, user.first_name)
    text = await _transcribe_telegram_media(message, bot, message.voice.file_id, f"voice_{message.voice.file_unique_id}.ogg")
    if not text:
        if not _local_stt_installed():
            await message.reply("❌ Локальная STT не установлена. Установите `faster-whisper` (и ffmpeg) на вашем ПК.")
        else:
            await message.reply("❌ Не удалось расшифровать голосовое.")
        return
    await message.reply(f"📝 Расшифровка голосового:\n{text}")


@dp.message(F.video_note)
async def video_note_handler_msg(message: Message, bot: Bot):
    """Расшифровка кружков в текст."""
    user = message.from_user
    if not user or not message.video_note:
        return
    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
        settings = await db.get_group_settings(message.chat.id)
        if not settings.get("stt_enabled", True):
            return
    await db.ensure_user_exists(user.id, user.username, user.first_name)
    text = await _transcribe_telegram_media(message, bot, message.video_note.file_id, f"video_note_{message.video_note.file_unique_id}.mp4")
    if not text:
        if not _local_stt_installed():
            await message.reply("❌ Локальная STT не установлена. Установите `faster-whisper` (и ffmpeg) на вашем ПК.")
        else:
            await message.reply("❌ Не удалось расшифровать кружок.")
        return
    await message.reply(f"📝 Расшифровка кружка:\n{text}")

@dp.message(F.chat.type == ChatType.PRIVATE, F.text, ~F.text.startswith('/'))
async def handle_text_message(message: Message, bot_instance: Bot, profile_manager: ProfileManager, sticker_manager: StickerManager):
    """
    Основной обработчик текстовых сообщений в приватных чатах.
    Взаимодействует с Ollama, управляет режимами и стикерами, логирует историю.
    """
    user_id = message.from_user.id

    await message.answer(
        "🤖 ИИ-ответы в личных сообщениях отключены.\n"
        "Используйте команды (/help, /mode, /stats и т.д.) или общайтесь с ИИ в групповом чате."
    )
    return

    try:
        await profile_manager.record_message(message.from_user)
    except Exception as e:
        logger.error(f"Error recording message for user {message.from_user.id}: {e}")

    # Убеждаемся, что пользователь есть в базе данных
    await db.ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    
    # Логируем взаимодействие
    await db.log_user_interaction(user_id, "mistral_private", "message")

    typing_msg = await typing_animation(message.chat.id, bot_instance)
    
    try:
        response_text = ""
        if not MISTRAL_API_KEY:
            response_text = "⚠️ MISTRAL_API_KEY не настроен. ЛС-ИИ временно недоступен."
        else:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "mistral-small-latest",
                    "messages": [
                        {"role": "system", "content": "Ты дружелюбный ИИ-помощник. Отвечай кратко и по делу."},
                        {"role": "user", "content": message.text}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 300
                }
                headers = {
                    "Authorization": f"Bearer {MISTRAL_API_KEY}",
                    "Content-Type": "application/json"
                }
                async with session.post("https://api.mistral.ai/v1/chat/completions", json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        response_text = data["choices"][0]["message"]["content"]
                    else:
                        response_text = f"⚠️ Mistral API error: {resp.status}"
        
        if not response_text:
            response_text = "Кажется, я не смог сформулировать ответ. Попробуй перефразировать?"
            logger.warning("Empty or error response from Mistral for user %s.", user_id)
        
        # Добавляем диалог в историю
        await db.add_chat_history_entry(user_id, "mistral_private", message.text, response_text)

        response_msg_obj: Optional[Message] = None
        # Пытаемся отредактировать сообщение с анимацией или отправить новое
        if typing_msg:
            with suppress(Exception):
                response_msg_obj = await typing_msg.edit_text(response_text)
        if not response_msg_obj: # Если анимация не удалась или не было, отправляем новое сообщение
            response_msg_obj = await safe_send_message(message.chat.id, response_text)

        # Добавляем кнопки оценки, если это не режим "офф" и пользователь не исчерпал возможности
        if response_msg_obj:
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

        # Случайная отправка стикера
        if random.random() < 0.3 and "saharoza" in sticker_manager.sticker_packs:
            sticker_id = sticker_manager.get_random_sticker("saharoza")
            if sticker_id: await message.answer_sticker(sticker_id)

    except Exception as e:
        logger.error(f"Error processing private mistral message for user {user_id}: {e}", exc_info=True)
        # Обработка ошибок и отправка соответствующего сообщения пользователю
        error_msg_text = "Ой, что-то пошло не так во время обработки запроса к Mistral. Попробуй ещё раз."
        if typing_msg:
            with suppress(Exception): await typing_msg.edit_text(error_msg_text)
        else:
            await safe_send_message(message.chat.id, error_msg_text)
