"""Конфигурация для игр казино"""

# Эмодзи для слотов
SLOT_EMOJIS = {
    'cherry': '🍒',
    'lemon': '🍋',
    'orange': '🍊',
    'grape': '🍇',
    'seven': '7️⃣',
    'diamond': '💎',
    'star': '⭐',
    'bell': '🔔',
}

# Множители выигрыша для слотов
SLOT_MULTIPLIERS = {
    'cherry': 2,
    'lemon': 3,
    'orange': 4,
    'grape': 5,
    'seven': 7,
    'diamond': 10,
    'star': 15,
    'bell': 20,
}

# Эмодзи для рулетки
ROULETTE_EMOJIS = {
    'red': '🔴',
    'black': '⚫',
    'green': '🟢',
}

# Множители для рулетки
ROULETTE_MULTIPLIERS = {
    'number': 36,  # Ставка на конкретное число
    'color': 2,    # Ставка на цвет
    'half': 2,     # Ставка на половину (1-18 или 19-36)
    'dozen': 3,    # Ставка на дюжину
    'row': 3,      # Ставка на ряд
}