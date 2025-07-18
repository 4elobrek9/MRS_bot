import os
import aiosqlite
import string
import sqlite3
import time
from datetime import datetime, date, timedelta
from io import BytesIO
from typing import Optional, Dict, Any, List, Tuple
from aiogram import Dispatcher, types, Bot, Router, F
from aiogram.filters import Command
import logging
logger = logging.getLogger(__name__)
from PIL import Image, ImageDraw, ImageFont, ImageOps
import random
import aiohttp
from aiogram.types import BufferedInputFile

from database import get_user_rp_stats, ensure_user_exists, get_user_profile_info
