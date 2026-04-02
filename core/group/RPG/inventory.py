from core.group.RPG.MAINrpg import rpg_router
from core.group.RPG.rpg_utils import ensure_db_initialized
from .item import ItemSystem
from core.group.stat.shop_config import ShopConfig
from .rpg_utils import quick_purchase_cache

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
import database as db

logger = logging.getLogger(__name__)
quick_item_use_cache = {}

async def get_user_lumcoins(profile_manager, user_id: int) -> int:
    try:
        return await profile_manager.get_lumcoins(user_id)
    except Exception as e:
        logger.error(f"Error getting lumcoins for user {user_id}: {e}")
        return 0

async def update_user_lumcoins(profile_manager, user_id: int, amount: int) -> bool:
    try:
        await profile_manager.update_lumcoins(user_id, amount)
        return True
    except Exception as e:
        logger.error(f"Error updating lumcoins for user {user_id}: {e}")
        return False

async def add_item_to_inventory_db(user_id: int, item_data: dict, quantity: int = 1) -> bool:
    try:
        await ensure_db_initialized()
        
        item_key = item_data.get('item_key', 'unknown')
        item_type = item_data.get('type', 'material')
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute(
                'SELECT quantity FROM user_inventory WHERE user_id = ? AND item_key = ?',
                (user_id, item_key)
            )
            existing = await cursor.fetchone()
            
            if existing:
                current_quantity = existing[0]
                new_quantity = min(current_quantity + quantity, 67)
                
                await conn.execute(
                    'UPDATE user_inventory SET quantity = ? WHERE user_id = ? AND item_key = ?',
                    (new_quantity, user_id, item_key)
                )
            else:
                await conn.execute('''
                    INSERT INTO user_inventory (user_id, item_key, item_type, quantity, item_data)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    user_id, 
                    item_key,
                    item_type,
                    min(quantity, 67),
                    json.dumps(item_data, ensure_ascii=False) if isinstance(item_data, dict) else str(item_data)
                ))
            
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"❌ Error adding item: {e}")
        return False

async def remove_item_from_inventory(user_id: int, item_key: str, quantity: int = 1) -> bool:
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute(
                'SELECT quantity FROM user_inventory WHERE user_id = ? AND item_key = ?',
                (user_id, item_key)
            )
            result = await cursor.fetchone()
            
            if not result:
                return False
            
            current_quantity = result[0]
            new_quantity = current_quantity - quantity
            
            if new_quantity <= 0:
                await conn.execute(
                    'DELETE FROM user_inventory WHERE user_id = ? AND item_key = ?',
                    (user_id, item_key)
                )
            else:
                await conn.execute(
                    'UPDATE user_inventory SET quantity = ? WHERE user_id = ? AND item_key = ?',
                    (new_quantity, user_id, item_key)
                )
            
            await conn.commit()
            return True
            
    except Exception as e:
        logger.error(f"❌ Error removing item: {e}")
        return False

async def get_user_inventory_db(user_id: int) -> List[dict]:
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute(
                'SELECT item_key, item_type, quantity, item_data FROM user_inventory WHERE user_id = ?',
                (user_id,)
            )
            rows = await cursor.fetchall()
            
            inventory = []
            for row in rows:
                try:
                    item_data = json.loads(row[3]) if row[3] else {}
                    item_data.update({
                        'item_key': row[0],
                        'type': row[1],
                        'quantity': row[2]
                    })
                    inventory.append(item_data)
                except Exception as e:
                    inventory.append({
                        'item_key': row[0],
                        'type': row[1], 
                        'quantity': row[2],
                        'name': str(row[3]) if row[3] else 'Неизвестный предмет'
                    })
            
            return inventory
    except Exception as e:
        logger.error(f"❌ Error getting inventory: {e}")
        return []

async def get_user_backgrounds_inventory(user_id: int) -> List[dict]:
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute(
                'SELECT item_key, item_data FROM user_inventory WHERE user_id = ? AND item_type = ?',
                (user_id, 'background')
            )
            rows = await cursor.fetchall()
            
            backgrounds = []
            for row in rows:
                try:
                    item_data = json.loads(row[1]) if row[1] else {}
                    backgrounds.append({
                        'item_key': row[0],
                        'name': item_data.get('name', 'Неизвестный фон'),
                        'type': 'background'
                    })
                except Exception as e:
                    backgrounds.append({
                        'item_key': row[0],
                        'name': 'Неизвестный фон',
                        'type': 'background'
                    })
            
            return backgrounds
    except Exception as e:
        logger.error(f"❌ Error getting backgrounds: {e}")
        return []

async def get_user_active_background(user_id: int) -> str:
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute(
                'SELECT bg_key FROM user_active_background WHERE user_id = ?',
                (user_id,)
            )
            row = await cursor.fetchone()
            return row[0] if row else 'default'
    except Exception as e:
        logger.error(f"❌ Error getting active background: {e}")
        return 'default'

async def set_user_active_background(user_id: int, bg_key: str) -> bool:
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            await conn.execute('''
                INSERT OR REPLACE INTO user_active_background (user_id, bg_key)
                VALUES (?, ?)
            ''', (user_id, bg_key))
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"❌ Error setting active background: {e}")
        return False

@rpg_router.message(F.text.lower() == "инвентарь")
async def show_inventory(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        
        builder = InlineKeyboardBuilder()
        
        builder.row(InlineKeyboardButton(
            text="🖼️ Фоны", 
            callback_data="rpg_show_backgrounds_f"
        ))
        builder.row(InlineKeyboardButton(
            text="🎒 Предметы", 
            callback_data="rpg_section:items"
        ))
        builder.row(InlineKeyboardButton(
            text="🛠️ Верстак", 
            callback_data="rpg_section:workbench"
        ))
        
        active_bg = await get_user_active_background(user_id)
        active_bg_name = "Стандартный" if active_bg == 'default' else active_bg
        
        text = (
            "🎒 **Инвентарь** 🎒\n\n"
            f"💼 Фон: {active_bg_name}\n"
            "💎 Выберите раздел:"
        )
        
        await message.answer(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ Error in show_inventory: {e}")
        await message.answer("❌ Ошибка при открытии инвентаря")

@rpg_router.callback_query(F.data.startswith("rpg_section:"))
async def handle_rpg_section(callback: types.CallbackQuery, profile_manager):
    try:
        section = callback.data.split(":")[1]
        
        if section == "backgrounds":
            await show_backgrounds_section(callback, profile_manager)
        elif section == "items":
            await show_items_section(callback, profile_manager)
        elif section == "workbench":
            await show_workbench_section(callback, profile_manager)
    except Exception as e:
        logger.error(f"❌ Error in handle_rpg_section: {e}")
        await callback.answer("❌ Ошибка при загрузке раздела")

async def show_backgrounds_section(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        active_background_key = await get_user_active_background(user_id)
        
        user_backgrounds = await get_user_backgrounds_inventory(user_id)
        
        builder = InlineKeyboardBuilder()
        text = "🖼️ **Фоны**\n\n"
        
        if user_backgrounds:
            for bg_item in user_backgrounds:
                bg_key = bg_item.get('item_key', 'unknown')
                bg_name = bg_item.get('name', 'Неизвестный фон')
                
                status = " ✅ (Активно)" if bg_key == active_background_key else ""
                
                builder.row(InlineKeyboardButton(
                    text=f"{bg_name}{status}", 
                    callback_data=f"activate_bg:{bg_key}"
                ))
        else:
            text += "📭 У вас пока нет фонов.\n"
            text += "🛒 Загляните в магазин!\n\n"
        
        default_status = " ✅ (Активно)" if active_background_key == 'default' else ""
        builder.row(InlineKeyboardButton(
            text=f"🔙 Стандартный{default_status}", 
            callback_data="reset_bg_to_default"
        ))
        
        builder.row(InlineKeyboardButton(
            text="🛒 Магазин фонов", 
            callback_data="shop_type:backgrounds"
        ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="rpg_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ Error in show_backgrounds_section: {e}")
        await callback.answer("❌ Ошибка при загрузке фонов")

async def show_items_section(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        
        builder = InlineKeyboardBuilder()
        text = "🎒 **Предметы**\n\n"
        
        user_inventory = await get_user_inventory_db(user_id)
        
        if user_inventory:
            non_background_items = [item for item in user_inventory if item.get('type') != 'background']
            
            if non_background_items:
                for item in non_background_items:
                    item_key = item.get('item_key', 'unknown')
                    item_name = item.get('name', 'Неизвестный предмет')
                    quantity = item.get('quantity', 1)
                    item_rarity = item.get('rarity', 'common')
                    
                    rarity_emoji = {
                        'common': '⚪',
                        'uncommon': '🟢', 
                        'rare': '🔵',
                        'epic': '🟣',
                        'legendary': '🟠'
                    }.get(item_rarity, '⚪')
                    
                    builder.row(InlineKeyboardButton(
                        text=f"{rarity_emoji} {item_name} ×{quantity}",
                        callback_data=f"item_info:{item_key}"
                    ))
            else:
                text += "📭 У вас пока нет предметов.\n"
        else:
            text += "📭 У вас пока нет предметов.\n"
        
        builder.row(InlineKeyboardButton(
            text="🛒 Магазин", 
            callback_data="shop_type:items"
        ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="rpg_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ Error in show_items_section: {e}")
        await callback.answer("❌ Ошибка при загрузке предметов")

@rpg_router.callback_query(F.data.startswith("item_info:"))
async def handle_item_info(callback: types.CallbackQuery, profile_manager):
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
        
        item_name = item_info.get('name', 'Неизвестный предмет')
        description = item_info.get('description', 'Описание отсутствует')
        rarity = item_info.get('rarity', 'common')
        item_type = item_info.get('type', 'material')
        
        text = f"📦 {item_name}\n"
        text += f"📖 {description}\n"
        text += f"💎 Редкость: {rarity}\n"
        text += f"💼 Тип: {item_type}\n"
        
        if 'stats' in item_info:
            stats = item_info['stats']
            text += "📊 Характеристики:\n"
            for stat, value in stats.items():
                text += f"   {stat}: +{value}\n"
        
        if 'effect' in item_info:
            effect = item_info['effect']
            text += "✨ Эффект:\n"
            for eff, val in effect.items():
                text += f"   {eff}: {val}\n"
        
        quick_use = quick_item_use_cache.get(user_id)
        is_double_tap = (
            quick_use
            and quick_use.get("item_key") == item_key
            and time.time() - quick_use.get("timestamp", 0) <= 5
        )

        if is_double_tap and item_key == "health_potion":
            rp_stats = await db.get_user_rp_stats(user_id)
            current_hp = rp_stats.get("hp", 100)
            max_hp = 100
            heal_value = int(item_info.get("effect", {}).get("heal", 30))
            if current_hp >= max_hp:
                await callback.answer("❤️ HP уже полное.", show_alert=True)
                return

            removed = await remove_item_from_inventory(user_id, item_key, quantity=1)
            if not removed:
                await callback.answer("❌ Не удалось использовать зелье.", show_alert=True)
                return

            new_hp = min(max_hp, current_hp + heal_value)
            await db.update_user_rp_stats(user_id, hp=new_hp)
            del quick_item_use_cache[user_id]
            await callback.answer(f"🧪 Использовано зелье! HP: {new_hp}/{max_hp}", show_alert=True)
            return

        quick_item_use_cache[user_id] = {"item_key": item_key, "timestamp": time.time()}
        if item_key == "health_potion":
            text += "\n\n💡 Нажмите ещё раз в течение 5 сек, чтобы использовать."

        await callback.answer(text, show_alert=True)
        
    except Exception as e:
        logger.error(f"❌ Error in handle_item_info: {e}")
        await callback.answer("❌ Ошибка при получении информации")

async def show_workbench_section(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        builder = InlineKeyboardBuilder()
        text = f"🛠️ **Верстак** | 💰 Баланс: {lumcoins} LUM\n\n"
        text += "Рецепты:\n\n"
        
        for recipe_key, recipe in ItemSystem.CRAFT_RECIPES.items():
            builder.row(InlineKeyboardButton(
                text=f"{recipe['name']} - 💰{recipe['cost']}",
                callback_data=f"rpg_craft_info:{recipe_key}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="🎨 Уникальный предмет - 💰5000",
            callback_data="rpg_craft_info:custom_item"
        ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="rpg_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ Error in show_workbench_section: {e}")
        await callback.answer("❌ Ошибка при загрузке верстака")

@rpg_router.callback_query(F.data == "rpg_show_backgrounds_f")
async def handle_show_backgrounds_f(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        active_background_key = await get_user_active_background(user_id)

        user_backgrounds = await get_user_backgrounds_inventory(user_id)
        
        builder = InlineKeyboardBuilder()
        text = "🖼️ **Фоны**\n\n"
        
        if user_backgrounds:
            for bg_item in user_backgrounds:
                bg_key = bg_item.get('item_key', 'unknown')
                bg_name = bg_item.get('name', 'Неизвестный фон')
                
                status = " ✅ (Активно)" if bg_key == active_background_key else ""
                builder.row(InlineKeyboardButton(
                    text=f"{bg_name}{status}", 
                    callback_data=f"activate_bg:{bg_key}"
                ))
        else:
            text += "📭 У вас пока нет фонов.\n"
            text += "🛒 Загляните в магазин!\n\n"
        
        default_status = " ✅ (Активно)" if active_background_key == 'default' else ""
        builder.row(InlineKeyboardButton(
            text=f"🔙 Стандартный{default_status}", 
            callback_data="reset_bg_to_default"
        ))
        
        builder.row(InlineKeyboardButton(
            text="🛒 Магазин фонов", 
            callback_data="shop_type:backgrounds"
        ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="rpg_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"❌ Error in handle_show_backgrounds_f: {e}")
        await callback.answer("❌ Ошибка при загрузке фонов")

@rpg_router.callback_query(F.data.startswith("shop_type:"))
async def handle_shop_type(callback: types.CallbackQuery, profile_manager):
    try:
        shop_type = callback.data.split(":")[1]
        
        if shop_type == "backgrounds":
            await show_shop_backgrounds(callback, profile_manager)
        elif shop_type == "items":
            await show_shop_items_page(callback, profile_manager, page=0)
    except Exception as e:
        logger.error(f"❌ Error in handle_shop_type: {e}")
        await callback.answer("❌ Ошибка при загрузке магазина")

async def show_shop_backgrounds(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        builder = InlineKeyboardBuilder()
        text = f"🖼️ **Магазин фонов** | 💰 Баланс: {lumcoins} LUM\n\n"
        
        available_backgrounds = ShopConfig.SHOP_BACKGROUNDS
        user_backgrounds = await get_user_backgrounds_inventory(user_id)
        user_bg_keys = [bg.get('item_key') for bg in user_backgrounds]
        
        for bg_key, bg_info in available_backgrounds.items():
            bg_name = bg_info['name']
            bg_price = bg_info.get('price', 0)
            
            if bg_key in user_bg_keys:
                status = " ✅ (Куплено)"
                builder.row(InlineKeyboardButton(
                    text=f"✅ {bg_name}{status}",
                    callback_data=f"bg_already_owned:{bg_key}"
                ))
            else:
                builder.row(InlineKeyboardButton(
                    text=f"🖼️ {bg_name} - 💰{bg_price}",
                    callback_data=f"buy_bg:{bg_key}"
                ))
        
        custom_bg_info = available_backgrounds.get("custom")
        if custom_bg_info:
            custom_price = custom_bg_info.get('price', 10000)
            has_custom = any(bg.get('item_key', '').startswith('custom:') for bg in user_backgrounds)
            
            if has_custom:
                builder.row(InlineKeyboardButton(
                    text=f"✅ Кастомный фон (Куплено)",
                    callback_data="bg_already_owned:custom"
                ))
            else:
                builder.row(InlineKeyboardButton(
                    text=f"🎨 Кастомный фон - 💰{custom_price}",
                    callback_data="buy_bg:custom"
                ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад",
            callback_data="shop_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ Error in show_shop_backgrounds: {e}")
        await callback.answer("❌ Ошибка при загрузке фонов")

async def show_shop_items_page(callback: types.CallbackQuery, profile_manager, page: int = 0):
    try:
        user_id = callback.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        sorted_items = ItemSystem.get_sorted_shop_items()
        
        items_per_page = 4
        total_pages = (len(sorted_items) + items_per_page - 1) // items_per_page
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(sorted_items))
        
        builder = InlineKeyboardBuilder()
        text = f"📦 **Магазин предметов** | 💰 Баланс: {lumcoins} LUM\n\n"
        text += f"📄 Страница {page + 1}/{total_pages}\n\n"
        
        for i in range(start_idx, end_idx):
            item_key, item_info = sorted_items[i]
            item_name = item_info['name']
            item_cost = item_info['cost']
            item_rarity = item_info.get('rarity', 'common')
            
            rarity_emoji = {
                'common': '⚪',
                'uncommon': '🟢',
                'rare': '🔵', 
                'epic': '🟣',
                'legendary': '🟠'
            }.get(item_rarity, '⚪')
            
            builder.row(InlineKeyboardButton(
                text=f"{rarity_emoji} {item_name} - 💰{item_cost}",
                callback_data=f"shop_item_info:{item_key}:{page}"
            ))
        
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(InlineKeyboardButton(
                text="⬅️", 
                callback_data=f"shop_items_page:{page-1}"
            ))
        
        if page < total_pages - 1:
            pagination_buttons.append(InlineKeyboardButton(
                text="➡️", 
                callback_data=f"shop_items_page:{page+1}"
            ))
        
        if pagination_buttons:
            builder.row(*pagination_buttons)
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад",
            callback_data="shop_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ Error in show_shop_items_page: {e}")
        await callback.answer("❌ Ошибка при загрузке товаров")

@rpg_router.callback_query(F.data.startswith("shop_items_page:"))
async def handle_shop_items_page(callback: types.CallbackQuery, profile_manager):
    try:
        page = int(callback.data.split(":")[1])
        await show_shop_items_page(callback, profile_manager, page)
    except Exception as e:
        logger.error(f"❌ Error in handle_shop_items_page: {e}")
        await callback.answer("❌ Ошибка при смене страницы")

@rpg_router.callback_query(F.data.startswith("buy_bg:"))
async def handle_buy_background(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        bg_key = callback.data.split(":")[1]
        
        available_backgrounds = ShopConfig.SHOP_BACKGROUNDS
        bg_info = available_backgrounds.get(bg_key)
        
        if not bg_info:
            await callback.answer("❌ Фон не найден")
            return
        
        bg_price = bg_info.get('price', 0)
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        if lumcoins < bg_price:
            await callback.answer(f"❌ Недостаточно LUM. Нужно: {bg_price}")
            return
        
        user_backgrounds = await get_user_backgrounds_inventory(user_id)
        user_bg_keys = [bg.get('item_key') for bg in user_backgrounds]
        
        if bg_key in user_bg_keys:
            await callback.answer("❌ У вас уже есть этот фон")
            return
        
        success = await update_user_lumcoins(profile_manager, user_id, -bg_price)
        if not success:
            await callback.answer("❌ Ошибка при списании")
            return
        
        bg_item_data = {
            'item_key': bg_key,
            'name': bg_info['name'],
            'type': 'background',
            'price': bg_price,
            'purchased_at': time.time()
        }
        
        success = await add_item_to_inventory_db(user_id, bg_item_data)
        if not success:
            await callback.answer("❌ Ошибка при добавлении")
            return
        
        await set_user_active_background(user_id, bg_key)
        
        await callback.answer(f"✅ Фон '{bg_info['name']}' куплен!")
        await show_shop_backgrounds(callback, profile_manager)
        
    except Exception as e:
        logger.error(f"❌ Error in handle_buy_background: {e}")
        await callback.answer("❌ Ошибка при покупке")

@rpg_router.callback_query(F.data.startswith("shop_item_info:"))
async def handle_shop_item_info(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        parts = callback.data.split(":")
        item_key = parts[1]
        page = int(parts[2]) if len(parts) > 2 else 0
        
        item_info = ItemSystem.SHOP_ITEMS.get(item_key)
        
        if not item_info:
            await callback.answer("❌ Товар не найден")
            return
        
        quick_purchase = quick_purchase_cache.get(user_id)
        if (quick_purchase and 
            quick_purchase['item_key'] == item_key and 
            time.time() - quick_purchase['timestamp'] <= 5):
            
            lumcoins = await get_user_lumcoins(profile_manager, user_id)

            if lumcoins < item_info['cost']:
                await callback.answer(f"❌ Недостаточно LUM. Нужно: {item_info['cost']}")
                return
            
            success = await update_user_lumcoins(profile_manager, user_id, -item_info['cost'])
            if not success:
                await callback.answer("❌ Ошибка при списании")
                return
            
            item_data = {
                'item_key': item_key,
                'name': item_info['name'],
                'type': item_info['type'],
                'rarity': item_info.get('rarity', 'common'),
                'description': item_info['description'],
                'cost': item_info['cost'],
                'effect': item_info.get('effect'),
                'purchased_at': time.time()
            }
            
            success = await add_item_to_inventory_db(user_id, item_data)
            if not success:
                await callback.answer("❌ Ошибка при добавлении")
                return
            
            del quick_purchase_cache[user_id]
            
            await callback.answer(f"✅ Куплено: {item_info['name']}!")
            await show_shop_items_page(callback, profile_manager, page)
            
        else:
            lumcoins = await get_user_lumcoins(profile_manager, user_id)
            
            quick_purchase_cache[user_id] = {
                'item_key': item_key,
                'timestamp': time.time(),
                'page': page
            }
            
            rarity_display = {
                'common': '⚪ Обычный',
                'uncommon': '🟢 Необычный', 
                'rare': '🔵 Редкий',
                'epic': '🟣 Эпический',
                'legendary': '🟠 Легендарный'
            }.get(item_info.get('rarity', 'common'), '⚪ Обычный')
            
            info_text = f"🛒 {item_info['name']}\n"
            info_text += f"📖 {item_info['description']}\n"
            info_text += f"💰 Цена: {item_info['cost']} LUM\n"
            info_text += f"💎 Редкость: {rarity_display}\n"
            info_text += f"💼 Тип: {item_info['type']}\n"
            
            if 'stats' in item_info:
                stats_text = ""
                for stat, value in item_info['stats'].items():
                    stats_text += f"   {stat}: +{value}\n"
                if stats_text:
                    info_text += f"📊 Характеристики:\n{stats_text}"
            
            info_text += f"\n✅ Нажмите ЕЩЁ РАЗ для покупки!"
            
            await callback.answer(info_text, show_alert=True)
            
    except Exception as e:
        logger.error(f"❌ Error in handle_shop_item_info: {e}")
        await callback.answer("❌ Ошибка при покупке")

@rpg_router.callback_query(F.data == "rpg_back_to_main")
async def back_to_rpg_main(callback: types.CallbackQuery, profile_manager):
    await show_inventory(callback.message, profile_manager)

@rpg_router.callback_query(F.data == "shop_back_to_main")
async def back_to_shop_main(callback: types.CallbackQuery, profile_manager):
    await show_shop_main(callback.message, profile_manager)

@rpg_router.callback_query(F.data.startswith("activate_bg:"))
async def process_activate_background(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        background_key_to_activate = callback.data.split(":")[1]

        user_backgrounds = await get_user_backgrounds_inventory(user_id)
        user_bg_keys = [bg.get('item_key') for bg in user_backgrounds]
        
        if background_key_to_activate in user_bg_keys or background_key_to_activate == 'default':
            await set_user_active_background(user_id, background_key_to_activate)
            
            if background_key_to_activate == 'default':
                bg_name = "Стандартный фон"
            else:
                bg_info = ShopConfig.SHOP_BACKGROUNDS.get(background_key_to_activate)
                bg_name = bg_info['name'] if bg_info else background_key_to_activate

            await callback.answer(f"✅ Фон '{bg_name}' активирован!")
            await show_backgrounds_section(callback, profile_manager)
        else:
            await callback.answer("❌ Этого фона нет в коллекции")
            
    except Exception as e:
        logger.error(f"❌ Error in process_activate_background: {e}")
        await callback.answer("❌ Ошибка при активации")

@rpg_router.callback_query(F.data == "reset_bg_to_default")
async def process_reset_background_to_default(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        await set_user_active_background(user_id, 'default')
        await callback.answer("✅ Стандартный фон активирован!")
        await show_backgrounds_section(callback, profile_manager)
    except Exception as e:
        logger.error(f"❌ Error in process_reset_background_to_default: {e}")
        await callback.answer("❌ Ошибка при сбросе")

@rpg_router.callback_query(F.data.startswith("bg_already_owned:"))
async def process_bg_already_owned(callback: types.CallbackQuery):
    bg_key = callback.data.split(":")[1]
    if bg_key == "custom":
        await callback.answer("✅ У вас уже есть кастомный фон!")
    else:
        bg_info = ShopConfig.SHOP_BACKGROUNDS.get(bg_key)
        bg_name = bg_info['name'] if bg_info else bg_key
        await callback.answer(f"✅ Фон '{bg_name}' уже в коллекции!")
