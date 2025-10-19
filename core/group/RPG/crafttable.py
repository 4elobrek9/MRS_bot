from core.group.RPG.MAINrpg import rpg_router
from core.group.RPG.rpg_utils import ensure_db_initialized
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import logging
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import aiosqlite
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

@rpg_router.message(F.text.lower() == "верстак")
async def show_workbench_cmd(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
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
        
        await message.answer(text, reply_markup=builder.as_markup())
    except Exception as e:
        logger.error(f"❌ Error in show_workbench_cmd: {e}")
        await message.answer("❌ Ошибка при открытии верстака")


@rpg_router.callback_query(F.data.startswith("rpg_craft_info:"))
async def show_craft_info(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
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
                await callback.answer("❌ Ошибка при списании")
                return
            
            success = await add_item_to_inventory_db(user_id, custom_item)
            if not success:
                await callback.answer("❌ Ошибка при создании")
                return
            
            await callback.message.edit_text(
                f"🎨 **Успешно создан!**\n\n"
                f"📦 {custom_item['name']}\n"
                f"📖 {custom_item['description']}\n"
                f"💎 Редкость: {custom_item['rarity']}\n"
                f"💰 Потрачено: 5000 LUM\n\n"
                f"⚔️ Атака: +{custom_item['stats']['attack']}\n"
                f"🛡️ Защита: +{custom_item['stats']['defense']}",
                reply_markup=InlineKeyboardBuilder().add(
                    InlineKeyboardButton(
                        text="↩️ Назад",
                        callback_data="rpg_section:workbench"
                    )
                ).as_markup()
            )
            return
        
        recipe = ItemSystem.CRAFT_RECIPES.get(recipe_key)
        if not recipe:
            await callback.answer("❌ Рецепт не найден")
            return
        
        user_id = callback.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        if lumcoins < recipe['cost']:
            await callback.answer(f"❌ Недостаточно LUM. Нужно: {recipe['cost']}")
            return
        
        user_inventory = await get_user_inventory_db(user_id)
        inventory_dict = {}
        for item in user_inventory:
            inventory_dict[item['item_key']] = item.get('quantity', 1)
        
        missing_materials = []
        for material_key, required_quantity in recipe.get('materials', {}).items():
            current_quantity = inventory_dict.get(material_key, 0)
            if current_quantity < required_quantity:
                material_info = ItemSystem.SHOP_ITEMS.get(material_key, {'name': material_key})
                missing_materials.append(f"{material_info['name']} (нужно: {required_quantity}, есть: {current_quantity})")
        
        if missing_materials:
            await callback.answer(f"❌ Не хватает:\n" + "\n".join(missing_materials))
            return
        
        success = await update_user_lumcoins(profile_manager, user_id, -recipe['cost'])
        if not success:
            await callback.answer("❌ Ошибка при списании")
            return
        
        for material_key, required_quantity in recipe.get('materials', {}).items():
            await remove_item_from_inventory(user_id, material_key, required_quantity)
        
        crafted_item_data = {
            'item_key': recipe['result'],
            'name': recipe['result_name'],
            'type': ItemSystem.CRAFTED_ITEMS[recipe['result']]['type'],
            'rarity': ItemSystem.CRAFTED_ITEMS[recipe['result']]['rarity'],
            'description': recipe['description'],
            'stats': recipe.get('stats', {}),
            'effect': ItemSystem.CRAFTED_ITEMS[recipe['result']].get('effect'),
            'crafted_at': time.time()
        }
        
        success = await add_item_to_inventory_db(user_id, crafted_item_data)
        if not success:
            await callback.answer("❌ Ошибка при добавлении")
            return
        
        await callback.message.edit_text(
            f"🛠️ **Успешный крафт!**\n\n"
            f"📦 Создан: {recipe['result_name']}\n"
            f"📖 {recipe['description']}\n"
            f"💰 Потрачено: {recipe['cost']} LUM\n\n"
            f"✅ Предмет добавлен!",
            reply_markup=InlineKeyboardBuilder().add(
                InlineKeyboardButton(
                    text="↩️ Назад",
                    callback_data="rpg_section:workbench"
                )
            ).as_markup()
        )
        
    except Exception as e:
        logger.error(f"❌ Error in show_craft_info: {e}")
        await callback.answer("❌ Ошибка при создании")
