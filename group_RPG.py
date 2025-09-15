from aiogram import Router, types, Bot, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.utils.markdown import hlink
import logging

from core.group.stat.manager import ProfileManager
from core.group.stat.shop_config import ShopConfig # Для доступа к информации о фонах
from aiogram.enums import ParseMode  # ← Добавьте эту строку

logger = logging.getLogger(__name__)

rpg_router = Router(name="rpg_router")

@rpg_router.message(F.text.lower() == "инвентарь")
async def show_inventory(message: types.Message, profile_manager: ProfileManager):
    logger.info(f"Received 'инвентарь' command from user {message.from_user.id}.")
    user_id = message.from_user.id

    # Получаем текущий активный фон пользователя
    user_profile = await profile_manager.get_user_profile(message.from_user)
    active_background_key = user_profile.get('active_background', 'default')

    # Получаем фоны из инвентаря пользователя
    user_backgrounds = await profile_manager.get_user_backgrounds_inventory(user_id)
    
    builder = InlineKeyboardBuilder()
    text = "🎒 **Ваш инвентарь** 🎒\n\n"
    
    # Раздел "Фоны"
    text += "🖼️ **Фоны:**\n"
    if user_backgrounds:
        for bg_key in user_backgrounds:
            # Обработка кастомных фонов
            if bg_key.startswith("custom:"):
                bg_name = "Кастомный фон"
                status = " ✅ (Активно)" if bg_key == active_background_key else ""
                
                # Кнопка для активации фона
                builder.row(InlineKeyboardButton(
                    text=f"🎨 {bg_name}{status}", 
                    callback_data=f"activate_bg:{bg_key}"
                ))
            else:
                bg_info = ShopConfig.SHOP_BACKGROUNDS.get(bg_key)
                bg_name = bg_info['name'] if bg_info else bg_key
                status = " ✅ (Активно)" if bg_key == active_background_key else ""
                
                # Кнопка для активации фона
                builder.row(InlineKeyboardButton(
                    text=f"🎨 {bg_name}{status}", 
                    callback_data=f"activate_bg:{bg_key}"
                ))
    else:
        text += "У вас пока нет фонов. Загляните в /магазин!\n"
    
    # Добавляем кнопку для возврата к фону по умолчанию
    default_status = " ✅ (Активно)" if active_background_key == 'default' else ""
    builder.row(InlineKeyboardButton(
        text=f"🔙 Вернуть стандартный фон{default_status}", 
        callback_data="reset_bg_to_default"
    ))
    
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.MARKDOWN)
    logger.info(f"Inventory list sent to user {user_id}.")


@rpg_router.callback_query(F.data.startswith("activate_bg:"))
async def process_activate_background(callback: types.CallbackQuery, profile_manager: ProfileManager):
    user_id = callback.from_user.id
    background_key_to_activate = callback.data.split(":")[1]

    logger.info(f"User {user_id} attempting to activate background: '{background_key_to_activate}'.")

    # Проверяем, есть ли фон в инвентаре пользователя
    user_backgrounds_inventory = await profile_manager.get_user_backgrounds_inventory(user_id)

    if background_key_to_activate in user_backgrounds_inventory:
        # Устанавливаем активный фон
        await profile_manager.set_user_background(user_id, background_key_to_activate)
        
        # Получаем информацию о фоне
        bg_info = ShopConfig.SHOP_BACKGROUNDS.get(background_key_to_activate)
        bg_name = bg_info['name'] if bg_info else background_key_to_activate

        logger.info(f"User {user_id} successfully activated background '{bg_name}'.")
        await callback.message.edit_text(
            f"✅ Фон '{bg_name}' успешно активирован!",
            reply_markup=None
        )
    else:
        logger.warning(f"User {user_id} tried to activate background '{background_key_to_activate}' not in inventory.")
        await callback.message.edit_text(
            "❌ Этого фона нет в вашем инвентаре.",
            reply_markup=None
        )


@rpg_router.callback_query(F.data == "reset_bg_to_default")
async def process_reset_background_to_default(callback: types.CallbackQuery, profile_manager: ProfileManager):
    user_id = callback.from_user.id

    logger.info(f"User {user_id} attempting to reset background to default.")
    
    # Устанавливаем фон по умолчанию
    await profile_manager.set_user_background(user_id, 'default')
    
    logger.info(f"User {user_id} successfully reset background to default.")
    await callback.message.edit_text(
        "✅ Стандартный фон успешно активирован!",
        reply_markup=None
    )


def setup_rpg_handlers(main_dp: Router):
    main_dp.include_router(rpg_router)
    logger.info("RPG router included in Dispatcher.")
