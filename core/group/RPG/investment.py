from core.group.RPG.MAINrpg import rpg_router
from core.group.RPG.rpg_utils import ensure_db_initialized
from .rpg_utils import investment_amounts, quick_purchase_cache

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
INVESTMENT_TERM_DAYS = 14

async def add_investment(user_id: int, amount: int, term_days: int, interest_rate: float, risk: float = 0) -> bool:
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            await conn.execute('''
                INSERT INTO user_investments (user_id, amount, term_days, interest_rate, risk, invested_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, amount, term_days, interest_rate, risk, time.time(), 'active'))
            
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"❌ Error adding investment: {e}")
        return False

async def get_user_active_investments(user_id: int) -> List[dict]:
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute('''
                SELECT * FROM user_investments 
                WHERE user_id = ? AND status = 'active'
            ''', (user_id,))
            
            rows = await cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            
            investments = []
            for row in rows:
                investment_dict = dict(zip(columns, row))
                investments.append(investment_dict)
            
            return investments
    except Exception as e:
        logger.error(f"❌ Error getting user investments: {e}")
        return []


async def get_user_investment_history(user_id: int, limit: int = 20) -> List[dict]:
    try:
        await ensure_db_initialized()
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute(
                '''
                SELECT * FROM user_investments
                WHERE user_id = ? AND status IN ('completed', 'failed')
                ORDER BY invested_at DESC
                LIMIT ?
                ''',
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        logger.error(f"❌ Error getting investment history: {e}")
        return []

@rpg_router.message(F.text.lower() == "инвестировать")
async def show_investment(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        active_investments = await get_user_active_investments(user_id)
        history = await get_user_investment_history(user_id, limit=5)
        
        builder = InlineKeyboardBuilder()
        text = f"💼 **Инвестиции** | 💰 Баланс: {lumcoins} LUM\n\n"
        
        if active_investments:
            # Считаем завершенные инвестиции
            ready_count = 0
            total_invested = 0
            total_profit = 0
            
            for investment in active_investments:
                days_passed = (time.time() - investment['invested_at']) / 86400
                if days_passed >= investment['term_days']:
                    ready_count += 1
                total_invested += investment['amount']
                total_profit += int(investment['amount'] * investment['interest_rate'])
            
            text += f"📊 **Активные инвестиции:** {len(active_investments)}\n"
            text += f"💰 **Всего вложено:** {total_invested} LUM\n"
            text += f"💸 **Ожидаемая прибыль:** +{total_profit} LUM\n"
            
            if ready_count > 0:
                text += f"✅ **Готовы к получению:** {ready_count}\n\n"
            else:
                # Показываем ближайшую инвестицию
                nearest = min(active_investments, 
                            key=lambda x: x['term_days'] - (time.time() - x['invested_at']) / 86400)
                days_left = nearest['term_days'] - (time.time() - nearest['invested_at']) / 86400
                text += f"⏰ **Ближайшая завершится через:** {int(days_left)} дней\n\n"
            
            # Всегда показываем только эти кнопки
            builder.row(InlineKeyboardButton(
                text="💰 Инвестировать", 
                callback_data="invest_start_new"
            ))
            
            builder.row(InlineKeyboardButton(
                text="🔄 Обновить", 
                callback_data="invest_refresh"
            ))
            
            if ready_count > 0:
                builder.row(InlineKeyboardButton(
                    text="💸 Забрать прибыль", 
                    callback_data="invest_claim_all"
                ))
                
        else:
            text += "💡 **Инвестируйте LUM под проценты!**\n\n"
            text += "📅 **Все инвестиции привязаны к сроку 14 дней.**\n"
            text += "🔒 Безопасная: 14 дней / +35%\n"
            text += "🎯 Рискованная: 14 дней / +70% (риск 35%)\n\n"
            
            builder.row(InlineKeyboardButton(
                text="💰 Инвестировать", 
                callback_data="invest_start_new"
            ))
            
            builder.row(InlineKeyboardButton(
                text="🔄 Обновить", 
                callback_data="invest_refresh"
            ))
        
        await message.answer(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in show_investment: {e}")
        await message.answer("❌ Ошибка при загрузке инвестиций")

@rpg_router.callback_query(F.data == "invest_new")
async def handle_invest_new(callback: types.CallbackQuery, profile_manager):
    """Просто открываем меню инвестиций"""
    await show_investment(callback.message, profile_manager)

@rpg_router.callback_query(F.data == "invest_start_new")
async def handle_invest_start_new(callback: types.CallbackQuery, profile_manager):
    """Начать новую инвестицию с проверкой кулдауна"""
    try:
        user_id = callback.from_user.id
        
        # Проверяем кулдаун - максимум 5 активных инвестиций
        active_investments = await get_user_active_investments(user_id)
        if len(active_investments) >= 5:
            await callback.answer("❌ Достигнут лимит: максимум 5 активных инвестиций одновременно")
            return
        
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        builder = InlineKeyboardBuilder()
        text = f"💼 **Новая инвестиция** | 💰 Баланс: {lumcoins} LUM\n\n"
        text += "💸 **Выберите сумму инвестиции:**\n\n"
        
        # Предлагаем суммы в зависимости от баланса
        amounts = [1000, 5000, 10000, 50000]
        available_amounts = [amt for amt in amounts if amt <= lumcoins]
        
        if not available_amounts:
            await callback.answer("❌ Недостаточно LUM для инвестирования")
            return
            
        for amount in available_amounts:
            builder.row(InlineKeyboardButton(
                text=f"💰 {amount:,} LUM", 
                callback_data=f"invest_amount:{amount}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="invest_new"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in handle_invest_start_new: {e}")
        await callback.answer("❌ Ошибка при создании инвестиции")

@rpg_router.callback_query(F.data == "invest_refresh")
async def handle_invest_refresh(callback: types.CallbackQuery, profile_manager):
    """Обновить информацию об инвестициях"""
    await show_investment(callback.message, profile_manager)

@rpg_router.callback_query(F.data.startswith("invest_amount:"))
async def handle_invest_amount(callback: types.CallbackQuery, profile_manager):
    """Обработка выбора суммы инвестиции"""
    try:
        user_id = callback.from_user.id
        amount = int(callback.data.split(":")[1])
        
        # Дополнительная проверка баланса
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        if lumcoins < amount:
            await callback.answer(f"❌ Недостаточно LUM. Нужно: {amount}")
            return
        
        investment_amounts[user_id] = amount
        
        builder = InlineKeyboardBuilder()
        text = f"💼 **Выбор инвестиции** | 💰 Сумма: {amount:,} LUM\n\n"
        text += "🔒 **Безопасные инвестиции:**\n"
        
        safe_investments = [
            ("🛡️ 14 дней, 35%", f"invest_safe:{INVESTMENT_TERM_DAYS}:0.35"),
        ]
        
        for name, data in safe_investments:
            parts = data.split(":")
            term_days = int(parts[1])
            interest_rate = float(parts[2])
            expected_return = int(amount * (1 + interest_rate))
            profit = expected_return - amount
            
            builder.row(InlineKeyboardButton(
                text=f"{name} | +{profit:,} LUM", 
                callback_data=f"{data}:{amount}"
            ))
        
        text += "\n🎯 **Рискованные инвестиции:**\n"
        
        risky_investments = [
            ("🎯 14 дней, 70%", f"invest_risky:{INVESTMENT_TERM_DAYS}:0.7:0.35")
        ]
        
        for name, data in risky_investments:
            parts = data.split(":")
            term_days = int(parts[1])
            interest_rate = float(parts[2])
            risk = float(parts[3])
            expected_return = int(amount * (1 + interest_rate))
            profit = expected_return - amount
            
            builder.row(InlineKeyboardButton(
                text=f"{name} | +{profit:,} LUM", 
                callback_data=f"{data}:{amount}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="invest_start_new"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in handle_invest_amount: {e}")
        await callback.answer("❌ Ошибка при выборе суммы")

@rpg_router.callback_query(F.data.startswith("invest_"))
async def handle_investment_actions(callback: types.CallbackQuery, profile_manager):
    """Обработка всех инвестиционных действий"""
    try:
        user_id = callback.from_user.id
        data = callback.data
        
        if data == "invest_back":
            await show_investment(callback.message, profile_manager)
            return
            
        if data.startswith("invest_safe:") or data.startswith("invest_risky:"):
            parts = data.split(":")
            
            if data.startswith("invest_safe:"):
                term_days = int(parts[1])
                interest_rate = float(parts[2])
                amount = int(parts[3])
                risk = 0
                investment_type = "🛡️ Безопасная"
            else:
                term_days = int(parts[1])
                interest_rate = float(parts[2])
                risk = float(parts[3])
                amount = int(parts[4])
                investment_type = "🎯 Рискованная"
            
            # Финальная проверка перед инвестированием
            lumcoins = await get_user_lumcoins(profile_manager, user_id)
            if lumcoins < amount:
                await callback.answer(f"❌ Недостаточно LUM. Нужно {amount}")
                return
            
            # Проверка кулдауна
            active_investments = await get_user_active_investments(user_id)
            if len(active_investments) >= 5:
                await callback.answer("❌ Достигнут лимит: максимум 5 активных инвестиций")
                return
            
            expected_return = int(amount * (1 + interest_rate))
            profit = expected_return - amount
            
            quick_invest = quick_purchase_cache.get(user_id)
            if (quick_invest and 
                quick_invest['data'] == data and 
                time.time() - quick_invest['timestamp'] <= 10):
                
                # Списание средств
                success = await update_user_lumcoins(profile_manager, user_id, -amount)
                if not success:
                    await callback.answer("❌ Ошибка при списании")
                    return
                
                # Создание инвестиции в базе данных
                await add_investment(user_id, amount, term_days, interest_rate, risk)
                
                if risk > 0 and random.random() < risk:
                    await callback.answer(f"❌ Инвестиция провалилась! Потеряно {amount} LUM")
                else:
                    await callback.answer(f"✅ Инвестировано {amount:,} LUM на {term_days} дней!")
                
                del quick_purchase_cache[user_id]
                await show_investment(callback.message, profile_manager)
                
            else:
                quick_purchase_cache[user_id] = {
                    'data': data,
                    'timestamp': time.time()
                }
                
                # СОКРАЩЕННЫЙ ТЕКСТ ДЛЯ ИЗБЕЖАНИЯ ОШИБКИ
                info_text = (
                    f"{investment_type} инвестиция\n\n"
                    f"💰 Сумма: {amount:,} LUM\n"
                    f"📅 Срок: {term_days} дней\n"
                    f"📈 Доход: {expected_return:,} LUM\n"
                    f"💸 Прибыль: +{profit:,} LUM\n"
                )
                
                if risk > 0:
                    info_text += f"⚠️ Риск: {risk*100}%\n\n"
                else:
                    info_text += "\n"
                
                info_text += "✅ Нажмите ЕЩЁ РАЗ для подтверждения!"
                
                await callback.answer(info_text, show_alert=True)
                
        elif data == "invest_claim_all":
            await handle_invest_claim_all(callback, profile_manager)
            
    except Exception as e:
        logger.error(f"❌ Error in handle_investment_actions: {e}")
        await callback.answer("❌ Ошибка при инвестировании")

@rpg_router.callback_query(F.data == "invest_claim_all")
async def handle_invest_claim_all(callback: types.CallbackQuery, profile_manager):
    """Забрать все готовые инвестиции"""
    try:
        user_id = callback.from_user.id
        active_investments = await get_user_active_investments(user_id)
        history = await get_user_investment_history(user_id, limit=5)
        
        total_profit = 0
        claimed_count = 0
        failed_count = 0
        
        for investment in active_investments:
            days_passed = (time.time() - investment['invested_at']) / 86400
            if days_passed >= investment['term_days']:
                expected_return = int(investment['amount'] * (1 + investment['interest_rate']))
                profit = expected_return - investment['amount']
                
                if investment['risk'] > 0 and random.random() < investment['risk']:
                    # Провал
                    await ensure_db_initialized()
                    async with aiosqlite.connect('profiles.db') as conn:
                        await conn.execute('''
                            UPDATE user_investments SET status = 'failed' 
                            WHERE user_id = ? AND invested_at = ?
                        ''', (user_id, investment['invested_at']))
                        await conn.commit()
                    failed_count += 1
                else:
                    # Успех
                    success = await update_user_lumcoins(profile_manager, user_id, expected_return)
                    if success:
                        total_profit += profit
                        await ensure_db_initialized()
                        async with aiosqlite.connect('profiles.db') as conn:
                            await conn.execute('''
                                UPDATE user_investments SET status = 'completed' 
                                WHERE user_id = ? AND invested_at = ?
                            ''', (user_id, investment['invested_at']))
                            await conn.commit()
                        claimed_count += 1
        
        if claimed_count == 0 and failed_count == 0:
            await callback.answer("📭 Нет завершенных инвестиций")
        else:
            result_text = ""
            if claimed_count > 0:
                result_text += f"✅ Забрано {claimed_count} инвестиций\n"
                result_text += f"💸 Общая прибыль: +{total_profit:,} LUM\n"
            if failed_count > 0:
                result_text += f"❌ Провалилось {failed_count} инвестиций\n"
            
            await callback.answer(result_text)
        
        await show_investment(callback.message, profile_manager)
        
    except Exception as e:
        logger.error(f"❌ Error in handle_invest_claim_all: {e}")
        await callback.answer("❌ Ошибка при получении инвестиций")

@rpg_router.message(F.text.lower() == "мои инвестиции")
async def show_my_investments(message: types.Message, profile_manager):
    """Детальный просмотр инвестиций"""
    try:
        user_id = message.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        active_investments = await get_user_active_investments(user_id)
        
        builder = InlineKeyboardBuilder()
        text = f"💼 **Мои инвестиции** | 💰 Баланс: {lumcoins} LUM\n\n"
        
        if not active_investments:
            text += "📭 У вас нет активных инвестиций.\n\n"
            text += "💡 Используйте команду 'инвестировать' чтобы начать!"
        else:
            text += f"📊 **Активные инвестиции ({len(active_investments)}/5):**\n\n"
            
            for i, investment in enumerate(active_investments, 1):
                days_passed = (time.time() - investment['invested_at']) / 86400
                days_left = max(0, investment['term_days'] - days_passed)
                hours_left = int((days_left - int(days_left)) * 24)
                expected_return = int(investment['amount'] * (1 + investment['interest_rate']))
                profit = expected_return - investment['amount']
                
                # Прогресс-бар
                progress_percent = min(100, int((days_passed / investment['term_days']) * 100))
                progress_bar = "🟢" * (progress_percent // 20) + "⚪" * (5 - progress_percent // 20)
                
                text += f"**#{i}** | {progress_bar} {progress_percent}%\n"
                text += f"💰 **Сумма:** {investment['amount']:,} LUM\n"
                text += f"📅 **Срок:** {investment['term_days']} дней\n"
                text += f"📈 **Процент:** {investment['interest_rate']*100}%\n"
                text += f"💵 **Ожидаемый доход:** {expected_return:,} LUM\n"
                text += f"💸 **Прибыль:** +{profit:,} LUM\n"
                
                if days_left <= 0:
                    text += f"✅ **Готова к получению!**\n"
                else:
                    text += f"⏰ **Осталось:** {int(days_left)}д {hours_left}ч\n"
                
                if investment['risk'] > 0:
                    text += f"⚠️ **Риск:** {investment['risk']*100}%\n"
                
                text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"

            if history:
                text += "\n📚 **История инвестиций (последние 5):**\n"
                for inv in history:
                    status_emoji = "✅" if inv.get("status") == "completed" else "❌"
                    text += f"{status_emoji} {inv.get('amount', 0):,} LUM • {inv.get('term_days', INVESTMENT_TERM_DAYS)}д\n"
        
        builder.row(InlineKeyboardButton(
            text="💰 Инвестировать", 
            callback_data="invest_new"
        ))
        
        builder.row(InlineKeyboardButton(
            text="🔄 Обновить", 
            callback_data="my_investments_refresh"
        ))
        
        if any(inv['term_days'] <= (time.time() - inv['invested_at']) / 86400 for inv in active_investments):
            builder.row(InlineKeyboardButton(
                text="💸 Забрать все готовые", 
                callback_data="invest_claim_all"
            ))
        
        await message.answer(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in show_my_investments_detailed: {e}")
        await message.answer("❌ Ошибка при загрузке инвестиций")

@rpg_router.callback_query(F.data == "my_investments_refresh")
async def handle_my_investments_refresh(callback: types.CallbackQuery, profile_manager):
    """Обновить детальный список инвестиций"""
    await show_my_investments(callback.message, profile_manager)

@rpg_router.message(F.text.lower() == "продать")
async def show_sell_menu(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        user_inventory = await get_user_inventory_db(user_id)
        
        sellable_items = [item for item in user_inventory if item.get('type') != 'background' and item.get('quantity', 0) > 0]
        
        if not sellable_items:
            await message.answer("📭 У вас нет предметов для продажи.")
            return
        
        builder = InlineKeyboardBuilder()
        text = "💰 **Продажа предметов**\n\n"
        text += "Выберите предмет для продажи:\n\n"
        
        for item in sellable_items:
            item_key = item.get('item_key', 'unknown')
            item_name = item.get('name', 'Неизвестный предмет')
            quantity = item.get('quantity', 1)
            sell_price = ItemSystem.get_item_sell_price(item_key)
            
            builder.row(InlineKeyboardButton(
                text=f"{item_name} ×{quantity} - 💰{sell_price}",
                callback_data=f"sell_item_info:{item_key}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="sell_back_to_main"
        ))
        
        await message.answer(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in show_sell_menu: {e}")
        await message.answer("❌ Ошибка при открытии меню продажи")

@rpg_router.callback_query(F.data.startswith("sell_item_info:"))
async def handle_sell_item_info(callback: types.CallbackQuery, profile_manager):
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
        
        sell_price = ItemSystem.get_item_sell_price(item_key)
        
        quick_sell = quick_sell_cache.get(user_id)
        if (quick_sell and 
            quick_sell['item_key'] == item_key and 
            time.time() - quick_sell['timestamp'] <= 5):
            
            item_quantity = item_data.get('quantity', 0)
            
            if item_quantity <= 0:
                await callback.answer("❌ У вас нет этого предмета")
                return
            
            success = await remove_item_from_inventory(user_id, item_key, 1)
            if not success:
                await callback.answer("❌ Ошибка при удалении предмета")
                return
            
            success = await update_user_lumcoins(profile_manager, user_id, sell_price)
            if not success:
                await callback.answer("❌ Ошибка при начислении средств")
                return
            
            del quick_sell_cache[user_id]
            
            await callback.answer(f"✅ Продано: {item_info['name']} за {sell_price} LUM!")
            await show_sell_menu(callback.message, profile_manager)
            
        else:
            quick_sell_cache[user_id] = {
                'item_key': item_key,
                'timestamp': time.time()
            }
            
            info_text = f"💰 **Продажа предмета**\n\n"
            info_text += f"📦 {item_info['name']}\n"
            info_text += f"📖 {item_info.get('description', 'Описание отсутствует')}\n"
            
            if 'stats' in item_info:
                stats_text = ""
                for stat, value in item_info['stats'].items():
                    stats_text += f"   {stat}: +{value}\n"
                if stats_text:
                    info_text += f"📊 Характеристики:\n{stats_text}"
            
            info_text += f"💎 Цена продажи: {sell_price} LUM (50% от стоимости)\n\n"
            info_text += f"✅ Нажмите ЕЩЁ РАЗ для продажи!"
            
            await callback.answer(info_text, show_alert=True)
            
    except Exception as e:
        logger.error(f"❌ Error in handle_sell_item_info: {e}")
        await callback.answer("❌ Ошибка при продаже предмета")
