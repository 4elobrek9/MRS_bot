import logging
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
@relations_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() == "дружить"))
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
@relations_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() in {"мои отношения", "отношения мои"}))
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
        lines.append(f"• {REL_LABELS.get(rel['relation_type'], rel['relation_type'])} с {member.user.full_name}")
    await message.reply("\n".join(lines))

