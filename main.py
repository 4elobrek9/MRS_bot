import asyncio
import logging
from pathlib import Path
from aiogram import Dispatcher, F, Router, Bot
from aiogram.fsm.strategy import FSMStrategy
from aiogram.enums import ChatType
from aiogram.filters import Command

# --- Основные импорты из CORE ---
from core.main.ez_main import *
from core.main.ollama import *
from core.main.command import *
from core.main.dec_command import *

# --- Импорты модулей из CORE ---
from core.group.stat.manager import ProfileManager
from core.group.promo import setup_promo_handlers, handle_promo_command
from core.group.casino import setup_casino_handlers, casino_main_menu
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
from core.group.RPG.investment import show_sell_menu
from core.group.RP.actions import RPActions

# --- Импорты из КОРНЯ проекта ---
from group_stat import (
    show_profile, 
    do_work, 
    show_shop, # Это магазин ФОНОВ (из group_stat.py)
    show_top, 
    manage_censor, 
    heal_hp,
    give_lumcoins,
    check_transfer_status,
    setup_stat_handlers # Важно для регистрации кнопок
)
from rp_module_refactored import (
    cmd_check_self_hp, 
    cmd_show_rp_actions_list, 
    handle_rp_action_via_text,
    setup_rp_handlers
)
from command import cmd_help
import database as db

# --- Импорты УТИЛИТ из CORE (Исправленные пути) ---
from censor_module import * # <<< ИСПРАВЛЕН ПУТЬ
# from core.utils.stickers import StickerManager
# from core.utils.jokes import jokes_task
# from core.group.RP.recovery import periodic_hp_recovery_task
# from core.group.stat.daily_reset import reset_daily_stats_task, migrate_existing_users_exp

# <<< ДОБАВЛЕНО: Импорт для П-Магазина
from core.group.stat.plum_shop_handlers import cmd_plum_shop, plum_shop_router


logger = logging.getLogger(__name__)

# --- Константы ---
BAD_WORDS_FILE = Path("data") / "bad_words.txt"
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
                        quantity INTEGER DEFAULT 1,
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

    logger.info("Проверка миграции...")
    await migrate_inventory_table()

    logger.info("Инициализация RPG...")
    try:
        await initialize_on_startup()
        logger.info("✅ RPG система инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка RPG: {e}")

    logger.info("Инициализация стикеров.")
    sticker_manager_instance = StickerManager(cache_file_path=STICKERS_CACHE_FILE)
    await sticker_manager_instance.fetch_stickers(bot)

    logger.info("Передача зависимостей.")
    dp["profile_manager"] = profile_manager
    dp["sticker_manager"] = sticker_manager_instance
    dp["bot_instance"] = bot

    direct_dispatch_handlers = {
        "профиль": (show_profile, ["message", "profile_manager", "bot"]),
        "работать": (do_work, ["message", "profile_manager"]),
        "топ": (show_top, ["message", "profile_manager"]),
        "помощь": (cmd_help, ["message"]),
        "help": (cmd_help, ["message"]),
        "команды": (cmd_help, ["message"]),
        "лечить": (heal_hp, ["message", "profile_manager"]),
        "моё хп": (cmd_check_self_hp, ["message", "bot", "profile_manager"]),
        "мое хп": (cmd_check_self_hp, ["message", "bot", "profile_manager"]),
        "моё здоровье": (cmd_check_self_hp, ["message", "bot", "profile_manager"]),
        "мое здоровье": (cmd_check_self_hp, ["message", "bot", "profile_manager"]),
        "хп": (cmd_check_self_hp, ["message", "bot", "profile_manager"]),
        "здоровье": (cmd_check_self_hp, ["message", "bot", "profile_manager"]),
        "список действий": (cmd_show_rp_actions_list, ["message", "bot"]),
        "рп действия": (cmd_show_rp_actions_list, ["message", "bot"]),
        "список рп": (cmd_show_rp_actions_list, ["message", "bot"]),
        "команды рп": (cmd_show_rp_actions_list, ["message", "bot"]),
        "цензура": (manage_censor, ["message", "bot"]),
        "промо": (handle_promo_command, ["message", "bot", "profile_manager"]),
        "promo": (handle_promo_command, ["message", "bot", "profile_manager"]),
        "дать": (give_lumcoins, ["message", "profile_manager"]),
        "передать": (give_lumcoins, ["message", "profile_manager"]),
        "перевод": (check_transfer_status, ["message"]),
        "трансфер": (check_transfer_status, ["message"]),
        "казино": (casino_main_menu, ["message", "profile_manager"]),
        "инвентарь": (show_inventory, ["message", "profile_manager"]),
        "верстак": (show_workbench_cmd, ["message", "profile_manager"]), 
        "магазин": (show_shop, ["message", "profile_manager"]), # Магазин ФОНОВ
        "продать": (show_sell_menu, ["message", "profile_manager"]),
        "обмен": (start_trade, ["message", "profile_manager"]),
        "аукцион": (show_auction, ["message", "profile_manager"]),
        "рынок": (show_market, ["message", "profile_manager"]),
        "инвестировать": (show_investment, ["message", "profile_manager"]),
        "мои инвестиции": (show_my_investments, ["message", "profile_manager"]),
        
        # <<< ДОБАВЛЕНО: Обработка П-Магазина
        "пмагазин": (cmd_plum_shop, ["message", "profile_manager"]),
        "pshop": (cmd_plum_shop, ["message", "profile_manager"]),
    }

    for action in RPActions.SORTED_COMMANDS_FOR_PARSING:
        if action not in direct_dispatch_handlers:
            direct_dispatch_handlers[action] = (handle_rp_action_via_text, ["message", "bot", "profile_manager"])

    non_slash_commands_to_exclude = list(direct_dispatch_handlers.keys())
    # <<< ИЗМЕНЕНИЕ: Добавляем "магазин", "пмагазин", "pshop" в исключения цензуры
    non_slash_commands_to_exclude.extend(["магазин", "пмагазин", "pshop"])
    non_slash_commands_to_exclude.sort(key=len, reverse=True)

    logger.info("Настройка цензуры.")
    censor_module = censor_message_handler() # <<< ИСПРАВЛЕН ПУТЬ (импорт)
    censor_module.setup_censor_handlers(
        main_dp=dp,
        bad_words_file_path=BAD_WORDS_FILE,
        non_slash_command_prefixes=non_slash_commands_to_exclude,
        direct_dispatch_handlers=direct_dispatch_handlers,
        profile_manager_instance=profile_manager,
        bot_instance=bot
    )
    logger.info("Цензура интегрирована.")

    group_text_router = Router(name="group_text_router")
    group_text_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
    logger.info("Создан групповой роутер.")

    logger.info("Включение stat_router.")
    setup_stat_handlers(main_dp=group_text_router) # Эта функция из group_stat.py

    # <<< ДОБАВЛЕНО: Регистрация роутера кнопок П-Магазина
    group_text_router.include_router(plum_shop_router)

    logger.info("Включение RPG handlers.")
    setup_rpg_handlers(main_dp=group_text_router) # Эта функция из core/group/RPG/MAINrpg.py

    logger.info("Включение rp_router.")
    setup_rp_handlers( # Эта функция из rp_module_refactored.py
        main_dp=group_text_router,
        bot_instance=bot,
        profile_manager_instance=profile_manager,
        database_module=db
    )

    logger.info("Настройка казино.")
    setup_casino_handlers(main_dp=group_text_router, profile_manager=profile_manager)

    dp.include_router(group_text_router)
    logger.info("group_text_router интегрирован.")

    private_router = Router(name="private_router")
    private_router.message.filter(F.chat.type == ChatType.PRIVATE)
    logger.info("Создан приватный роутер.")

    logger.info("Регистрация команд для ЛС.")
    private_router.message(Command("start"))(cmd_start)
    private_router.message(Command("mode"))(cmd_mode)
    private_router.message(Command("stats"))(cmd_stats)
    private_router.message(Command("joke"))(cmd_joke)
    private_router.message(Command("check_value"))(cmd_check_value)
    private_router.message(Command("subscribe_value", "val"))(cmd_subscribe_value)
    private_router.message(Command("unsubscribe_value", "sval"))(cmd_unsubscribe_value)
    private_router.message(Command("help"))(cmd_help)
    private_router.message(F.photo)(photo_handler)
    private_router.message(F.voice)(voice_handler_msg)
    private_router.message(F.text)(handle_text_message)
    logger.info("Обработчики ЛС зарегистрированы.")

    logger.info("Настройка промокодов.")
    setup_promo_handlers(
        main_dp=dp,
        bot_instance=bot,
        profile_manager_instance=profile_manager
    )

    dp.include_router(private_router)
    logger.info("private_router интегрирован.")

    logger.info("Запуск фоновых задач.")
    jokes_bg_task = asyncio.create_task(jokes_task(bot))
    rp_recovery_bg_task = asyncio.create_task(periodic_hp_recovery_task(bot, profile_manager, db))
    daily_reset_task = asyncio.create_task(reset_daily_stats_task(profile_manager))
    await migrate_existing_users_exp()

    logger.info("Запуск поллинга...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.critical(f"Ошибка поллинга: {e}")
    finally:
        logger.info("Остановка бота...")
        jokes_bg_task.cancel()
        rp_recovery_bg_task.cancel()
        daily_reset_task.cancel()
        try:
            await asyncio.gather(jokes_bg_task, rp_recovery_bg_task, daily_reset_task, return_exceptions=True)
            logger.info("Фоновые задачи отменены.")
        except asyncio.CancelledError:
            logger.info("Фоновые задачи отменены.")
        
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