import asyncio
import time
import random
import logging
from typing import Dict, Any, Optional, List, Tuple, Set
import aiosqlite
from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType, ParseMode, MessageEntityType
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from contextlib import suppress
import database as db

try:
    from group_stat import ProfileManager as RealProfileManager
    HAS_PROFILE_MANAGER = True
except ImportError:
    logging.critical("CRITICAL: Module 'group_stat' or 'ProfileManager' not found. RP functionality will be severely impaired or non-functional.")
    HAS_PROFILE_MANAGER = False
    class RealProfileManager:
        async def get_user_rp_stats(self, user_id: int) -> Dict[str, Any]:
            return {'hp': 100, 'recovery_end_ts': 0.0, 'heal_cooldown_ts': 0.0}
        async def update_user_rp_stats(self, user_id: int, **kwargs: Any) -> None:
            pass
        async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
            return None
        async def connect(self) -> None:
            pass
        async def close(self) -> None:
            pass

ProfileManager = RealProfileManager

logger = logging.getLogger(__name__)
