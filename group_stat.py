from core.group.stat.smain import *
from core.group.stat.config import *
from core.group.stat.manager import ProfileManager
# from core.group.stat.command import * # Этот импорт может быть не нужен
# from group_stat import * # Циклический импорт

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, BufferedInputFile
from aiogram.utils.markdown import hlink

formatter = string.Formatter()

stat_router = Router(name="stat_router")

@stat_router.message(F.text.lower().startswith(("профиль", "/профиль")))
async def show_profile(message: types.Message, profile_manager: ProfileManager, bot: Bot):
    logger.info(f"DEBUG: show_profile handler entered for user {message.from_user.id} with text '{message.text}'.")
    
    await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.first_name)

    profile = await profile_manager.get_user_profile(message.from_user)
    if not profile:
        logger.error(f"Failed to load profile for user {message.from_user.id} after /profile command.")
        await message.reply("❌ Не удалось загрузить профиль!")
        return
    
    logger.debug(f"Generating profile image for user {message.from_user.id}.")
    image_bytes = await profile_manager.generate_profile_image(message.from_user, profile, bot)
    input_file = BufferedInputFile(image_bytes.getvalue(), filename="profile.png")
    
    logger.info(f"Sending profile image to user {message.from_user.id}.")
    await message.answer_photo(
        photo=input_file,
        caption=f"Профиль пользователя {message.from_user.first_name}"
    )

@stat_router.message(F.text.lower() == "работать")
async def do_work(message: types.Message, profile_manager: ProfileManager):
    logger.info(f"Received 'работать' command from user {message.from_user.id}.")
    user_id = message.from_user.id
    current_time = time.time()
    last_work_time = await profile_manager.get_last_work_time(user_id)
    time_elapsed = current_time - last_work_time
    time_left = ProfileConfig.WORK_COOLDOWN_SECONDS - time_elapsed
    
    if time_elapsed < ProfileConfig.WORK_COOLDOWN_SECONDS:
        minutes_left = int(time_left // 60)
        seconds_left = int(time_left % 60)
        logger.info(f"User {user_id} tried to work, but still on cooldown. Time left: {minutes_left}m {seconds_left}s.")
        await message.reply(f"⏳ Работать можно будет через {minutes_left} мин {seconds_left} сек.")
    else:
        reward = random.randint(ProfileConfig.WORK_REWARD_MIN, ProfileConfig.WORK_REWARD_MAX)
        task = random.choice(ProfileConfig.WORK_TASKS)
        await profile_manager.update_lumcoins(user_id, reward)
        await profile_manager.update_last_work_time(user_id, current_time)
        logger.info(f"User {user_id} successfully worked, earned {reward} Lumcoins. Task: '{task}'.")
        await message.reply(f"{message.from_user.first_name} {task} и заработал(а) {reward} LUMcoins!")

@stat_router.message(F.text.lower() == "магазин")
async def show_shop(message: types.Message, profile_manager: ProfileManager):
    logger.info(f"Received 'магазин' command from user {message.from_user.id}.")
    
    shop_items = profile_manager.get_available_backgrounds()
    
    builder = InlineKeyboardBuilder()
    for key, item in shop_items.items():
        builder.row(
            InlineKeyboardButton(
                text=f"{item['name']} - {item['cost']} LUM",
                callback_data=f"buy_background:{key}"
            )
        )

    text = "🛍️ **Магазин фонов** 🛍️\n\nВыберите фон для покупки:"
    
    await message.reply(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    logger.info(f"Shop list with inline buttons sent to user {message.from_user.id}.")

# =================================================================
# ИЗМЕНЕНИЕ: Обновлена логика подтверждения покупки
# =================================================================
@stat_router.callback_query(F.data.startswith("buy_background:"))
async def process_buy_background(callback: types.CallbackQuery, profile_manager: ProfileManager):
    original_command_message = callback.message.reply_to_message
    
    if not original_command_message or callback.from_user.id != original_command_message.from_user.id:
        await callback.answer("Вы не можете использовать этот магазин.", show_alert=True)
        return

    await callback.answer()

    user_id = callback.from_user.id
    item_key = callback.data.split(":")[1]
    
    logger.info(f"User {user_id} initiated purchase of background: '{item_key}'.")

    shop_items = profile_manager.get_available_backgrounds()
    if item_key in shop_items:
        item = shop_items[item_key]
        user_coins = await profile_manager.get_lumcoins(user_id)
        
        logger.debug(f"User {user_id} has {user_coins} Lumcoins. Item '{item['name']}' costs {item['cost']}.")

        if user_coins >= item['cost']:
            await profile_manager.update_lumcoins(user_id, -item['cost'])
            await profile_manager.set_user_background(user_id, item_key)
            
            logger.info(f"User {user_id} successfully bought and set background '{item['name']}'.")
            
            # Формируем имя пользователя для упоминания
            user_info = callback.from_user
            user_mention = hlink(user_info.full_name, f"tg://user?id={user_info.id}")

            # Отправляем публичное сообщение о покупке в чат
            await callback.message.answer(
                f"✅ Пользователь {user_mention} успешно приобрел(а) фон для профиля: **{item['name']}**!",
                parse_mode="HTML"
            )
            # Редактируем исходное сообщение магазина, чтобы закрыть его
            await callback.message.edit_text("Покупка совершена.", reply_markup=None)

        else:
            logger.info(f"User {user_id} failed to buy background '{item['name']}' due to insufficient funds.")
            await callback.message.answer(
                f"❌ Недостаточно LUMcoins! Цена фона '{item['name']}': {item['cost']}, у вас: {user_coins}."
            )
            # Закрываем магазин после неудачной попытки
            await callback.message.edit_text("Недостаточно средств.", reply_markup=None)
    else:
        logger.warning(f"User {user_id} tried to buy non-existent background '{item_key}'.")
        await callback.message.edit_text("❌ Произошла ошибка. Такого предмета больше нет в магазине.", reply_markup=None)
# =================================================================

@stat_router.message(F.text.lower().startswith("топ"))
async def show_top(message: types.Message, profile_manager: ProfileManager):
    logger.info(f"Received 'топ' command from user {message.from_user.id}.")
    args = message.text.lower().split()
    top_type = "уровень"

    if len(args) > 1:
        if "уровень" in args:
            top_type = "уровень"
        elif "люмкоины" in args or "монеты" in args:
            top_type = "люмкоины"
        else:
            await message.reply("Неверный формат команды. Используйте `топ уровень` или `топ люмкоины`.")
            return

    if top_type == "уровень":
        top_users = await profile_manager.get_top_users_by_level(limit=10)
        title = "🏆 Топ пользователей по уровню 🏆\n\n"
        if not top_users:
            response_text = "Пока нет данных для топа по уровню."
        else:
            response_text = ""
            for i, user_data in enumerate(top_users):
                response_text += f"{i+1}. {user_data['display_name']} - Уровень: {user_data['level']}, EXP: {user_data['exp']}\n"
    elif top_type == "люмкоины":
        top_users = await profile_manager.get_top_users_by_lumcoins(limit=10)
        title = "💰 Топ пользователей по Lumcoins 💰\n\n"
        if not top_users:
            response_text = "Пока нет данных для топа по Lumcoins."
        else:
            response_text = ""
            for i, user_data in enumerate(top_users):
                response_text += f"{i+1}. {user_data['display_name']} - Lumcoins: {user_data['lumcoins']}₽\n"
    
    await message.reply(title + response_text, parse_mode="Markdown")
    logger.info(f"Top {top_type} sent to user {message.from_user.id}.")


def init_db_sync_profiles():
    logger.info("Attempting to initialize profiles database (sync).")
    if not os.path.exists('profiles.db'):
        logger.info("profiles.db not found, creating new database.")
        conn = sqlite3.connect('profiles.db')
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            profile_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            hp INTEGER DEFAULT 100 CHECK(hp >= 0 AND hp <= 150),
            level INTEGER DEFAULT 1 CHECK(level >= 1 AND level <= 169),
            exp INTEGER DEFAULT 0,
            lumcoins INTEGER DEFAULT 0,
            daily_messages INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            flames INTEGER DEFAULT 0,
            last_work_time REAL DEFAULT 0,
            active_background TEXT DEFAULT 'default',
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)')
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully (sync).")
    else:
        logger.info("Database profiles.db already exists, skipping sync initialization.")

init_db_sync_profiles()

@stat_router.message()
async def track_message_activity(message: types.Message, profile_manager: ProfileManager):
    logger.debug(f"Tracking message activity for user {message.from_user.id}.")
    if message.from_user.id == message.bot.id or message.content_type != types.ContentType.TEXT:
        logger.debug(f"Ignoring message from bot or non-text message for user {message.from_user.id}.")
        return
    
    user_id = message.from_user.id
    
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)

    old_profile = await profile_manager.get_user_profile(message.from_user)
    if not old_profile:
        logger.error(f"Failed to get old profile for user_id {user_id} in track_message_activity. Aborting.")
        return
    old_level = old_profile.get('level', 1)
    old_lumcoins = old_profile.get('lumcoins', 0)
    
    await profile_manager.record_message(message.from_user)
    
    new_profile = await profile_manager.get_user_profile(message.from_user)
    if not new_profile:
        logger.error(f"Failed to get new profile for user_id {user_id} after record_message. Aborting.")
        return
    new_level = new_profile.get('level', 1)
    new_lumcoins = new_profile.get('lumcoins', 0)
    lumcoins_earned_from_level = new_lumcoins - old_lumcoins
    
    if new_level > old_level and lumcoins_earned_from_level > 0:
        logger.info(f"User {user_id} leveled up to {new_level} and earned {lumcoins_earned_from_level} Lumcoins.")
        await message.reply(
            f"🎉 Поздравляю, {message.from_user.first_name}! Ты достиг(ла) Уровня {new_level}! "
            f"Награда: {lumcoins_earned_from_level} LUMcoins."
        )

def setup_stat_handlers(dp: Dispatcher, bot: Bot, profile_manager: ProfileManager):
    logger.info("Registering stat router handlers.")
    dp.include_router(stat_router)
    logger.info("Stat router included in Dispatcher.")
    return dp
