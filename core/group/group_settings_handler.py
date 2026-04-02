import logging
import re
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.enums import ChatType, ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

# Импортируем измененные функции БД
import database as db
# Предполагаем, что ADMIN_USER_ID доступен для доп. проверок (если нужно)
from core.main.ez_main import ADMIN_USER_ID

logger = logging.getLogger(__name__)

settings_router = Router(name="settings_router")


def _normalize_group_command(text: str) -> str:
    normalized = (text or "").strip().lower()
    return re.sub(r"[\s\.,!?:;]+$", "", normalized)

# --- Главное меню настроек (команда "доп. функции") ---

@settings_router.message(Command("dop_func", "config", "cfg"))
@settings_router.message(
    F.text.func(
        lambda text: isinstance(text, str) and _normalize_group_command(text) in {
            "доп. функции", "дополнительные функции", "настройки", "settings", "конфиг", "config", "cfg"
        }
    )
)
async def cmd_show_group_settings(message: types.Message, bot: Bot):
    """Показывает меню дополнительных функций/настроек группы."""
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.reply("Эта команда работает только в групповых чатах.")
        return

    # Проверка на администратора (только админы могут открывать меню)
    is_admin = False
    try:
        # Проверка статуса в чате
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in ('administrator', 'creator'):
            is_admin = True
    except Exception as e:
        logger.error(f"Error checking admin status in {message.chat.id}: {e}")

    if not is_admin:
        # Ответ для не-админов
        await message.reply("⚙️ **Дополнительные функции:**\n"
                            "Вы не являетесь администратором группы. Только администраторы могут менять настройки.",
                            parse_mode=ParseMode.MARKDOWN)
        return

    text, markup = await _build_settings_ui(message.chat.id)
    await message.reply(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

# --- Обработчик колбэков ---

@settings_router.callback_query(F.data.regexp(r"^toggle:(bot|ai|rp|economy|casino|promo|stt)$"))
async def handle_ai_toggle_callback(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    feature = callback.data.split(":", 1)[1]

    # Повторная проверка на администратора
    is_admin = False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ('administrator', 'creator'):
            is_admin = True
    except Exception as e:
        logger.error(f"Error checking admin status on callback in {chat_id}: {e}")

    if not is_admin:
        await callback.answer("❌ Только администраторы могут менять настройки.", show_alert=True)
        return

    settings = await db.get_group_settings(chat_id)
    field = f"{feature}_enabled"
    new_value = not bool(settings.get(field, True))
    await db.set_group_setting(chat_id, field, 1 if new_value else 0)

    text, markup = await _build_settings_ui(chat_id)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=markup,
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer("Настройка обновлена.", show_alert=False)
    except Exception as e:
        logger.error(f"Failed to edit settings message: {e}")
        await callback.answer("Ошибка при обновлении сообщения.", show_alert=True)


@settings_router.callback_query(F.data.regexp(r"^setcd:(work|transfer):(\d+)$"))
async def handle_cooldown_callback(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    kind, value_str = callback.data.split(":")[1:]
    value = int(value_str)

    is_admin = False
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        if member.status in ('administrator', 'creator'):
            is_admin = True
    except Exception as e:
        logger.error(f"Error checking admin status on cooldown callback in {chat_id}: {e}")

    if not is_admin:
        await callback.answer("❌ Только администраторы могут менять настройки.", show_alert=True)
        return

    field = "work_cooldown_seconds" if kind == "work" else "transfer_cooldown_seconds"
    await db.set_group_setting(chat_id, field, value)
    text, markup = await _build_settings_ui(chat_id)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    await callback.answer("Кулдаун обновлён.")


async def _build_settings_ui(chat_id: int):
    settings = await db.get_group_settings(chat_id)
    on_off = lambda v: "✅ Вкл" if v else "❌ Выкл"
    work_cd_min = settings["work_cooldown_seconds"] // 60
    transfer_cd_hours = settings["transfer_cooldown_seconds"] // 3600

    text = (
        "⚙️ **Конфиг группы**\n\n"
        f"🛑 Бот в группе: {on_off(settings['bot_enabled'])}\n"
        f"🤖 LLM: {on_off(settings['ai_enabled'])}\n"
        f"🎭 RP: {on_off(settings['rp_enabled'])}\n"
        f"💰 Экономика: {on_off(settings['economy_enabled'])}\n"
        f"🎰 Казино: {on_off(settings['casino_enabled'])}\n"
        f"🎟 Промокоды: {on_off(settings['promo_enabled'])}\n\n"
        f"🎤 Расшифровка ГС/кружков: {on_off(settings['stt_enabled'])}\n\n"
        f"⏳ Work кулдаун: **{work_cd_min} мин**\n"
        f"⏳ Transfer кулдаун: **{transfer_cd_hours} ч**"
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"Бот {on_off(settings['bot_enabled'])}", callback_data="toggle:bot"))
    builder.row(
        InlineKeyboardButton(text=f"LLM {on_off(settings['ai_enabled'])}", callback_data="toggle:ai"),
        InlineKeyboardButton(text=f"RP {on_off(settings['rp_enabled'])}", callback_data="toggle:rp"),
    )
    builder.row(
        InlineKeyboardButton(text=f"Экономика {on_off(settings['economy_enabled'])}", callback_data="toggle:economy"),
        InlineKeyboardButton(text=f"Казино {on_off(settings['casino_enabled'])}", callback_data="toggle:casino"),
    )
    builder.row(InlineKeyboardButton(text=f"Промо {on_off(settings['promo_enabled'])}", callback_data="toggle:promo"))
    builder.row(InlineKeyboardButton(text=f"STT {on_off(settings['stt_enabled'])}", callback_data="toggle:stt"))
    builder.row(
        InlineKeyboardButton(text="Work 5м", callback_data="setcd:work:300"),
        InlineKeyboardButton(text="Work 15м", callback_data="setcd:work:900"),
        InlineKeyboardButton(text="Work 30м", callback_data="setcd:work:1800"),
    )
    builder.row(
        InlineKeyboardButton(text="Transfer 1ч", callback_data="setcd:transfer:3600"),
        InlineKeyboardButton(text="Transfer 4ч", callback_data="setcd:transfer:14400"),
        InlineKeyboardButton(text="Transfer 10ч", callback_data="setcd:transfer:36000"),
    )
    return text, builder.as_markup()
