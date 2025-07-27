from core.group.stat.smain import *
from core.group.stat.config import *
from core.group.stat.manager import ProfileManager
import string # Добавлен импорт string
import time # Добавлен импорт time
import random # Добавлен импорт random

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, BufferedInputFile
from aiogram.utils.markdown import hlink
from aiogram.enums import ParseMode # Добавлен импорт ParseMode

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
    
    logger.info(f"Sending profile image to user {message.from_user.id}.")
    await message.reply_photo(BufferedInputFile(image_bytes.getvalue(), filename="profile.png"))


@stat_router.message(F.text.lower().startswith(("работать", "/работать")))
async def do_work(message: types.Message, profile_manager: ProfileManager):
    user_id = message.from_user.id
    logger.info(f"Received 'работать' command from user {user_id}.")

    last_work_time = await profile_manager.get_last_work_time(user_id)
    current_time = time.time()
    
    # Проверка кулдауна
    if current_time - last_work_time < WorkConfig.COOLDOWN_SECONDS:
        remaining_time = int(WorkConfig.COOLDOWN_SECONDS - (current_time - last_work_time))
        minutes, seconds = divmod(remaining_time, 60)
        await message.reply(f"⏳ Вы сможете работать снова через {minutes} мин. {seconds} сек.")
        return

    # Выбор случайной задачи и награды
    task_name, lumcoins_reward = random.choice(list(WorkConfig.WORK_TASKS.items()))

    # Обновление Lumcoins и времени последней работы
    await profile_manager.update_lumcoins(user_id, lumcoins_reward)
    await profile_manager.update_last_work_time(user_id, current_time)

    await message.reply(f"✅ Вы успешно {task_name} и заработали {lumcoins_reward} Lumcoins!")
    logger.info(f"User {user_id} successfully worked, earned {lumcoins_reward} Lumcoins. Task: '{task_name}'.")


@stat_router.message(F.text.lower().startswith(("магазин", "/магазин")))
async def show_shop(message: types.Message, profile_manager: ProfileManager):
    user_id = message.from_user.id
    logger.info(f"Received 'магазин' command from user {user_id}.")

    user_lumcoins = await profile_manager.get_lumcoins(user_id)
    available_backgrounds = profile_manager.get_available_backgrounds()
    user_backgrounds_inventory = await profile_manager.get_user_backgrounds_inventory(user_id)

    builder = InlineKeyboardBuilder()
    text = f"🛍️ **Магазин фонов** 🛍️\n\nВаши Lumcoins: {user_lumcoins} LUM\n\n"
    text += "🖼️ **Доступные фоны:**\n"

    for key, bg_info in available_backgrounds.items():
        name = bg_info['name']
        # Безопасное получение цены, если она отсутствует, по умолчанию 0
        price = bg_info.get('price', 0) 
        
        status = ""
        if key in user_backgrounds_inventory:
            status = " (Куплено)"
            # Получаем активный фон пользователя внутри цикла, чтобы избежать повторного вызова get_user_profile
            user_profile = await profile_manager.get_user_profile(message.from_user) 
            if key == user_profile.get('active_background', 'default'):
                status = " (Активно)"
            builder.add(InlineKeyboardButton(text=f"✅ {name}{status}", callback_data=f"activate_bg:{key}"))
        else:
            builder.add(InlineKeyboardButton(text=f"💰 {name} ({price} LUM)", callback_data=f"buy_bg:{key}"))
    
    builder.adjust(1) # Одна кнопка в ряду
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.MARKDOWN)
    logger.info(f"Shop list with inline buttons sent to user {user_id}.")


@stat_router.callback_query(F.data.startswith("buy_bg:"))
async def process_buy_background(callback: types.CallbackQuery, profile_manager: ProfileManager):
    user_id = callback.from_user.id
    background_key_to_buy = callback.data.split(":")[1]

    logger.info(f"User {user_id} attempting to buy background: '{background_key_to_buy}'.")

    available_backgrounds = profile_manager.get_available_backgrounds()
    bg_info = available_backgrounds.get(background_key_to_buy)

    if not bg_info:
        logger.warning(f"User {user_id} tried to buy unknown background '{background_key_to_buy}'.")
        await callback.message.edit_text("❌ Неизвестный фон.", reply_markup=None)
        return

    bg_name = bg_info['name']
    bg_price = bg_info.get('price', 0) # Безопасное получение цены
    user_lumcoins = await profile_manager.get_lumcoins(user_id)
    user_backgrounds_inventory = await profile_manager.get_user_backgrounds_inventory(user_id)

    if background_key_to_buy in user_backgrounds_inventory:
        logger.info(f"User {user_id} already owns background '{bg_name}'.")
        await callback.message.edit_text(f"✅ У вас уже есть фон '{bg_name}'.", reply_markup=None)
        return

    if user_lumcoins >= bg_price:
        await profile_manager.update_lumcoins(user_id, -bg_price) # Списываем Lumcoins
        # set_user_background уже вызывает add_item_to_inventory внутри
        await profile_manager.set_user_background(user_id, background_key_to_buy) # Добавляем в инвентарь и устанавливаем активным
        
        logger.info(f"User {user_id} successfully bought and activated background '{bg_name}'.")
        await callback.message.edit_text(
            f"🎉 Вы успешно купили и активировали фон '{bg_name}' за {bg_price} Lumcoins! Ваш профиль теперь выглядит по-новому.",
            reply_markup=None # Убираем кнопки после покупки
        )
    else:
        logger.info(f"User {user_id} tried to buy background '{bg_name}' but has insufficient Lumcoins ({user_lumcoins}/{bg_price}).")
        await callback.message.edit_text(
            f"❌ Недостаточно Lumcoins для покупки фона '{bg_name}'. Вам нужно {bg_price} Lumcoins, у вас {user_lumcoins}.",
            reply_markup=None
        )


@stat_router.callback_query(F.data.startswith("activate_bg:"))
async def process_activate_background(callback: types.CallbackQuery, profile_manager: ProfileManager):
    user_id = callback.from_user.id
    background_key_to_activate = callback.data.split(":")[1]

    logger.info(f"User {user_id} attempting to activate background: '{background_key_to_activate}'.")

    # Проверяем, есть ли фон в инвентаре пользователя
    user_backgrounds_inventory = await profile_manager.get_user_backgrounds_inventory(user_id)

    if background_key_to_activate in user_backgrounds_inventory:
        # Используем метод ProfileManager для установки активного фона
        await profile_manager.set_user_background(user_id, background_key_to_activate) 
        
        # Получаем информацию о фоне для отображения имени
        bg_info = ShopConfig.SHOP_BACKGROUNDS.get(background_key_to_activate)
        bg_name = bg_info['name'] if bg_info else background_key_to_activate

        logger.info(f"User {user_id} successfully activated background '{bg_name}'.")
        await callback.message.edit_text(
            f"✅ Фон '{bg_name}' успешно активирован! Ваш профиль теперь выглядит по-новому.",
            reply_markup=None # Убираем кнопки после активации
        )
    else:
        logger.warning(f"User {user_id} tried to activate background '{background_key_to_activate}' not in inventory.")
        await callback.message.edit_text(
            "❌ Этого фона нет в вашем инвентаре или произошла ошибка.",
            reply_markup=None
        )


@stat_router.message(F.text.lower().startswith(("топ", "/топ")))
async def show_top(message: types.Message, profile_manager: ProfileManager):
    user_id = message.from_user.id
    logger.info(f"Received 'топ' command from user {user_id}.")

    # Получаем топ пользователей по уровню
    top_users_level = await profile_manager.get_top_users_by_level(limit=10)
    
    response_text = "🏆 **Топ 10 игроков по уровню:** 🏆\n\n"
    if top_users_level:
        for i, user_data in enumerate(top_users_level):
            # Используем 'username' или 'first_name' для отображения имени пользователя
            # 'username' может быть None, поэтому проверяем его первым
            display_name = user_data.get('username') or user_data.get('first_name', 'Неизвестный')
            response_text += f"{i+1}. {display_name} - Уровень: {user_data['level']}, EXP: {user_data['exp']}\n"
    else:
        response_text += "Пока нет данных для топа по уровню.\n"

    response_text += "\n💰 **Топ 10 игроков по Lumcoins:** 💰\n\n"
    # Получаем топ пользователей по Lumcoins
    top_users_lumcoins = await profile_manager.get_top_users_by_lumcoins(limit=10)
    if top_users_lumcoins:
        for i, user_data in enumerate(top_users_lumcoins):
            # Используем 'username' или 'first_name' для отображения имени пользователя
            display_name = user_data.get('username') or user_data.get('first_name', 'Неизвестный')
            response_text += f"{i+1}. {display_name} - Lumcoins: {user_data['lumcoins']}\n"
    else:
        response_text += "Пока нет данных для топа по Lumcoins.\n"

    await message.answer(response_text, parse_mode=ParseMode.MARKDOWN)
    logger.info(f"Top players list sent to user {user_id}.")


async def ensure_user_exists(user_id: int, username: Optional[str], first_name: str, last_name: Optional[str] = None):
    """
    Убеждается, что пользователь существует в основной базе данных и в базе данных профилей.
    Создает записи, если их нет.
    """
    # Подключение к основной БД бота
    main_db_conn = await aiosqlite.connect('bot_database.db')
    try:
        await main_db_conn.execute('''
            INSERT INTO users (user_id, username, first_name, last_active_ts)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_active_ts = excluded.last_active_ts
        ''', (user_id, username, first_name, time.time()))
        await main_db_conn.execute('''
            INSERT OR IGNORE INTO user_modes (user_id, mode, rating_opportunities_count)
            VALUES (?, 'saharoza', 0)
        ''', (user_id,))
        await main_db_conn.execute('''
            INSERT OR IGNORE INTO rp_user_stats (user_id) VALUES (?)
        ''', (user_id,))
        await main_db_conn.commit()
        logger.debug(f"User {user_id} ensured in main bot database.")
    except Exception as e:
        logger.error(f"Error ensuring user {user_id} in main bot database: {e}", exc_info=True)
    finally:
        await main_db_conn.close()

    # Подключение к базе данных профилей
    profiles_db_conn = await aiosqlite.connect('profiles.db')
    try:
        await profiles_db_conn.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        await profiles_db_conn.execute('''
            INSERT OR IGNORE INTO user_profiles (user_id, active_background)
            VALUES (?, 'default')
        ''', (user_id,))
        await profiles_db_conn.commit()
        logger.debug(f"User {user_id} ensured in profiles database.")
    except Exception as e:
        logger.error(f"Error ensuring user {user_id} in profiles database: {e}", exc_info=True)
    finally:
        await profiles_db_conn.close()


def setup_stat_handlers(main_dp: Router):
    main_dp.include_router(stat_router)
    logger.info("Registering stat router handlers.")
    logger.info("Stat router included in Dispatcher.")
