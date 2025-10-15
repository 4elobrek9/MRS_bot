from core.main.ez_main import *
from core.main.ollama import *
from core.main.command import *
from core.main.dec_command import *
from core.group.stat.manager import ProfileManager
from aiogram.fsm.strategy import FSMStrategy
from core.group.promo import setup_promo_handlers, handle_promo_command
from core.group.casino import setup_casino_handlers, casino_main_menu
from core.group.RPG.unified_rpg import show_inventory, show_workbench_cmd, show_shop_main

dp = Dispatcher(fsm_strategy=FSMStrategy.USER_IN_CHAT)

from group_stat import (
    show_profile, 
    do_work, 
    show_shop, 
    show_top, 
    manage_censor, 
    heal_hp,
    give_lumcoins,
    check_transfer_status
)
from core.group.RP.actions import RPActions
from rp_module_refactored import cmd_check_self_hp, cmd_show_rp_actions_list, handle_rp_action_via_text
from command import cmd_help

async def main():
    logger.info("Запуск основной функции бота.")

    profile_manager = ProfileManager()
    try:
        await profile_manager.connect()
        logger.info("ProfileManager подключен.")
    except Exception as e:
        logger.critical(f"Не удалось подключить ProfileManager: {e}. Бот не будет запущен.", exc_info=True)
        exit(1)

    logger.info("Инициализация основной базы данных.")
    await db.initialize_database()
    await db.create_promo_table()

    try:
        import aiosqlite
        async with aiosqlite.connect('profiles.db') as conn:
            await conn.execute('DROP TABLE IF EXISTS user_inventory')
            
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_inventory (
                    user_id INTEGER,
                    item_key TEXT,
                    item_type TEXT,
                    item_data TEXT,
                    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, item_key)
                )
            ''')
            await conn.commit()
            logger.info("RPG inventory table reinitialized with correct structure")
            
            cursor = await conn.execute('SELECT user_id, active_background FROM user_profiles WHERE active_background != "default"')
            users_with_backgrounds = await cursor.fetchall()
            
            for user_id, background in users_with_backgrounds:
                await conn.execute('''
                    INSERT OR IGNORE INTO user_inventory (user_id, item_key, item_type, item_data)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, background, 'background', json.dumps({'name': background, 'type': 'background'})))
            
            await conn.commit()
            logger.info(f"Synced {len(users_with_backgrounds)} existing backgrounds to inventory")
            
    except Exception as e:
        logger.error(f"Error initializing RPG inventory table: {e}")

    logger.info("Инициализация StickerManager и загрузка стикеров.")
    sticker_manager_instance = StickerManager(cache_file_path=STICKERS_CACHE_FILE)
    await sticker_manager_instance.fetch_stickers(bot)

    logger.info("Передача зависимостей в диспетчер.")
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
        "магазин": (show_shop_main, ["message", "profile_manager"]),
    }

    for action in RPActions.SORTED_COMMANDS_FOR_PARSING:
        if action not in direct_dispatch_handlers:
            direct_dispatch_handlers[action] = (handle_rp_action_via_text, ["message", "bot", "profile_manager"])

    non_slash_commands_to_exclude = list(direct_dispatch_handlers.keys())
    non_slash_commands_to_exclude.sort(key=len, reverse=True)

    logger.info("Настройка и включение модуля цензуры.")
    censor_module.setup_censor_handlers(
        main_dp=dp,
        bad_words_file_path=BAD_WORDS_FILE,
        non_slash_command_prefixes=non_slash_commands_to_exclude,
        direct_dispatch_handlers=direct_dispatch_handlers,
        profile_manager_instance=profile_manager,
        bot_instance=bot
    )
    logger.info("Модуль цензуры успешно интегрирован.")

    group_text_router = Router(name="group_text_router")
    group_text_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
    logger.info("Создан роутер для групповых текстовых сообщений.")

    logger.info("Включение stat_router в group_text_router.")
    setup_stat_handlers(main_dp=group_text_router)

    logger.info("Включение RPG handlers.")
    from core.group.RPG.unified_rpg import setup_rpg_handlers
    setup_rpg_handlers(main_dp=group_text_router)

    logger.info("Включение rp_router в group_text_router.")
    setup_rp_handlers(
        main_dp=group_text_router,
        bot_instance=bot,
        profile_manager_instance=profile_manager,
        database_module=db
    )

    logger.info("Настройка обработчиков казино.")
    setup_casino_handlers(main_dp=group_text_router, profile_manager=profile_manager)

    dp.include_router(group_text_router)
    logger.info("group_text_router успешно интегрирован в главный диспетчер.")

    private_router = Router(name="private_router")
    private_router.message.filter(F.chat.type == ChatType.PRIVATE)
    logger.info("Создан роутер для приватных чатов.")

    logger.info("Регистрация основных обработчиков команд ТОЛЬКО для приватных чатов.")
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
    logger.info("Основной обработчик текстовых сообщений для ЛС зарегистрирован в private_router.")

    logger.info("Настройка обработчиков промокодов.")
    setup_promo_handlers(
        main_dp=dp,
        bot_instance=bot,
        profile_manager_instance=profile_manager
    )

    dp.include_router(private_router)
    logger.info("private_router успешно интегрирован в главный диспетчер.")

    logger.info("Запуск фоновых задач.")
    jokes_bg_task = asyncio.create_task(jokes_task(bot))
    rp_recovery_bg_task = asyncio.create_task(periodic_hp_recovery_task(bot, profile_manager, db))
    daily_reset_task = asyncio.create_task(reset_daily_stats_task(profile_manager))
    await migrate_existing_users_exp()

    logger.info("Запуск поллинга бота...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.critical(f"Опрос бота завершился с ошибкой: {e}", exc_info=True)
    finally:
        logger.info("Остановка бота...")
        jokes_bg_task.cancel()
        rp_recovery_bg_task.cancel()
        daily_reset_task.cancel()
        try:
            await asyncio.gather(jokes_bg_task, rp_recovery_bg_task, return_exceptions=True)
            logger.info("Фоновые задачи успешно отменены.")
        except asyncio.CancelledError:
            logger.info("Фоновые задачи были отменены во время завершения работы.")
        
        await profile_manager.close()
        logger.info("Соединение ProfileManager закрыто.")

        await bot.session.close()
        logger.info("Сессия бота закрыта. Выход.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Необработанное исключение при основном выполнении: {e}", exc_info=True)