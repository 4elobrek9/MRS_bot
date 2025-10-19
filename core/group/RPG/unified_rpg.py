# unified_rpg.py
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
from core.group.stat.shop_config import ShopConfig
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)
rpg_router = Router(name="rpg_router")

quick_purchase_cache = {}
shop_pages_cache = {}
quick_sell_cache = {}
trade_sessions = {}
auction_listings = {}
market_listings = {}
user_investments = {}
investment_amounts = {}

db_initialized = False
db_lock = asyncio.Lock()

# Состояния для FSM
class MarketStates(StatesGroup):
    waiting_for_price = State()

class AuctionStates(StatesGroup):
    waiting_for_price = State()

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
        "iron_ingot": {
            "name": "🔩 Железный слиток", 
            "result": "iron_ingot", 
            "result_name": "🔩 Железный слиток", 
            "cost": 25, 
            "materials": {"iron_ore": 3}, 
            "description": "Выплавленный железный слиток"
        },
        "basic_sword": {
            "name": "⚔️ Обычный меч", 
            "result": "basic_sword", 
            "result_name": "⚔️ Обычный меч", 
            "cost": 50, 
            "materials": {"wood": 2, "iron_ingot": 1}, 
            "description": "Надёжный железный меч", 
            "stats": {"attack": 5}
        },
        "advanced_potion": {
            "name": "🧪 Улучшенное зелье", 
            "result": "advanced_potion", 
            "result_name": "🧪 Улучшенное зелье здоровья", 
            "cost": 100, 
            "materials": {"health_potion": 2, "magic_crystal": 1}, 
            "description": "Восстанавливает 60 HP", 
            "effect": {"heal": 60}
        }
    }

    CRAFTED_ITEMS = {
        "iron_ingot": {"name": "🔩 Железный слиток", "type": "material", "rarity": "uncommon", "description": "Выплавленный железный слиток"},
        "basic_sword": {"name": "⚔️ Обычный меч", "type": "equipment", "rarity": "uncommon", "description": "Надёжный железный меч", "stats": {"attack": 5}},
        "advanced_potion": {"name": "🧪 Улучшенное зелье здоровья", "type": "consumable", "rarity": "rare", "description": "Восстанавливает 60 HP", "effect": {"heal": 60}}
    }

    @classmethod
    def get_sorted_shop_items(cls) -> List[tuple]:
        return sorted(cls.SHOP_ITEMS.items(), key=lambda x: x[1]['cost'])

    @classmethod
    def get_item_sell_price(cls, item_key: str) -> int:
        if item_key in cls.SHOP_ITEMS:
            return max(1, cls.SHOP_ITEMS[item_key]['cost'] // 2)
        elif item_key in cls.CRAFTED_ITEMS:
            base_prices = {
                "iron_ingot": 12,
                "basic_sword": 25,
                "advanced_potion": 50
            }
            return base_prices.get(item_key, 10)
        else:
            return 5

async def ensure_db_initialized():
    global db_initialized
    async with db_lock:
        if not db_initialized:
            await init_inventory_db()
            db_initialized = True

async def init_inventory_db():
    try:
        async with aiosqlite.connect('profiles.db') as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_inventory (
                    user_id INTEGER,
                    item_key TEXT,
                    item_type TEXT,
                    quantity INTEGER DEFAULT 1,
                    item_data TEXT,
                    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, item_key)
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_active_background (
                    user_id INTEGER PRIMARY KEY,
                    bg_key TEXT DEFAULT 'default'
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS auction_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER,
                    item_key TEXT,
                    item_data TEXT,
                    start_price INTEGER,
                    current_bid INTEGER,
                    current_bidder_id INTEGER,
                    end_time TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS market_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER,
                    item_key TEXT,
                    item_data TEXT,
                    price INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_investments (
                    user_id INTEGER,
                    amount INTEGER,
                    term_days INTEGER,
                    interest_rate REAL,
                    risk REAL DEFAULT 0,
                    invested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    PRIMARY KEY (user_id, invested_at)
                )
            ''')
            
            await conn.commit()
            logger.info("✅ RPG DB initialized")
    except Exception as e:
        logger.error(f"❌ RPG DB init error: {e}")

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

# Обработчик команды "цена" для установки цены
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
        
        await message.answer(text, reply_markup=builder.as_markup())
        
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

@rpg_router.message(F.text.lower() == "инвестировать")
async def show_investment(message: types.Message, profile_manager):
    try:
        user_id = message.from_user.id
        lumcoins = await get_user_lumcoins(profile_manager, user_id)
        
        active_investments = await get_user_active_investments(user_id)
        
        builder = InlineKeyboardBuilder()
        text = f"💼 **Инвестиции** | 💰 Баланс: {lumcoins} LUM\n\n"
        
        if active_investments:
            text += "📊 **Активные инвестиции:**\n\n"
            for investment in active_investments:
                days_passed = (time.time() - investment['invested_at']) / 86400
                days_left = max(0, investment['term_days'] - days_passed)
                expected_return = int(investment['amount'] * (1 + investment['interest_rate']))
                profit = expected_return - investment['amount']
                
                text += f"💰 Инвестировано: {investment['amount']} LUM\n"
                text += f"📅 Срок: {investment['term_days']} дней\n"
                text += f"📈 Ожидаемый доход: {expected_return} LUM\n"
                text += f"💸 Прибыль: +{profit} LUM\n"
                text += f"⏰ Осталось: {int(days_left)} дней\n\n"
        else:
            text += "💡 **Инвестируйте LUM под проценты!**\n\n"
            text += "🔒 **Безопасные инвестиции:**\n"
            text += "• 7 дней - 15% прибыли\n"
            text += "• 30 дней - 50% прибыли\n\n"
            text += "🎯 **Рискованные инвестиции:**\n" 
            text += "• 3 дня - 30% прибыли (риск 20%)\n"
            text += "• 14 дней - 80% прибыли (риск 40%)\n\n"
            text += "💸 **Выберите сумму инвестиции:**\n\n"
        
        builder.row(InlineKeyboardButton(
            text="💰 1,000 LUM", 
            callback_data="invest_amount:1000"
        ))
        
        builder.row(InlineKeyboardButton(
            text="💰 5,000 LUM", 
            callback_data="invest_amount:5000"
        ))
        
        builder.row(InlineKeyboardButton(
            text="💰 10,000 LUM", 
            callback_data="invest_amount:10000"
        ))
        
        builder.row(InlineKeyboardButton(
            text="💰 50,000 LUM", 
            callback_data="invest_amount:50000"
        ))
        
        if active_investments:
            builder.row(InlineKeyboardButton(
                text="💰 Забрать доход", 
                callback_data="invest_claim"
            ))
        
        await message.answer(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in show_investment: {e}")
        await message.answer("❌ Ошибка при загрузке инвестиций")

@rpg_router.callback_query(F.data.startswith("invest_amount:"))
async def handle_invest_amount(callback: types.CallbackQuery, profile_manager):
    try:
        user_id = callback.from_user.id
        amount = int(callback.data.split(":")[1])
        
        investment_amounts[user_id] = amount
        
        builder = InlineKeyboardBuilder()
        text = f"💼 **Выбор инвестиции** | 💰 Сумма: {amount} LUM\n\n"
        text += "🔒 **Безопасные инвестиции:**\n"
        
        safe_investments = [
            ("🛡️ 7 дней, 15%", "invest_safe:7:0.15"),
            ("🛡️ 30 дней, 50%", "invest_safe:30:0.5")
        ]
        
        for name, data in safe_investments:
            parts = data.split(":")
            term_days = int(parts[1])
            interest_rate = float(parts[2])
            expected_return = int(amount * (1 + interest_rate))
            profit = expected_return - amount
            
            builder.row(InlineKeyboardButton(
                text=f"{name} | +{profit} LUM", 
                callback_data=f"{data}:{amount}"
            ))
        
        text += "\n🎯 **Рискованные инвестиции:**\n"
        
        risky_investments = [
            ("🎯 3 дня, 30%", "invest_risky:3:0.3:0.2"),
            ("🎯 14 дней, 80%", "invest_risky:14:0.8:0.4")
        ]
        
        for name, data in risky_investments:
            parts = data.split(":")
            term_days = int(parts[1])
            interest_rate = float(parts[2])
            risk = float(parts[3])
            expected_return = int(amount * (1 + interest_rate))
            profit = expected_return - amount
            
            builder.row(InlineKeyboardButton(
                text=f"{name} | +{profit} LUM", 
                callback_data=f"{data}:{amount}"
            ))
        
        builder.row(InlineKeyboardButton(
            text="↩️ Назад", 
            callback_data="invest_back"
        ))
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        logger.error(f"❌ Error in handle_invest_amount: {e}")
        await callback.answer("❌ Ошибка при выборе суммы")

@rpg_router.callback_query(F.data.startswith("invest_"))
async def handle_investment_actions(callback: types.CallbackQuery, profile_manager):
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
            
            expected_return = int(amount * (1 + interest_rate))
            profit = expected_return - amount
            daily_profit = profit / term_days
            
            quick_invest = quick_purchase_cache.get(user_id)
            if (quick_invest and 
                quick_invest['data'] == data and 
                time.time() - quick_invest['timestamp'] <= 10):
                
                lumcoins = await get_user_lumcoins(profile_manager, user_id)
                
                if lumcoins < amount:
                    await callback.answer(f"❌ Недостаточно LUM. Нужно {amount}")
                    return
                
                success = await update_user_lumcoins(profile_manager, user_id, -amount)
                if not success:
                    await callback.answer("❌ Ошибка при списании")
                    return
                
                await add_investment(user_id, amount, term_days, interest_rate, risk)
                
                if risk > 0 and random.random() < risk:
                    await callback.answer(f"❌ Инвестиция провалилась! Потеряно {amount} LUM")
                else:
                    await callback.answer(f"✅ Инвестировано {amount} LUM на {term_days} дней!")
                
                del quick_purchase_cache[user_id]
                await show_investment(callback.message, profile_manager)
                
            else:
                quick_purchase_cache[user_id] = {
                    'data': data,
                    'timestamp': time.time()
                }
                
                info_text = (
                    f"{investment_type} инвестиция\n\n"
                    f"💰 Сумма: {amount} LUM\n"
                    f"📅 Срок: {term_days} дней\n"
                    f"📈 Процент: {interest_rate*100}%\n"
                    f"💵 Ожидаемый доход: {expected_return} LUM\n"
                    f"💸 Прибыль: +{profit} LUM\n"
                    f"📊 Ежедневная прибыль: ~{int(daily_profit)} LUM/день\n"
                )
                
                if risk > 0:
                    info_text += f"⚠️ Риск потери: {risk*100}%\n\n"
                else:
                    info_text += "\n"
                
                info_text += "✅ Нажмите ЕЩЁ РАЗ для подтверждения инвестиции!"
                
                await callback.answer(info_text, show_alert=True)
                
        elif data == "invest_claim":
            active_investments = await get_user_active_investments(user_id)
            total_profit = 0
            
            for investment in active_investments:
                days_passed = (time.time() - investment['invested_at']) / 86400
                if days_passed >= investment['term_days']:
                    expected_return = int(investment['amount'] * (1 + investment['interest_rate']))
                    profit = expected_return - investment['amount']
                    
                    if investment['risk'] > 0 and random.random() < investment['risk']:
                        await callback.answer(f"❌ Инвестиция провалилась! Потеряно {investment['amount']} LUM")
                    else:
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
            
            if total_profit > 0:
                await callback.answer(f"✅ Получено {total_profit} LUM прибыли!")
            else:
                await callback.answer("📭 Нет завершенных инвестиций")
                
            await show_investment(callback.message, profile_manager)
            
    except Exception as e:
        logger.error(f"❌ Error in handle_investment_actions: {e}")
        await callback.answer("❌ Ошибка при инвестировании")

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

def setup_rpg_handlers(main_dp: Router):
    main_dp.include_router(rpg_router)
    logger.info("RPG router included.")

async def initialize_on_startup():
    await ensure_db_initialized()
    logger.info("✅ RPG system initialized")