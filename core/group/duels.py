import random
import time
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ChatType
import database as db

duel_router = Router(name="duel_router")
duel_sessions = {}
game_sessions = {}
duel_cooldowns = {}


def _kb(buttons):
    b = InlineKeyboardBuilder()
    b.row(*buttons)
    return b.as_markup()


@duel_router.message(Command("sharp_knife"))
@duel_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() == "точить нож"))
async def cmd_sharpen_knife(message: types.Message, profile_manager):
    user_id = message.from_user.id
    # цена прокачки силы
    cost = 500
    lum = await profile_manager.get_lumcoins(user_id)
    if lum < cost:
        await message.reply(f"❌ Нужно {cost} LUM для заточки ножа.")
        return
    await profile_manager.update_lumcoins(user_id, -cost)
    stats = await db.update_duel_stats(user_id, strength_delta=5)
    await message.reply(f"🔪 Сила увеличена! Текущая сила: {stats['strength']}")


@duel_router.message(Command("play"))
@duel_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() == "играть"))
async def cmd_play_game(message: types.Message):
    user_id = message.from_user.id
    game_sessions[user_id] = {"stage": 1, "hits": 0, "last_hit": 0}
    kb = _kb([InlineKeyboardButton(text="🟩🎲", callback_data=f"game_hit:{user_id}")])
    await message.reply("🎮 Нажми зелёный кубик 5 раз подряд (не позже 0.5 сек между кликами).", reply_markup=kb)


@duel_router.callback_query(F.data.regexp(r"^game_hit:(\d+)$"))
async def cb_game_hit(callback: types.CallbackQuery):
    user_id = int(callback.data.split(":")[1])
    if callback.from_user.id != user_id:
        await callback.answer("Это не ваша игра.", show_alert=True)
        return
    sess = game_sessions.get(user_id)
    if not sess:
        await callback.answer("Сессия игры не найдена.", show_alert=True)
        return

    now = time.time()
    if sess["hits"] > 0 and now - sess["last_hit"] > 0.5:
        del game_sessions[user_id]
        await callback.message.edit_text("⌛ Слишком медленно. Попробуй ещё раз командой 'играть'.")
        return

    sess["hits"] += 1
    sess["last_hit"] = now

    if sess["hits"] < 5:
        await callback.answer(f"Попадание {sess['hits']}/5")
        return

    # этап 2: 3 кубика, один зелёный
    choices = ["🟥🎲", "🟥🎲", "🟩🎲"]
    random.shuffle(choices)
    kb = InlineKeyboardBuilder()
    for idx, c in enumerate(choices):
        color = "green" if "🟩" in c else "red"
        kb.add(InlineKeyboardButton(text=c, callback_data=f"game_pick:{user_id}:{color}"))
    kb.adjust(3)
    sess["stage"] = 2
    await callback.message.edit_text("🔥 Финал! Нажми ЗЕЛЕНЫЙ кубик.", reply_markup=kb.as_markup())
    await callback.answer()


@duel_router.callback_query(F.data.regexp(r"^game_pick:(\d+):(green|red)$"))
async def cb_game_pick(callback: types.CallbackQuery):
    _, user_id, color = callback.data.split(":")
    user_id = int(user_id)
    if callback.from_user.id != user_id:
        await callback.answer("Это не ваша игра.", show_alert=True)
        return
    sess = game_sessions.get(user_id)
    if not sess or sess.get("stage") != 2:
        await callback.answer("Сессия недействительна.", show_alert=True)
        return
    del game_sessions[user_id]
    if color != "green":
        await callback.message.edit_text("❌ Это был не зелёный кубик.")
        return
    stats = await db.update_duel_stats(user_id, agility_delta=10)
    await callback.message.edit_text(f"✅ Победа! +10 ловкости. Ловкость: {stats['agility']}")


@duel_router.message(Command("duel"))
@duel_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() == "дуэль"))
async def cmd_duel(message: types.Message):
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("Ответь на сообщение соперника командой 'дуэль'.")
        return
    attacker = message.from_user
    defender = message.reply_to_message.from_user
    if attacker.id == defender.id or defender.is_bot:
        await message.reply("Нужен живой соперник.")
        return
    now = time.time()
    if duel_cooldowns.get(attacker.id, 0) > now:
        remain = int(duel_cooldowns[attacker.id] - now)
        await message.reply(f"😵 Вы в нокауте после дуэли. Подождите {remain // 60}м {remain % 60}с.")
        return
    if duel_cooldowns.get(defender.id, 0) > now:
        await message.reply("😵 Соперник сейчас в нокауте 10 минут и не может принять дуэль.")
        return
    duel_sessions[message.chat.id] = {"a": attacker.id, "d": defender.id}
    kb = _kb([InlineKeyboardButton(text="⚔️ Принять дуэль", callback_data=f"duel_accept:{attacker.id}:{defender.id}")])
    await message.reply(f"{defender.full_name}, вам брошен вызов на дуэль!", reply_markup=kb)


@duel_router.callback_query(F.data.regexp(r"^duel_accept:(\d+):(\d+)$"))
async def cb_duel_accept(callback: types.CallbackQuery):
    _, a_id, d_id = callback.data.split(":")
    a_id, d_id = int(a_id), int(d_id)
    if callback.from_user.id != d_id:
        await callback.answer("Только вызванный игрок может принять.", show_alert=True)
        return

    duel_sessions[callback.message.chat.id] = {"a": a_id, "d": d_id, "active": True}
    kb = _kb([InlineKeyboardButton(text="⚔️ УДАР", callback_data=f"duel_hit:{a_id}:{d_id}")])
    await callback.message.edit_text("Дуэль началась! Кто быстрее нажмёт «УДАР», тот атакует.", reply_markup=kb)


@duel_router.callback_query(F.data.regexp(r"^duel_hit:(\d+):(\d+)$"))
async def cb_duel_hit(callback: types.CallbackQuery):
    _, a_id, d_id = callback.data.split(":")
    a_id, d_id = int(a_id), int(d_id)
    if callback.from_user.id not in {a_id, d_id}:
        await callback.answer("Вы не участник дуэли.", show_alert=True)
        return

    now = time.time()
    if duel_cooldowns.get(callback.from_user.id, 0) > now:
        await callback.answer("Вы в нокауте и не можете драться.", show_alert=True)
        return

    attacker = callback.from_user.id
    target = d_id if attacker == a_id else a_id
    a_stats = await db.get_duel_stats(attacker)
    t_stats = await db.get_duel_stats(target)
    rp = await db.get_user_rp_stats(target)
    target_hp = rp.get("hp", 100)

    hit_chance = 70 - max(0, (t_stats["agility"] - a_stats["agility"]) // 10)
    hit_roll = random.randint(1, 100)
    if hit_roll > hit_chance:
        duel_cooldowns[attacker] = time.time() + 600
        duel_sessions.pop(callback.message.chat.id, None)
        await callback.message.edit_text(
            f"💨 Промах! Дуэль окончена.\n"
            f"Шанс попадания: {hit_chance}% | Бросок: {hit_roll}\n"
            f"Атакующий в нокауте на 10 минут."
        )
        return

    damage = 50 + ((a_stats["strength"] - t_stats["strength"]) // 10)
    damage = max(10, damage)
    new_hp = max(0, target_hp - damage)
    await db.update_user_rp_stats(target, hp=new_hp)

    duel_cooldowns[target] = time.time() + 600
    duel_sessions.pop(callback.message.chat.id, None)
    await db.update_user_rp_stats(target, hp=max(1, new_hp), recovery_end_ts=time.time() + 600)
    await callback.message.edit_text(
        f"🏆 Дуэль окончена!\nИгрок {attacker} победил.\n"
        f"Шанс попадания: {hit_chance}% | Урон: {damage}\n"
        f"HP противника после удара: {new_hp}\n"
        f"Проигравший в нокауте на 10 минут."
    )


@duel_router.message(Command("duels"))
@duel_router.message(F.text.func(lambda t: isinstance(t, str) and t.strip().lower() in {"дуэли", "дуэли команды"}))
async def cmd_duels_info(message: types.Message):
    user_id = message.from_user.id
    stats = await db.get_duel_stats(user_id)
    await message.reply(
        "⚔️ Команды дуэлей:\n"
        "• дуэль / /duel — вызов (ответом на сообщение)\n"
        "• дуэли / /duels — показать это меню\n"
        "• точить нож / /sharp_knife — +5 силы за 500 LUM\n"
        "• играть / /play — мини-игра, +10 ловкости за победу\n\n"
        "📌 Алгоритм:\n"
        "• Нажал УДАР первым — ты атакующий\n"
        "• База попадания: 70%\n"
        "• Если у цели ловкость выше, шанс падает на (разница ловкости / 10)\n"
        "  Пример: разница 10 => 69%\n"
        "• База урона: 50 HP из RP-системы\n"
        "• За каждые 10 силы разницы урон меняется на 1\n"
        "• Проигравший получает нокаут 10 минут\n\n"
        f"Ваши статы: 💪 {stats['strength']} | 🏃 {stats['agility']} | 🛡 {stats['stamina']}"
    )
