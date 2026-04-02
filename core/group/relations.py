import logging
import time
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from aiogram.enums import ChatType
import database as db

logger = logging.getLogger(__name__)
relations_router = Router(name="relations_router")

REL_LABELS = {
    "friend": "🤝 Дружба",
    "romantic": "💘 Романтика",
    "married": "💍 Брак",
}


def _intimacy_tier_title(relation_type: str, intimacy_level: int) -> str:
    tiers = {
        "friend": ["знакомые", "друзья", "близкие друзья", "ОЧЕНЬ близкие друзья"],
        "romantic": ["пара", "крепкая пара", "неразлей вода"],
        "married": ["молодожёны", "супруги", "крепкая семья", "легендарный союз"],
    }
    names = tiers.get(relation_type, ["связь"])
    level = 0
    threshold = 100
    points = max(0, int(intimacy_level or 0))
    while points >= threshold:
        points -= threshold
        level += 1
        threshold += 50
    if level < len(names):
        return names[level]
    return f"{names[-1]}+"


async def _extract_target_user(message: types.Message, bot: Bot):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    text = (message.text or "").strip()
    for word in text.split():
        if word.startswith("@") and len(word) > 1:
            user_data = await db.get_user_by_username(word[1:])
            if user_data:
                try:
                    member = await bot.get_chat_member(message.chat.id, user_data["user_id"])
                    return member.user
                except Exception:
                    return None
    return None


def _build_request_keyboard(kind: str, from_user_id: int, to_user_id: int):
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Принять", callback_data=f"rel_accept:{kind}:{from_user_id}:{to_user_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"rel_decline:{kind}:{from_user_id}:{to_user_id}"),
    )
    return kb.as_markup()


async def _send_relation_request(message: types.Message, kind: str):
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.reply("Эта команда работает только в группе.")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("Ответьте этой командой на сообщение человека, с которым хотите отношения.")
        return

    from_user = message.from_user
    to_user = message.reply_to_message.from_user
    if from_user.id == to_user.id:
        await message.reply("С собой отношения заключать нельзя 😅")
        return

    if to_user.is_bot:
        await message.reply("С ботами отношения нельзя оформить.")
        return

    await message.reply(
        f"{to_user.mention_html()}, вам запрос: **{REL_LABELS[kind]}** от {from_user.mention_html()}",
        reply_markup=_build_request_keyboard(kind, from_user.id, to_user.id),
        parse_mode="HTML",
    )


@relations_router.message(Command("friend"))
@relations_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() in {"дружить", "дружба"}))
async def cmd_friend(message: types.Message):
    await _send_relation_request(message, "friend")


@relations_router.message(Command("love"))
@relations_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() in {"любовь", "отношения"}))
async def cmd_love(message: types.Message):
    await _send_relation_request(message, "romantic")


@relations_router.message(Command("marry"))
@relations_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() in {"пожениться", "брак"}))
async def cmd_marry(message: types.Message):
    await _send_relation_request(message, "married")


@relations_router.callback_query(F.data.regexp(r"^rel_accept:(friend|romantic|married):(\d+):(\d+)$"))
async def cb_accept_relation(callback: types.CallbackQuery, bot: Bot):
    kind, from_user_id, to_user_id = callback.data.split(":")[1:]
    from_user_id = int(from_user_id)
    to_user_id = int(to_user_id)

    if callback.from_user.id != to_user_id:
        await callback.answer("Только получатель может принять запрос.", show_alert=True)
        return

    await db.set_group_relationship(callback.message.chat.id, from_user_id, to_user_id, kind)
    from_member = await bot.get_chat_member(callback.message.chat.id, from_user_id)
    await callback.message.edit_text(
        f"🎉 {from_member.user.mention_html()} и {callback.from_user.mention_html()} теперь: {REL_LABELS[kind]}",
        parse_mode="HTML",
    )
    await callback.answer("Принято!")


@relations_router.callback_query(F.data.regexp(r"^rel_decline:(friend|romantic|married):(\d+):(\d+)$"))
async def cb_decline_relation(callback: types.CallbackQuery):
    kind, from_user_id, to_user_id = callback.data.split(":")[1:]
    to_user_id = int(to_user_id)

    if callback.from_user.id != to_user_id:
        await callback.answer("Только получатель может отклонить запрос.", show_alert=True)
        return

    await callback.message.edit_text("❌ Запрос отклонён.")
    await callback.answer("Отклонено")


@relations_router.message(Command("breakup"))
@relations_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() in {"расстаться", "развод"}))
async def cmd_breakup(message: types.Message):
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("Ответьте на сообщение человека, с которым нужно завершить отношения.")
        return
    partner_id = message.reply_to_message.from_user.id
    await db.remove_group_relationship(message.chat.id, message.from_user.id, partner_id)
    await message.reply("✅ Отношения завершены.")


@relations_router.message(Command("myrelations"))
@relations_router.message(Command("relations"))
@relations_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() in {"мои отношения", "отношения мои", "отношения", "отн"}))
async def cmd_my_relations(message: types.Message, bot: Bot):
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return
    relations = await db.get_user_group_relationships(message.chat.id, message.from_user.id)
    if not relations:
        await message.reply("У вас пока нет отношений в этой группе.")
        return

    lines = ["💞 Ваши отношения в этой группе:"]
    for rel in relations[:10]:
        member = await bot.get_chat_member(message.chat.id, rel["partner_id"])
        tier = _intimacy_tier_title(rel["relation_type"], rel.get("intimacy_level", 0))
        lines.append(
            f"• {REL_LABELS.get(rel['relation_type'], rel['relation_type'])} с {member.user.full_name} "
            f"(близость: {rel.get('intimacy_level', 0)}, статус: {tier})"
        )
    await message.reply("\n".join(lines))


@relations_router.message(Command("sex"))
@relations_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower().startswith("потрахаться")))
async def cmd_sex_offer(message: types.Message, bot: Bot):
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return

    from_user = message.from_user
    target_user = await _extract_target_user(message, bot)
    if not target_user:
        await message.reply("Ответьте на сообщение партнёра или укажите @username: `потрахаться @user`")
        return
    if from_user.id == target_user.id or target_user.is_bot:
        await message.reply("Нужен живой партнёр.")
        return

    relation = await db.get_group_relationship(message.chat.id, from_user.id, target_user.id)
    if not relation:
        await message.reply("❌ Эта команда доступна только для оформленных отношений.")
        return

    cooldown = 24 * 60 * 60
    last_used = await db.get_relationship_action_last_used(message.chat.id, from_user.id, target_user.id, "sex_offer")
    now = time.time()
    if now - last_used < cooldown:
        rem = int(cooldown - (now - last_used))
        await message.reply(f"⏳ Перезарядка команды: {rem // 3600}ч {(rem % 3600) // 60}м.")
        return

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Согласиться", callback_data=f"sex_accept:{from_user.id}:{target_user.id}"),
        InlineKeyboardButton(text="❌ Отказать", callback_data=f"sex_decline:{from_user.id}:{target_user.id}"),
    )
    await message.reply(
        f"{target_user.mention_html()}, {from_user.mention_html()} предлагает потрахаться 😏",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@relations_router.callback_query(F.data.regexp(r"^sex_accept:(\d+):(\d+)$"))
async def cb_sex_accept(callback: types.CallbackQuery, bot: Bot):
    _, from_user_id, to_user_id = callback.data.split(":")
    from_user_id, to_user_id = int(from_user_id), int(to_user_id)
    if callback.from_user.id != to_user_id:
        await callback.answer("Только приглашённый может ответить.", show_alert=True)
        return

    relation = await db.get_group_relationship(callback.message.chat.id, from_user_id, to_user_id)
    if not relation:
        await callback.message.edit_text("❌ Отношения не найдены.")
        return

    now = time.time()
    await db.set_relationship_action_last_used(callback.message.chat.id, from_user_id, to_user_id, "sex_offer", now)
    new_level = await db.increment_relationship_intimacy(callback.message.chat.id, from_user_id, to_user_id, delta=30)
    tier = _intimacy_tier_title(relation["relation_type"], new_level or relation.get("intimacy_level", 0))
    from_member = await bot.get_chat_member(callback.message.chat.id, from_user_id)
    await callback.message.edit_text(
        f"🔥 {from_member.user.mention_html()} и {callback.from_user.mention_html()} провели жаркую ночь.\n"
        f"💞 Близость +30 → {new_level}\n"
        f"🏷 Текущий статус: {tier}",
        parse_mode="HTML",
    )
    await callback.answer("Успешно!")


@relations_router.callback_query(F.data.regexp(r"^sex_decline:(\d+):(\d+)$"))
async def cb_sex_decline(callback: types.CallbackQuery):
    _, _, to_user_id = callback.data.split(":")
    if callback.from_user.id != int(to_user_id):
        await callback.answer("Только приглашённый может ответить.", show_alert=True)
        return
    await callback.message.edit_text("❌ Предложение отклонено.")
    await callback.answer("Отклонено")
