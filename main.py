import asyncio
import logging
import os
from pathlib import Path
from typing import Callable, Awaitable, Dict, Any
from aiogram import Dispatcher, F, Router, Bot, types
from aiogram.fsm.strategy import FSMStrategy
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand

# --- Основные импорты из CORE ---
from core.main.ez_main import *
from core.main.ollama import *
from core.main.command import *
from core.main.dec_command import *
from core.main.watermark import apply_watermark
from mistral_group_chat import MistralGroupHandler
from core.group.group_settings_handler import settings_router

# --- Импорты модулей из CORE ---
from core.group.stat.manager import ProfileManager
from core.group.promo import setup_promo_handlers, handle_promo_command
from core.group.casino import setup_casino_handlers, casino_main_menu
from core.group.stat.plum_shop_handlers import cmd_plum_shop
from core.group.stat.quests_handlers import cmd_show_quests
from core.group.RPG import (
    setup_rpg_handlers,
    initialize_on_startup,
    show_inventory,
    show_workbench_cmd,
    show_shop_main,
    start_trade,
    show_auction,
    show_market,
    show_investment,
    show_my_investments
)
from group_RPG import show_inventoryF
from core.group.RPG.investment import show_sell_menu
from core.group.RP.actions import RPActions
from core.group.stat.quests_handlers import (
    ensure_quests_db,
    update_message_quests,
    update_casino_quests,
    update_work_quests,
    update_exp_quests,
    update_market_quests,
    update_rp_quests,
    update_crafting_quests,
    update_activity_quests
)

# --- Импорты из КОРНЯ проекта ---
from group_stat import (
    show_profile,
    do_work,
    show_shop,
    show_top,
    heal_hp,
    give_lumcoins,
    check_transfer_status,
    setup_stat_handlers,
    show_online_admins
)
from rp_module_refactored import (
    cmd_check_self_hp,
    cmd_show_rp_actions_list,
    handle_rp_action_via_text,
    setup_rp_handlers
)
from command import cmd_help
import database as db
from core.main.jokes_manager import JokesManager

logger = logging.getLogger(__name__)

# --- Константы ---
STICKERS_CACHE_FILE = Path("data") / "stickers_cache.json"

dp = Dispatcher(fsm_strategy=FSMStrategy.USER_IN_CHAT)

async def migrate_inventory_table():
    try:
        import aiosqlite
        async with aiosqlite.connect('profiles.db') as conn:
            cursor = await conn.execute("PRAGMA table_info(user_inventory)")
            columns = await cursor.fetchall()
            column_names = [column[1] for column in columns]

            if 'quantity' not in column_names:
                logger.info("Добавляем столбец quantity")

                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_inventory_new (
                        user_id INTEGER,
                        item_key TEXT,
                        item_type TEXT,
                        quantity INTEGER DEFAULT1,
                        item_data TEXT,
                        acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, item_key)
                    )
                ''')

                await conn.execute('''
                    INSERT INTO user_inventory_new (user_id, item_key, item_type, quantity, item_data, acquired_at)
                    SELECT user_id, item_key, item_type, 1, item_data, acquired_at
                    FROM user_inventory
                ''')

                await conn.execute('DROP TABLE user_inventory')
                await conn.execute('ALTER TABLE user_inventory_new RENAME TO user_inventory')

                await conn.commit()
                logger.info("✅ Миграция завершена")
            else:
                logger.info("✅ Таблица уже имеет quantity")

    except Exception as e:
        logger.error(f"❌ Ошибка миграции: {e}")

async def main():
    logger.info("Запуск бота.")

    profile_manager = ProfileManager()
    try:
        await profile_manager.connect()
        logger.info("ProfileManager подключен.")
    except Exception as e:
        logger.critical(f"Не удалось подключить ProfileManager: {e}")
        exit(1)

    logger.info("Инициализация БД.")
    await db.initialize_database()
    await db.create_promo_table()
    await db.create_group_settings_table() # ❗ NEW: Добавьте вызов создания таблицы

    logger.info("Проверка миграции...")
    await migrate_inventory_table()

    logger.info("Инициализация системы заданий...")
    try:
        await ensure_quests_db()
        logger.info("✅ Система заданий инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации заданий: {e}")

    logger.info("Инициализация RPG...")
    try:
        await initialize_on_startup()
        logger.info("✅ RPG система инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка RPG: {e}")

    logger.info("Инициализация стикеров.")
    sticker_manager_instance = StickerManager(cache_file_path=STICKERS_CACHE_FILE)
    await sticker_manager_instance.fetch_stickers(bot)

    # Инициализация менеджера анекдотов
    jokes_manager = JokesManager()

    logger.info("Передача зависимостей.")
    dp["profile_manager"] = profile_manager
    dp["sticker_manager"] = sticker_manager_instance
    dp["bot_instance"] = bot

    # Регистрация роутера настроек
    dp.include_router(settings_router) # NEW: Регистрация роутера настроек

    # Регистрация всех специализированных роутеров для команд
    setup_stat_handlers(dp, profile_manager, db, sticker_manager_instance, jokes_manager, bot)
    setup_rpg_handlers(dp, bot, profile_manager, db)
    setup_promo_handlers(dp, profile_manager, db)
    setup_casino_handlers(dp, profile_manager)
    setup_rp_handlers(dp, bot, profile_manager, db)

    # Инициализация Mistral Group Handler
    MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
    mistral_task = None
    mistral_handler = None

    if MISTRAL_API_KEY:
        logger.info("🔑 Mistral API Key найден, инициализирую Mistral Group Handler...")
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username

            mistral_handler = MistralGroupHandler(bot, MISTRAL_API_KEY, bot_username)
            dp["mistral_handler"] = mistral_handler

            # Запуск фоновой задачи для вопросов (12:00-00:00, раз в час)
            mistral_task = asyncio.create_task(mistral_handler.periodic_question_task())

            # Регистрация LLM хендлера для всех сообщений в группах/супергруппах
            dp.message.register(
                mistral_handler.handle_all_group_messages,
                F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})
            )
            logger.info("Mistral Group Chat LLM feature ENABLED.")
        except Exception as e:
            logger.warning("Mistral Group Chat LLM feature DISABLED (MISTRAL_API_KEY or bot_username missing).")
    else:
        logger.warning("⚠️ MISTRAL_API_KEY не найден.")

    # Регистрация команд с Telegram
    commands = [
        BotCommand(command="start", description="🚀 Начать работу с ботом"),
        BotCommand(command="help", description="❓ Показать полную справку и список команд"),

        BotCommand(command="mode", description="💬 Сменить режим общения (доступно только в ЛС)"),

        # RPG / Экономика
        BotCommand(command="profile", description="👤 Ваш игровой профиль (также 'профиль')"),
        BotCommand(command="inventory", description="🎒 Инвентарь и фоны (также 'инвентарь')"),
        BotCommand(command="work", description="💰 Выполнить работу (также 'работать')"),
        BotCommand(command="top", description="🏆 Топ игроков по уровню (также 'топ')"),
        BotCommand(command="shop", description="🛒 Магазин предметов (также 'магазин')"),
        BotCommand(command="pshop", description="💎 Магазин за PLUM-коины (также 'пмагазин')"),
        BotCommand(command="quests", description="🗓️ Ежедневные/еженедельные задания (также 'задания')"),

        # Экономические взаимодействия
        BotCommand(command="give", description="💸 Перевести Lumcoins пользователю (/give 100 @user)"),
        BotCommand(command="invest", description="📈 Инвестировать LUM под проценты (также 'инвестировать')"),
        BotCommand(command="auction", description="🔨 Показать активные аукционы (также 'аукцион')"),
        BotCommand(command="market", description="🏷️ Рынок для торговли с игроками (также 'рынок')"),

        # RP / Здоровье
        BotCommand(command="myhp", description="❤️ Проверить здоровье (также 'мое здоровье')"),
        BotCommand(command="heal", description="💊 Использовать аптечку (также 'лечить')"),
        BotCommand(command="rpactions", description="⚔️ Список доступных RP действий (также 'рп действия')"),

        # Разное
        BotCommand(command="joke", description="🤣 Случайный анекдот (также 'анекдот')"),
        BotCommand(command="stats", description="📊 Статистика использования бота (также 'статистика')"),
        BotCommand(command="dop_func", description="⚙️ Настройки и доп. функции группы (только для админов)"), # NEW COMMAND
    ]

    await bot.set_my_commands(commands)

    logger.info("Запуск поллинга...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.critical(f"Ошибка поллинга: {e}")
    finally:
        logger.info("Остановка бота...")

        # Отмена всех фоновых задач, включая Mistral
        # tasks_to_cancel = [jokes_bg_task, rp_recovery_bg_task, daily_reset_task, mistral_task]
        # tasks_to_cancel = [t for t in tasks_to_cancel if t is not None]

        # for task in tasks_to_cancel:
        #     task.cancel()

        await profile_manager.close()
        logger.info("ProfileManager закрыт.")

        await bot.session.close()
        logger.info("Сессия бота закрыта.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную.")
    except Exception as e:
        logger.critical(f"Необработанное исключение: {e}")