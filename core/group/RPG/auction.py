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

async def get_active_auctions() -> List[dict]:
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute('''
                SELECT * FROM auction_listings 
                WHERE end_time > ? OR end_time IS NULL
                ORDER BY created_at DESC
            ''', (time.time(),))
            
            rows = await cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            auctions = []
            for row in rows:
                auction_dict = dict(zip(columns, row))
                auctions.append(auction_dict)
            
            return auctions
    except Exception as e:
        logger.error(f"❌ Error getting active auctions: {e}")
        return []

async def get_market_listings() -> List[dict]:
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute('''
                SELECT * FROM market_listings 
                ORDER BY created_at DESC
            ''')
            
            rows = await cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            listings = []
            for row in rows:
                listing_dict = dict(zip(columns, row))
                listings.append(listing_dict)
            
            return listings
    except Exception as e:
        logger.error(f"❌ Error getting market listings: {e}")
        return []

@rpg_router.message(F.text.regexp(r'^цена\s+(\d+)$'))
async def handle_price_command(message: types.Message, state: FSMContext, profile_manager):
    try:
        current_state = await state.get_state()
        if not current_state:
            return
            
        price = int(message.text.split()[1])
        
        if current_state == MarketStates.waiting_for_price.state:
            await handle_market_price_input(message, state, profile_manager)
        elif current_state == AuctionStates.waiting_for_price.state:
            await handle_auction_price_input(message, state, profile_manager)
            
    except Exception as e:
        logger.error(f"❌ Error in handle_price_command: {e}")
        await message.answer("❌ Ошибка при установке цены")

@rpg_router.message(F.text.lower() == "аукцион")
async def show_auction(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        builder = InlineKeyboardBuilder()
        text = f"🎭 **Аукцион** | 💰 Баланс: {lumcoins} LUM\n\n"
        
        active_auctions = await get_active_auctions()
        
        if active_auctions:
            text += "📋 **Активные лоты:**\n\n"
            for auction in active_auctions[:5]:
                time_left = auction['end_time'] - time.time()
                hours_left = max(0, int(time_left // 3600))
                minutes_left = max(0, int((time_left % 3600) // 60))
                
                item_info = json.loads(auction['item_data'])
                item_name = item_info.get('name', 'Неизвестный предмет')
                
                current_bid = auction['current_bid'] if auction['current_bid'] else auction['start_price']
                bidder_text = f"👤 {auction['current_bidder_id']}" if auction['current_bidder_id'] else "🚫 Нет ставок"
                
                text += f"📦 {item_name}\n"
                text += f"💰 Текущая ставка: {current_bid} LUM\n"
                text += f"⏰ Осталось: {hours_left}ч {minutes_left}м\n"
                text += f"{bidder_text}\n\n"
                
                builder.row(InlineKeyboardButton(
                    text=f"🛒 {item_name} - {current_bid} LUM",
                    callback_data=f"auction_bid:{auction['id']}"
                ))
        else:
            text += "📭 На аукционе пока нет лотов.\n"
        
        builder.row(InlineKeyboardButton(
            text="📤 Выставить предмет", 
            callback_data="auction_sell_menu"
        ))
        
        builder.row(InlineKeyboardButton(
            text="🔄 Обновить", 
            callback_data="auction_refresh"
        ))
        
        builder.row(InlineKeyboardButton(
            text="📦 Мои лоты", 
            callback_data="auction_my_listings"
        ))
        
        await message.answer(text, reply_mup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in show_auction: {e}")
        await message.answer("❌ Ошибка при загрузке аукциона")

@rpg_router.callback_query(F.data == "auction_sell_menu")
async def handle_auction_sell_menu(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        user_inventory = await get_user_inventory_db(user_id)
        
        sellable_items = [item for item in user_inventory if item.get('type') != 'background' and item.get('quantity', 0) > 0]
        
        if not sellable_items:
            await callback.answer("❌ У вас нет предметов для продажи на аукционе")
            return
        
        builder = InlineKeyboardBuilder()
        text = "🎭 **Выставление на аукцион**\n\n"
        text += "Выберите предмет для аукциона:\n\n"
        
        for item in sellable_items[:5]:
            item_key = item.get('item_key', 'unknown')
            item_name = item.get('name', 'Неизвестный предмет')
            quantity = item.get('quantity', 1)
            
            builder.row(InlineKeyboardButton(
                text=f"{item_name} ×{quantity}",
                callback_data=f"auction_select:{item_key}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="auction_back"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in show_auction_sell_menu: {e}")
        await callback.answer("❌ Ошибка при загрузке меню")

@rpg_router.callback_query(F.data.startswith("auction_select:"))
async def handle_auction_select(callback: types.CallbackQuery, profile_manager, state: FSMContext):
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
        
        base_price = ItemSystem.get_item_sell_price(item_key) * 2
        
        # Варианты цен для аукциона
        price_options = [
            int(base_price * 0.5),   # 50%
            base_price,              # 100%
            int(base_price * 1.5),   # 150%
            int(base_price * 2)      # 200%
        ]
        
        builder = InlineKeyboardBuilder()
        text = f"🎪 **Аукцион: {item_name}**\n\n"
        text += "Выберите начальную цену:\n\n"
        
        for i, price in enumerate(price_options):
            percentage = ["50%", "100%", "150%", "200%"][i]
            builder.row(InlineKeyboardButton(
                text=f"💰 {price} LUM || {percentage}",
                callback_data=f"auction_set_price:{item_key}:{price}"
            ))
        
        # Кнопка для своей цены
        builder.row(InlineKeyboardButton(
            text="💎 Указать свою цену",
            callback_data=f"auction_custom_price:{item_key}"
        ))
        
        builder.row(InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="auction_cancel"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in handle_auction_select: {e}")
        await callback.answer("❌ Ошибка")

@rpg_router.callback_query(F.data.startswith("auction_custom_price:"))
async def handle_auction_custom_price(callback: types.CallbackQuery, state: FSMContext):
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
        
        base_price = ItemSystem.get_item_sell_price(item_key) * 2
        min_price = int(base_price * 0.5)
        max_price = int(base_price * 2)
        
        await state.set_state(AuctionStates.waiting_for_price)
        await state.update_data(
            auction_item_key=item_key,
            auction_item_name=item_name,
            auction_base_price=base_price,
            auction_min_price=min_price,
            auction_max_price=max_price
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="auction_cancel"
        ))
        
        await callback.message.edit_text(
            f"🎪 **Аукцион: {item_name}**\n\n"
            f"💰 Базовая цена: {base_price} LUM\n\n"
            f"💎 **Введите вашу начальную цену:**\n"
            f"Напишите в чат: цена [число]\n"
            f"Например: цена {min_price + 10}\n\n"
            f"📊 Диапазон цен:\n"
            f"• Минимум: {min_price} LUM (50%)\n"
            f"• Максимум: {max_price} LUM (200%)",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"❌ Error in handle_auction_custom_price: {e}")
        await callback.answer("❌ Ошибка")

@rpg_router.message(AuctionStates.waiting_for_price)
async def handle_auction_price_input(message: types.Message, state: FSMContext, profile_manager):
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        item_key = data.get('auction_item_key')
        item_name = data.get('auction_item_name')
        base_price = data.get('auction_base_price')
        min_price = data.get('auction_min_price')
        max_price = data.get('auction_max_price')
        
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
        
        # Продолжаем создание аукциона
        await create_auction_listing(user_id, item_key, price, message, state)
        
    except Exception as e:
        logger.error(f"❌ Error in handle_auction_price_input: {e}")
        await message.answer("❌ Произошла ошибка")
        await state.clear()

async def create_auction_listing(user_id, item_key, price, message, state):
    try:
        user_inventory = await get_user_inventory_db(user_id)
        item_data = None
        for item in user_inventory:
            if item.get('item_key') == item_key:
                item_data = item
                break
        
        if not item_data:
            await message.answer("❌ Предмет не найден в вашем инвентаре")
            await state.clear()
            return
        
        # Удаляем предмет из инвентаря
        success = await remove_item_from_inventory(user_id, item_key, 1)
        if not success:
            await message.answer("❌ Ошибка при удалении предмета из инвентаря")
            await state.clear()
            return
        
        # Добавляем в аукцион
        await ensure_db_initialized()
        async with aiosqlite.connect('profiles.db') as conn:
            await conn.execute('''
                INSERT INTO auction_listings (seller_id, item_key, item_data, start_price, current_bid, end_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, item_key, json.dumps(item_data), price, price, int(time.time()) + 24 * 3600))
            await conn.commit()
        
        item_info = ItemSystem.SHOP_ITEMS.get(item_key) or ItemSystem.CRAFTED_ITEMS.get(item_key)
        item_name = item_info['name'] if item_info else item_data.get('name', 'Неизвестный предмет')
        
        await message.answer(f"✅ {item_name} выставлен на аукцион за {price} LUM!")
        await state.clear()
        
    except Exception as e:
        logger.error(f"❌ Error in create_auction_listing: {e}")
        await message.answer("❌ Произошла ошибка при создании аукциона")
        await state.clear()

@rpg_router.callback_query(F.data.startswith("auction_set_price:"))
async def handle_auction_set_price(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        parts = callback.data.split(":")
        item_key = parts[1]
        price = int(parts[2])
        
        user_inventory = await get_user_inventory_db(user_id)
        item_data = None
        for item in user_inventory:
            if item.get('item_key') == item_key:
                item_data = item
                break
        
        if not item_data:
            await callback.answer("❌ Предмет не найден")
            return
        
        success = await remove_item_from_inventory(user_id, item_key, 1)
        if not success:
            await callback.answer("❌ Ошибка при удалении предмета")
            return
        
        await ensure_db_initialized()
        async with aiosqlite.connect('profiles.db') as conn:
            await conn.execute('''
                INSERT INTO auction_listings (seller_id, item_key, item_data, start_price, current_bid, end_time)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, item_key, json.dumps(item_data), price, price, time.time() + 24 * 3600))
            
            await conn.commit()
        
        item_info = ItemSystem.SHOP_ITEMS.get(item_key) or ItemSystem.CRAFTED_ITEMS.get(item_key)
        item_name = item_info['name'] if item_info else item_data.get('name', 'Неизвестный предмет')
        
        await callback.answer(f"✅ {item_name} выставлен на аукцион за {price} LUM!")
        await show_auction(callback.message, profile_manager)
        
    except Exception as e:
        logger.error(f"❌ Error in handle_auction_set_price: {e}")
        await callback.answer("❌ Ошибка при создании аукциона")

@rpg_router.callback_query(F.data == "auction_refresh")
async def handle_auction_refresh(callback: types.CallbackQuery, profile_manager):
    await show_auction(callback.message, profile_manager)

@rpg_router.callback_query(F.data == "auction_back")
async def handle_auction_back(callback: types.CallbackQuery, profile_manager):
    await show_auction(callback.message, profile_manager)

@rpg_router.callback_query(F.data == "auction_cancel")
async def handle_auction_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Создание аукциона отменено")