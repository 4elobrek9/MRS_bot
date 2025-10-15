from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import logging
from typing import Dict, List
import random
import time
import json
import aiosqlite
from core.group.stat.shop_config import ShopConfig

logger = logging.getLogger(__name__)
rpg_router = Router(name="rpg_router")

quick_purchase_cache = {}
shop_pages_cache = {}

class ItemSystem:
    SHOP_ITEMS = {
        "wood": {"name": "🪵 Дерево", "type": "material", "rarity": "common", "cost": 10, "description": "Обычная древесина для крафта"},
        "iron_ore": {"name": "⛏️ Железная руда", "type": "material", "rarity": "common", "cost": 25, "description": "Руда для выплавки железа"},
        "health_potion": {"name": "🧪 Зелье здоровья", "type": "consumable", "rarity": "uncommon", "cost": 50, "description": "Восстанавливает 30 HP", "effect": {"heal": 30}},
        "magic_crystal": {"name": "💎 Магический кристалл", "type": "material", "rarity": "rare", "cost": 150, "description": "Редкий магический компонент"},
        "energy_drink": {"name": "⚡ Энергетик", "type": "consumable", "rarity": "common", "cost": 30, "description": "Восстанавливает энергию", "effect": {"energy": 20}},
        "gold_ingot": {"name": "🥇 Золотой слиток", "type": "material", "rarity": "rare", "cost": 200, "description": "Ценный металл для крафта"},
        "lucky_charm": {"name": "🍀 Талисман удачи", "type": "equipment", "rarity": "epic", "cost": 500, "description": "Увеличивает удачу", "stats": {"luck": 10}},
        "dragon_scale": {"name": "🐉 Чешуя дракона", "type": "material", "rarity": "legendary", "cost": 1000, "description": "Легендарный материал"}
    }

    CRAFT_RECIPES = {
        "iron_ingot": {"name": "🔩 Железный слиток", "result": "iron_ingot", "result_name": "🔩 Железный слиток", "cost": 25, "materials": {"iron_ore": 3}, "description": "Выплавленный железный слиток"},
        "basic_sword": {"name": "⚔️ Обычный меч", "result": "basic_sword", "result_name": "⚔️ Обычный меч", "cost": 50, "materials": {"wood": 2, "iron_ingot": 1}, "description": "Надёжный железный меч", "stats": {"attack": 5}}
    }

    @classmethod
    def get_sorted_shop_items(cls) -> List[tuple]:
        return sorted(cls.SHOP_ITEMS.items(), key=lambda x: x[1]['cost'])

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

async def add_item_to_inventory_db(user_id: int, item_data: dict):
    try:
        async with aiosqlite.connect('profiles.db') as conn:
            await conn.execute('''
                INSERT OR REPLACE INTO user_inventory 
                (user_id, item_key, item_type, item_data) 
                VALUES (?, ?, ?, ?)
            ''', (
                user_id, 
                item_data.get('item_key', 'unknown'),
                item_data.get('type', 'material'),
                json.dumps(item_data, ensure_ascii=False) if isinstance(item_data, dict) else str(item_data)
            ))
            await conn.commit()
            logger.info(f"Item added to inventory for user {user_id}: {item_data.get('item_key')}")
            return True
    except Exception as e:
        logger.error(f"Error adding item to inventory for user {user_id}: {e}")
        return False

async def get_user_inventory_db(user_id: int) -> List[dict]:
    try:
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute(
                'SELECT item_data FROM user_inventory WHERE user_id = ?',
                (user_id,)
            )
            rows = await cursor.fetchall()
            
            inventory = []
            for row in rows:
                try:
                    item_data = json.loads(row[0])
                    inventory.append(item_data)
                except Exception as e:
                    logger.error(f"Error parsing item data for user {user_id}: {e}")
                    inventory.append({'name': str(row[0])})
            
            return inventory
    except Exception as e:
        logger.error(f"Error getting inventory for user {user_id}: {e}")
        return []

async def get_user_backgrounds_inventory(user_id: int) -> List[dict]:
    try:
        inventory = await get_user_inventory_db(user_id)
        return [item for item in inventory if item.get('type') == 'background']
    except Exception as e:
        logger.error(f"Error getting backgrounds for user {user_id}: {e}")
        return []

@rpg_router.message(F.text.lower() == "инвентарь")
async def show_inventory(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        
        builder = InlineKeyboardBuilder()
        
        builder.row(InlineKeyboardButton(
            text="🖼️ Коллекция фонов", 
            callback_data="rpg_show_backgrounds_f"
        ))
        builder.row(InlineKeyboardButton(
            text="🎒 Предметы и ресурсы", 
            callback_data="rpg_section:items"
        ))
        builder.row(InlineKeyboardButton(
            text="🛠️ Верстак крафта", 
            callback_data="rpg_section:workbench"
        ))
        
        user_profile = await profile_manager.get_user_profile(message.from_user)
        active_bg = user_profile.get('active_background', 'default') if user_profile else 'default'
        
        text = (
            "🎒 **Ваш инвентарь** 🎒\n\n"
            f"💼 Активный фон: {active_bg}\n"
            "💎 Выберите раздел:"
        )
        
        await message.answer(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error in show_inventory: {e}")
        await message.answer("❌ Ошибка при открытии инвентаря")

@rpg_router.message(F.text.lower() == "верстак")
async def show_workbench_cmd(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        builder = InlineKeyboardBuilder()
        text = f"🛠️ **Верстак крафта** | 💰 Баланс: {lumcoins} LUM\n\n"
        text += "Доступные рецепты:\n\n"
        
        for recipe_key, recipe in ItemSystem.CRAFT_RECIPES.items():
            builder.row(InlineKeyboardButton(
                text=f"{recipe['name']} - 💰{recipe['cost']}",
                callback_data=f"rpg_craft_info:{recipe_key}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="🎨 Создать уникальный предмет - 💰5000",
            callback_data="rpg_craft_info:custom_item"
        ))
        
        await message.answer(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error in show_workbench_cmd: {e}")
        await message.answer("❌ Ошибка при открытии верстака")

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
            "🛒 **Универсальный магазин** 🛒\n\n"
            f"💰 Ваш баланс: {lumcoins} LUM\n\n"
            "🎯 Выберите тип товаров:"
        )
        
        await message.answer(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error in show_shop_main: {e}")
        await message.answer("❌ Ошибка при открытии магазина")

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
        logger.error(f"Error in handle_rpg_section: {e}")
        await callback.answer("❌ Ошибка при загрузке раздела")

async def show_backgrounds_section(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        user_profile = await profile_manager.get_user_profile(callback.from_user)
        active_background = user_profile.get('active_background', 'default') if user_profile else 'default'
        
        user_backgrounds = await get_user_backgrounds_inventory(user_id)
        
        builder = InlineKeyboardBuilder()
        text = "🖼️ **Коллекция фонов**\n\n"
        
        if user_backgrounds:
            for bg_item in user_backgrounds:
                bg_key = bg_item.get('item_key', bg_item.get('name', 'unknown'))
                bg_name = bg_item.get('name', 'Неизвестный фон')
                
                if bg_key.startswith("custom:"):
                    bg_display_name = "🎨 Кастомный фон"
                else:
                    bg_display_name = bg_name
                
                status = " ✅ (Активно)" if bg_key == active_background else ""
                
                builder.row(InlineKeyboardButton(
                    text=f"{bg_display_name}{status}", 
                    callback_data=f"activate_bg:{bg_key}"
                ))
        else:
            text += "📭 У вас пока нет фонов.\n"
            text += "🛒 Загляните в магазин фонов!\n\n"
        
        default_status = " ✅ (Активно)" if active_background == 'default' else ""
        builder.row(InlineKeyboardButton(
            text=f"🔙 Стандартный фон{default_status}", 
            callback_data="reset_bg_to_default"
        ))
        
        builder.row(InlineKeyboardButton(
            text="🛒 Магазин фонов", 
            callback_data="shop_type:backgrounds"
        ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад к инвентарю", 
            callback_data="rpg_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error in show_backgrounds_section: {e}")
        await callback.answer("❌ Ошибка при загрузке фонов")

async def show_items_section(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        
        builder = InlineKeyboardBuilder()
        text = "🎒 **Предметы и ресурсы**\n\n"
        
        user_inventory = await get_user_inventory_db(user_id)
        
        if user_inventory:
            non_background_items = [item for item in user_inventory if item.get('type') != 'background']
            
            if non_background_items:
                for item in non_background_items:
                    item_name = item.get('name', 'Неизвестный предмет')
                    item_rarity = item.get('rarity', 'common')
                    
                    rarity_emoji = {
                        'common': '⚪',
                        'uncommon': '🟢', 
                        'rare': '🔵',
                        'epic': '🟣',
                        'legendary': '🟠'
                    }.get(item_rarity, '⚪')
                    
                    text += f"{rarity_emoji} {item_name}\n"
            else:
                text += "📭 У вас пока нет предметов.\n"
                text += "🛒 Посетите магазин или верстак\n\n"
        else:
            text += "📭 У вас пока нет предметов.\n"
            text += "🛒 Посетите магазин или верстак\n\n"
        
        builder.row(InlineKeyboardButton(
            text="🛒 Магазин предметов", 
            callback_data="shop_type:items"
        ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад к инвентарю", 
            callback_data="rpg_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error in show_items_section: {e}")
        await callback.answer("❌ Ошибка при загрузке предметов")

async def show_workbench_section(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        builder = InlineKeyboardBuilder()
        text = f"🛠️ **Верстак крафта** | 💰 Баланс: {lumcoins} LUM\n\n"
        text += "Доступные рецепты:\n\n"
        
        for recipe_key, recipe in ItemSystem.CRAFT_RECIPES.items():
            builder.row(InlineKeyboardButton(
                text=f"{recipe['name']} - 💰{recipe['cost']}",
                callback_data=f"rpg_craft_info:{recipe_key}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="🎨 Создать уникальный предмет - 💰5000",
            callback_data="rpg_craft_info:custom_item"
        ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад к инвентарю", 
            callback_data="rpg_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error in show_workbench_section: {e}")
        await callback.answer("❌ Ошибка при загрузке верстака")

@rpg_router.callback_query(F.data == "rpg_show_backgrounds_f")
async def handle_show_backgrounds_f(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        user_profile = await profile_manager.get_user_profile(callback.from_user)
        active_background_key = user_profile.get('active_background', 'default') if user_profile else 'default'

        user_backgrounds = await get_user_backgrounds_inventory(user_id)
        
        builder = InlineKeyboardBuilder()
        text = "🖼️ **Коллекция фонов**\n\n"
        
        if user_backgrounds:
            for bg_item in user_backgrounds:
                bg_key = bg_item.get('item_key', 'unknown')
                if bg_key.startswith("custom:"):
                    bg_name = "🎨 Кастомный фон"
                else:
                    bg_info = ShopConfig.SHOP_BACKGROUNDS.get(bg_key)
                    bg_name = bg_info['name'] if bg_info else bg_key
                
                status = " ✅ (Активно)" if bg_key == active_background_key else ""
                builder.row(InlineKeyboardButton(
                    text=f"{bg_name}{status}", 
                    callback_data=f"activate_bg:{bg_key}"
                ))
        else:
            text += "📭 У вас пока нет фонов.\n"
            text += "🛒 Загляните в магазин фонов!\n\n"
        
        default_status = " ✅ (Активно)" if active_background_key == 'default' else ""
        builder.row(InlineKeyboardButton(
            text=f"🔙 Стандартный фон{default_status}", 
            callback_data="reset_bg_to_default"
        ))
        
        builder.row(InlineKeyboardButton(
            text="🛒 Магазин фонов", 
            callback_data="shop_type:backgrounds"
        ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад к инвентарю", 
            callback_data="rpg_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in handle_show_backgrounds_f: {e}")
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
        logger.error(f"Error in handle_shop_type: {e}")
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
            text="↩️ Назад в магазин",
            callback_data="shop_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error in show_shop_backgrounds: {e}")
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
                text="⬅️ Назад", 
                callback_data=f"shop_items_page:{page-1}"
            ))
        
        if page < total_pages - 1:
            pagination_buttons.append(InlineKeyboardButton(
                text="Вперед ➡️", 
                callback_data=f"shop_items_page:{page+1}"
            ))
        
        if pagination_buttons:
            builder.row(*pagination_buttons)
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад в магазин",
            callback_data="shop_back_to_main"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"Error in show_shop_items_page: {e}")
        await callback.answer("❌ Ошибка при загрузке товаров")

@rpg_router.callback_query(F.data.startswith("shop_items_page:"))
async def handle_shop_items_page(callback: types.CallbackQuery, profile_manager):
    try:
        page = int(callback.data.split(":")[1])
        await show_shop_items_page(callback, profile_manager, page)
    except Exception as e:
        logger.error(f"Error in handle_shop_items_page: {e}")
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
            await callback.answer("❌ Ошибка при списании средств")
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
            await callback.answer("❌ Ошибка при добавлении в инвентарь")
            return
        
        await profile_manager.set_user_background(user_id, bg_key)
        
        await callback.answer(f"✅ Фон '{bg_info['name']}' куплен и активирован!")
        await show_shop_backgrounds(callback, profile_manager)
        
    except Exception as e:
        logger.error(f"Error in handle_buy_background: {e}")
        await callback.answer("❌ Ошибка при покупке фона")

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
                await callback.answer("❌ Ошибка при списании средств")
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
                await callback.answer("❌ Ошибка при добавлении в инвентарь")
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
            
            info_text = (
                f"🛒 {item_info['name']}\n"
                f"📖 {item_info['description']}\n"
                f"💰 Цена: {item_info['cost']} LUM\n"
                f"💎 Редкость: {rarity_display}\n"
                f"💼 Тип: {item_info['type']}\n\n"
                f"✅ Нажмите ЕЩЁ РАЗ для покупки!"
            )
            
            await callback.answer(info_text, show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in handle_shop_item_info: {e}")
        await callback.answer("❌ Ошибка при покупке")

@rpg_router.callback_query(F.data.startswith("rpg_craft_info:"))
async def show_craft_info(callback: types.CallbackQuery, profile_manager):
    try:
        recipe_key = callback.data.split(":")[1]
        
        if recipe_key == "custom_item":
            user_id = callback.from_user.id
            lumcoins = await get_user_lumcoins(profile_manager, user_id)
            
            if lumcoins < 5000:
                await callback.answer("❌ Недостаточно LUM. Нужно 5000.")
                return
            
            custom_names = ["Кастомный меч", "Уникальный артефакт", "Личный талисман", "Магический жезл", "Древний амулет"]
            custom_descriptions = [
                "Предмет, созданный специально для вас",
                "Уникальное творение мастера",
                "Наполненный магической энергией", 
                "Изготовлен из редких материалов"
            ]
            
            custom_item = {
                "item_key": f"custom_{random.randint(1000, 9999)}",
                "name": f"🎨 {random.choice(custom_names)}",
                "type": "equipment",
                "rarity": random.choice(["common", "uncommon", "rare"]),
                "description": random.choice(custom_descriptions),
                "stats": {"attack": random.randint(1, 5), "defense": random.randint(1, 3)},
                "crafted_at": time.time()
            }
            
            success = await update_user_lumcoins(profile_manager, user_id, -5000)
            if not success:
                await callback.answer("❌ Ошибка при списании средств")
                return
            
            success = await add_item_to_inventory_db(user_id, custom_item)
            if not success:
                await callback.answer("❌ Ошибка при создании предмета")
                return
            
            await callback.message.edit_text(
                f"🎨 **Успешно создан уникальный предмет!**\n\n"
                f"📦 {custom_item['name']}\n"
                f"📖 {custom_item['description']}\n"
                f"💎 Редкость: {custom_item['rarity']}\n"
                f"💰 Потрачено: 5000 LUM\n\n"
                f"⚔️ Атака: +{custom_item['stats']['attack']}\n"
                f"🛡️ Защита: +{custom_item['stats']['defense']}",
                reply_markup=InlineKeyboardBuilder().add(
                    InlineKeyboardButton(
                        text="↩️ Назад к верстаку",
                        callback_data="rpg_section:workbench"
                    )
                ).as_markup()
            )
            return
        
        recipe = ItemSystem.CRAFT_RECIPES.get(recipe_key)
        if not recipe:
            await callback.answer("❌ Рецепт не найден")
            return
        
        requirements_text = "Требуется: "
        if recipe.get('materials'):
            for material_key, quantity in recipe['materials'].items():
                material_info = ItemSystem.SHOP_ITEMS.get(material_key, {'name': material_key})
                requirements_text += f"{material_info['name']} x{quantity}, "
            requirements_text = requirements_text.rstrip(", ")
        else:
            requirements_text = "Нет требований"
        
        await callback.answer(f"📋 {recipe['name']}\n{requirements_text}\n💰 Стоимость: {recipe['cost']} LUM")
        
    except Exception as e:
        logger.error(f"Error in show_craft_info: {e}")
        await callback.answer("❌ Ошибка при создании предмета")

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
            await profile_manager.set_user_background(user_id, background_key_to_activate)
            
            if background_key_to_activate == 'default':
                bg_name = "Стандартный фон"
            elif background_key_to_activate.startswith("custom:"):
                bg_name = "Кастомный фон"
            else:
                bg_info = ShopConfig.SHOP_BACKGROUNDS.get(background_key_to_activate)
                bg_name = bg_info['name'] if bg_info else background_key_to_activate

            await callback.answer(f"✅ Фон '{bg_name}' активирован!")
            await show_backgrounds_section(callback, profile_manager)
        else:
            await callback.answer("❌ Этого фона нет в вашей коллекции")
            
    except Exception as e:
        logger.error(f"Error in process_activate_background: {e}")
        await callback.answer("❌ Ошибка при активации фона")

@rpg_router.callback_query(F.data == "reset_bg_to_default")
async def process_reset_background_to_default(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        await profile_manager.set_user_background(user_id, 'default')
        await callback.answer("✅ Стандартный фон активирован!")
        await show_backgrounds_section(callback, profile_manager)
    except Exception as e:
        logger.error(f"Error in process_reset_background_to_default: {e}")
        await callback.answer("❌ Ошибка при сбросе фона")

@rpg_router.callback_query(F.data.startswith("bg_already_owned:"))
async def process_bg_already_owned(callback: types.CallbackQuery):
    bg_key = callback.data.split(":")[1]
    if bg_key == "custom":
        await callback.answer("✅ У вас уже есть кастомный фон!")
    else:
        bg_info = ShopConfig.SHOP_BACKGROUNDS.get(bg_key)
        bg_name = bg_info['name'] if bg_info else bg_key
        await callback.answer(f"✅ Фон '{bg_name}' уже в вашей коллекции!")

def setup_rpg_handlers(main_dp: Router):
    main_dp.include_router(rpg_router)
    logger.info("RPG router included in Dispatcher.")