from core.main.ez_main import *

async def fetch_random_joke() -> str:
    try:
        # Проверяем, есть ли кэш анекдотов и не устарел ли он
        if JOKES_CACHE_FILE.exists():
            with open(JOKES_CACHE_FILE, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            # Кэш считается актуальным в течение 12 часов
            if time.time() - cache_data.get('timestamp', 0) < 12 * 3600:
                jokes = cache_data.get('jokes', [])
                if jokes:
                    logger.info("Jokes loaded from cache.")
                    return random.choice(jokes)
        
        logger.info("Fetching jokes from anekdot.ru...")
        async with aiohttp.ClientSession() as session:
            async with session.get("https://www.anekdot.ru/random/anekdot/") as response:
                response.raise_for_status()
                html = await response.text()
        
        soup = BeautifulSoup(html, 'html.parser')
        joke_divs = soup.find_all('div', class_='text')
        
        jokes = [div.get_text(separator="\n").strip() for div in joke_divs if div.get_text(separator="\n").strip()]
        
        if jokes:
            # Сохраняем в кэш
            with open(JOKES_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({'timestamp': time.time(), 'jokes': jokes}, f, ensure_ascii=False, indent=4)
            logger.info(f"Fetched and cached {len(jokes)} jokes.")
            return random.choice(jokes)
        else:
            logger.warning("No jokes found on anekdot.ru.")
            return "Не удалось найти анекдот. Попробуйте позже."

    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching jokes: {e}")
        return "Не могу сейчас получить анекдот с сайта. Проблемы с сетью или сайтом."
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching jokes: {e}", exc_info=True)
        return "Произошла непредвиденная ошибка при поиске анекдота."
    
async def cmd_start(message: Message, profile_manager: ProfileManager):
    user = message.from_user
    if not user:
        logger.warning("Received start command without user info.")
        return

    # Убеждаемся, что пользователь существует в БД и логируем взаимодействие
    await db.ensure_user_exists(user.id, user.username, user.first_name)
    await db.log_user_interaction(user.id, "start_command", "command")

    # Получаем или создаем игровой профиль (если group_stat активен)
    profile = await profile_manager.get_user_profile(user)
    if not profile:
        logger.error(f"Failed to get profile for user {user.id} after start.")
        # Несмотря на ошибку профиля, продолжаем, чтобы бот хоть как-то отвечал
        pass

    response_text = (
        f"Привет, {hbold(user.first_name)}! Я ваш личный ИИ-помощник и многоликий собеседник. "
        "Я могу говорить с вами в разных режимах. Чтобы сменить режим, используйте команду /mode.\n\n"
        "Вот что я умею:\n"
        "✨ /mode - Показать доступные режимы и сменить текущий.\n"
        "📊 /stats - Показать вашу статистику использования.\n"
        "🤣 /joke - Рассказать случайный анекдот.\n"
        "🔍 /check_value - Проверить значение из файла (если настроено).\n"
        "🔔 /subscribe_value - Подписаться на уведомления об изменении значения.\n"
        "🔕 /unsubscribe_value - Отписаться от уведомлений.\n"
        "👤 /profile - Показать ваш игровой профиль (если есть, регистрируется в group_stat).\n"
        "⚒️ /rp_commands - Показать список RP-действий (регистрируется в rp_module_refactored).\n"
        "❤️ /hp - Показать ваше текущее HP (в RP-модуле, регистрируется в rp_module_refactored).\n"
        "✍️ Просто пишите мне, и я буду отвечать в текущем режиме!"
    )
    await message.answer(response_text, parse_mode=ParseMode.HTML)

async def safe_send_message(chat_id: int, text: str, **kwargs) -> Optional[Message]:
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logger.error(f"Failed to send message to chat {chat_id}: {e}")
        return None

async def typing_animation(chat_id: int, bot_instance: Bot) -> Optional[Message]:
    """
    Создает и управляет анимацией "печатает..." для имитации активности бота.
    Возвращает объект сообщения с анимацией, который можно будет отредактировать.
    """
    typing_msg = None
    try:
        typing_msg = await bot_instance.send_message(chat_id, "✍️ Печатает...")
        for _ in range(3): # Анимация из 3 точек
            await asyncio.sleep(0.7)
            current_text = typing_msg.text
            if current_text == "✍️ Печатает...":
                await typing_msg.edit_text("✍️ Печатает..")
            elif current_text == "✍️ Печатает..":
                await typing_msg.edit_text("✍️ Печатает.")
            else:
                await typing_msg.edit_text("✍️ Печатает...")
        return typing_msg
    except Exception as e:
        logger.warning(f"Typing animation error in chat {chat_id}: {e}")
        if typing_msg:
            with suppress(Exception): # Подавляем ошибки при попытке удалить сообщение
                await typing_msg.delete()
        return None

async def jokes_task(bot_instance: Bot):
    """
    Фоновая задача для периодической отправки анекдотов в заданный канал.
    """
    logger.info("Jokes task started.")
    if not CHANNEL_ID:
        logger.warning("Jokes task disabled: CHANNEL_ID is not set or invalid.")
        return
    
    while True:
        # Отправляем анекдот каждые 1-2 часа (случайный интервал)
        await asyncio.sleep(random.randint(3500, 7200))
        logger.info("Starting periodic jokes cache update.")
        try:
            joke_text = await fetch_random_joke()
            # Проверяем, что анекдот не является сообщением об ошибке
            if joke_text != "Не удалось найти анекдот. Попробуйте позже." and \
               joke_text != "Не могу сейчас получить анекдот с сайта. Проблемы с сетью или сайтом." and \
               joke_text != "Произошла непредвиденная ошибка при поиске анекдота.":
                await safe_send_message(CHANNEL_ID, f"🎭 {joke_text}")
                logger.info(f"Joke sent to channel {CHANNEL_ID}.")
            else:
                logger.warning(f"Failed to fetch joke for channel: {joke_text}")
            logger.info("Finished periodic jokes cache update.")
        except Exception as e:
            logger.error(f"Error during periodic jokes cache update: {e}", exc_info=True)