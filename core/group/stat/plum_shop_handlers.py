from core.group.stat.smain import *
from core.group.stat.manager import ProfileManager # Используем ProfileManager
from core.group.stat.plum_shop_config import PlumShopConfig, RARITY_ICONS
from database import add_item_to_inventory # Используем существующую функцию добавления в инвентарь
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.filters import Command  # <<< ИСПРАВЛЕНИЕ: Убран 'Text'
from aiogram.utils.markdown import hbold, hcode

import logging
logger = logging.getLogger(__name__)

# Роутер для обработки КНОПОК
plum_shop_router = Router(name="plum_shop_router")

# Функция для вызова из main.py
async def cmd_plum_shop(message: types.Message, profile_manager: ProfileManager):
    """Показывает П-Магазин с товарами за PLUMcoins."""
    user_id = message.from_user.id
    
    # Получаем текущий баланс PLUMcoins для отображения
    plumcoins = await profile_manager.get_plumcoins(user_id) 

    text = (
        f"🌟 **П-Магазин (PLUM-Shop)** 🌟\n\n"
        f"Ваш текущий баланс: {hbold(plumcoins)} PLUMcoins\n\n"
        f"**Доступные товары:**\n"
    )

    builder = InlineKeyboardBuilder()
    
    # Отображаем все предметы в магазине
    for item_key, item_info in PlumShopConfig.PLUM_SHOP_ITEMS.items():
        rarity_icon = RARITY_ICONS.get(item_info['rarity'], '🔹')
        button_text = f"{item_info['icon']} {item_info['name']} ({item_info['price']} PLUM) {rarity_icon}"
        callback_data = f"{PlumShopConfig.BUY_ITEM_CALLBACK_DATA}:{item_key}"
        builder.row(InlineKeyboardButton(text=button_text, callback_data=callback_data))

    builder.row(InlineKeyboardButton(text="⬅️ Закрыть", callback_data="close_shop"))

    await message.reply(
        text, 
        reply_markup=builder.as_markup(), 
        parse_mode=ParseMode.MARKDOWN
    )

# <<< ИСПРАВЛЕНИЕ: (было Text(startswith=...))
@plum_shop_router.callback_query(F.data.startswith(f"{PlumShopConfig.BUY_ITEM_CALLBACK_DATA}:"))
async def plum_shop_buy_callback(call: CallbackQuery, profile_manager: ProfileManager):
    """Обработка покупки предмета за PLUMcoins."""
    user_id = call.from_user.id
    try:
        # Извлекаем ключ предмета из callback_data
        item_key = call.data.split(":")[1]
        item = PlumShopConfig.get_item_by_key(item_key)
        
        if not item:
            await call.answer("❌ Неизвестный предмет.", show_alert=True)
            return

        price = item['price']
        inventory_key = item['inventory_key']
        
        # Получаем баланс пользователя
        current_plumcoins = await profile_manager.get_plumcoins(user_id) 

        if current_plumcoins < price:
            await call.answer(
                f"❌ Недостаточно PLUMcoins! Нужно {price}, у вас {current_plumcoins}.", 
                show_alert=True
            )
            return
            
        # 1. Снимаем PLUMcoins
        await profile_manager.update_plumcoins(user_id, -price) 
        
        # 2. Добавляем предмет в инвентарь (item_type=rpg_item)
        # Убедитесь, что `add_item_to_inventory` импортирована из `database.py` или `core/group/RPG/inventory.py`
        # Судя по вашим файлам, она должна быть в `core/group/RPG/inventory.py`
        from core.group.RPG.inventory import add_item_to_inventory_db
        await add_item_to_inventory_db(user_id, item, 1) # item - это dict, quantity=1
        
        # Обновляем баланс
        new_plumcoins = await profile_manager.get_plumcoins(user_id) 
        
        purchase_info = (
            f"🎉 **Покупка совершена!** 🎉\n\n"
            f"Вы успешно приобрели: {hbold(item['name'])}.\n"
            f"🔸 Стоимость: {price} PLUMcoins.\n"
            f"💰 Новый баланс: {hbold(new_plumcoins)} PLUMcoins.\n\n"
            f"Проверьте свой инвентарь: {hcode('инвентарь')}"
        )
        
        # Обновляем клавиатуру
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⬅️ Назад / Закрыть", callback_data="close_shop"))

        await call.message.edit_text(
            purchase_info, 
            reply_markup=builder.as_markup(), 
            parse_mode=ParseMode.MARKDOWN
        )
        await call.answer(f"Вы купили {item['name']} за {price} PLUMcoins!", show_alert=False)

    except Exception as e:
        logger.error(f"Error in plum_shop_buy_callback for user {user_id}: {e}", exc_info=True)
        await call.answer("Произошла ошибка при обработке покупки.", show_alert=True)

# <<< ИСПРАВЛЕНИЕ: (было Text("close_shop"))
@plum_shop_router.callback_query(F.data == "close_shop")
async def process_close_shop(call: CallbackQuery):
    """Закрывает окно магазина."""
    await call.message.delete()
    await call.answer("Магазин закрыт.")