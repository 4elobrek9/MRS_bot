import re
from aiogram.utils.markdown import hbold # Removed html import from aiogram.utils.markdown
import html # Added direct html import
from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType, ParseMode, MessageEntityType
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from contextlib import suppress
import time
from typing import Optional, Tuple, Any, List
import asyncio 
import logging # Added logging import

# Import from main database module
import database as db

# Import ProfileManager (assuming it's in group_stat.manager)
try:
    from core.group.stat.manager import ProfileManager as RealProfileManager
    HAS_PROFILE_MANAGER = True
except ImportError:
    # import logging # This import was here, but should be at the beginning of the file.
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

# Import RP configuration
from core.group.RP.config import RPConfig
from core.group.RP.actions import RPActions

# Import functions from more.py
from core.group.RP.more import (
    get_user_display_name, 
    _update_user_hp, 
    _parse_rp_message, # Import new parsing function
    format_timedelta, 
    is_user_knocked_out
)

# Logger setup
logger = logging.getLogger(__name__)

rp_router = Router(name="rp_module")
rp_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

async def handle_rp_action(
    message: types.Message, 
    bot: Bot, 
    profile_manager: ProfileManager,
    action_name: str,
    target_user: Optional[types.User] = None,
    custom_text: Optional[str] = None
):
    """
    Handles an RP action, updates participants' HP, and sends a message.
    """
    sender_id = message.from_user.id
    sender_name = html.escape(get_user_display_name(message.from_user))
    action_data = RPActions.ALL_ACTION_DATA.get(action_name.lower())

    if not action_data:
        logger.warning(f"RP Action '{action_name}' not found in ALL_ACTION_DATA.")
        await message.reply("❌ Неизвестное RP-действие.")
        return

    hp_change_sender = action_data.get("hp_change_sender", 0)
    hp_change_target = action_data.get("hp_change_target", 0)
    action_verb = action_data.get("verb", action_name)

    # Check if sender is knocked out
    if await is_user_knocked_out(profile_manager, sender_id, bot, message):
        logger.info(f"Sender {sender_id} is knocked out. Cannot perform RP action.")
        return

    # Update sender's HP
    new_sender_hp, sender_knocked_out = await _update_user_hp(profile_manager, sender_id, hp_change_sender)

    if target_user:
        if target_user.is_bot:
            await message.reply("🤖 РП-действия на ботов запрещены.")
            return

        if target_user.id == sender_id:
            await message.reply("🚫 Вы не можете совершать RP-действия на самого себя.")
            return

        target_id = target_user.id
        target_name = html.escape(get_user_display_name(target_user))

        # Check if target is knocked out
        if await is_user_knocked_out(profile_manager, target_id, bot, message):
            logger.info(f"Target {target_id} is knocked out. Cannot perform RP action on them.")
            return

        # Update target's HP
        new_target_hp, target_knocked_out = await _update_user_hp(profile_manager, target_id, hp_change_target)

        # Формируем сообщение
        escaped_custom_text = html.escape(custom_text) if custom_text else ""
        action_message = f"{sender_name} {html.escape(action_verb)} {target_name}"
        if escaped_custom_text:
            action_message += f" {escaped_custom_text}"
        
        action_message += f"\n({target_name} {hp_change_target:+d} HP, {sender_name} {hp_change_sender:+d} HP)"
        action_message += f"\n\nHP {target_name}: {new_target_hp}/{RPConfig.MAX_HP}"
        action_message += f"\nHP {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP}"

        # Add knockout messages
        if target_knocked_out:
            action_message += f"\n💥 {target_name} нокаутирован(а)! Он(а) не может совершать действия {RPConfig.HP_RECOVERY_TIME_SECONDS // 60} минут."
        if sender_knocked_out:
            action_message += f"\n😩 {sender_name} нокаутирован(а)! Вы не можете совершать действия {RPConfig.HP_RECOVERY_TIME_SECONDS // 60} минут."

        await message.answer(action_message, parse_mode=ParseMode.HTML)
        logger.info(f"RP Action '{action_name}' performed by {sender_id} on {target_id}. Sender HP: {new_sender_hp}, Target HP: {new_target_hp}.")

        # ✅ ДОБАВЛЕНО: Обновляем задания для RP-действий
        try:
            from core.group.stat.quests_handlers import update_rp_quests
            # Определяем, является ли действие уникальным (обнять, погладить и т.д.)
            is_unique_action = action_name.lower() in ['обнять', 'погладить', 'поцеловать', 'укусить', 'лизнуть']
            await update_rp_quests(
                user_id=sender_id,
                action_type='rp',
                unique_action=is_unique_action,
                bot=bot
            )
            logger.info(f"✅ Обновлены задания RP для пользователя {sender_id}, действие: {action_name}")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления RP заданий: {e}")

    else:
        # Action without a target
        escaped_custom_text = html.escape(custom_text) if custom_text else ""
        action_message = f"{sender_name} {html.escape(action_verb)}"
        if escaped_custom_text:
            action_message += f" {escaped_custom_text}"
        action_message += f"\n(HP {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP})"
        if sender_knocked_out:
            action_message += f"\n😩 {sender_name} нокаутирован(а)! Вы не можете совершать действия {RPConfig.HP_RECOVERY_TIME_SECONDS // 60} минут."
        await message.answer(action_message, parse_mode=ParseMode.HTML)
        logger.info(f"RP Action '{action_name}' performed by {sender_id}. Sender HP: {new_sender_hp}.")

        # ✅ ДОБАВЛЕНО: Обновляем задания для RP-действий без цели
        try:
            from core.group.stat.quests_handlers import update_rp_quests
            await update_rp_quests(
                user_id=sender_id,
                action_type='rp',
                unique_action=False,
                bot=bot
            )
            logger.info(f"✅ Обновлены задания RP для пользователя {sender_id}, действие без цели: {action_name}")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления RP заданий: {e}")

    # Delete original message if it wasn't a slash command
    if message.text and not message.text.startswith('/'):
        with suppress(TelegramAPIError):
            await message.delete()
            logger.info(f"Original message {message.message_id} deleted after RP action.")



@rp_router.message(Command("hp", "хп", "моехп", "моёхп", "здоровье", "мое здоровье", "моё здоровье"))
async def cmd_check_self_hp(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Shows the user's current HP and recovery status.
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
    Sends a list of available RP actions.
    """
    logger.info(f"User {message.from_user.id} requested RP actions list.")
    
    response_text = hbold("Доступные RP-действия:\n")
    for category, actions in RPActions.INTIMATE_ACTIONS.items():
        # Escape category name as well, just in case
        response_text += f"\n{hbold(html.escape(category.capitalize()))}:\n"
        for action_name, data in actions.items():
            hp_target = data.get('hp_change_target', 0)
            hp_sender = data.get('hp_change_sender', 0)
            
            hp_info = []
            # if hp_target != 0:
            #     hp_info.append(f"Цель: {hp_target:+d} HP")
            # if hp_sender != 0:
            #     hp_info.append(f"Вы: {hp_sender:+d} HP")
            
            hp_str = f" ({', '.join(hp_info)})" if hp_info else ""
            
            # Escape action_name to avoid HTML parsing issues
            escaped_action_name = html.escape(action_name)
            response_text += f"  - {escaped_action_name}{hp_str}\n" 

    # Escaping angle brackets in the instruction string
    response_text += "\nИспользуйте команду в формате: /&lt;действие&gt; или &lt;действие&gt; &lt;@пользователь&gt; [дополнительный текст]"
    
    await message.answer(response_text, parse_mode=ParseMode.HTML)


@rp_router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.text, ~F.text.startswith('/'))
async def handle_rp_action_via_text(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    settings = await db.get_group_settings(message.chat.id)
    if not settings.get("rp_enabled", True):
        return

    logger.debug(f"handle_rp_action_via_text: Received text message: '{message.text}' from user {message.from_user.id}.")
    action_name, target_user, custom_text = await _parse_rp_message(message, bot)

    if not action_name:
        logger.debug(f"handle_rp_action_via_text: No RP action found in text: '{message.text}'. Skipping.")
        return # This is not an RP action, skip

    logger.info(f"handle_rp_action_via_text: Processing RP action '{action_name}' (via text) for user {message.from_user.id}. Target: {target_user.id if target_user else 'None'}. Custom text: '{custom_text}'")
    await handle_rp_action(message, bot, profile_manager, action_name, target_user, custom_text)


@rp_router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.text.regexp(r"^/(\w+)(?:\s+(.*?))?$")) # Updated to capture custom_text
async def handle_rp_action_via_slash_command(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Handles RP actions sent as slash commands (e.g., /kiss @username).
    """
    logger.debug(f"handle_rp_action_via_slash_command: Received slash command: '{message.text}' from user {message.from_user.id}.")
    settings = await db.get_group_settings(message.chat.id)
    if not settings.get("rp_enabled", True):
        return
    try:
        await db.ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.first_name)
        await db.log_user_interaction(message.from_user.id, "group_message", "message")
    except Exception as e:
        logger.error(f"Failed to persist slash group message for user {message.from_user.id}: {e}")
    
    action_name, target_user, custom_text = await _parse_rp_message(message, bot)

    if not action_name:
        logger.debug(f"handle_rp_action_via_slash_command: No RP action found in command: '{message.text}'. Skipping.")
        return # This is not an RP action, skip

    logger.info(f"handle_rp_action_via_slash_command: Processing RP action '{action_name}' (via slash command) for user {message.from_user.id}. Target: {target_user.id if target_user else 'None'}. Custom text: '{custom_text}'")
    await handle_rp_action(message, bot, profile_manager, action_name, target_user, custom_text)


@rp_router.message(Command("heal", "лечить"))
async def cmd_heal(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Allows the user to manually restore HP for Lumcoins.
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

    # Perform healing
    new_hp, _ = await _update_user_hp(profile_manager, user_id, RPConfig.HEAL_AMOUNT)
    
    # Deduct Lumcoins
    await profile_manager.update_lumcoins(user_id, -RPConfig.HEAL_COST)

    # Set healing cooldown
    new_cooldown_ts = now + RPConfig.HEAL_COOLDOWN_SECONDS
    await profile_manager.update_user_rp_stats(user_id, heal_cooldown_ts=new_cooldown_ts)

    await message.reply(f"💊 Вы успешно вылечились на {RPConfig.HEAL_AMOUNT} HP! Ваше HP: {new_hp}/{RPConfig.MAX_HP}. Потрачено {RPConfig.HEAL_COST} Lumcoins.")
    logger.info(f"User {user_id} healed for {RPConfig.HEAL_AMOUNT} HP. New HP: {new_hp}. Lumcoins spent: {RPConfig.HEAL_COST}.")


async def periodic_hp_recovery_task(bot: Bot, profile_manager: ProfileManager, db_module: Any):
    """
    Background task for periodic HP recovery of knocked-out users.
    """
    logger.info("Periodic HP recovery task started.")
    while True:
        try:
            # Fixed: Used HP_RECOVERY_TIME_SECONDS instead of HP_RECOVERY_INTERVAL_SECONDS
            await asyncio.sleep(RPConfig.HP_RECOVERY_TIME_SECONDS) 
            logger.debug("Periodic recovery: Checking for users to recover HP.")
            
            now = time.time()
            # Get users whose HP <= MIN_HP and recovery time has expired
            # Use db_module to access database functions
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
    Sets up the RP module: registers handlers and passes dependencies.
    """
    if not HAS_PROFILE_MANAGER:
        logging.error("Not setting up RP handlers because ProfileManager is missing.")
        return

    # Removed rp_router.message.bind_arg(...) lines as they caused AttributeError.
    # Dependencies should be available via dispatcher context or explicitly passed to handlers.

    # Register handlers
    main_dp.include_router(rp_router)
    logger.info("RP router included and configured.")
