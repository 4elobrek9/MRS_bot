import logging
import json
import aiosqlite
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from .rpg_utils import ensure_db_initialized
from .item import ItemSystem

logger = logging.getLogger(__name__)

async def validate_item_for_market(item_key: str, item_data: dict) -> Tuple[bool, str]:
    """Validate if an item can be listed on the market"""
    try:
        # Check if item exists in either SHOP_ITEMS or CRAFTED_ITEMS
        if item_key not in ItemSystem.SHOP_ITEMS and item_key not in ItemSystem.CRAFTED_ITEMS:
            return False, "❌ Недопустимый предмет"

        # Get item info
        item_info = ItemSystem.SHOP_ITEMS.get(item_key) or ItemSystem.CRAFTED_ITEMS.get(item_key)
        
        # Verify item type
        if item_info.get('type') == 'background':
            return False, "❌ Фоны нельзя продавать на рынке"
            
        return True, ""
    except Exception as e:
        logger.error(f"❌ Error validating market item: {e}")
        return False, "❌ Ошибка при проверке предмета"

async def get_market_listings() -> List[dict]:
    """Get all active market listings"""
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute('''
                SELECT 
                    id, seller_id, item_key, item_data, price, created_at
                FROM market_listings
                ORDER BY created_at DESC
                LIMIT 10
            ''')
            rows = await cursor.fetchall()
            
            listings = []
            for row in rows:
                listing = {
                    'id': row[0],
                    'seller_id': row[1],
                    'item_key': row[2],
                    'item_data': json.loads(row[3]) if row[3] else {},
                    'price': row[4],
                    'created_at': row[5]
                }
                listings.append(listing)
            
            return listings
            
    except Exception as e:
        logger.error(f"❌ Error getting market listings: {e}")
        return []

async def add_market_listing(seller_id: int, item_key: str, item_data: dict, price: int) -> Tuple[bool, str]:
    """Add a new market listing"""
    try:
        # Validate item first
        valid, error_msg = await validate_item_for_market(item_key, item_data)
        if not valid:
            return False, error_msg
            
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            # Check if seller already has too many listings
            cursor = await conn.execute(
                'SELECT COUNT(*) FROM market_listings WHERE seller_id = ?', 
                (seller_id,)
            )
            count = (await cursor.fetchone())[0]
            if count >= 5:
                return False, "❌ У вас уже есть максимальное количество предметов на рынке (5)"
            
            # Add the listing
            await conn.execute('''
                INSERT INTO market_listings (seller_id, item_key, item_data, price)
                VALUES (?, ?, ?, ?)
            ''', (seller_id, item_key, json.dumps(item_data), price))
            await conn.commit()
            return True, "✅ Предмет успешно выставлен на рынок"
            
    except Exception as e:
        logger.error(f"❌ Error adding market listing: {e}")
        return False, "❌ Произошла ошибка при добавлении предмета на рынок"

async def remove_market_listing(listing_id: int, seller_id: Optional[int] = None) -> Tuple[bool, str]:
    """Remove a market listing. If seller_id is provided, verify ownership."""
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            # If seller_id provided, verify ownership
            if seller_id is not None:
                cursor = await conn.execute(
                    'SELECT seller_id FROM market_listings WHERE id = ?',
                    (listing_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    return False, "❌ Предмет не найден"
                if row[0] != seller_id:
                    return False, "❌ Это не ваш предмет"
            
            await conn.execute('DELETE FROM market_listings WHERE id = ?', (listing_id,))
            await conn.commit()
            return True, "✅ Предмет успешно удален с рынка"
            
    except Exception as e:
        logger.error(f"❌ Error removing market listing: {e}")
        return False, "❌ Произошла ошибка при удалении предмета с рынка"

async def get_listing(listing_id: int) -> Optional[Dict]:
    """Get a specific market listing by ID"""
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute('''
                SELECT id, seller_id, item_key, item_data, price, created_at
                FROM market_listings 
                WHERE id = ?
            ''', (listing_id,))
            row = await cursor.fetchone()
            
            if not row:
                return None
                
            return {
                'id': row[0],
                'seller_id': row[1],
                'item_key': row[2],
                'item_data': json.loads(row[3]) if row[3] else {},
                'price': row[4],
                'created_at': row[5]
            }
            
    except Exception as e:
        logger.error(f"❌ Error getting market listing: {e}")
        return None

async def get_seller_listings(seller_id: int) -> List[Dict]:
    """Get all market listings for a specific seller"""
    try:
        await ensure_db_initialized()
        
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute('''
                SELECT id, seller_id, item_key, item_data, price, created_at
                FROM market_listings 
                WHERE seller_id = ?
                ORDER BY created_at DESC
            ''', (seller_id,))
            rows = await cursor.fetchall()
            
            listings = []
            for row in rows:
                listing = {
                    'id': row[0],
                    'seller_id': row[1],
                    'item_key': row[2],
                    'item_data': json.loads(row[3]) if row[3] else {},
                    'price': row[4],
                    'created_at': row[5]
                }
                listings.append(listing)
            
            return listings
            
    except Exception as e:
        logger.error(f"❌ Error getting seller listings: {e}")
        return []