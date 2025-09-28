from core.group.stat.smain import *
from core.group.stat.config import *
from core.group.stat.manager import ProfileManager
from core.group.stat.shop_config import *
import string # Добавлен импорт string
import time # Добавлен импорт time
import random # Добавлен импорт random
from database import add_item_to_inventory, set_user_active_background, get_user_rp_stats, update_user_rp_stats
import asyncio  # Добавьте эту строку в начале файла
import aiosqlite  # Убедитесь, что этот импорт тоже есть
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import re
from urllib.parse import urlparse
# Добавьте эти импорты если их нет:
from aiogram.enums import ChatType
from database import set_group_censor_setting, get_group_censor_setting, get_group_admins
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, BufferedInputFile
from aiogram.utils.markdown import hlink
from aiogram.enums import ParseMode # Добавлен импорт ParseMode
from core.group.stat.config import WorkConfig, ProfileConfig

import logging
logger = logging.getLogger(__name__)

formatter = string.Formatter()

stat_router = Router(name="stat_router")

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import re
from urllib.parse import urlparse

__all__ = [
    'show_profile', 
    'do_work', 
    'show_shop', 
    'show_top',
    'manage_censor',
    'show_admins', 
    'group_stats'
]

class CustomBackgroundStates(StatesGroup):
    waiting_for_url = State()

custom_bg_purchases = {}

# Добавим обработчик для покупки кастомного фона
@stat_router.callback_query(F.data == "buy_bg:custom")
async def process_buy_custom_background(callback: types.CallbackQuery, profile_manager: ProfileManager, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} attempting to buy custom background.")

    available_backgrounds = profile_manager.get_available_backgrounds()
    bg_info = available_backgrounds.get("custom")

    if not bg_info:
        await callback.message.edit_text("❌ Неизвестный фон.", reply_markup=None)
        return

    bg_price = bg_info.get('price', 10000)
    user_lumcoins = await profile_manager.get_lumcoins(user_id)

    if user_lumcoins >= bg_price:
        # Сохраняем информацию о покупке
        custom_bg_purchases[user_id] = {
            "message_id": callback.message.message_id,
            "price": bg_price,
            "lumcoins_before": user_lumcoins
        }
        
        # Переходим в состояние ожидания URL
        await state.set_state(CustomBackgroundStates.waiting_for_url)
        
        await callback.message.edit_text(
            "🖼️ Отправьте ссылку на изображение для вашего кастомного фона.\n\n"
            "Требования:\n"
            "• Формат: JPG, PNG или GIF\n"
            "• Соотношение сторон: 21:9 (широкоформатное)\n"
            "• Минимальное разрешение: 1680×720\n\n"
            "Для отмены отправьте /cancel",
            reply_markup=None
        )
    else:
        await callback.message.edit_text(
            f"❌ Недостаточно Lumcoins для покупки кастомного фона. Нужно {bg_price} Lumcoins, у вас {user_lumcoins}.",
            reply_markup=None
        )

# Добавим обработчик для получения URL
@stat_router.message(CustomBackgroundStates.waiting_for_url)
async def process_custom_bg_url(message: types.Message, profile_manager: ProfileManager, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    
    # Проверяем отмену
    if message.text and message.text.lower() in ["/cancel", "отмена", "cancel"]:
        await state.clear()
        if user_id in custom_bg_purchases:
            del custom_bg_purchases[user_id]
        await message.answer("❌ Покупка кастомного фона отменена.")
        return
    
    # Проверяем, что сообщение содержит URL
    url = message.text.strip()
    
    # Простая проверка URL
    if not re.match(r'^https?://', url):
        await message.answer("❌ Это не похоже на валидный URL. Отправьте корректную ссылку на изображение.\n\nДля отмены отправьте /cancel")
        return
    
    # Проверяем расширение файла
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    if not any(path.endswith(ext) for ext in valid_extensions):
        await message.answer(
            "❌ URL должен вести на изображение (JPG, PNG, GIF или WebP).\n\n"
            "Поддерживаемые форматы: .jpg, .jpeg, .png, .gif, .webp\n"
            "Для отмены отправьте /cancel"
        )
        return
    
    # Получаем информацию о покупке
    purchase_info = custom_bg_purchases.get(user_id)
    if not purchase_info:
        await state.clear()
        await message.answer("❌ Информация о покупке не найдена. Начните заново.")
        return
    
    # Создаем клавиатуру для подтверждения
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_custom_bg:{url}"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_custom_bg")
    )
    
    # Сохраняем URL в состоянии
    await state.update_data(custom_bg_url=url)
    
    await message.answer(
        f"📸 **Предпросмотр кастомного фона**\n"
        f"🔗 Ссылка: {url}\n\n"
        f"💎 Цена: {purchase_info['price']} Lumcoins\n"
        f"💰 Ваш баланс: {purchase_info['lumcoins_before']} → {purchase_info['lumcoins_before'] - purchase_info['price']} Lumcoins\n\n"
        "Подтверждаете покупку?",
        reply_markup=builder.as_markup(),
        disable_web_page_preview=False
    )
# Добавим функцию для очистки устаревших покупок
async def cleanup_old_purchases():
    """Очищает устаревшие записи о покупках"""
    global custom_bg_purchases
    current_time = time.time()
    # Удаляем покупки старше 1 часа
    custom_bg_purchases = {k: v for k, v in custom_bg_purchases.items() 
                          if current_time - v.get('timestamp', 0) < 3600}


# Обновим процесс покупки чтобы добавлять timestamp
@stat_router.callback_query(F.data == "buy_bg:custom")
async def process_buy_custom_background(callback: types.CallbackQuery, profile_manager: ProfileManager, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} attempting to buy custom background.")

    # Очищаем старые покупки
    await cleanup_old_purchases()

    available_backgrounds = profile_manager.get_available_backgrounds()
    bg_info = available_backgrounds.get("custom")

    if not bg_info:
        await callback.message.edit_text("❌ Неизвестный фон.", reply_markup=None)
        return

    bg_price = bg_info.get('price', 10000)
    user_lumcoins = await profile_manager.get_lumcoins(user_id)

    if user_lumcoins >= bg_price:
        # Сохраняем информацию о покупке
        custom_bg_purchases[user_id] = {
            "message_id": callback.message.message_id,
            "price": bg_price,
            "lumcoins_before": user_lumcoins,
            "timestamp": time.time()  # Добавляем timestamp
        }
        
        # Переходим в состояние ожидания URL
        await state.set_state(CustomBackgroundStates.waiting_for_url)
        
        await callback.message.edit_text(
            "🖼️ **Покупка кастомного фона**\n\n"
            "Отправьте ссылку на изображение для вашего фона.\n\n"
            "📋 Требования:\n"
            "• Формат: JPG, PNG, GIF или WebP\n"
            "• Соотношение сторон: 21:9 (широкоформатное)\n"
            "• Рекомендуемое разрешение: 1680×720 или выше\n\n"
            "❌ Ссылки на сайты (например, Google Drive, Dropbox) не принимаются\n"
            "✅ Используйте прямые ссылки на изображения\n\n"
            "Для отмены отправьте /cancel",
            reply_markup=None
        )
    else:
        await callback.message.edit_text(
            f"❌ Недостаточно Lumcoins для покупки кастомного фона.\n\n"
            f"Нужно: {bg_price} Lumcoins\n"
            f"У вас: {user_lumcoins} Lumcoins\n\n"
            f"Заработать Lumcoins можно командой 'работать'",
            reply_markup=None
        )

# Добавим обработчик подтверждения
@stat_router.callback_query(F.data.startswith("confirm_custom_bg:"))
async def process_confirm_custom_bg(callback: types.CallbackQuery, profile_manager: ProfileManager, state: FSMContext):
    user_id = callback.from_user.id
    url = callback.data.split(":", 1)[1]
    
    # Получаем информацию о покупке
    purchase_info = custom_bg_purchases.get(user_id)
    if not purchase_info:
        await callback.message.edit_text("❌ Информация о покупке не найдена.")
        await state.clear()
        return
    
    # Списываем Lumcoins
    await profile_manager.update_lumcoins(user_id, -purchase_info['price'])
    
    # Добавляем кастомный фон в инвентарь
    await add_item_to_inventory(user_id, f"custom:{user_id}", 'background')
    
    # Сохраняем URL кастомного фона в отдельной таблице
    async with aiosqlite.connect('profiles.db') as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS custom_backgrounds (
                user_id INTEGER PRIMARY KEY,
                background_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await conn.execute('''
            INSERT OR REPLACE INTO custom_backgrounds (user_id, background_url)
            VALUES (?, ?)
        ''', (user_id, url))
        await conn.commit()
    
    # Активируем фон
    await profile_manager.set_user_background(user_id, f"custom:{user_id}")
    
    # Очищаем состояние
    await state.clear()
    
    if user_id in custom_bg_purchases:
        del custom_bg_purchases[user_id]
    
    await callback.message.edit_text(
        f"✅ Кастомный фон успешно приобретен и активирован!\n\n"
        f"Ссылка: {url}\n"
        f"Списано: {purchase_info['price']} Lumcoins\n"
        f"Новый баланс: {await profile_manager.get_lumcoins(user_id)} Lumcoins",
        disable_web_page_preview=True
    )

# Добавим обработчик отмены
@stat_router.callback_query(F.data == "cancel_custom_bg")
async def process_cancel_custom_bg(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if user_id in custom_bg_purchases:
        del custom_bg_purchases[user_id]
    
    await state.clear()
    await callback.message.edit_text("❌ Покупка кастомного фона отменена.")

# Добавим проверку кастомных фонов в функцию активации
@stat_router.callback_query(F.data.startswith("activate_bg:"))
async def process_activate_background(callback: types.CallbackQuery, profile_manager: ProfileManager):
    user_id = callback.from_user.id
    background_key_to_activate = callback.data.split(":")[1]

    logger.info(f"User {user_id} attempting to activate background: '{background_key_to_activate}'.")

    # Проверяем, есть ли фон в инвентаре пользователя
    user_backgrounds_inventory = await profile_manager.get_user_backgrounds_inventory(user_id)

    if background_key_to_activate in user_backgrounds_inventory:
        # Если это кастомный фон, проверяем его наличие
        if background_key_to_activate.startswith("custom:"):
            async with aiosqlite.connect('profiles.db') as conn:
                cursor = await conn.execute(
                    'SELECT background_url FROM custom_backgrounds WHERE user_id = ?',
                    (user_id,)
                )
                custom_bg = await cursor.fetchone()
                
                if not custom_bg:
                    await callback.message.edit_text(
                        "❌ Кастомный фон не найден. Обратитесь к администратору.",
                        reply_markup=None
                    )
                    return
        
        # Используем метод ProfileManager для установки активного фона
        await profile_manager.set_user_background(user_id, background_key_to_activate) 
        
        # Получаем информацию о фоне для отображения имени
        if background_key_to_activate.startswith("custom:"):
            bg_name = "Кастомный фон"
        else:
            bg_info = ShopConfig.SHOP_BACKGROUNDS.get(background_key_to_activate)
            bg_name = bg_info['name'] if bg_info else background_key_to_activate

        logger.info(f"User {user_id} successfully activated background '{bg_name}'.")
        await callback.message.edit_text(
            f"✅ Фон '{bg_name}' успешно активирован!",
            reply_markup=None
        )
        
    else:
        logger.warning(f"User {user_id} tried to activate background '{background_key_to_activate}' not in inventory.")
        await callback.message.edit_text(
            "❌ Этого фона нет в вашем инвентаре.",
            reply_markup=None
        )

# В файле group_stat.py
@stat_router.message(F.text.lower().startswith(("профиль", "/профиль")))
async def show_profile(message: types.Message, profile_manager: ProfileManager, bot: Bot):
    logger.info(f"DEBUG: show_profile handler entered for user {message.from_user.id} with text '{message.text}'.")
    
    await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.first_name)

    profile = await profile_manager.get_user_profile(message.from_user)
    if not profile:
        logger.error(f"Failed to load profile for user {message.from_user.id} after /profile command.")
        await message.reply("❌ Не удалось загрузить профиль!")
        return
    
    from database import get_user_rp_stats
    rp_stats = await get_user_rp_stats(message.from_user.id)
    if rp_stats:
        profile['hp'] = rp_stats.get('hp', 100)
    
    logger.debug(f"Generating profile image for user {message.from_user.id}.")
    image_bytes = await ProfileManager.generate_profile_image(profile_manager, message.from_user, profile, bot)


    
    if image_bytes is None:
        logger.error(f"Failed to generate profile image for user {message.from_user.id}.")
        await message.reply("❌ Не удалось сгенерировать изображение профиля!")
        return
    
    logger.info(f"Sending profile image to user {message.from_user.id}.")
    await message.reply_photo(BufferedInputFile(image_bytes.getvalue(), filename="profile.png"))


@stat_router.message(F.text.lower().startswith(("лечить", "/лечить")))
async def heal_hp(message: types.Message, profile_manager: ProfileManager):
    user_id = message.from_user.id
    logger.info(f"Received 'лечить' command from user {user_id}.")

    # Получаем текущее HP из RP-статистики
    rp_stats = await get_user_rp_stats(user_id)
    if not rp_stats:
        await message.reply("❌ Ошибка получения данных о здоровье.")
        return

    current_hp = rp_stats.get('hp', 100)
    max_hp = ProfileConfig.MAX_HP

    # Проверяем, нужно ли лечение
    if current_hp >= max_hp:
        await message.reply("❤️ Ваше здоровье уже полностью восстановлено!")
        return

    # Получаем баланс Lumcoins
    lumcoins = await profile_manager.get_lumcoins(user_id)
    
    # Расчет стоимости лечения (10 LUM за 10 HP)
    hp_needed = max_hp - current_hp
    heal_amount = min(hp_needed, 10)  # Максимум 10 HP за раз
    cost = 10  # Фиксированная стоимость 10 LUM

    if lumcoins < cost:
        await message.reply(f"❌ Недостаточно Lumcoins для лечения. Нужно {cost} LUM, у вас {lumcoins} LUM.")
        return

    # Выполняем лечение
    new_hp = current_hp + heal_amount
    await update_user_rp_stats(user_id, hp=new_hp)
    await profile_manager.update_lumcoins(user_id, -cost)

    await message.reply(
        f"✅ Вы восстановили {heal_amount} HP за {cost} LUM!\n"
        f"❤️ Текущее здоровье: {new_hp}/{max_hp}\n"
        f"💰 Осталось Lumcoins: {lumcoins - cost}"
    )
    logger.info(f"User {user_id} healed {heal_amount} HP for {cost} Lumcoins.")

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
        price = bg_info.get('price', 0) 
        
        # Проверяем, есть ли у пользователя кастомный фон
        has_custom = any(bg.startswith("custom:") for bg in user_backgrounds_inventory)
        
        status = ""
        if key == "custom" and has_custom:
            status = " (Куплено)"
            user_profile = await profile_manager.get_user_profile(message.from_user) 
            if any(bg.startswith("custom:") and bg == user_profile.get('active_background', 'default') for bg in user_backgrounds_inventory):
                status = " (Активно)"
            builder.add(InlineKeyboardButton(text=f"✅ {name}{status}", callback_data=f"activate_bg:custom:{user_id}"))
        elif key in user_backgrounds_inventory or (key == "custom" and has_custom):
            status = " (Куплено)"
            user_profile = await profile_manager.get_user_profile(message.from_user) 
            if key == user_profile.get('active_background', 'default'):
                status = " (Активно)"
            builder.add(InlineKeyboardButton(text=f"✅ {name}{status}", callback_data=f"activate_bg:{key}"))
        else:
            builder.add(InlineKeyboardButton(text=f"💰 {name} ({price} LUM)", callback_data=f"buy_bg:{key}"))
    
    builder.adjust(1)
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
    bg_price = bg_info.get('price', 0)
    user_lumcoins = await profile_manager.get_lumcoins(user_id)
    user_backgrounds_inventory = await profile_manager.get_user_backgrounds_inventory(user_id)

    if background_key_to_buy in user_backgrounds_inventory:
        logger.info(f"User {user_id} already owns background '{bg_name}'.")
        await callback.message.edit_text(f"✅ У вас уже есть фон '{bg_name}'.", reply_markup=None)
        return

    if user_lumcoins >= bg_price:
        # Сначала списываем Lumcoins
        await profile_manager.update_lumcoins(user_id, -bg_price)
        
        # Добавляем в инвентарь
        await add_item_to_inventory(user_id, background_key_to_buy, 'background')
        
        # Устанавливаем активный фон через профиль менеджер
        await profile_manager.set_user_background(user_id, background_key_to_buy)
        
        logger.info(f"User {user_id} successfully bought and activated background '{bg_name}'.")
        await callback.message.edit_text(
            f"🎉 Вы успешно купили и активировали фон '{bg_name}' за {bg_price} Lumcoins!",
            reply_markup=None
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
            f"✅ Фон '{bg_name}' успешно активирован!",
            reply_markup=None
        )
        
        # Добавляем небольшую задержку и обновляем профиль
        await asyncio.sleep(1)
        try:
            user_profile = await profile_manager.get_user_profile(callback.from_user)
            if user_profile:
                image_bytes = await profile_manager.generate_profile_image(callback.from_user, user_profile, bot)
            from core.main.ez_main import bot
            await bot.send_photo(callback.message.chat.id, BufferedInputFile(image_bytes.getvalue(), filename="profile_updated.png"))
        except Exception as e:
            logger.error(f"Error showing updated profile: {e}")
    else:
        logger.warning(f"User {user_id} tried to activate background '{background_key_to_activate}' not in inventory.")
        await callback.message.edit_text(
            "❌ Этого фона нет в вашем инвентаре.",
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
    try:
        main_db_conn = await aiosqlite.connect('bot_database.db')
        # Проверяем существование таблицы users
        cursor = await main_db_conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = await cursor.fetchone()
        
        if not table_exists:
            # Если таблицы нет, создаем её
            await main_db_conn.execute('''
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT NOT NULL,
                    last_active_ts REAL DEFAULT 0
                )
            ''')
            await main_db_conn.commit()
            
        # Остальной код без изменений
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
        if main_db_conn:
            await main_db_conn.close()


def setup_stat_handlers(main_dp: Router):
    main_dp.include_router(stat_router)
    logger.info("Registering stat router handlers.")
    logger.info("Stat router included in Dispatcher.")

@stat_router.message(F.text.lower().startswith(("цензура", "/цензура")))
async def manage_censor(message: types.Message, bot: Bot):
    """Управление настройками цензуры в группе"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Проверяем права администратора
    admins = await get_group_admins(chat_id)
    if user_id not in admins:
        await message.reply("❌ Эта команда доступна только администраторам группы.")
        return
        
    text = message.text.lower().split()
    if len(text) < 2:
        # Показываем текущий статус цензуры
        is_enabled = await get_group_censor_setting(chat_id)
        status = "включена" if is_enabled else "выключена"
        await message.reply(f"🔧 Цензура в этой группе {status}.\n\n"
                          "Используйте:\n"
                          "• `цензура вкл` - включить\n"
                          "• `цензура выкл` - выключить")
        return
        
    action = text[1]
    if action in ["вкл", "on", "enable"]:
        await set_group_censor_setting(chat_id, True)
        await message.reply("✅ Цензура включена. Теперь буду следить за плохими словами!")
    elif action in ["выкл", "off", "disable"]:
        await set_group_censor_setting(chat_id, False)
        await message.reply("❌ Цензура выключена. Могу ругаться сколько угодно!")
    else:
        await message.reply("❌ Неизвестная команда. Используйте `цензура вкл` или `цензура выкл`")