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

async def _process_rp_action(
    message: types.Message,
    bot: Bot,
    profile_manager: ProfileManager,
    command_text_payload: str
):
    if not HAS_PROFILE_MANAGER:
        await message.reply("⚠️ RP-модуль временно недоступен из-за внутренней ошибки конфигурации.")
        return
    sender_user = message.from_user
    if not sender_user:
        logger.warning("Cannot identify sender for an RP action.")
        return

    if await check_and_notify_rp_state(sender_user, bot, profile_manager, message_to_delete_on_block=message):
        return

    target_user: Optional[types.User] = None
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    else:
        entities = message.entities or []
        for entity in entities:
            if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                target_user = entity.user
                break

    if not target_user:
        await message.reply(
            "⚠️ Укажите цель: ответьте на сообщение пользователя или упомяните его (@ИмяПользователя так, чтобы он был кликабелен)."
        )
        return

    command, additional_text = get_command_from_text(command_text_payload)
    if not command:
        return

    if target_user.id == sender_user.id:
        await message.reply("🤦 Вы не можете использовать RP-команды на себе!")
        with suppress(TelegramAPIError): await message.delete()
        return
    if target_user.id == bot.id:
        await message.reply(f"🤖 Нельзя применять RP-действия ко мне, {sender_user.first_name}!")
        with suppress(TelegramAPIError): await message.delete()
        return
    if target_user.is_bot:
        await message.reply("👻 Действия на других ботов не имеют смысла.")
        with suppress(TelegramAPIError): await message.delete()
        return

    sender_name = get_user_display_name(sender_user)
    target_name = get_user_display_name(target_user)

    action_data = RPActions.ALL_ACTION_DATA.get(command, {})
    action_category = next((cat for cat, cmds in RPActions.INTIMATE_ACTIONS.items() if command in cmds), None)

    if action_category == "добрые" and action_data.get("hp_change_target", 0) > 0:
        sender_stats = await db.get_user_rp_stats(sender_user.id)
        heal_cd_ts = sender_stats.get('heal_cooldown_ts', 0.0)
        now = time.time()
        if now < heal_cd_ts:
            remaining_cd_str = format_timedelta(heal_cd_ts - now)
            await message.reply(
                f"{sender_name}, вы сможете снова использовать лечащие команды через {remaining_cd_str}."
            )
            with suppress(TelegramAPIError): await message.delete()
            return
        else:
            await db.update_user_rp_stats(
                sender_user.id, heal_cooldown_ts=now + RPConfig.HEAL_COOLDOWN_SECONDS
            )

    hp_change_target_val = action_data.get("hp_change_target", 0)
    hp_change_sender_val = action_data.get("hp_change_sender", 0)

    target_initial_stats = await db.get_user_rp_stats(target_user.id)
    target_current_hp_before_action = target_initial_stats.get('hp', RPConfig.DEFAULT_HP)
    if target_current_hp_before_action <= RPConfig.MIN_HP and \
       hp_change_target_val < 0 and \
       command != "превратить":
        await message.reply(f"{target_name} уже без сознания. Зачем же его мучить еще больше?", parse_mode=ParseMode.HTML)
        with suppress(TelegramAPIError): await message.delete()
        return

    new_target_hp, target_knocked_out = (target_current_hp_before_action, False)
    if hp_change_target_val != 0:
        new_target_hp, target_knocked_out = await _update_user_hp(profile_manager, target_user.id, hp_change_target_val)
    new_sender_hp, sender_knocked_out = await _update_user_hp(profile_manager, sender_user.id, hp_change_sender_val)

    command_display = command
    if command.endswith("ть"):
        command_display = command[:-2] + "л(-а)"
    elif command.endswith("ться"):
        command_display = command[:-3] + "л(-а)ся"

    response_text = f"{sender_name} {command_display} {target_name}"
    if additional_text:
        response_text += f" {additional_text}"

    hp_report_parts = []
    if hp_change_target_val > 0: hp_report_parts.append(f"{target_name} <b style='color:green;'>+{hp_change_target_val} HP</b>")
    elif hp_change_target_val < 0: hp_report_parts.append(f"{target_name} <b style='color:red;'>{hp_change_target_val} HP</b>")
    if hp_change_sender_val > 0: hp_report_parts.append(f"{sender_name} <b style='color:green;'>+{hp_change_sender_val} HP</b>")
    elif hp_change_sender_val < 0: hp_report_parts.append(f"{sender_name} <b style='color:red;'>{hp_change_sender_val} HP</b>")

    if hp_report_parts:
        response_text += f"\n({', '.join(hp_report_parts)})"

    status_lines = []
    if target_knocked_out:
        status_lines.append(f"😵 {target_name} теряет сознание! (Восстановление через {format_timedelta(RPConfig.HP_RECOVERY_TIME_SECONDS)})")
    elif hp_change_target_val != 0 :
        status_lines.append(f"HP {target_name}: {new_target_hp}/{RPConfig.MAX_HP}")

    if hp_change_sender_val != 0 or new_sender_hp < RPConfig.MAX_HP :
        status_lines.append(f"HP {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP}")

    if sender_knocked_out:
         status_lines.append(f"😵 {sender_name} перестарался и теряет сознание! (Восстановление через {format_timedelta(RPConfig.HP_RECOVERY_TIME_SECONDS)})")

    if status_lines:
        response_text += "\n\n" + "\n".join(status_lines)

    await message.reply(response_text, parse_mode=ParseMode.HTML)
    with suppress(TelegramAPIError):
        await message.delete()


@rp_router.message(F.text, lambda msg: get_command_from_text(msg.text)[0] is not None)
async def handle_rp_action_via_text(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    command_text = message.text
    await _process_rp_action(message, bot, profile_manager, command_text)

@rp_router.message(Command("rp"))
async def handle_rp_action_via_command(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    command_payload = message.text[len("/rp"):].strip()
    if not command_payload or get_command_from_text(command_payload)[0] is None:
        await message.reply(
            "⚠️ Укажите действие после <code>/rp</code>. Например: <code>/rp поцеловать</code>\n"
            "И не забудьте ответить на сообщение цели или упомянуть её.\n"
            "Список действий: /rp_commands", parse_mode=ParseMode.HTML
        )
        return
    await _process_rp_action(message, bot, profile_manager, command_payload)

@rp_router.message(F.text.lower().startswith((
    "моё хп", "мое хп", "моё здоровье", "мое здоровье", "хп", "здоровье"
)))
@rp_router.message(Command("myhp", "hp"))
async def cmd_check_self_hp(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    if not message.from_user: return
    if not HAS_PROFILE_MANAGER:
        await message.reply("⚠️ RP-модуль временно недоступен.")
        return
    
    user = message.from_user
    if await check_and_notify_rp_state(user, bot, profile_manager, message_to_delete_on_block=message):
        return

    stats = await db.get_user_rp_stats(user.id)
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    recovery_ts = stats.get('recovery_end_ts', 0.0)
    heal_cd_ts = stats.get('heal_cooldown_ts', 0.0)
    now = time.time()

    user_display_name = get_user_display_name(user)
    response_lines = [f"{user_display_name}, ваше состояние:"]
    response_lines.append(f"❤️ Здоровье: <b>{current_hp}/{RPConfig.MAX_HP}</b>")

    if current_hp <= RPConfig.MIN_HP and recovery_ts > now:
        response_lines.append(
            f"😵 Вы без сознания. Восстановление через: {format_timedelta(recovery_ts - now)}"
        )
    elif recovery_ts > 0.0 and recovery_ts <= now and current_hp <= RPConfig.MIN_HP:
        response_lines.append(f"⏳ HP должно было восстановиться, попробуйте еще раз или подождите немного.")

    if heal_cd_ts > now:
        response_lines.append(f"🕒 Кулдаун лечащих действий: {format_timedelta(heal_cd_ts - now)}")
    else:
        response_lines.append("✅ Лечащие действия: готовы!")

    await message.reply("\n".join(response_lines), parse_mode=ParseMode.HTML)

@rp_router.message(Command("rp_commands", "rphelp"))
@rp_router.message(F.text.lower().startswith(("список действий", "рп действия", "список рп", "команды рп")))
async def cmd_show_rp_actions_list(message: types.Message, bot: Bot):
    response_parts = ["<b>📋 Доступные RP-действия:</b>\n"]
    for category_name, actions in RPActions.ALL_ACTIONS_LIST_BY_CATEGORY.items():
        response_parts.append(f"<b>{category_name}:</b>")
        action_lines = [f"  • <code>{action}</code> (или <code>/rp {action}</code>)" for action in actions]
        response_parts.append("\n".join(action_lines))
        response_parts.append("")

    response_parts.append(
        "<i>Использование: ответьте на сообщение цели и напишите команду (<code>обнять</code>) "
        "или используйте <code>/rp обнять</code>, также отвечая или упоминая цель (@ник).</i>"
    )
    await message.reply("\n".join(response_parts), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

@rp_router.message(F.text.lower().contains("спасибо"))
async def reaction_thanks(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    if not message.from_user: return
    if await check_and_notify_rp_state(message.from_user, bot, profile_manager, message): return
    await message.reply("Всегда пожалуйста! 😊")

@rp_router.message(F.text.lower().contains("люблю"))
async def reaction_love(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    if not message.from_user: return
    if await check_and_notify_rp_state(message.from_user, bot, profile_manager, message): return
    await message.reply("И я вас люблю! ❤️🤡")

async def periodic_hp_recovery_task(bot: Bot, profile_manager: ProfileManager, db_module: Any):
    if not HAS_PROFILE_MANAGER:
        logger.error("Periodic HP recovery task cannot start: ProfileManager is missing.")
        return
    logger.info("Periodic HP recovery task started.")
    while True:
        await asyncio.sleep(60)
        now = time.time()
        try:
            if not hasattr(db_module, 'get_users_for_hp_recovery'):
                logger.error("Periodic HP recovery: db_module.get_users_for_hp_recovery function is missing!")
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
    if not HAS_PROFILE_MANAGER:
        logging.error("Not setting up RP handlers because ProfileManager is missing.")
        return
    main_dp.include_router(rp_router)
    logger.info("RP router included and configured.")
