from core.main.ez_main import *
from core.main.ollama import *
from core.main.command import *
from core.main.dec_command import *
import censor_module # Импорт модуля цензуры
from pathlib import Path # Импорт Path для BAD_WORDS_FILE
from core.group.RP.actions import RPActions # Импорт RPActions для получения списка команд

# --- Обработчики команд ---


async def main():
    """
    Основная функция запуска бота.
    Инициализирует все менеджеры, базы данных, регистрирует обработчики
    и запускает поллинг бота.
    """
    logger.info("main: Запуск основной функции бота.")

    profile_manager = ProfileManager()
    try:
        if hasattr(profile_manager, 'connect'):
            await profile_manager.connect()
            logger.info("main: ProfileManager подключен.")
        else:
            logger.critical("main: ProfileManager не имеет метода 'connect'. Завершение работы.")
            exit(1)
    except Exception as e:
        logger.critical(f"main: Не удалось подключить ProfileManager: {e}. Бот не будет запущен.", exc_info=True)
        exit(1)

    # Инициализация основной базы данных (для общего функционала бота)
    logger.info("main: Инициализация основной базы данных.")
    await db.initialize_database()

    # Инициализация StickerManager и загрузка стикеров
    logger.info("main: Инициализация StickerManager и загрузка стикеров.")
    sticker_manager_instance = StickerManager(cache_file_path=STICKERS_CACHE_FILE)
    await sticker_manager_instance.fetch_stickers(bot)

    # Передача зависимостей в диспетчер для удобства доступа в обработчиках
    logger.debug("main: Передача зависимостей в диспетчер.")
    dp["profile_manager"] = profile_manager
    dp["sticker_manager"] = sticker_manager_instance
    dp["bot_instance"] = bot

    # Список не-слеш команд, которые цензор должен игнорировать
    # Собираем все известные не-слеш команды из разных модулей
    non_slash_commands_to_exclude = [
        "профиль", "работать", "магазин", "топ", # Из group_stat.py
        "моё хп", "мое хп", "моё здоровье", "мое здоровье", "хп", "здоровье", # Из rp_module_refactored.py
        "список действий", "рп действия", "список рп", "команды рп", # Из rp_module_refactored.py
    ]
    # Добавляем все RP-действия из RPActions
    non_slash_commands_to_exclude.extend(RPActions.SORTED_COMMANDS_FOR_PARSING)
    # Удаляем дубликаты и приводим к нижнему регистру
    non_slash_commands_to_exclude = list(set([cmd.lower() for cmd in non_slash_commands_to_exclude]))
    # Сортируем по длине в убывающем порядке, чтобы более длинные команды проверялись первыми (например, "моё хп" раньше "хп")
    non_slash_commands_to_exclude.sort(key=len, reverse=True)

    # *** ВАЖНОЕ: censor_module должен быть включен ПЕРВЫМ в dp! ***
    # Он будет работать только в группах и пропускать сообщения, начинающиеся с '/' или являющиеся известными не-слеш командами.
    logger.info("main: Настройка и включение модуля цензуры (первый приоритет для групп).")
    censor_module.setup_censor_handlers(
        main_dp=dp,
        bad_words_file_path=BAD_WORDS_FILE,
        non_slash_command_prefixes=non_slash_commands_to_exclude
    )
    logger.info("main: Модуль цензуры успешно интегрирован.")

    # --- Роутер для ГРУППОВЫХ ЧАТОВ (текстовые сообщения, не команды, не мат) ---
    # Этот роутер будет обрабатывать сообщения в группах, которые не были зацензурированы
    # и не являются командами (т.к. команды обрабатываются Command-фильтрами напрямую или пропускаются цензором).
    group_text_router = Router(name="group_text_router")
    group_text_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
    # Удалена строка group_text_router.message.filter(~Command()), так как она вызывала ошибку
    # и является избыточной, потому что censor_module уже пропускает команды.
    logger.info("main: Создан роутер для групповых текстовых сообщений.")

    # Включаем stat_router в group_text_router
    # Это позволит командам из group_stat (например, "профиль" без '/') работать в группах.
    logger.info("main: Включение stat_router в group_text_router.")
    setup_stat_handlers(
        dp=group_text_router, # Передаем group_text_router вместо dp
        bot=bot,
        profile_manager=profile_manager
    )
    # Включаем rp_router в group_text_router, если он должен работать в группах
    logger.info("main: Включение rp_router в group_text_router.")
    setup_rp_handlers(
        main_dp=group_text_router, # Передаем group_text_router вместо dp
        bot_instance=bot,
        profile_manager_instance=profile_manager,
        database_module=db
    )

    # Включаем group_text_router в главный диспетчер
    dp.include_router(group_text_router)
    logger.info("main: group_text_router успешно интегрирован в главный диспетчер.")


    # --- Роутер для ПРИВАТНЫХ ЧАТОВ (все сообщения) ---
    private_router = Router(name="private_router")
    private_router.message.filter(F.chat.type == ChatType.PRIVATE)
    logger.info("main: Создан роутер для приватных чатов.")

    # Регистрация основных обработчиков команд (теперь в private_router)
    logger.info("main: Регистрация основных обработчиков команд ТОЛЬКО для приватных чатов.")
    private_router.message(Command("start"))(cmd_start)
    private_router.message(Command("mode"))(cmd_mode)
    private_router.message(Command("stats"))(cmd_stats)
    private_router.message(Command("joke"))(cmd_joke)
    private_router.message(Command("check_value"))(cmd_check_value)
    private_router.message(Command("subscribe_value", "val"))(cmd_subscribe_value)
    private_router.message(Command("unsubscribe_value", "sval"))(cmd_unsubscribe_value)
    private_router.message(F.photo)(photo_handler)
    private_router.message(F.voice)(voice_handler_msg)
    
    # Общий обработчик текстовых сообщений ТОЛЬКО для приватных чатов
    private_router.message(F.text)(handle_text_message) 
    logger.info("main: Основной обработчик текстовых сообщений для ЛС зарегистрирован в private_router.")

    # Включаем private_router в главный диспетчер
    dp.include_router(private_router)
    logger.info("main: private_router успешно интегрирован в главный диспетчер.")


    # Запуск фоновых задач
    logger.info("main: Запуск фоновых задач.")
    jokes_bg_task = asyncio.create_task(jokes_task(bot))
    rp_recovery_bg_task = asyncio.create_task(periodic_hp_recovery_task(bot, profile_manager, db))

    logger.info("main: Запуск поллинга бота...")
    try:
        # Запуск поллинга Aiogram
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
        
        if hasattr(profile_manager, 'close'):
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
