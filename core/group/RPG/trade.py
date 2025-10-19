from core.group.RPG.MAINrpg import rpg_router
from core.group.RPG.rpg_utils import ensure_db_initialized
from .rpg_utils import trade_sessions
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import logging
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
@rpg_router.message(F.text.lower() == "обмен")
async def start_trade(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        user_inventory = await get_user_inventory_db(user_id)
        
        tradable_items = [item for item in user_inventory if item.get('type') != 'background' and item.get('quantity', 0) > 0]
        
        if not tradable_items:
            await message.answer("📭 У вас нет предметов для обмена.")
            return
        
        builder = InlineKeyboardBuilder()
        text = "🤝 **Обмен**\n\n"
        text += "Выберите предмет для обмена:\n\n"
        
        for item in tradable_items:
            item_key = item.get('item_key', 'unknown')
            item_name = item.get('name', 'Неизвестный предмет')
            quantity = item.get('quantity', 1)
            
            builder.row(InlineKeyboardButton(
                text=f"{item_name} ×{quantity}",
                callback_data=f"trade_select:{item_key}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="❌ Отмена", 
            callback_data="trade_cancel"
        ))
        
        await message.answer(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in start_trade: {e}")
        await message.answer("❌ Ошибка при запуске обмена")

@rpg_router.callback_query(F.data.startswith("trade_select:"))
async def handle_trade_select(callback: types.CallbackQuery, profile_manager):
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
        if not item_info:
            item_info = item_data
        
        trade_sessions[user_id] = {
            'my_item': item_key,
            'timestamp': time.time()
        }
        
        item_name = item_info.get('name', 'Неизвестный предмет')
        
        info_text = f"📦 {item_name}\n"
        info_text += f"📖 {item_info.get('description', 'Описание отсутствует')}\n"
        
        if 'stats' in item_info:
            stats_text = ""
            for stat, value in item_info['stats'].items():
                stats_text += f"   {stat}: +{value}\n"
            if stats_text:
                info_text += f"📊 Характеристики:\n{stats_text}"
        
        info_text += f"\n✅ Выбран для обмена!\n\n"
        info_text += f"Ответьте на сообщение пользователя командой:\n\n`обменять`"
        
        await callback.answer(info_text, show_alert=True)
        await callback.message.edit_text(f"🤝 **Обмен: Шаг 1/2**\n\n📦 Ваш предмет: {item_name}\n\nОтветьте на сообщение пользователя командой:\n\n`обменять`")
        
    except Exception as e:
        logger.error(f"❌ Error in handle_trade_select: {e}")
        await callback.answer("❌ Ошибка при выборе предмета")

@rpg_router.message(F.text.lower() == "обменять")
async def handle_trade_with_user(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        
        if not message.reply_to_message:
            await message.answer("❌ Ответьте на сообщение пользователя.")
            return
        
        target_user_id = message.reply_to_message.from_user.id
        
        if target_user_id not in trade_sessions:
            await message.answer("❌ У пользователя нет активного предложения.")
            return
        
        trade_offer = trade_sessions[target_user_id]
        offer_item_key = trade_offer['my_item']
        offer_item_info = ItemSystem.SHOP_ITEMS.get(offer_item_key) or ItemSystem.CRAFTED_ITEMS.get(offer_item_key)
        if not offer_item_info:
            offer_item_info = {'name': 'Неизвестный предмет'}
        
        offer_item_name = offer_item_info['name']
        
        user_inventory = await get_user_inventory_db(user_id)
        tradable_items = [item for item in user_inventory if item.get('type') != 'background' and item.get('quantity', 0) > 0]
        
        if not tradable_items:
            await message.answer("📭 У вас нет предметов для обмена.")
            return
        
        builder = InlineKeyboardBuilder()
        text = (
            f"🤝 **Обмен: Шаг 2/2**\n\n"
            f"📦 Предложение: {offer_item_name}\n"
            f"👤 От: {message.reply_to_message.from_user.first_name}\n\n"
            f"Выберите ваш предмет:\n\n"
        )
        
        for item in tradable_items:
            item_key = item.get('item_key', 'unknown')
            item_name = item.get('name', 'Неизвестный предмет')
            quantity = item.get('quantity', 1)
            
            builder.row(InlineKeyboardButton(
                text=f"{item_name} ×{quantity}",
                callback_data=f"trade_confirm:{target_user_id}:{item_key}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="❌ Отмена", 
            callback_data="trade_cancel"
        ))
        
        await message.answer(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in handle_trade_with_user: {e}")
        await message.answer("❌ Ошибка при обмене")

@rpg_router.callback_query(F.data.startswith("trade_confirm:"))
async def handle_trade_confirm(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        parts = callback.data.split(":")
        target_user_id = int(parts[1])
        my_item_key = parts[2]
        
        if target_user_id not in trade_sessions:
            await callback.answer("❌ Предложение устарело")
            return
        
        trade_offer = trade_sessions[target_user_id]
        offer_item_key = trade_offer['my_item']
        
        user1_inventory = await get_user_inventory_db(target_user_id)
        user2_inventory = await get_user_inventory_db(user_id)
        
        user1_has_item = any(item.get('item_key') == offer_item_key and item.get('quantity', 0) > 0 for item in user1_inventory)
        user2_has_item = any(item.get('item_key') == my_item_key and item.get('quantity', 0) > 0 for item in user2_inventory)
        
        if not user1_has_item:
            await callback.answer("❌ У пользователя нет предмета")
            del trade_sessions[target_user_id]
            return
        
        if not user2_has_item:
            await callback.answer("❌ У вас нет предмета")
            return
        
        success1 = await remove_item_from_inventory(target_user_id, offer_item_key, 1)
        success2 = await remove_item_from_inventory(user_id, my_item_key, 1)
        
        if not success1 or not success2:
            await callback.answer("❌ Ошибка при обмене")
            return
        
        offer_item_info = ItemSystem.SHOP_ITEMS.get(offer_item_key) or ItemSystem.CRAFTED_ITEMS.get(offer_item_key)
        my_item_info = ItemSystem.SHOP_ITEMS.get(my_item_key) or ItemSystem.CRAFTED_ITEMS.get(my_item_key)
        
        offer_item_data = {
            'item_key': offer_item_key,
            'name': offer_item_info['name'] if offer_item_info else "Неизвестный предмет",
            'type': offer_item_info.get('type', 'material') if offer_item_info else 'material',
            'rarity': offer_item_info.get('rarity', 'common') if offer_item_info else 'common',
            'description': offer_item_info.get('description', '') if offer_item_info else '',
            'traded_at': time.time()
        }
        
        my_item_data = {
            'item_key': my_item_key,
            'name': my_item_info['name'] if my_item_info else "Неизвестный предмет",
            'type': my_item_info.get('type', 'material') if my_item_info else 'material',
            'rarity': my_item_info.get('rarity', 'common') if my_item_info else 'common',
            'description': my_item_info.get('description', '') if my_item_info else '',
            'traded_at': time.time()
        }
        
        success3 = await add_item_to_inventory_db(user_id, offer_item_data)
        success4 = await add_item_to_inventory_db(target_user_id, my_item_data)
        
        if not success3 or not success4:
            await callback.answer("❌ Ошибка при добавлении")
            return
        
        del trade_sessions[target_user_id]
        
        offer_item_name = offer_item_info['name'] if offer_item_info else "Неизвестный предмет"
        my_item_name = my_item_info['name'] if my_item_info else "Неизвестный предмет"
        
        success_text = (
            f"🤝 **Обмен завершен!**\n\n"
            f"📦 Вы получили: {offer_item_name}\n"
            f"📦 Вы отдали: {my_item_name}\n\n"
            f"✅ Предметы обменяны!"
        )
        
        await callback.message.edit_text(success_text)
        await callback.answer()
        
        try:
            target_user_name = callback.from_user.first_name
            notification_text = (
                f"🤝 **Обмен завершен!**\n\n"
                f"📦 Вы получили: {my_item_name}\n"
                f"📦 Вы отдали: {offer_item_name}\n\n"
                f"✅ Обмен с {target_user_name} завершен!"
            )
            await callback.bot.send_message(target_user_id, notification_text)
        except Exception as e:
            logger.error(f"Не удалось уведомить {target_user_id}: {e}")
        
    except Exception as e:
        logger.error(f"❌ Error in handle_trade_confirm: {e}")
        await callback.answer("❌ Ошибка при подтверждении")

@rpg_router.callback_query(F.data == "trade_cancel")
async def handle_trade_cancel(callback: types.CallbackQuery):
    try:
        user_id = callback.from_user.id
        if user_id in trade_sessions:
            del trade_sessions[user_id]
        
        await callback.message.edit_text("❌ Обмен отменен.")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in handle_trade_cancel: {e}")
        await callback.answer("❌ Ошибка при отмене обмена")

@rpg_router.callback_query(F.data == "sell_back_to_main")
async def back_from_sell(callback: types.CallbackQuery, profile_manager):
    await show_inventory(callback.message, profile_manager)
