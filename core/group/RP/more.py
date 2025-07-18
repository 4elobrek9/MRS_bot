from core.group.RP.rmain import *
from core.group.RP.config import *
from core.group.RP.actions import *

def get_user_display_name(user: types.User) -> str:
    name = f"@{user.username}" if user.username else user.full_name
    return name

async def _update_user_hp(
    profile_manager: ProfileManager,
    user_id: int,
    hp_change: int
) -> Tuple[int, bool]:
    stats = await db.get_user_rp_stats(user_id)
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    new_hp = max(RPConfig.MIN_HP, min(RPConfig.MAX_HP, current_hp + hp_change))
    knocked_out_this_time = False
    update_fields = {'hp': new_hp}

    if new_hp <= RPConfig.MIN_HP and current_hp > RPConfig.MIN_HP:
        recovery_ts = time.time() + RPConfig.HP_RECOVERY_TIME_SECONDS
        update_fields['recovery_end_ts'] = recovery_ts
        knocked_out_this_time = True
        logger.info(f"User {user_id} HP dropped to {new_hp}. Recovery timer set for {RPConfig.HP_RECOVERY_TIME_SECONDS}s.")
    elif new_hp > RPConfig.MIN_HP and stats.get('recovery_end_ts', 0.0) > 0 :
        update_fields['recovery_end_ts'] = 0.0
        logger.info(f"User {user_id} HP recovered above {RPConfig.MIN_HP}. Recovery timer reset.")

    await db.update_user_rp_stats(user_id, **update_fields)
    return new_hp, knocked_out_this_time

def get_command_from_text(text: Optional[str]) -> Tuple[Optional[str], str]:
    if not text:
        return None, ""
    text_lower = text.lower()
    for cmd in RPActions.SORTED_COMMANDS_FOR_PARSING:
        if text_lower.startswith(cmd) and \
           (len(text_lower) == len(cmd) or text_lower[len(cmd)].isspace()):
            additional_text = text[len(cmd):].strip()
            return cmd, additional_text
    return None, ""

def format_timedelta(seconds: float) -> str:
    if seconds <= 0:
        return "уже можно"
    total_seconds = int(seconds)
    minutes = total_seconds // 60
    secs = total_seconds % 60
    if minutes > 0 and secs > 0:
        return f"{minutes} мин {secs} сек"
    elif minutes > 0:
        return f"{minutes} мин"
    return f"{secs} сек"

async def check_and_notify_rp_state(
    user: types.User,
    bot: Bot,
    profile_manager: ProfileManager,
    message_to_delete_on_block: Optional[types.Message] = None
) -> bool:
    if not HAS_PROFILE_MANAGER:
        logger.error(f"Cannot check RP state for user {user.id} due to missing ProfileManager.")
        try:
            await bot.send_message(user.id, "⚠️ Произошла ошибка с модулем профилей, RP-действия временно недоступны.")
        except TelegramAPIError:
            pass
        if message_to_delete_on_block:
             with suppress(TelegramAPIError): await message_to_delete_on_block.delete()
        return True

    stats = await db.get_user_rp_stats(user.id)
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    recovery_ts = stats.get('recovery_end_ts', 0.0)
    now = time.time()

    if current_hp <= RPConfig.MIN_HP:
        if recovery_ts > 0.0 and now < recovery_ts:
            remaining_recovery = recovery_ts - now
            time_str = format_timedelta(remaining_recovery)
            try:
                await bot.send_message(
                    user.id,
                    f"Вы сейчас не можете совершать RP-действия (HP: {current_hp}).\n"
                    f"Автоматическое восстановление {RPConfig.HP_RECOVERY_AMOUNT} HP через: {time_str}."
                )
            except TelegramAPIError as e:
                logger.warning(f"Could not send RP state PM to user {user.id}: {e}")
                if message_to_delete_on_block:
                    await message_to_delete_on_block.reply(
                        f"{get_user_display_name(user)}, вы пока не можете действовать (HP: {current_hp}). "
                        f"Восстановление через {time_str}."
                    )
            if message_to_delete_on_block:
                with suppress(TelegramAPIError): await message_to_delete_on_block.delete()
            return True
        elif recovery_ts == 0.0 or now >= recovery_ts:
            recovered_hp, _ = await _update_user_hp(profile_manager, user.id, RPConfig.HP_RECOVERY_AMOUNT)
            logger.info(f"User {user.id} HP auto-recovered to {recovered_hp} upon action attempt.")
            try:
                await bot.send_message(user.id, f"Ваше HP восстановлено до {recovered_hp}! Теперь вы можете совершать RP-действия.")
            except TelegramAPIError:
                pass
            return False
    return False
