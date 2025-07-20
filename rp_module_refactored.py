import re
from aiogram.utils.markdown import hbold
from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType, ParseMode, MessageEntityType
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from contextlib import suppress
import time
from typing import Optional, Tuple, Any, List
import asyncio 
import logging # Добавлен импорт logging

# Импорт из основного модуля базы данных
import database as db

# Импорт ProfileManager (предполагаем, что он находится в group_stat.manager)
try:
    from core.group.stat.manager import ProfileManager as RealProfileManager
    HAS_PROFILE_MANAGER = True
except ImportError:
    # import logging # Этот импорт был здесь, но должен быть в начале файла.
    logging.critical("CRITICAL: Module 'core.group.stat.manager' or 'ProfileManager' not found. RP functionality will be severely impaired or non-functional.")
    HAS_PROFILE_MANAGER = False
    class RealProfileManager:
        async def get_user_rp_stats(self, user_id: int) -> dict:
            return {'hp': 100, 'recovery_end_ts': 0.0, 'heal_cooldown_ts': 0.0}
        async def update_user_rp_stats(self, user_id: int, **kwargs: Any) -> None:
            pass
        async def get_user_profile(self, user: types.User) -> Optional[dict]:
            return None
        async def connect(self) -> None:
            pass
        async def close(self) -> None:
            pass

ProfileManager = RealProfileManager

# Импорт конфигурации RP
from core.group.RP.config import RPConfig
from core.group.RP.actions import RPActions

# Импорт функций из more.py
from core.group.RP.more import (
    get_user_display_name, 
    _update_user_hp, 
    _parse_rp_message, # Импортируем новую функцию парсинга
    format_timedelta, 
    is_user_knocked_out
)

# Настройка логгера
logger = logging.getLogger(__name__)

rp_router = Router(name="rp_module")
rp_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

async def handle_rp_action(
    message: types.Message, 
    bot: Bot, 
    profile_manager: ProfileManager,
    action_name: str,
    target_user: Optional[types.User] = None,
    custom_text: Optional[str] = None # Новый параметр для дополнительного текста
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
        # =================================================================
        # ИЗМЕНЕНИЕ: Запрет на использование РП команд на ботов
        # =================================================================
        if target_user.is_bot:
            await message.reply("🤖 РП-действия на ботов запрещены.")
            return
        # =================================================================

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

        # Формирование сообщения о действии с новым форматированием
        action_message = f"{sender_name} {action_name} {target_name}"
        if custom_text: # Добавляем дополнительный текст, если он есть
            action_message += f" {custom_text}"
        
        action_message += f"\n({target_name} {hp_change_target:+d} HP, {sender_name} {hp_change_sender:+d} HP)"
        action_message += f"\n\nHP {target_name}: {new_target_hp}/{RPConfig.MAX_HP}"
        action_message += f"\nHP {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP}"

        # Добавление сообщений о нокауте
        if target_knocked_out:
            action_message += f"\n💥 {target_name} нокаутирован(а)! Он(а) не может совершать действия {RPConfig.HP_RECOVERY_TIME_SECONDS // 60} минут."
        if sender_knocked_out:
            action_message += f"\n😩 {sender_name} нокаутирован(а)! Вы не можете совершать действия {RPConfig.HP_RECOVERY_TIME_SECONDS // 60} минут."

        await message.answer(action_message)
        logger.info(f"RP Action '{action_name}' performed by {sender_id} on {target_id}. Sender HP: {new_sender_hp}, Target HP: {new_target_hp}.")
    else:
        # Действие без цели (например, "засмеяться")
        action_message = f"{sender_name} {action_name}"
        if custom_text: # Добавляем дополнительный текст, если он есть
            action_message += f" {custom_text}"
        action_message += f"\n(HP {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP})"
        if sender_knocked_out:
            action_message += f"\n😩 {sender_name} нокаутирован(а)! Вы не можете совершать действия {RPConfig.HP_RECOVERY_TIME_SECONDS // 60} минут."
        await message.answer(action_message)
        logger.info(f"RP Action '{action_name}' performed by {sender_id}. Sender HP: {new_sender_hp}.")

    # Удаляем оригинальное сообщение, если оно не было командой со слэшем
    if message.text and not message.text.startswith('/'):
        with suppress(TelegramAPIError):
            await message.delete()
            logger.info(f"Original message {message.message_id} deleted after RP action.")


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

    response_text += "\nИспользуйте команду в формате: /<действие> или <действие> <@пользователь> [дополнительный текст]"
    
    await message.answer(response_text, parse_mode=ParseMode.HTML)


@rp_router.message(F.text)
async def handle_rp_action_via_text(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Обрабатывает RP-действия, отправленные текстом (без слеша).
    Использует message.text для получения текста сообщения.
    """
    logger.debug(f"handle_rp_action_via_text: Received text message: '{message.text}' from user {message.from_user.id}.")

    action_name, target_user, custom_text = await _parse_rp_message(message, bot)

    if not action_name:
        logger.debug(f"handle_rp_action_via_text: No RP action found in text: '{message.text}'. Skipping.")
        return # Это не RP-действие, пропускаем

    logger.info(f"handle_rp_action_via_text: Processing RP action '{action_name}' (via text) for user {message.from_user.id}. Target: {target_user.id if target_user else 'None'}. Custom text: '{custom_text}'")
    await handle_rp_action(message, bot, profile_manager, action_name, target_user, custom_text)


@rp_router.message(F.text.regexp(r"^/(\w+)(?:\s+(.*?))?$")) # Обновлено для захвата custom_text
async def handle_rp_action_via_slash_command(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Обрабатывает RP-действия, отправленные как слеш-команды (например, /поцеловать @username).
    """
    logger.debug(f"handle_rp_action_via_slash_command: Received slash command: '{message.text}' from user {message.from_user.id}.")
    
    action_name, target_user, custom_text = await _parse_rp_message(message, bot)

    if not action_name:
        logger.debug(f"handle_rp_action_via_slash_command: No RP action found in command: '{message.text}'. Skipping.")
        return # Это не RP-действие, пропускаем

    logger.info(f"handle_rp_action_via_slash_command: Processing RP action '{action_name}' (via slash command) for user {message.from_user.id}. Target: {target_user.id if target_user else 'None'}. Custom text: '{custom_text}'")
    await handle_rp_action(message, bot, profile_manager, action_name, target_user, custom_text)


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
    await profile_manager.update_lumcoins(user_id, -RPConfig.HEAL_COST)

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