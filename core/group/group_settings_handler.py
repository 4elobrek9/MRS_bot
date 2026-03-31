import logging
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

# --- Главное меню настроек (команда "доп. функции") ---

@settings_router.message(Command("dop_func", "config", "cfg"))
@settings_router.message(F.text.lower().in_({"доп. функции", "дополнительные функции", "настройки", "settings", "конфиг", "config"}))
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

    chat_id = message.chat.id
    ai_status = await db.get_ai_status(chat_id)

    status_text = "✅ Включен" if ai_status else "❌ Выключен"

    text = (
        "⚙️ **Настройки дополнительных функций группы** ⚙️\n\n"
        "**🤖 LLM Чат (Mistral):**\n"
        f"Статус: **{status_text}**\n"
        "Когда включен, бот отвечает на упоминания и реплаи, используя LLM."
    )

    builder = InlineKeyboardBuilder()

    # Кнопка переключения AI
    action = "disable_ai" if ai_status else "enable_ai"
    button_text = "📴 Отключить LLM Чат" if ai_status else "💡 Включить LLM Чат"

    builder.row(InlineKeyboardButton(text=button_text, callback_data=action))

    await message.reply(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.MARKDOWN)

# --- Обработчик колбэков ---

@settings_router.callback_query(F.data.in_({"enable_ai", "disable_ai"}))
async def handle_ai_toggle_callback(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    action = callback.data

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

    # Логика переключения
    new_status = action == "enable_ai"
    await db.set_ai_status(chat_id, new_status)

    # Обновление сообщения
    ai_status = await db.get_ai_status(chat_id)
    status_text = "✅ Включен" if ai_status else "❌ Выключен"

    text = (
        "⚙️ **Настройки дополнительных функций группы** ⚙️\n\n"
        "**🤖 LLM Чат (Mistral):**\n"
        f"Статус: **{status_text}**\n"
        "Когда включен, бот отвечает на упоминания и реплаи, используя LLM."
    )

    builder = InlineKeyboardBuilder()

    # Обновляем кнопку после изменения
    new_action = "disable_ai" if ai_status else "enable_ai"
    button_text = "📴 Отключить LLM Чат" if ai_status else "💡 Включить LLM Чат"

    builder.row(InlineKeyboardButton(text=button_text, callback_data=new_action))

    try:
        await callback.message.edit_text(
            text,
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer(f"LLM Чат успешно {status_text.lower()}!", show_alert=False)
    except Exception as e:
        logger.error(f"Failed to edit settings message: {e}")
        await callback.answer("Ошибка при обновлении сообщения.", show_alert=True)
