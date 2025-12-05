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

from .rpg_utils import ensure_db_initialized, quick_purchase_cache, shop_pages_cache, quick_sell_cache

logger = logging.getLogger(__name__)
rpg_router = Router(name="rpg_router")

# Состояния для FSM
class MarketStates(StatesGroup):
    waiting_for_price = State()

class AuctionStates(StatesGroup):
    waiting_for_price = State()

def setup_rpg_handlers(main_dp, bot_instance, profile_manager_instance, database_module):
    main_dp.include_router(rpg_router)
    logger.info("RPG router included.")

async def initialize_on_startup():
    await ensure_db_initialized()
    logger.info("✅ RPG system initialized")
