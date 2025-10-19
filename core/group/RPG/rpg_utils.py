import aiosqlite  # Добавь этот импорт
import logging
from typing import Dict, List
import time
import json

logger = logging.getLogger(__name__)

# Глобальные переменные для кэшей
quick_purchase_cache = {}
shop_pages_cache = {}
quick_sell_cache = {}
trade_sessions = {}
auction_listings = {}
user_investments = {}
investment_amounts = {}

async def ensure_db_initialized():
    """Инициализация БД для RPG системы"""
    try:
        async with aiosqlite.connect('profiles.db') as conn:
            # Таблица инвентаря
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
            
            # Таблица активных фонов
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_active_background (
                    user_id INTEGER PRIMARY KEY,
                    bg_key TEXT DEFAULT 'default'
                )
            ''')
            
            # Таблица аукциона
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
            
            # Таблица рынка
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
            
            # Таблица инвестиций
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

# Глобальные переменные для кэшей
quick_purchase_cache = {}
shop_pages_cache = {}
quick_sell_cache = {}
trade_sessions = {}
auction_listings = {}
user_investments = {}
investment_amounts = {}