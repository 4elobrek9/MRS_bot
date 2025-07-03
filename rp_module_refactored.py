import asyncio
import time
import random
import logging
from typing import Dict, Any, Optional, List, Tuple, Set
import aiosqlite
from aiogram import Router, types, F, Bot
from aiogram.enums import ChatType, ParseMode, MessageEntityType
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError
from contextlib import suppress
import database as db

try:
    from group_stat import ProfileManager as RealProfileManager
    HAS_PROFILE_MANAGER = True
except ImportError:
    logging.critical("CRITICAL: Module 'group_stat' or 'ProfileManager' not found. RP functionality will be severely impaired or non-functional.")
    HAS_PROFILE_MANAGER = False
    # Заглушка ProfileManager, которая соответствует интерфейсу RealProfileManager
    class RealProfileManager:
        async def get_user_rp_stats(self, user_id: int) -> Dict[str, Any]:
            return {'hp': 100, 'recovery_end_ts': 0.0, 'heal_cooldown_ts': 0.0}
        async def update_user_rp_stats(self, user_id: int, **kwargs: Any) -> None:
            pass
        async def get_user_profile(self, user: types.User) -> Optional[Dict[str, Any]]:
            return None
        async def connect(self) -> None:
            pass
        async def close(self) -> None:
            pass

# Присваиваем ProfileManager либо реальный класс, либо заглушку
ProfileManager = RealProfileManager

logger = logging.getLogger(__name__)

# Инициализация роутера для RP-модуля. Фильтруем сообщения только для групп и супергрупп.
rp_router = Router(name="rp_module")
rp_router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

class RPConfig:
    """Конфигурационные параметры для RP-системы."""
    DEFAULT_HP: int = 100
    MAX_HP: int = 150
    MIN_HP: int = 0 # Минимальное HP, при котором считается "без сознания"
    HEAL_COOLDOWN_SECONDS: int = 120 
    HP_RECOVERY_TIME_SECONDS: int = 600 # 10 минут время восстановления из нокаута
    HP_RECOVERY_AMOUNT: int = 25 # Количество HP, восстанавливаемое за раз

class RPActions:
    """Определения RP-действий и их эффектов на HP."""
    INTIMATE_ACTIONS: Dict[str, Dict[str, Dict[str, int]]] = {
        "добрые": {
            "поцеловать": {"hp_change_target": +10, "hp_change_sender": +1},
            "обнять": {"hp_change_target": +15, "hp_change_sender": +5},
            "погладить": {"hp_change_target": +5, "hp_change_sender": +2},
            "романтический поцелуй": {"hp_change_target": +20, "hp_change_sender": +10},
            "трахнуть": {"hp_change_target": +30, "hp_change_sender": +15},
            "поцеловать в щёчку": {"hp_change_target": +7, "hp_change_sender": +3},
            "прижать к себе": {"hp_change_target": +12, "hp_change_sender": +6},
            "покормить": {"hp_change_target": +9, "hp_change_sender": -2},
            "напоить": {"hp_change_target": +6, "hp_change_sender": -1},
            "сделать массаж": {"hp_change_target": +15, "hp_change_sender": +3},
            "спеть песню": {"hp_change_target": +5, "hp_change_sender": +1},
            "подарить цветы": {"hp_change_target": +12, "hp_change_sender": -12},
            "подрочить": {"hp_change_target": +12, "hp_change_sender": 0},
            "полечить": {"hp_change_target": +25, "hp_change_sender": -5},
        },
        "нейтральные": {
            "толкнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "схватить": {"hp_change_target": 0, "hp_change_sender": 0},
            "помахать": {"hp_change_target": 0, "hp_change_sender": 0},
            "кивнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "похлопать": {"hp_change_target": 0, "hp_change_sender": 0},
            "постучать": {"hp_change_target": 0, "hp_change_sender": 0},
            "попрощаться": {"hp_change_target": 0, "hp_change_sender": 0},
            "шепнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "почесать спинку": {"hp_change_target": +5, "hp_change_sender": 0},
            "успокоить": {"hp_change_target": +5, "hp_change_sender": +1},
            "заплакать": {}, "засмеяться": {}, "удивиться": {}, "подмигнуть": {},
        },
        "злые": {
            "уебать": {"hp_change_target": -20, "hp_change_sender": -2},
            "схватить за шею": {"hp_change_target": -25, "hp_change_sender": -3},
            "ударить": {"hp_change_target": -10, "hp_change_sender": -1},
            "укусить": {"hp_change_target": -15, "hp_change_sender": 0},
            "шлепнуть": {"hp_change_target": -8, "hp_change_sender": 0},
            "пощечина": {"hp_change_target": -12, "hp_change_sender": -1},
            "пнуть": {"hp_change_target": -10, "hp_change_sender": 0},
            "ущипнуть": {"hp_change_target": -7, "hp_change_sender": 0},
            "толкнуть сильно": {"hp_change_target": -9, "hp_change_sender": -1},
            "обозвать": {"hp_change_target": -5, "hp_change_sender": 0},
            "плюнуть": {"hp_change_target": -6, "hp_change_sender": 0},
            "превратить": {"hp_change_target": -80, "hp_change_sender": -10},
            "обидеть": {"hp_change_target": -7, "hp_change_sender": 0},
            "разозлиться": {"hp_change_target": -2, "hp_change_sender": -1},
            "испугаться": {"hp_change_target": -1, "hp_change_sender": 0},
            "издеваться": {"hp_change_target": -10, "hp_change_sender": -1},
        }
    }
    # Объединение всех действий в один словарь для удобного доступа
    ALL_ACTION_DATA: Dict[str, Dict[str, int]] = {
        action: data if data else {}
        for category_actions in INTIMATE_ACTIONS.values()
        for action, data in category_actions.items()
    }
    # Список команд, отсортированных по длине для правильного парсинга (длинные команды первыми)
    SORTED_COMMANDS_FOR_PARSING: List[str] = sorted(
        ALL_ACTION_DATA.keys(), key=len, reverse=True
    )
    # Действия, сгруппированные по категориям для отображения в списке команд
    ALL_ACTIONS_LIST_BY_CATEGORY: Dict[str, List[str]] = {
        "Добрые действия ❤️": list(INTIMATE_ACTIONS["добрые"].keys()),
        "Нейтральные действия 😐": list(INTIMATE_ACTIONS["нейтральные"].keys()),
        "Злые действия 💀": list(INTIMATE_ACTIONS["злые"].keys())
    }

def get_user_display_name(user: types.User) -> str:
    """
    Формирует отображаемое имя пользователя для использования в сообщениях.
    Предпочитает username, если доступен, иначе использует полное имя.
    """
    name = f"@{user.username}" if user.username else user.full_name
    return name

async def _update_user_hp(
    profile_manager: ProfileManager,
    user_id: int,
    hp_change: int
) -> Tuple[int, bool]:
    """
    Обновляет HP пользователя и проверяет, потерял ли он сознание.
    Корректирует HP, чтобы оно оставалось в допустимых пределах (MIN_HP до MAX_HP).

    Args:
        profile_manager (ProfileManager): Менеджер профилей для доступа к RP-статистике.
        user_id (int): ID пользователя.
        hp_change (int): Изменение HP (может быть положительным или отрицательным).

    Returns:
        Tuple[int, bool]: Новое значение HP и флаг, указывающий, потерял ли пользователь сознание.
    """
    stats = await db.get_user_rp_stats(user_id) # Использование db.get_user_rp_stats
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    new_hp = max(RPConfig.MIN_HP, min(RPConfig.MAX_HP, current_hp + hp_change))
    knocked_out_this_time = False
    update_fields = {'hp': new_hp}

    # Если HP упало до или ниже нуля, и это не было так ранее
    if new_hp <= RPConfig.MIN_HP and current_hp > RPConfig.MIN_HP:
        recovery_ts = time.time() + RPConfig.HP_RECOVERY_TIME_SECONDS
        update_fields['recovery_end_ts'] = recovery_ts
        knocked_out_this_time = True
        logger.info(f"User {user_id} HP dropped to {new_hp}. Recovery timer set for {RPConfig.HP_RECOVERY_TIME_SECONDS}s.")
    # Если HP восстановилось выше нуля
    elif new_hp > RPConfig.MIN_HP and stats.get('recovery_end_ts', 0.0) > 0 :
        # Сбрасываем таймер восстановления, если пользователь восстановился
        update_fields['recovery_end_ts'] = 0.0
        logger.info(f"User {user_id} HP recovered above {RPConfig.MIN_HP}. Recovery timer reset.")

    await db.update_user_rp_stats(user_id, **update_fields) # Использование db.update_user_rp_stats
    return new_hp, knocked_out_this_time

def get_command_from_text(text: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Извлекает RP-команду из текстового сообщения.
    Ищет самую длинную совпадающую команду в начале строки.

    Args:
        text (Optional[str]): Входной текст сообщения.

    Returns:
        Tuple[Optional[str], str]: Найденная команда (или None) и остальной текст.
    """
    if not text:
        return None, ""
    text_lower = text.lower()
    for cmd in RPActions.SORTED_COMMANDS_FOR_PARSING:
        # Проверяем, что команда либо является полным сообщением, либо за ней идет пробел
        if text_lower.startswith(cmd) and \
           (len(text_lower) == len(cmd) or text_lower[len(cmd)].isspace()):
            additional_text = text[len(cmd):].strip()
            return cmd, additional_text
    return None, ""

def format_timedelta(seconds: float) -> str:
    """
    Форматирует количество секунд в читаемый формат (мин/сек).

    Args:
        seconds (float): Количество секунд.

    Returns:
        str: Отформатированная строка времени.
    """
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
    """
    Проверяет состояние HP пользователя и уведомляет его, если он не может выполнять RP-действия
    из-за низкого HP или активного таймера восстановления.

    Args:
        user (types.User): Объект пользователя, который пытается выполнить действие.
        bot (Bot): Экземпляр бота.
        profile_manager (ProfileManager): Менеджер профилей.
        message_to_delete_on_block (Optional[types.Message]): Сообщение, которое нужно удалить,
                                                              если действие заблокировано (например, RP-команда).

    Returns:
        bool: True, если действие заблокировано (пользователь без HP), False иначе.
    """
    if not HAS_PROFILE_MANAGER:
        logger.error(f"Cannot check RP state for user {user.id} due to missing ProfileManager.")
        try:
            # Отправка личного сообщения пользователю об ошибке модуля
            await bot.send_message(user.id, "⚠️ Произошла ошибка с модулем профилей, RP-действия временно недоступны.")
        except TelegramAPIError:
            pass # Если не удалось отправить PM, просто игнорируем
        if message_to_delete_on_block:
             with suppress(TelegramAPIError): await message_to_delete_on_block.delete()
        return True # Действие заблокировано

    stats = await db.get_user_rp_stats(user.id) # Использование db.get_user_rp_stats
    current_hp = stats.get('hp', RPConfig.DEFAULT_HP)
    recovery_ts = stats.get('recovery_end_ts', 0.0)
    now = time.time()

    if current_hp <= RPConfig.MIN_HP:
        if recovery_ts > 0.0 and now < recovery_ts:
            # Пользователь без сознания, и таймер восстановления еще не истек
            remaining_recovery = recovery_ts - now
            time_str = format_timedelta(remaining_recovery)
            try:
                # Попытка отправить личное сообщение
                await bot.send_message(
                    user.id,
                    f"Вы сейчас не можете совершать RP-действия (HP: {current_hp}).\n"
                    f"Автоматическое восстановление {RPConfig.HP_RECOVERY_AMOUNT} HP через: {time_str}."
                )
            except TelegramAPIError as e:
                # Если PM не удался, отправляем сообщение в чат
                logger.warning(f"Could not send RP state PM to user {user.id}: {e}")
                if message_to_delete_on_block:
                    await message_to_delete_on_block.reply(
                        f"{get_user_display_name(user)}, вы пока не можете действовать (HP: {current_hp}). "
                        f"Восстановление через {time_str}."
                    )
            if message_to_delete_on_block:
                with suppress(TelegramAPIError): await message_to_delete_on_block.delete()
            return True # Действие заблокировано
        elif recovery_ts == 0.0 or now >= recovery_ts:
            # Пользователь без сознания, но таймер истек или не был установлен. Восстанавливаем HP.
            recovered_hp, _ = await _update_user_hp(profile_manager, user.id, RPConfig.HP_RECOVERY_AMOUNT)
            logger.info(f"User {user.id} HP auto-recovered to {recovered_hp} upon action attempt.")
            try:
                await bot.send_message(user.id, f"Ваше HP восстановлено до {recovered_hp}! Теперь вы можете совершать RP-действия.")
            except TelegramAPIError:
                pass # Не критично, если не удалось отправить уведомление
            return False # Действие не заблокировано, можно продолжить
    return False # Действие не заблокировано (HP в норме)

async def _process_rp_action(
    message: types.Message,
    bot: Bot,
    profile_manager: ProfileManager,
    command_text_payload: str
):
    """
    Обрабатывает RP-действие, инициированное пользователем.
    Определяет отправителя, цель, применяет изменения HP,
    и отправляет ответное сообщение.

    Args:
        message (types.Message): Объект сообщения Telegram.
        bot (Bot): Экземпляр бота.
        profile_manager (ProfileManager): Менеджер профилей.
        command_text_payload (str): Текст команды RP (например, "поцеловать @username").
    """
    if not HAS_PROFILE_MANAGER:
        await message.reply("⚠️ RP-модуль временно недоступен из-за внутренней ошибки конфигурации.")
        return
    sender_user = message.from_user
    if not sender_user:
        logger.warning("Cannot identify sender for an RP action.")
        return

    # Проверка состояния HP отправителя перед выполнением действия
    if await check_and_notify_rp_state(sender_user, bot, profile_manager, message_to_delete_on_block=message):
        return

    target_user: Optional[types.User] = None
    # Попытка определить цель по ответу на сообщение
    if message.reply_to_message and message.reply_to_message.from_user:
        target_user = message.reply_to_message.from_user
    else:
        # Попытка определить цель по упоминанию в тексте сообщения
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

    # Извлечение команды и дополнительного текста
    command, additional_text = get_command_from_text(command_text_payload)
    if not command:
        # Если команда не найдена (чего не должно быть, так как обработчик уже отфильтровал), выходим
        return

    # Проверки на использование команд на себе, ботах
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

    # Логика кулдауна для "добрых" (лечащих) действий
    if action_category == "добрые" and action_data.get("hp_change_target", 0) > 0:
        sender_stats = await db.get_user_rp_stats(sender_user.id) # Использование db.get_user_rp_stats
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
            # Устанавливаем новый кулдаун
            await db.update_user_rp_stats( # Использование db.update_user_rp_stats
                sender_user.id, heal_cooldown_ts=now + RPConfig.HEAL_COOLDOWN_SECONDS
            )

    hp_change_target_val = action_data.get("hp_change_target", 0)
    hp_change_sender_val = action_data.get("hp_change_sender", 0)

    # Проверка, можно ли нанести урон цели, если она уже без сознания
    target_initial_stats = await db.get_user_rp_stats(target_user.id) # Использование db.get_user_rp_stats
    target_current_hp_before_action = target_initial_stats.get('hp', RPConfig.DEFAULT_HP)
    if target_current_hp_before_action <= RPConfig.MIN_HP and \
       hp_change_target_val < 0 and \
       command != "превратить": # "превратить" может быть исключением
        await message.reply(f"{target_name} уже без сознания. Зачем же его мучить еще больше?", parse_mode=ParseMode.HTML)
        with suppress(TelegramAPIError): await message.delete()
        return

    # Обновление HP цели и отправителя
    new_target_hp, target_knocked_out = (target_current_hp_before_action, False) # Дефолтные значения
    if hp_change_target_val != 0: # Обновляем HP цели, только если есть изменение
        new_target_hp, target_knocked_out = await _update_user_hp(profile_manager, target_user.id, hp_change_target_val)
    new_sender_hp, sender_knocked_out = await _update_user_hp(profile_manager, sender_user.id, hp_change_sender_val)


    # Измененная логика для использования бесполых окончаний
    # Здесь мы будем проверять, заканчивается ли глагол на "ть" и заменять его на "л(-а)"
    command_display = command
    if command.endswith("ть"):
        command_display = command[:-2] + "л(-а)" # Например, "поцеловать" -> "поцеловал(-а)"
    elif command.endswith("ться"):
        command_display = command[:-3] + "л(-а)ся" # Например, "отмыться" -> "отмыл(-а)ся"


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
    elif hp_change_target_val != 0 : # Показываем HP цели, если оно изменилось
        status_lines.append(f"HP {target_name}: {new_target_hp}/{RPConfig.MAX_HP}")

    if hp_change_sender_val != 0 or new_sender_hp < RPConfig.MAX_HP : # Показываем HP отправителя, если оно изменилось или низкое
        status_lines.append(f"HP {sender_name}: {new_sender_hp}/{RPConfig.MAX_HP}")

    if sender_knocked_out:
         status_lines.append(f"😵 {sender_name} перестарался и теряет сознание! (Восстановление через {format_timedelta(RPConfig.HP_RECOVERY_TIME_SECONDS)})")

    if status_lines:
        response_text += "\n\n" + "\n".join(status_lines)

    await message.reply(response_text, parse_mode=ParseMode.HTML)
    with suppress(TelegramAPIError): # Пытаемся удалить исходное сообщение с командой
        await message.delete()

@rp_router.message(F.text, lambda msg: get_command_from_text(msg.text)[0] is not None)
async def handle_rp_action_via_text(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Обрабатывает RP-действия, если команда найдена в тексте сообщения.
    """
    command_text = message.text
    await _process_rp_action(message, bot, profile_manager, command_text)

@rp_router.message(Command("rp"))
async def handle_rp_action_via_command(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """
    Обрабатывает RP-действия, инициированные командой /rp.
    """
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
    """
    Позволяет пользователю проверить свое текущее HP и состояние.
    """
    if not message.from_user: return # Сообщения без отправителя игнорируем
    if not HAS_PROFILE_MANAGER:
        await message.reply("⚠️ RP-модуль временно недоступен.")
        return
    
    user = message.from_user
    # Проверяем, может ли пользователь действовать (не без сознания)
    if await check_and_notify_rp_state(user, bot, profile_manager, message_to_delete_on_block=message):
        return

    stats = await db.get_user_rp_stats(user.id) # Использование db.get_user_rp_stats
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
        # Это случай, когда таймер восстановления истек, но HP по какой-то причине еще не обновилось
        response_lines.append(f"⏳ HP должно было восстановиться, попробуйте еще раз или подождите немного.")

    if heal_cd_ts > now:
        response_lines.append(f"🕒 Кулдаун лечащих действий: {format_timedelta(heal_cd_ts - now)}")
    else:
        response_lines.append("✅ Лечащие действия: готовы!")

    await message.reply("\n".join(response_lines), parse_mode=ParseMode.HTML)

@rp_router.message(Command("rp_commands", "rphelp"))
@rp_router.message(F.text.lower().startswith(("список действий", "рп действия", "список рп", "команды рп")))
async def cmd_show_rp_actions_list(message: types.Message, bot: Bot):
    """
    Показывает полный список доступных RP-действий, сгруппированных по категориям.
    """
    response_parts = ["<b>📋 Доступные RP-действия:</b>\n"]
    for category_name, actions in RPActions.ALL_ACTIONS_LIST_BY_CATEGORY.items():
        response_parts.append(f"<b>{category_name}:</b>")
        action_lines = [f"  • <code>{action}</code> (или <code>/rp {action}</code>)" for action in actions]
        response_parts.append("\n".join(action_lines))
        response_parts.append("") # Пустая строка для разделения категорий

    response_parts.append(
        "<i>Использование: ответьте на сообщение цели и напишите команду (<code>обнять</code>) "
        "или используйте <code>/rp обнять</code>, также отвечая или упоминая цель (@ник).</i>"
    )
    await message.reply("\n".join(response_parts), parse_mode=ParseMode.HTML, disable_web_page_preview=True)

@rp_router.message(F.text.lower().contains("спасибо"))
async def reaction_thanks(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """Пример: Реакция на "спасибо"."""
    if not message.from_user: return
    # Проверяем состояние HP перед ответом
    if await check_and_notify_rp_state(message.from_user, bot, profile_manager, message): return
    await message.reply("Всегда пожалуйста! 😊")

@rp_router.message(F.text.lower().contains("люблю"))
async def reaction_love(message: types.Message, bot: Bot, profile_manager: ProfileManager):
    """Пример: Реакция на "люблю"."""
    if not message.from_user: return
    # Проверяем состояние HP перед ответом
    if await check_and_notify_rp_state(message.from_user, bot, profile_manager, message): return
    await message.reply("И я вас люблю! ❤️🤡")


async def periodic_hp_recovery_task(bot: Bot, profile_manager: ProfileManager, db_module: Any):
    """
    Периодическая фоновая задача для восстановления HP пользователей.
    Сканирует базу данных на предмет пользователей, которым требуется восстановление HP.
    """
    if not HAS_PROFILE_MANAGER:
        logger.error("Periodic HP recovery task cannot start: ProfileManager is missing.")
        return
    logger.info("Periodic HP recovery task started.")
    while True:
        await asyncio.sleep(60) # Проверка каждую минуту
        now = time.time()
        try:
            # Проверяем наличие функции в db_module (для безопасности)
            if not hasattr(db_module, 'get_users_for_hp_recovery'):
                logger.error("Periodic HP recovery: db_module.get_users_for_hp_recovery function is missing!")
                continue
            
            # Получаем пользователей, нуждающихся в восстановлении HP
            users_to_recover: List[Tuple[int, int]] = await db_module.get_users_for_hp_recovery(now, RPConfig.MIN_HP)

            if users_to_recover:
                logger.info(f"Periodic recovery: Found {len(users_to_recover)} users for HP recovery.")
                for user_id, current_hp_val in users_to_recover:
                    # Восстанавливаем HP и сбрасываем таймер
                    new_hp, _ = await _update_user_hp(profile_manager, user_id, RPConfig.HP_RECOVERY_AMOUNT)
                    logger.info(f"Periodic recovery: User {user_id} HP auto-recovered from {current_hp_val} to {new_hp}.")
                    try:
                        # Отправляем уведомление пользователю в PM
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

