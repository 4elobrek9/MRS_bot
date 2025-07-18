from core.group.RP.rmain import *
from core.group.RP.config import *
from core.group.RP.actions import *
from core.group.RP.more import *

rp_router = Router(name="rp_module")
rp_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
 
async def _update_user_hp(
    profile_manager: ProfileManager,
    user_id: int,
    hp_change: int
) -> Tuple[int, bool]:
    """
    Обновляет HP пользователя и возвращает новое HP и флаг, был ли пользователь нокаутирован.
    """
    stats = await db.get_user_rp_stats(user_id)
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    new_hp = max(RPConfig.MIN_HP, min(RPConfig.MAX_HP, current_hp + hp_change))
    knocked_out_this_time = False
    update_fields = {'hp': new_hp}

    if new_hp <= RPConfig.MIN_HP and current_hp > RPConfig.MIN_HP:
        # Если HP упало до или ниже минимального, и раньше было выше минимального
        recovery_ts = time.time() + RPConfig.HP_RECOVERY_TIME_SECONDS
        update_fields['recovery_end_ts'] = recovery_ts
        knocked_out_this_time = True
        logger.info(f"User {user_id} HP dropped to {new_hp}. Recovery timer set for {RPConfig.HP_RECOVERY_TIME_SECONDS}s.")
    elif new_hp > RPConfig.MIN_HP and stats.get('recovery_end_ts', 0.0) > 0.0:
        # Если HP восстановилось выше минимального, сбрасываем таймер восстановления
        update_fields['recovery_end_ts'] = 0.0
        logger.info(f"User {user_id} HP recovered above min. Recovery timer reset.")

    await profile_manager.update_user_rp_stats(user_id, **update_fields)
    return new_hp, knocked_out_this_time

async def handle_rp_action(
    message: types.Message, 
    bot: Bot, 
    profile_manager: ProfileManager,
    action_name: str,
    target_user: Optional[types.User] = None
):
    """
    Обрабатывает RP-действие, обновляет HP участников и отправляет сообщение.
    """
    sender_id = message.from_user.id
    sender_name = get_user_display_name(message.from_user)
    action_data = RPActions.ALL_ACTION_DATA.get(action_name.lower())

    if not action_data:
        logger.warning(f"RP Action '{action_name}' not found in ALL_ACTION_DATA.")
        await message.reply("❌ Неизвестное RP-действие.")
        return

    hp_change_sender = action_data.get("hp_change_sender", 0)
    hp_change_target = action_data.get("hp_change_target", 0)

    # Проверка на нокаут отправителя
    if await is_user_knocked_out(profile_manager, sender_id, bot, message):
        logger.info(f"Sender {sender_id} is knocked out. Cannot perform RP action.")
        return

    # Обновление HP отправителя
    new_sender_hp, sender_knocked_out = await _update_user_hp(profile_manager, sender_id, hp_change_sender)

    if target_user:
        if target_user.id == sender_id:
            await message.reply("🚫 Вы не можете совершать RP-действия на самого себя.")
            return

        target_id = target_user.id
        target_name = get_user_display_name(target_user)

        # Проверка на нокаут цели (если это не действие на себя)
        if await is_user_knocked_out(profile_manager, target_id, bot, message):
            logger.info(f"Target {target_id} is knocked out. Cannot perform RP action on them.")
            return

        # Обновление HP цели
        new_target_hp, target_knocked_out = await _update_user_hp(profile_manager, target_id, hp_change_target)

        # Формирование сообщения о действии
        action_message = f"{sender_name} {action_name} {target_name}!"
        
        # Добавление информации о HP
        action_message += f" (HP: {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP}, {target_name}: {new_target_hp}/{RPConfig.MAX_HP})"

        # Добавление сообщений о нокауте
        if target_knocked_out:
            action_message += f"\n💥 {target_name} нокаутирован(а)! Он(а) не может совершать действия {RPConfig.HP_RECOVERY_TIME_SECONDS // 60} минут."
        if sender_knocked_out:
            action_message += f"\n😩 {sender_name} нокаутирован(а)! Вы не можете совершать действия {RPConfig.HP_RECOVERY_TIME_SECONDS // 60} минут."

        await message.answer(action_message)
        logger.info(f"RP Action '{action_name}' performed by {sender_id} on {target_id}. Sender HP: {new_sender_hp}, Target HP: {new_target_hp}.")
    else:
        # Действие без цели (например, "засмеяться")
        action_message = f"{sender_name} {action_name}!"
        action_message += f" (HP: {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP})"
        if sender_knocked_out:
            action_message += f"\n😩 {sender_name} нокаутирован(а)! Вы не можете совершать действия {RPConfig.HP_RECOVERY_TIME_SECONDS // 60} минут."
        await message.answer(action_message)
        logger.info(f"RP Action '{action_name}' performed by {sender_id}. Sender HP: {new_sender_hp}.")

@rp_router.message(Command("hp", "хп", "моехп", "моёхп", "здоровье", "мое здоровье", "моё здоровье"))
async def cmd_check_self_hp(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Показывает текущее HP пользователя и статус восстановления.
    """
    user_id = message.from_user.id
    logger.info(f"User {user_id} requested HP check.")
    
    stats = await db.get_user_rp_stats(user_id)
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    recovery_end_ts = stats.get('recovery_end_ts', 0.0)
    heal_cooldown_ts = stats.get('heal_cooldown_ts', 0.0)

    status_message = f"❤️ Ваше текущее HP: {current_hp}/{RPConfig.MAX_HP}.\n"

    if current_hp <= RPConfig.MIN_HP:
        now = time.time()
        if recovery_end_ts > now:
            remaining_time = int(recovery_end_ts - now)
            status_message += f"Вы нокаутированы! Автоматическое восстановление через: {format_timedelta(remaining_time)}.\n"
        else:
            status_message += "Вы нокаутированы, но время восстановления истекло. Вы можете совершить действие, чтобы восстановиться.\n"
    
    now = time.time()
    if heal_cooldown_ts > now:
        remaining_heal_cooldown = int(heal_cooldown_ts - now)
        status_message += f"До следующего ручного лечения: {format_timedelta(remaining_heal_cooldown)}."

    await message.reply(status_message)


@rp_router.message(Command("rpactions", "rp_actions", "списокдействий", "список_действий", "рпдействия", "рп_действия", "командырп", "команды_рп", "списокрп", "список_рп"))
async def cmd_show_rp_actions_list(message: types.Message, bot: Bot):
    """
    Отправляет список доступных RP-действий.
    """
    logger.info(f"User {message.from_user.id} requested RP actions list.")
    
    response_text = hbold("Доступные RP-действия:\n")
    for category, actions in RPActions.INTIMATE_ACTIONS.items():
        response_text += f"\n{hbold(category.capitalize())}:\n"
        for action_name, data in actions.items():
            hp_target = data.get('hp_change_target', 0)
            hp_sender = data.get('hp_change_sender', 0)
            
            hp_info = []
            if hp_target != 0:
                hp_info.append(f"Цель: {hp_target:+d} HP")
            if hp_sender != 0:
                hp_info.append(f"Вы: {hp_sender:+d} HP")
            
            hp_str = f" ({', '.join(hp_info)})" if hp_info else ""
            
            response_text += f"  - /{action_name}{hp_str}\n" # Пока что указываем как слеш-команды

    response_text += "\nИспользуйте команду в формате: /<действие> или <действие> <@пользователь>"
    
    await message.answer(response_text, parse_mode=ParseMode.HTML)


@rp_router.message(F.text)
async def handle_rp_action_via_text(message: types.Message, bot: Bot, profile_manager: ProfileManager, command_text_payload: str):
    """
    Обрабатывает RP-действия, отправленные текстом (без слеша),
    используя прямой вызов из censor_module.
    command_text_payload содержит полный текст сообщения.
    """
    logger.debug(f"handle_rp_action_via_text: Received text message: '{command_text_payload}' from user {message.from_user.id}.")

    # Извлекаем действие и, возможно, цель из полного текста сообщения
    parts = command_text_payload.lower().split()
    
    # Ищем действие, которое является префиксом сообщения
    action_name = None
    target_mention = None

    # Сортируем команды по длине в убывающем порядке, чтобы более длинные команды (например, "романтический поцелуй")
    # имели приоритет над короткими ("поцеловать").
    sorted_actions = sorted(RPActions.ALL_ACTION_DATA.keys(), key=len, reverse=True)

    for action_key in sorted_actions:
        if command_text_payload.startswith(action_key):
            action_name = action_key
            # Оставшаяся часть сообщения может быть упоминанием пользователя
            remaining_text = command_text_payload[len(action_key):].strip()
            if remaining_text:
                # Попытка найти упоминание пользователя
                match = re.search(r'@(\w+)', remaining_text)
                if match:
                    target_mention = match.group(1)
            break # Нашли действие, выходим

    if not action_name:
        logger.debug(f"handle_rp_action_via_text: No RP action found in text: '{command_text_payload}'.")
        return # Это не RP-действие, пропускаем

    target_user = None
    if target_mention:
        # В реальном приложении здесь должна быть логика для получения user_id по username
        # Для простоты примера, мы пока проигнорируем target_user и будем считать, что
        # действие всегда без цели, если нет прямого упоминания.
        # В вашем случае, если бот умеет резолвить @username в user_id, это нужно сделать здесь.
        # Например, через базу данных или API Telegram, если пользователь уже писал боту.
        
        # Для демонстрации, если цель упомянута, но не найдена, можно отправить сообщение
        # или просто проигнорировать цель и выполнить действие без нее.
        # Пока что, мы просто не будем устанавливать target_user, если не можем его найти.
        logger.warning(f"handle_rp_action_via_text: Target user mention '{target_mention}' found, but resolution to user object is not implemented.")
        # Если у вас есть способ получить объект пользователя по username, используйте его:
        # target_user = await get_user_by_username(target_mention) 
        pass # Продолжаем без target_user, если не смогли его найти

    logger.info(f"handle_rp_action_via_text: Processing RP action '{action_name}' (via text) for user {message.from_user.id}.")
    await handle_rp_action(message, bot, profile_manager, action_name, target_user)


@rp_router.message(F.text.regexp(r"^/(\w+)(?:\s+@(\w+))?"))
async def handle_rp_action_via_slash_command(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Обрабатывает RP-действия, отправленные как слеш-команды (например, /поцеловать @username).
    """
    logger.debug(f"handle_rp_action_via_slash_command: Received slash command: '{message.text}' from user {message.from_user.id}.")
    
    match = re.match(r"^/(\w+)(?:\s+@(\w+))?", message.text)
    if not match:
        logger.warning(f"handle_rp_action_via_slash_command: Regex did not match for message: '{message.text}'. Skipping.")
        return

    action_name = match.group(1).lower()
    target_mention = match.group(2)

    if action_name not in RPActions.ALL_ACTION_DATA:
        logger.debug(f"handle_rp_action_via_slash_command: Action '{action_name}' not a recognized RP action. Skipping.")
        return # Это не RP-действие, пропускаем

    target_user = None
    if target_mention:
        # Здесь должна быть логика для получения объекта пользователя по username.
        # В Aiogram это может быть сделано через message.bot.get_chat_member или похожие методы,
        # если пользователь находится в том же чате и бот имеет к нему доступ.
        # Или, если у вас есть база данных пользователей, можно получить user_id по username.
        try:
            # Попытка получить информацию о пользователе из Telegram
            # Это может быть не всегда возможно, если бот не видит пользователя
            # или пользователь не писал боту в личку.
            # Для простоты, мы можем использовать mock-объект или пропустить, если не найдено.
            # В реальном приложении, возможно, потребуется более сложная логика.
            
            # Получаем всех участников чата и ищем по username
            chat_members = await bot.get_chat_administrators(message.chat.id) # Это только админы, нужно получить всех
            # Более универсальный способ получить всех участников чата не всегда доступен напрямую для обычных ботов.
            # Лучший способ - это если у вас есть своя база данных пользователей, которую вы заполняете.
            
            # Для примера, пока что, мы будем считать, что target_user - это просто объект с id и first_name
            # Если у вас есть способ получить реальный объект types.User, используйте его.
            
            # Простой пример: если target_mention - это username, то можно создать фиктивный объект User
            # или получить его из базы данных, если она у вас есть.
            
            # Если вы хотите, чтобы бот мог "видеть" всех пользователей в группе,
            # ему нужно быть администратором с соответствующими правами.
            # Или же, если вы храните пользователей в своей БД, то извлекать оттуда.
            
            # В данном случае, для простоты, мы будем использовать `message.reply_to_message`
            # если пользователь ответил на чье-то сообщение.
            if message.reply_to_message and message.reply_to_message.from_user:
                target_user = message.reply_to_message.from_user
                logger.debug(f"RP action: Target user resolved from reply_to_message: {target_user.id}")
            else:
                # Если нет ответа, ищем по упоминанию. Это сложнее без БД пользователей.
                # Пока что оставим target_user как None, если не удалось найти через reply_to_message.
                logger.warning(f"RP action: Could not resolve target user '{target_mention}' from reply or internal database.")
                await message.reply(f"Не удалось найти пользователя @{target_mention}. Убедитесь, что он(а) находится в этом чате или ответьте на его(её) сообщение.")
                return # Прерываем выполнение, если цель не найдена
        except Exception as e:
            logger.error(f"Error resolving target user '{target_mention}': {e}", exc_info=True)
            await message.reply(f"Произошла ошибка при поиске пользователя @{target_mention}.")
            return # Прерываем выполнение, если произошла ошибка при поиске цели

    logger.info(f"handle_rp_action_via_slash_command: Processing RP action '{action_name}' (via slash command) for user {message.from_user.id}.")
    await handle_rp_action(message, bot, profile_manager, action_name, target_user)


@rp_router.message(Command("heal", "лечить"))
async def cmd_heal(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Позволяет пользователю восстановить HP вручную за Lumcoins.
    """
    user_id = message.from_user.id
    logger.info(f"User {user_id} requested to heal.")

    stats = await db.get_user_rp_stats(user_id)
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    heal_cooldown_ts = stats.get('heal_cooldown_ts', 0.0)
    
    now = time.time()

    if current_hp >= RPConfig.MAX_HP:
        await message.reply("😌 Ваше HP уже полное!")
        return

    if heal_cooldown_ts > now:
        remaining_time = int(heal_cooldown_ts - now)
        await message.reply(f"⏳ Вы можете лечиться снова через {format_timedelta(remaining_time)}.")
        return

    user_profile = await profile_manager.get_user_profile(message.from_user)
    if not user_profile:
        logger.error(f"Failed to get user profile for {user_id} during heal attempt.")
        await message.reply("❌ Не удалось загрузить ваш профиль для лечения.")
        return

    lumcoins = user_profile.get('lumcoins', 0)

    if lumcoins < RPConfig.HEAL_COST:
        await message.reply(f"💰 У вас недостаточно Lumcoins для лечения. Нужно {RPConfig.HEAL_COST}, у вас {lumcoins}.")
        return

    # Выполняем лечение
    new_hp, _ = await _update_user_hp(profile_manager, user_id, RPConfig.HEAL_AMOUNT)
    
    # Снимаем Lumcoins
    await profile_manager.update_user_profile(user_id, lumcoins=lumcoins - RPConfig.HEAL_COST)

    # Устанавливаем кулдаун на лечение
    new_cooldown_ts = now + RPConfig.HEAL_COOLDOWN_SECONDS
    await profile_manager.update_user_rp_stats(user_id, heal_cooldown_ts=new_cooldown_ts)

    await message.reply(f"💊 Вы успешно вылечились на {RPConfig.HEAL_AMOUNT} HP! Ваше HP: {new_hp}/{RPConfig.MAX_HP}. Потрачено {RPConfig.HEAL_COST} Lumcoins.")
    logger.info(f"User {user_id} healed for {RPConfig.HEAL_AMOUNT} HP. New HP: {new_hp}. Lumcoins spent: {RPConfig.HEAL_COST}.")


async def periodic_hp_recovery_task(bot: Bot, profile_manager: ProfileManager, db_module: Any):
    """
    Фоновая задача для периодического восстановления HP нокаутированных пользователей.
    """
    logger.info("Periodic HP recovery task started.")
    while True:
        try:
            # Исправлено: Использовано HP_RECOVERY_TIME_SECONDS вместо HP_RECOVERY_INTERVAL_SECONDS
            await asyncio.sleep(RPConfig.HP_RECOVERY_TIME_SECONDS) 
            logger.debug("Periodic recovery: Checking for users to recover HP.")
            
            now = time.time()
            # Получаем пользователей, у которых HP <= MIN_HP и время восстановления истекло
            # Используем db_module для доступа к функциям базы данных
            if not hasattr(db_module, 'get_users_for_hp_recovery'):
                logger.error("Database module does not have 'get_users_for_hp_recovery' function. Aborting periodic recovery.")
                continue
            
            users_to_recover: List[Tuple[int, int]] = await db_module.get_users_for_hp_recovery(now, RPConfig.MIN_HP)

            if users_to_recover:
                logger.info(f"Periodic recovery: Found {len(users_to_recover)} users for HP recovery.")
                for user_id, current_hp_val in users_to_recover:
                    new_hp, _ = await _update_user_hp(profile_manager, user_id, RPConfig.HP_RECOVERY_AMOUNT)
                    logger.info(f"Periodic recovery: User {user_id} HP auto-recovered from {current_hp_val} to {new_hp}.")
                    try:
                        await bot.send_message(
                            user_id,
                            f"✅ Ваше HP автоматически восстановлено до {new_hp}/{RPConfig.MAX_HP}! Вы снова в строю."
                        )
                    except TelegramAPIError as e:
                        logger.warning(f"Periodic recovery: Could not send PM to user {user_id}: {e.message}")
        except Exception as e:
            logger.error(f"Error in periodic_hp_recovery_task: {e}", exc_info=True)

def setup_rp_handlers(main_dp: Router, bot_instance: Bot, profile_manager_instance: ProfileManager, database_module: Any):
    """
    Настраивает RP-модуль: регистрирует обработчики и передает зависимости.
    """
    if not HAS_PROFILE_MANAGER:
        logging.error("Not setting up RP handlers because ProfileManager is missing.")
        return

    # Удалены строки rp_router.message.bind_arg(...), так как они вызывали AttributeError.
    # Зависимости должны быть доступны через контекст диспетчера или явно переданы в обработчики.

    # Регистрация обработчиков
    main_dp.include_router(rp_router)
    logger.info("RP router included and configured.")
