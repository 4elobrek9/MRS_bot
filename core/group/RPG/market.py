from core.group.RPG.MAINrpg import *
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import logging
from typing import Dict, List, Tuple
import random
import time
import json
import aiosqlite
import asyncio
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from core.group.stat.shop_config import ShopConfig
from core.group.RPG.auction import *
from core.group.RPG.crafttable import *
from core.group.RPG.inventory import *
from core.group.RPG.investment import *
from core.group.RPG.item import *
from core.group.RPG.market import *
from core.group.RPG.trade import *
@rpg_router.message(F.text.lower() == "рынок")
async def show_market(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        builder = InlineKeyboardBuilder()
        text = f"🏪 **Рынок** | 💰 Баланс: {lumcoins} LUM\n\n"
        
        market_items = await get_market_listings()
        
        if market_items:
            text += "🛒 **Товары:**\n\n"
            for item in market_items[:5]:
                item_info = json.loads(item['item_data'])
                item_name = item_info.get('name', 'Неизвестный предмет')
                seller_name = f"👤 {item['seller_id']}"
                
                text += f"📦 {item_name}\n"
                text += f"💰 Цена: {item['price']} LUM\n"
                text += f"{seller_name}\n\n"
                
                builder.row(InlineKeyboardButton(
                    text=f"🛒 {item_name} - {item['price']} LUM",
                    callback_data=f"market_buy:{item['id']}"
                ))
        else:
            text += "📭 На рынке пока нет товаров.\n"
        
        builder.row(InlineKeyboardButton(
            text="📤 Выставить товар", 
            callback_data="market_sell_menu"
        ))
        
        builder.row(InlineKeyboardButton(
            text="🔄 Обновить", 
            callback_data="market_refresh"
        ))
        
        builder.row(InlineKeyboardButton(
            text="📦 Мои товары", 
            callback_data="market_my_listings"
        ))
        
        await message.answer(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in show_market: {e}")
        await message.answer("❌ Ошибка при загрузке рынка")

@rpg_router.callback_query(F.data == "market_sell_menu")
async def handle_market_sell_menu(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        user_inventory = await get_user_inventory_db(user_id)
        
        sellable_items = [item for item in user_inventory if item.get('type') != 'background' and item.get('quantity', 0) > 0]
        
        if not sellable_items:
            await callback.answer("❌ У вас нет предметов для продажи")
            return
        
        builder = InlineKeyboardBuilder()
        text = "🏪 **Продажа на рынке**\n\n"
        text += "Выберите предмет для продажи:\n\n"
        
        for item in sellable_items[:5]:
            item_key = item.get('item_key', 'unknown')
            item_name = item.get('name', 'Неизвестный предмет')
            quantity = item.get('quantity', 1)
            
            builder.row(InlineKeyboardButton(
                text=f"{item_name} ×{quantity}",
                callback_data=f"market_select:{item_key}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="market_back"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in show_market_sell_menu: {e}")
        await callback.answer("❌ Ошибка при загрузке меню")

@rpg_router.callback_query(F.data.startswith("market_select:"))
async def handle_market_select(callback: types.CallbackQuery, profile_manager, state: FSMContext):
    try:
        user_id = callback.from_user.id
        item_key = callback.data.split(":")[1]
        
        user_inventory = await get_user_inventory_db(user_id)
        item_data = None
        for item in user_inventory:
            if item.get('item_key') == item_key:
                item_data = item
                break
        
        if not item_data:
            await callback.answer("❌ Предмет не найден")
            return
        
        item_info = ItemSystem.SHOP_ITEMS.get(item_key) or ItemSystem.CRAFTED_ITEMS.get(item_key)
        item_name = item_info['name'] if item_info else item_data.get('name', 'Неизвестный предмет')
        
        base_price = ItemSystem.get_item_sell_price(item_key) * 3
        min_price = int(base_price * 0.5)
        max_price = int(base_price * 3)
        
        await state.set_state(MarketStates.waiting_for_price)
        await state.update_data(
            market_item_key=item_key,
            market_item_name=item_name,
            market_base_price=base_price,
            market_min_price=min_price,
            market_max_price=max_price
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="market_cancel"
        ))
        
        await callback.message.edit_text(
            f"🏪 **Продажа: {item_name}**\n\n"
            f"💰 Базовая цена: {base_price} LUM\n\n"
            f"💎 **Введите вашу цену:**\n"
            f"Напишите в чат: цена [число]\n"
            f"Например: цена {min_price + 10}\n\n"
            f"📊 Диапазон цен:\n"
            f"• Минимум: {min_price} LUM (50%)\n"
            f"• Максимум: {max_price} LUM (300%)",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"❌ Error in handle_market_select: {e}")
        await callback.answer("❌ Ошибка")

@rpg_router.message(MarketStates.waiting_for_price)
async def handle_market_price_input(message: types.Message, state: FSMContext, profile_manager):
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        item_key = data.get('market_item_key')
        item_name = data.get('market_item_name')
        base_price = data.get('market_base_price')
        min_price = data.get('market_min_price')
        max_price = data.get('market_max_price')
        
        if not item_key:
            await message.answer("❌ Ошибка: предмет не найден")
            await state.clear()
            return
        
        # Проверяем, что введено число
        try:
            if message.text.lower().startswith('цена '):
                price = int(message.text.split()[1])
            else:
                price = int(message.text.strip())
        except (ValueError, AttributeError, IndexError):
            await message.answer("❌ Цена должна быть числом. Используйте формат: цена [число]")
            return
        
        if price < min_price:
            await message.answer(f"❌ Цена слишком низкая. Минимум: {min_price} LUM")
            return
        
        if price > max_price:
            await message.answer(f"❌ Цена слишком высокая. Максимум: {max_price} LUM")
            return
        
        # Проверяем, что предмет еще есть у пользователя
        user_inventory = await get_user_inventory_db(user_id)
        item_found = False
        for item in user_inventory:
            if item.get('item_key') == item_key:
                item_found = True
                break
        
        if not item_found:
            await message.answer("❌ Предмет не найден в вашем инвентаре")
            await state.clear()
            return
        
        # Удаляем предмет из инвентаря
        success = await remove_item_from_inventory(user_id, item_key, 1)
        if not success:
            await message.answer("❌ Ошибка при удалении предмета из инвентаря")
            await state.clear()
            return
        
        # Добавляем в listings
        await ensure_db_initialized()
        async with aiosqlite.connect('profiles.db') as conn:
            await conn.execute('''
                INSERT INTO market_listings (seller_id, item_key, item_data, price)
                VALUES (?, ?, ?, ?)
            ''', (user_id, item_key, json.dumps(item_data), price))
            await conn.commit()
        
        await message.answer(f"✅ {item_name} выставлен на рынок за {price} LUM!")
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ Error in handle_market_price_input: {e}")
        await message.answer("❌ Произошла ошибка")
        await state.clear()

@rpg_router.callback_query(F.data == "market_cancel")
async def handle_market_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Выставление предмета отменено")

@rpg_router.callback_query(F.data == "market_refresh")
async def handle_market_refresh(callback: types.CallbackQuery, profile_manager):
    await show_market(callback.message, profile_manager)

@rpg_router.callback_query(F.data == "market_back")
async def handle_market_back(callback: types.CallbackQuery, profile_manager):
    await show_market(callback.message, profile_manager)

@rpg_router.message(F.text.lower() == "магазин")
async def show_shop_main(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        builder = InlineKeyboardBuilder()
        
        builder.row(InlineKeyboardButton(
            text="🖼️ Магазин фонов", 
            callback_data="shop_type:backgrounds"
        ))
        builder.row(InlineKeyboardButton(
            text="📦 Магазин предметов", 
            callback_data="shop_type:items"
        ))
        
        text = (
            "🛒 **Магазин** 🛒\n\n"
            f"💰 Баланс: {lumcoins} LUM\n\n"
            "🎯 Выберите тип:"
        )
        
        await message.answer(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ Error in show_shop_main: {e}")
        await message.answer("❌ Ошибка при открытии магазина")