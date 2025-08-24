from core.main.ez_main import *
from core.main.ollama import *
from core.main.command import *
from core.main.dec_command import *
import censor_module
from pathlib import Path
from core.group.RP.actions import RPActions
from group_stat import show_profile, do_work, show_shop, show_top
from rp_module_refactored import cmd_check_self_hp, cmd_show_rp_actions_list, handle_rp_action_via_text
from group_RPG import show_inventory
from command import cmd_help

async def main():
    logger.info("main: Запуск основной функции бота.")

    profile_manager = ProfileManager()
    try:
        await profile_manager.connect()
        logger.info("main: ProfileManager подключен.")
    except Exception as e:
        logger.critical(f"main: Не удалось подключить ProfileManager: {e}. Бот не будет запущен.", exc_info=True)
        exit(1)

    logger.info("main: Инициализация основной базы данных.")
    await db.initialize_database()

    logger.info("main: Инициализация StickerManager и загрузка стикеров.")
    sticker_manager_instance = StickerManager(cache_file_path=STICKERS_CACHE_FILE)
    await sticker_manager_instance.fetch_stickers(bot)

    logger.debug("main: Передача зависимостей в диспетчер.")
    dp["profile_manager"] = profile_manager
    dp["sticker_manager"] = sticker_manager_instance
    dp["bot_instance"] = bot

    direct_dispatch_handlers = {
        "профиль": (show_profile, ["message", "profile_manager", "bot"]),
        "работать": (do_work, ["message", "profile_manager"]),
        "магазин": (show_shop, ["message", "profile_manager"]),
        "топ": (show_top, ["message", "profile_manager"]),
        "инвентарь": (show_inventory, ["message", "profile_manager"]),
        "помощь": (cmd_help, ["message"]),
        "help": (cmd_help, ["message"]),
        "команды": (cmd_help, ["message"]),
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
    }

    for action in RPActions.SORTED_COMMANDS_FOR_PARSING:
        if action not in direct_dispatch_handlers:
            direct_dispatch_handlers[action] = (handle_rp_action_via_text, ["message", "bot", "profile_manager"])

    non_slash_commands_to_exclude = list(direct_dispatch_handlers.keys())
    non_slash_commands_to_exclude.sort(key=len, reverse=True)

    logger.info("main: Настройка и включение модуля цензуры (первый приоритет для групп).")
    censor_module.setup_censor_handlers(
        main_dp=dp,
        bad_words_file_path=BAD_WORDS_FILE,
        non_slash_command_prefixes=non_slash_commands_to_exclude,
        direct_dispatch_handlers=direct_dispatch_handlers,
        profile_manager_instance=profile_manager,
        bot_instance=bot
    )
    logger.info("main: Модуль цензуры успешно интегрирован.")

    group_text_router = Router(name="group_text_router")
    group_text_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
    logger.info("main: Создан роутер для групповых текстовых сообщений.")

    logger.info("main: Включение stat_router в group_text_router.")
    setup_stat_handlers(main_dp=group_text_router)

    logger.info("main: Включение rp_router в group_text_router.")
    setup_rp_handlers(
        main_dp=group_text_router,
        bot_instance=bot,
        profile_manager_instance=profile_manager,
        database_module=db
    )

    dp.include_router(group_text_router)
    logger.info("main: group_text_router успешно интегрирован в главный диспетчер.")

    private_router = Router(name="private_router")
    private_router.message.filter(F.chat.type == ChatType.PRIVATE)
    logger.info("main: Создан роутер для приватных чатов.")

    logger.info("main: Регистрация основных обработчиков команд ТОЛЬКО для приватных чатов.")
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
    logger.info("main: Основной обработчик текстовых сообщений для ЛС зарегистрирован в private_router.")

    dp.include_router(private_router)
    logger.info("main: private_router успешно интегрирован в главный диспетчер.")

    profile_manager = ProfileManager()
    try:
        await profile_manager.connect()
        logger.info("main: ProfileManager подключен.")
        
        # Синхронизируем профили с основной базой данных
        await profile_manager.sync_profiles_with_main_db()
        
    except Exception as e:
        logger.critical(f"main: Не удалось подключить ProfileManager: {e}. Бот не будет запущен.", exc_info=True)
        exit(1)
    
    logger.info("main: Запуск фоновых задач.")
    jokes_bg_task = asyncio.create_task(jokes_task(bot))
    rp_recovery_bg_task = asyncio.create_task(periodic_hp_recovery_task(bot, profile_manager, db))

    logger.info("main: Запуск поллинга бота...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.critical(f"main: Опрос бота завершился с ошибкой: {e}", exc_info=True)
    finally:
        logger.info("main: Остановка бота...")
        jokes_bg_task.cancel()
        rp_recovery_bg_task.cancel()

        try:
            await asyncio.gather(jokes_bg_task, rp_recovery_bg_task, return_exceptions=True)
            logger.info("main: Фоновые задачи успешно отменены.")
        except asyncio.CancelledError:
            logger.info("main: Фоновые задачи были отменены во время завершения работы.")
        
        await profile_manager.close()
        logger.info("main: Соединение ProfileManager закрыто.")

        await bot.session.close()
        logger.info("main: Сессия бота закрыта. Выход.")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("main: Бот остановлен вручную (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"main: Необработанное исключение при основном выполнении: {e}", exc_info=True)