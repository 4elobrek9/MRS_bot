import random
import logging
import asyncio
from typing import Dict, Any, List
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from core.group.stat.manager import ProfileManager

logger = logging.getLogger(__name__)

casino_router = Router(name="casino_router")

# Глобальные словари для хранения статистики и активных игр
user_win_streaks = {}
user_loss_streaks = {}
blackjack_games = {}
active_blackjack_sessions = {}

class Card:
    suits = ['♥', '♦', '♣', '♠']
    values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    
    def __init__(self, suit, value):
        self.suit = suit
        self.value = value
    
    def __str__(self):
        return f'{self.suit}{self.value}'
    
    def score(self):
        if self.value in ['J', 'Q', 'K']:
            return 10
        elif self.value == 'A':
            return 11
        return int(self.value)

class Deck:
    def __init__(self):
        self.cards = [Card(s, v) for s in Card.suits for v in Card.values]
        random.shuffle(self.cards)
    
    def deal(self):
        return self.cards.pop() if self.cards else None

def calculate_score(hand):
    score = sum(card.score() for card in hand)
    aces = sum(1 for card in hand if card.value == 'A')
    
    while score > 21 and aces:
        score -= 10
        aces -= 1
    return score

def get_adjusted_probability(base_probability: float, user_id: int, game_type: str = "slots") -> float:
    """Рассчитывает скорректированную вероятность с учетом статистики пользователя"""
    win_streak = user_win_streaks.get(user_id, 0)
    loss_streak = user_loss_streaks.get(f"{user_id}_{game_type}", 0)
    
    # Гарантированная победа после 7 проигрышей подряд
    if loss_streak >= 7:
        logger.info(f"User {user_id} gets guaranteed win after {loss_streak} losses in {game_type}")
        return 1.0
    
    # Уменьшение шансов после каждой победы
    win_modifier = 0.9 ** win_streak
    
    adjusted_prob = base_probability * win_modifier
    return max(0.05, min(0.95, adjusted_prob))

def should_user_win(adjusted_probability: float) -> bool:
    return random.random() < adjusted_probability

class CasinoGames:
    """Класс для игр казино"""
    
    @staticmethod
    async def play_slots(bet: int, user_id: int) -> Dict[str, Any]:
        """Игра в слоты с системой шансов"""
        symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣"]
        
        # Базовая вероятность выигрыша для слотов
        base_probability = 0.4
        adjusted_probability = get_adjusted_probability(base_probability, user_id, "slots")
        should_win = should_user_win(adjusted_probability)
        
        if should_win:
            # Генерация выигрышной комбинации
            win_types = [
                {"type": "two_equal", "multiplier": 1, "prob": 0.6},
                {"type": "three_equal", "multiplier": 3, "prob": 0.3},
                {"type": "three_seven", "multiplier": 5, "prob": 0.05},
                {"type": "three_diamond", "multiplier": 10, "prob": 0.05}
            ]
            
            win_type = random.choices(
                [wt["type"] for wt in win_types],
                [wt["prob"] for wt in win_types]
            )[0]
            
            if win_type == "two_equal":
                symbol1 = random.choice(symbols)
                symbol2 = symbol1
                symbol3 = random.choice([s for s in symbols if s != symbol1])
                result = [symbol1, symbol2, symbol3]
                multiplier = 1
            else:
                if win_type == "three_seven":
                    symbol = "7️⃣"
                    multiplier = 5
                elif win_type == "three_diamond":
                    symbol = "💎"
                    multiplier = 10
                else:
                    symbol = random.choice([s for s in symbols if s not in ["7️⃣", "💎"]])
                    multiplier = 3
                result = [symbol, symbol, symbol]
            
            win_amount = bet * multiplier
            
            # Обновляем статистику
            user_win_streaks[user_id] = user_win_streaks.get(user_id, 0) + 1
            user_loss_streaks[f"{user_id}_slots"] = 0
            
            return {
                "won": True,
                "result": " ".join(result),
                "win_amount": win_amount,
                "multiplier": multiplier
            }
        else:
            # Генерация проигрышной комбинации
            while True:
                result = [random.choice(symbols) for _ in range(3)]
                # Проверяем, что это действительно проигрышная комбинация
                if (result[0] != result[1] and result[1] != result[2] and result[0] != result[2]):
                    break
            
            # Обновляем статистику
            user_win_streaks[user_id] = 0
            user_loss_streaks[f"{user_id}_slots"] = user_loss_streaks.get(f"{user_id}_slots", 0) + 1
            
            return {
                "won": False,
                "result": " ".join(result),
                "win_amount": 0
            }
    
    @staticmethod
    async def play_roulette(bet: int, choice: str, user_id: int) -> Dict[str, Any]:
        """Игра в рулетку с системой шансов"""
        # Последовательность чисел в рулетке (европейская)
        roulette_sequence = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
        
        # Определяем цвета для чисел
        def get_color(number):
            if number == 0:
                return "green"
            red_numbers = [32, 19, 21, 25, 34, 27, 36, 30, 23, 5, 16, 1, 14, 9, 18, 7, 12, 3]
            return "red" if number in red_numbers else "black"
        
        # Базовая вероятность в зависимости от типа ставки
        if choice in ["red", "black"]:
            base_probability = 18/37
        elif choice in ["green", "0"]:
            base_probability = 1/37
        elif choice in ["1-12", "13-24", "25-36"]:
            base_probability = 12/37
        else:
            try:
                number_choice = int(choice)
                base_probability = 1/37
            except ValueError:
                base_probability = 1/37
        
        adjusted_probability = get_adjusted_probability(base_probability, user_id, "roulette")
        should_win = should_user_win(adjusted_probability)
        
        logger.info(f"Roulette - User {user_id}: choice={choice}, base_prob={base_probability:.3f}, adjusted_prob={adjusted_probability:.3f}, should_win={should_win}")
        
        # Выбираем результат с учетом скорректированной вероятности
        if should_win:
            if choice in ["red", "black"]:
                result = random.choice([n for n in roulette_sequence if get_color(n) == choice and n != 0])
            elif choice in ["green", "0"]:
                result = 0
            elif choice in ["1-12", "13-24", "25-36"]:
                if choice == "1-12":
                    result = random.choice([n for n in roulette_sequence if 1 <= n <= 12])
                elif choice == "13-24":
                    result = random.choice([n for n in roulette_sequence if 13 <= n <= 24])
                elif choice == "25-36":
                    result = random.choice([n for n in roulette_sequence if 25 <= n <= 36])
            else:
                try:
                    result = int(choice)
                except ValueError:
                    result = random.choice([n for n in roulette_sequence if n != 0])
        else:
            if choice in ["red", "black"]:
                result = random.choice([n for n in roulette_sequence if get_color(n) != choice])
            elif choice in ["green", "0"]:
                result = random.choice([n for n in roulette_sequence if n != 0])
            elif choice in ["1-12", "13-24", "25-36"]:
                if choice == "1-12":
                    result = random.choice([n for n in roulette_sequence if not (1 <= n <= 12)])
                elif choice == "13-24":
                    result = random.choice([n for n in roulette_sequence if not (13 <= n <= 24)])
                elif choice == "25-36":
                    result = random.choice([n for n in roulette_sequence if not (25 <= n <= 36)])
            else:
                try:
                    result = random.choice([n for n in roulette_sequence if n != int(choice)])
                except ValueError:
                    result = random.choice([n for n in roulette_sequence if n != 0])
        
        color = get_color(result)
        
        # Проверка выигрыша
        won = False
        multiplier = 1
        
        if choice == "red" and color == "red":
            won = True
            multiplier = 2
        elif choice == "black" and color == "black":
            won = True
            multiplier = 2
        elif choice == "green" and color == "green":
            won = True
            multiplier = 35
        elif choice in ["1-12", "13-24", "25-36"]:
            if choice == "1-12" and 1 <= result <= 12:
                won = True
                multiplier = 3
            elif choice == "13-24" and 13 <= result <= 24:
                won = True
                multiplier = 3
            elif choice == "25-36" and 25 <= result <= 36:
                won = True
                multiplier = 3
        else:
            try:
                if int(choice) == result:
                    won = True
                    multiplier = 35
            except ValueError:
                won = False
        
        if won:
            user_win_streaks[user_id] = user_win_streaks.get(user_id, 0) + 1
            user_loss_streaks[f"{user_id}_roulette"] = 0
        else:
            user_win_streaks[user_id] = 0
            user_loss_streaks[f"{user_id}_roulette"] = user_loss_streaks.get(f"{user_id}_roulette", 0) + 1
        
        return {
            "won": won,
            "result": result,
            "color": color,
            "win_amount": bet * multiplier if won else 0,
            "multiplier": multiplier if won else 0
        }

    @staticmethod
    async def play_blackjack(bet: int, user_id: int, action: str = None) -> Dict[str, Any]:
        """Игра в блэкджек с пошаговой раздачей карт"""
        if user_id not in blackjack_games or action == "start":
            deck = Deck()
            
            player_hand = []
            dealer_hand = []
            
            player_hand.append(deck.deal())
            dealer_hand.append(deck.deal())
            player_hand.append(deck.deal())
            dealer_hand.append(deck.deal())
            
            blackjack_games[user_id] = {
                'deck': deck,
                'player_hand': player_hand,
                'dealer_hand': dealer_hand,
                'bet': bet,
                'state': 'playing'
            }
            
            active_blackjack_sessions[user_id] = {
                'message_id': None,
                'bet': bet
            }
            
            player_score = calculate_score(player_hand)
            dealer_score = calculate_score([dealer_hand[0]])
            
            if player_score == 21:
                blackjack_games[user_id]['state'] = 'blackjack'
                return await CasinoGames.finish_blackjack(user_id, bet, player_hand, dealer_hand)
            
            return {
                "state": "playing",
                "player_hand": player_hand,
                "dealer_hand": [dealer_hand[0], "?"],
                "player_score": player_score,
                "dealer_score": dealer_score,
                "message": "Карты разданы! Ваш ход!"
            }
        
        game = blackjack_games[user_id]
        
        if action == "hit":
            new_card = game['deck'].deal()
            game['player_hand'].append(new_card)
            player_score = calculate_score(game['player_hand'])
            
            if player_score > 21:
                return await CasinoGames.finish_blackjack(user_id, game['bet'], game['player_hand'], game['dealer_hand'])
            
            return {
                "state": "playing",
                "player_hand": game['player_hand'],
                "dealer_hand": [game['dealer_hand'][0], "?"],
                "player_score": player_score,
                "dealer_score": calculate_score([game['dealer_hand'][0]]),
                "message": f"Вы взяли карту: {new_card}! Выберите следующее действие:"
            }
        
        elif action == "stand":
            dealer_score = calculate_score(game['dealer_hand'])
            dealer_cards = game['dealer_hand']
            
            while dealer_score < 17:
                new_card = game['deck'].deal()
                dealer_cards.append(new_card)
                dealer_score = calculate_score(dealer_cards)
            
            return await CasinoGames.finish_blackjack(user_id, game['bet'], game['player_hand'], dealer_cards)
        
        elif action == "surrender":
            if user_id in blackjack_games:
                del blackjack_games[user_id]
            if user_id in active_blackjack_sessions:
                del active_blackjack_sessions[user_id]
            return {
                "state": "surrender",
                "win_amount": bet // 2,
                "message": "Вы сдались. Возвращена половина ставки."
            }

    @staticmethod
    async def finish_blackjack(user_id: int, bet: int, player_hand: List[Card], dealer_hand: List[Card]) -> Dict[str, Any]:
        """Завершение игры в блэкджек и определение результата"""
        player_score = calculate_score(player_hand)
        dealer_score = calculate_score(dealer_hand)
        
        if player_score > 21:
            result = "lose"
            win_amount = 0
            user_win_streaks[user_id] = 0
            user_loss_streaks[f"{user_id}_blackjack"] = user_loss_streaks.get(f"{user_id}_blackjack", 0) + 1
        elif dealer_score > 21:
            result = "win"
            win_amount = bet * 2
            user_win_streaks[user_id] = user_win_streaks.get(user_id, 0) + 1
            user_loss_streaks[f"{user_id}_blackjack"] = 0
        elif player_score == dealer_score:
            result = "push"
            win_amount = bet
        elif player_score == 21 and len(player_hand) == 2:
            result = "blackjack"
            win_amount = int(bet * 2.5)
            user_win_streaks[user_id] = user_win_streaks.get(user_id, 0) + 1
            user_loss_streaks[f"{user_id}_blackjack"] = 0
        elif player_score > dealer_score:
            result = "win"
            win_amount = bet * 2
            user_win_streaks[user_id] = user_win_streaks.get(user_id, 0) + 1
            user_loss_streaks[f"{user_id}_blackjack"] = 0
        else:
            result = "lose"
            win_amount = 0
            user_win_streaks[user_id] = 0
            user_loss_streaks[f"{user_id}_blackjack"] = user_loss_streaks.get(f"{user_id}_blackjack", 0) + 1
        
        if user_id in blackjack_games:
            del blackjack_games[user_id]
        if user_id in active_blackjack_sessions:
            del active_blackjack_sessions[user_id]
        
        return {
            "state": "finished",
            "result": result,
            "player_hand": player_hand,
            "dealer_hand": dealer_hand,
            "player_score": player_score,
            "dealer_score": dealer_score,
            "win_amount": win_amount,
            "message": CasinoGames.get_blackjack_message(result, win_amount, bet)
        }

    @staticmethod
    def get_blackjack_message(result: str, win_amount: int, bet: int) -> str:
        messages = {
            "win": f"🎉 Вы выиграли {win_amount} LUM!",
            "lose": f"💸 Вы проиграли {bet} LUM!",
            "push": "🤝 Ничья! Ставка возвращена.",
            "blackjack": f"🎊 БЛЭКДЖЕК! Вы выиграли {win_amount} LUM!"
        }
        return messages.get(result, "Игра завершена.")

# Доступные ставки
AVAILABLE_BETS = [10, 20, 50, 75, 100, 150, 520, 1000, 2500]

async def safe_send_message(bot, chat_id: int, text: str, reply_markup=None, reply_to_message_id: int = None):
    """Безопасная отправка сообщения с обработкой ошибок"""
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id
        )
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return None

async def safe_answer_callback(callback: types.CallbackQuery, text: str = None, show_alert: bool = False):
    """Безопасный ответ на callback"""
    try:
        await callback.answer(text, show_alert=show_alert)
        return True
    except Exception as e:
        logger.warning(f"Error answering callback: {e}")
        return False

async def simple_roulette_animation(bot, chat_id: int, message_thread_id: int = None):
    """Простая анимация рулетки"""
    roulette_sequence = [0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26]
    
    def get_color_emoji(number):
        if number == 0:
            return "🟢"
        red_numbers = [32, 19, 21, 25, 34, 27, 36, 30, 23, 5, 16, 1, 14, 9, 18, 7, 12, 3]
        return "🔴" if number in red_numbers else "⚫"
    
    # Отправляем анимацию как новое сообщение
    start_idx = random.randint(0, len(roulette_sequence) - 3)
    showing_numbers = roulette_sequence[start_idx:start_idx + 3]
    animation_text = f"🎡 **Крутится рулетка...** 🎡\n\n" + " → ".join(f"{get_color_emoji(n)}{n}" for n in showing_numbers)
    
    anim_message = await safe_send_message(bot, chat_id, animation_text, reply_to_message_id=message_thread_id)
    await asyncio.sleep(1.5)
    
    return anim_message

async def simple_slots_animation(bot, chat_id: int, message_thread_id: int = None):
    """Простая анимация слотов"""
    symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣"]
    
    slot_display = [random.choice(symbols) for _ in range(3)]
    animation_text = f"🎰 **Крутятся слоты...** 🎰\n\n" + " | ".join(slot_display)
    
    anim_message = await safe_send_message(bot, chat_id, animation_text, reply_to_message_id=message_thread_id)
    await asyncio.sleep(1.5)
    
    return anim_message

# Главное меню казино
@casino_router.message(F.text.lower().startswith(("казино", "/казино")))
async def casino_main_menu(message: types.Message, profile_manager: ProfileManager):
    """Главное меню казино - только для групп"""
    user_id = message.from_user.id
    balance = await profile_manager.get_lumcoins(user_id)
    
    win_streak = user_win_streaks.get(user_id, 0)
    current_multiplier = 0.9 ** win_streak
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎰 Слоты", callback_data="casino_choose_game_slots"),
        InlineKeyboardButton(text="🎡 Рулетка", callback_data="casino_choose_game_roulette"),
        InlineKeyboardButton(text="🃏 Блэкджек", callback_data="casino_choose_game_blackjack")
    )
    builder.row(InlineKeyboardButton(text="ℹ️ Информация", callback_data="casino_info_main"))
    
    await message.reply(
        f"🎰 **Казино Lumcoins** 🎰\n\n"
        f"💰 Ваш баланс: {balance} LUM\n"
        f"📉 Текущий множитель шансов: {current_multiplier:.2f}\n\n"
        f"Выберите игру:",
        reply_markup=builder.as_markup()
    )

# Обработчики выбора игры
@casino_router.callback_query(F.data == "casino_choose_game_slots")
async def choose_slots_game(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Выбор игры в слоты"""
    user_id = callback.from_user.id
    balance = await profile_manager.get_lumcoins(user_id)
    
    keyboard = InlineKeyboardBuilder()
    row = []
    for bet in AVAILABLE_BETS:
        if bet > balance:
            row.append(InlineKeyboardButton(text=f"❌ {bet}", callback_data='none'))
        else:
            row.append(InlineKeyboardButton(text=f"{bet}", callback_data=f'slots_bet_{bet}_{user_id}'))
        
        if len(row) == 3:
            keyboard.row(*row)
            row = []
    
    if row:
        keyboard.row(*row)
    
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="casino_back_to_main"))
    
    win_streak = user_win_streaks.get(user_id, 0)
    current_multiplier = 0.9 ** win_streak
    
    await callback.message.edit_text(
        f"🎰 **Игра в слоты** 🎰\n\n"
        f"💰 Ваш баланс: {balance} LUM\n"
        f"📉 Текущий множитель шансов: {current_multiplier:.2f}\n\n"
        f"Выберите ставку:",
        reply_markup=keyboard.as_markup()
    )
    await safe_answer_callback(callback)

@casino_router.callback_query(F.data == "casino_choose_game_roulette")
async def choose_roulette_game(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Выбор игры в рулетку"""
    user_id = callback.from_user.id
    balance = await profile_manager.get_lumcoins(user_id)
    
    keyboard = InlineKeyboardBuilder()
    row = []
    for bet in AVAILABLE_BETS:
        if bet > balance:
            row.append(InlineKeyboardButton(text=f"❌ {bet}", callback_data='none'))
        else:
            row.append(InlineKeyboardButton(text=f"{bet}", callback_data=f'roulette_bet_{bet}_{user_id}'))
        
        if len(row) == 3:
            keyboard.row(*row)
            row = []
    
    if row:
        keyboard.row(*row)
    
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="casino_back_to_main"))
    
    win_streak = user_win_streaks.get(user_id, 0)
    current_multiplier = 0.9 ** win_streak
    
    await callback.message.edit_text(
        f"🎡 **Рулетка** 🎡\n\n"
        f"💰 Ваш баланс: {balance} LUM\n"
        f"📉 Текущий множитель шансов: {current_multiplier:.2f}\n\n"
        f"Выберите ставку:",
        reply_markup=keyboard.as_markup()
    )
    await safe_answer_callback(callback)

@casino_router.callback_query(F.data == "casino_choose_game_blackjack")
async def choose_blackjack_game(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Выбор игры в блэкджек"""
    user_id = callback.from_user.id
    balance = await profile_manager.get_lumcoins(user_id)
    
    keyboard = InlineKeyboardBuilder()
    row = []
    for bet in AVAILABLE_BETS:
        if bet > balance:
            row.append(InlineKeyboardButton(text=f"❌ {bet}", callback_data='none'))
        else:
            row.append(InlineKeyboardButton(text=f"{bet}", callback_data=f'blackjack_bet_{bet}_{user_id}'))
        
        if len(row) == 3:
            keyboard.row(*row)
            row = []
    
    if row:
        keyboard.row(*row)
    
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="casino_back_to_main"))
    
    win_streak = user_win_streaks.get(user_id, 0)
    current_multiplier = 0.9 ** win_streak
    
    await callback.message.edit_text(
        f"🃏 **Блэкджек** 🃏\n\n"
        f"💰 Ваш баланс: {balance} LUM\n"
        f"📉 Текущий множитель шансов: {current_multiplier:.2f}\n\n"
        f"Выберите ставку:",
        reply_markup=keyboard.as_markup()
    )
    await safe_answer_callback(callback)

# Обработчики для слотов
@casino_router.callback_query(F.data.startswith("slots_bet_"))
async def slots_bet_handler(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Обработчик выбора ставки для слотов"""
    user_id = callback.from_user.id
    data_parts = callback.data.split("_")
    
    if len(data_parts) < 4:
        await safe_answer_callback(callback, "❌ Ошибка в данных!")
        return
    
    bet_amount = int(data_parts[2])
    callback_user_id = int(data_parts[3])
    
    if user_id != callback_user_id:
        await safe_answer_callback(callback, "❌ Это не ваша игра!", show_alert=True)
        return
    
    balance = await profile_manager.get_lumcoins(user_id)
    if balance < bet_amount:
        await safe_answer_callback(callback, "❌ Недостаточно Lumcoins!")
        return
    
    try:
        await profile_manager.update_lumcoins(user_id, -bet_amount)
    except Exception as e:
        logger.error(f"Error deducting bet for user {user_id}: {e}")
        await safe_answer_callback(callback, "❌ Ошибка при списании средств!")
        return
    
    # Показываем анимацию слотов как новое сообщение
    anim_message = await simple_slots_animation(callback.bot, callback.message.chat.id)
    
    # Получаем результат
    result = await CasinoGames.play_slots(bet_amount, user_id)
    
    if result["won"]:
        await profile_manager.update_lumcoins(user_id, result["win_amount"])
        new_balance = await profile_manager.get_lumcoins(user_id)
        
        result_text = (
            f"🎰 **СЛОТЫ** 🎰\n\n"
            f"Результат: {result['result']}\n"
            f"✅ ВЫИГРЫШ! x{result['multiplier']}\n"
            f"💎 Выигрыш: {result['win_amount']} LUM\n"
            f"💰 Новый баланс: {new_balance} LUM"
        )
    else:
        new_balance = await profile_manager.get_lumcoins(user_id)
        result_text = (
            f"🎰 **СЛОТЫ** 🎰\n\n"
            f"Результат: {result['result']}\n"
            f"❌ ПРОИГРЫШ\n"
            f"💸 Потеряно: {bet_amount} LUM\n"
            f"💰 Новый баланс: {new_balance} LUM"
        )
    
    keyboard = InlineKeyboardBuilder().add(
        InlineKeyboardButton(text="🎰 Играть снова", callback_data="casino_choose_game_slots"),
        InlineKeyboardButton(text="🔙 В меню", callback_data="casino_back_to_main")
    ).as_markup()
    
    # Отправляем результат как новое сообщение
    await safe_send_message(callback.bot, callback.message.chat.id, result_text, keyboard)
    await safe_answer_callback(callback)

# Обработчики для рулетки
@casino_router.callback_query(F.data.startswith("roulette_bet_"))
async def roulette_bet_handler(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Обработчик выбора ставки для рулетки"""
    user_id = callback.from_user.id
    data_parts = callback.data.split("_")
    
    if len(data_parts) < 4:
        await safe_answer_callback(callback, "❌ Ошибка в данных!")
        return
    
    bet_amount = int(data_parts[2])
    callback_user_id = int(data_parts[3])
    
    if user_id != callback_user_id:
        await safe_answer_callback(callback, "❌ Это не ваша игра!", show_alert=True)
        return
    
    balance = await profile_manager.get_lumcoins(user_id)
    if balance < bet_amount:
        await safe_answer_callback(callback, "❌ Недостаточно Lumcoins!")
        return
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="🔴 Красное", callback_data=f'roulette_type_red_{bet_amount}_{user_id}'),
        InlineKeyboardButton(text="⚫ Черное", callback_data=f'roulette_type_black_{bet_amount}_{user_id}')
    )
    keyboard.row(
        InlineKeyboardButton(text="🟢 Зеро", callback_data=f'roulette_type_green_{bet_amount}_{user_id}'),
        InlineKeyboardButton(text="1-12", callback_data=f'roulette_type_1-12_{bet_amount}_{user_id}')
    )
    keyboard.row(
        InlineKeyboardButton(text="13-24", callback_data=f'roulette_type_13-24_{bet_amount}_{user_id}'),
        InlineKeyboardButton(text="25-36", callback_data=f'roulette_type_25-36_{bet_amount}_{user_id}')
    )
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data="casino_choose_game_roulette"))
    
    await callback.message.edit_text(
        f"🎡 **Рулетка** 🎡\n\n"
        f"💰 Ваша ставка: {bet_amount} LUM\n\n"
        f"Выберите тип ставки:",
        reply_markup=keyboard.as_markup()
    )
    await safe_answer_callback(callback)

@casino_router.callback_query(F.data.startswith("roulette_type_"))
async def roulette_type_handler(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Обработчик выбора типа ставки для рулетки"""
    user_id = callback.from_user.id
    data_parts = callback.data.split("_")
    
    if len(data_parts) < 5:
        await safe_answer_callback(callback, "❌ Ошибка в данных!")
        return
    
    choice = data_parts[2]
    bet_amount = int(data_parts[3])
    callback_user_id = int(data_parts[4])
    
    if user_id != callback_user_id:
        await safe_answer_callback(callback, "❌ Это не ваша игра!", show_alert=True)
        return
    
    try:
        await profile_manager.update_lumcoins(user_id, -bet_amount)
    except Exception as e:
        logger.error(f"Error deducting bet for user {user_id}: {e}")
        await safe_answer_callback(callback, "❌ Ошибка при списании средств!")
        return
    
    # Показываем анимацию рулетки как новое сообщение
    anim_message = await simple_roulette_animation(callback.bot, callback.message.chat.id)
    
    # Получаем результат
    result = await CasinoGames.play_roulette(bet_amount, choice, user_id)
    
    def get_color_emoji(number):
        if number == 0:
            return "🟢"
        red_numbers = [32, 19, 21, 25, 34, 27, 36, 30, 23, 5, 16, 1, 14, 9, 18, 7, 12, 3]
        return "🔴" if number in red_numbers else "⚫"
    
    if result["won"]:
        await profile_manager.update_lumcoins(user_id, result["win_amount"])
        new_balance = await profile_manager.get_lumcoins(user_id)
        
        result_text = (
            f"🎡 **РУЛЕТКА** 🎡\n\n"
            f"Выпало: {result['result']} {get_color_emoji(result['result'])}\n"
            f"✅ ВЫИГРЫШ! x{result['multiplier']}\n"
            f"💎 Выигрыш: {result['win_amount']} LUM\n"
            f"💰 Новый баланс: {new_balance} LUM"
        )
    else:
        new_balance = await profile_manager.get_lumcoins(user_id)
        result_text = (
            f"🎡 **РУЛЕТКА** 🎡\n\n"
            f"Выпало: {result['result']} {get_color_emoji(result['result'])}\n"
            f"❌ ПРОИГРЫШ\n"
            f"💸 Потеряно: {bet_amount} LUM\n"
            f"💰 Новый баланс: {new_balance} LUM"
        )
    
    keyboard = InlineKeyboardBuilder().add(
        InlineKeyboardButton(text="🎡 Играть снова", callback_data="casino_choose_game_roulette"),
        InlineKeyboardButton(text="🔙 В меню", callback_data="casino_back_to_main")
    ).as_markup()
    
    # Отправляем результат как новое сообщение
    await safe_send_message(callback.bot, callback.message.chat.id, result_text, keyboard)
    await safe_answer_callback(callback)

# Обработчики для блэкджека
@casino_router.callback_query(F.data.startswith("blackjack_bet_"))
async def blackjack_bet_handler(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Обработчик выбора ставки для блэкджека"""
    user_id = callback.from_user.id
    data_parts = callback.data.split("_")
    
    if len(data_parts) < 4:
        await safe_answer_callback(callback, "❌ Ошибка в данных!")
        return
    
    bet_amount = int(data_parts[2])
    callback_user_id = int(data_parts[3])
    
    if user_id != callback_user_id:
        await safe_answer_callback(callback, "❌ Это не ваша игра!", show_alert=True)
        return
    
    balance = await profile_manager.get_lumcoins(user_id)
    if balance < bet_amount:
        await safe_answer_callback(callback, "❌ Недостаточно Lumcoins!")
        return
    
    try:
        await profile_manager.update_lumcoins(user_id, -bet_amount)
    except Exception as e:
        logger.error(f"Error deducting bet for user {user_id}: {e}")
        await safe_answer_callback(callback, "❌ Ошибка при списании средств!")
        return
    
    # Начинаем игру
    result = await CasinoGames.play_blackjack(bet_amount, user_id, "start")
    
    if result["state"] == "playing":
        keyboard = InlineKeyboardBuilder()
        keyboard.row(
            InlineKeyboardButton(text="➕ Взять карту", callback_data=f'bj_hit_{bet_amount}_{user_id}'),
            InlineKeyboardButton(text="✋ Остановиться", callback_data=f'bj_stand_{bet_amount}_{user_id}')
        )
        keyboard.row(InlineKeyboardButton(text="🏳️ Сдаться", callback_data=f'bj_surrender_{bet_amount}_{user_id}'))
        
        response_text = (
            f"🃏 **БЛЭКДЖЕК** 🃏\n\n"
            f"💰 Ставка: {bet_amount} LUM\n\n"
            f"👤 Ваши карты: {' '.join(str(card) for card in result['player_hand'])}\n"
            f"💎 Ваши очки: {result['player_score']}\n\n"
            f"🎭 Карты дилера: {result['dealer_hand'][0]} ?\n"
            f"💎 Очки дилера: ?\n\n"
            f"{result['message']}"
        )
        
        # Отправляем новое сообщение с игрой
        new_message = await safe_send_message(callback.bot, callback.message.chat.id, response_text, keyboard.as_markup())
        
        if user_id in active_blackjack_sessions and new_message:
            active_blackjack_sessions[user_id]['message_id'] = new_message.message_id
    else:
        if result["result"] == "blackjack":
            await profile_manager.update_lumcoins(user_id, result["win_amount"])
        
        new_balance = await profile_manager.get_lumcoins(user_id)
        
        response_text = (
            f"🃏 **БЛЭКДЖЕК** 🃏\n\n"
            f"👤 Ваши карты: {' '.join(str(card) for card in result['player_hand'])}\n"
            f"💎 Ваши очки: {result['player_score']}\n\n"
            f"🎭 Карты дилера: {' '.join(str(card) for card in result['dealer_hand'])}\n"
            f"💎 Очки дилера: {result['dealer_score']}\n\n"
            f"{result['message']}\n"
            f"💰 Новый баланс: {new_balance} LUM"
        )
        
        keyboard = InlineKeyboardBuilder().add(
            InlineKeyboardButton(text="🃏 Новая игра", callback_data="casino_choose_game_blackjack"),
            InlineKeyboardButton(text="🔙 В меню", callback_data="casino_back_to_main")
        ).as_markup()
        
        # Отправляем результат как новое сообщение
        await safe_send_message(callback.bot, callback.message.chat.id, response_text, keyboard)
    
    await safe_answer_callback(callback)

@casino_router.callback_query(F.data.startswith("bj_"))
async def blackjack_callback_handler(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Обработчик callback-ов для блэкджека"""
    user_id = callback.from_user.id
    data_parts = callback.data.split("_")
    
    if len(data_parts) < 4:
        await safe_answer_callback(callback, "❌ Ошибка в данных!")
        return
    
    action = data_parts[1]
    bet = int(data_parts[2])
    callback_user_id = int(data_parts[3])
    
    if user_id != callback_user_id:
        await safe_answer_callback(callback, "❌ Это не ваша игра!", show_alert=True)
        return
    
    result = await CasinoGames.play_blackjack(bet, user_id, action)
    
    if result["state"] in ["playing", "finished", "surrender"]:
        if result["state"] == "playing":
            keyboard = InlineKeyboardBuilder()
            keyboard.row(
                InlineKeyboardButton(text="➕ Взять карту", callback_data=f'bj_hit_{bet}_{user_id}'),
                InlineKeyboardButton(text="✋ Остановиться", callback_data=f'bj_stand_{bet}_{user_id}')
            )
            keyboard.row(InlineKeyboardButton(text="🏳️ Сдаться", callback_data=f'bj_surrender_{bet}_{user_id}'))
            
            response_text = (
                f"🃏 **БЛЭКДЖЕК** 🃏\n\n"
                f"💰 Ставка: {bet} LUM\n\n"
                f"👤 Ваши карты: {' '.join(str(card) for card in result['player_hand'])}\n"
                f"💎 Ваши очки: {result['player_score']}\n\n"
                f"🎭 Карты дилера: {result['dealer_hand'][0]} ?\n"
                f"💎 Очки дилера: ?\n\n"
                f"{result['message']}"
            )
            
            # Отправляем новое сообщение
            await safe_send_message(callback.bot, callback.message.chat.id, response_text, keyboard.as_markup())
        else:
            if result["state"] == "finished" and result["win_amount"] > 0:
                await profile_manager.update_lumcoins(user_id, result["win_amount"])
            elif result["state"] == "surrender":
                await profile_manager.update_lumcoins(user_id, result["win_amount"])
            
            new_balance = await profile_manager.get_lumcoins(user_id)
            
            if result["state"] == "finished":
                response_text = (
                    f"🃏 **БЛЭКДЖЕК** 🃏\n\n"
                    f"👤 Ваши карты: {' '.join(str(card) for card in result['player_hand'])}\n"
                    f"💎 Ваши очки: {result['player_score']}\n\n"
                    f"🎭 Карты дилера: {' '.join(str(card) for card in result['dealer_hand'])}\n"
                    f"💎 Очки дилера: {result['dealer_score']}\n\n"
                    f"{result['message']}\n"
                    f"💰 Новый баланс: {new_balance} LUM"
                )
            else:
                response_text = (
                    f"🃏 **БЛЭКДЖЕК** 🃏\n\n"
                    f"{result['message']}\n"
                    f"💰 Новый баланс: {new_balance} LUM"
                )
            
            keyboard = InlineKeyboardBuilder().add(
                InlineKeyboardButton(text="🃏 Новая игра", callback_data="casino_choose_game_blackjack"),
                InlineKeyboardButton(text="🔙 В меню", callback_data="casino_back_to_main")
            ).as_markup()
            
            # Отправляем результат как новое сообщение
            await safe_send_message(callback.bot, callback.message.chat.id, response_text, keyboard)
        
        await safe_answer_callback(callback)
    else:
        await safe_answer_callback(callback, "❌ Неизвестное состояние игры!")

# Информационные обработчики
@casino_router.callback_query(F.data == "casino_info_main")
async def casino_info_main(callback: types.CallbackQuery):
    """Главная информация о казино"""
    await callback.message.edit_text(
        "🎰 **Казино Lumcoins** 🎰\n\n"
        "**🎯 Система шансов:**\n"
        "• Каждая победа уменьшает шансы на 10%\n"
        "• После 7 проигрышей подряд - гарантированная победа\n"
        "• Шансы автоматически корректируются для баланса\n\n"
        
        "**🎰 Слоты:**\n"
        "• 2 одинаковых символа: x1\n" 
        "• 3 одинаковых символа: x3\n"
        "• 3 семёрки (7️⃣): x5\n"
        "• 3 алмаза (💎): x10\n\n"
        
        "**🎡 Рулетка (Европейская):**\n"
        "• Красное/Черное: x2\n"
        "• Зеро (0): x35\n"
        "• Конкретное число: x35\n"
        "• Диапазоны (1-12, 13-24, 25-36): x3\n"
        "• 37 чисел (0-36)\n\n"
        
        "**🃏 Блэкджек:**\n"
        "• Цель: набрать больше очков чем дилер, но не более 21\n"
        "• Карты 2-10 = номиналу, J/Q/K = 10, A = 1 или 11\n"
        "• Блэкджек (21 двумя картами): x2.5\n"
        "• Победа: x2, Ничья: возврат ставки\n"
        "• Дилер берет карты до 17 очков\n\n"
        
        "**💰 Ставки:** 10, 20, 50, 75, 100, 150, 520, 1000, 2500 LUM\n\n"
        "Удачи в игре! 🍀",
        reply_markup=InlineKeyboardBuilder().add(
            InlineKeyboardButton(text="🔙 Назад", callback_data="casino_back_to_main")
        ).as_markup()
    )
    await safe_answer_callback(callback)

@casino_router.callback_query(F.data == "casino_back_to_main")
async def casino_back_to_main(callback: types.CallbackQuery, profile_manager: ProfileManager):
    """Возврат в главное меню казино"""
    user_id = callback.from_user.id
    balance = await profile_manager.get_lumcoins(user_id)
    
    win_streak = user_win_streaks.get(user_id, 0)
    current_multiplier = 0.9 ** win_streak
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎰 Слоты", callback_data="casino_choose_game_slots"),
        InlineKeyboardButton(text="🎡 Рулетка", callback_data="casino_choose_game_roulette"),
        InlineKeyboardButton(text="🃏 Блэкджек", callback_data="casino_choose_game_blackjack")
    )
    builder.row(InlineKeyboardButton(text="ℹ️ Информация", callback_data="casino_info_main"))
    
    await callback.message.edit_text(
        f"🎰 **Казино Lumcoins** 🎰\n\n"
        f"💰 Ваш баланс: {balance} LUM\n"
        f"📉 Текущий множитель шансов: {current_multiplier:.2f}\n\n"
        f"Выберите игру:",
        reply_markup=builder.as_markup()
    )
    await safe_answer_callback(callback)

def setup_casino_handlers(main_dp, profile_manager: ProfileManager):
    """Настройка обработчиков казино"""
    main_dp.include_router(casino_router)
    logger.info("Casino handlers setup complete")