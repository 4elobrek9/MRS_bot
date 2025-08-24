class ProfileConfig:
    DEFAULT_LOCAL_BG_PATH = "background/defolt.jpg"
    DEFAULT_AVATAR_URL = "https://placehold.co/120x120/CCCCCC/FFFFFF/png?text=AV"

    FONT_PATH = "Hlobus.ttf"
    TEXT_COLOR = (255, 255, 255)
    TEXT_SHADOW_COLOR = (0, 0, 0)
    
    CARD_WIDTH = 700
    CARD_HEIGHT = 280
    CARD_RADIUS = 20

    MARGIN = 30

    AVATAR_SIZE = 120
    
    _INITIAL_AVATAR_Y = (CARD_HEIGHT - AVATAR_SIZE) // 2
    _INITIAL_USERNAME_Y = _INITIAL_AVATAR_Y - 10

    AVATAR_Y = _INITIAL_AVATAR_Y - int(CARD_HEIGHT * 0.02)
    AVATAR_X = MARGIN
    AVATAR_OFFSET = (AVATAR_X, AVATAR_Y)

    USERNAME_Y = _INITIAL_USERNAME_Y + int(CARD_HEIGHT * 0.05)
    TEXT_BLOCK_LEFT_X = AVATAR_X + AVATAR_SIZE + MARGIN // 2

    EXPERIENCE_LABEL_Y = CARD_HEIGHT - MARGIN - 20 - 25
    EXP_BAR_Y = EXPERIENCE_LABEL_Y + 25
    EXP_BAR_X = MARGIN
    EXP_BAR_HEIGHT = 20
    EXP_BAR_WIDTH = int( (CARD_WIDTH - EXP_BAR_X - MARGIN - 70) )

    RIGHT_COLUMN_X = CARD_WIDTH - MARGIN
    RIGHT_COLUMN_TOP_Y = MARGIN + 20 
    ITEM_SPACING_Y = 70 
    
    HP_COLORS = {
        "full": (0, 200, 0),
        "high": (50, 150, 0),
        "medium": (255, 165, 0),
        "low": (255, 0, 0),
        "empty": (128, 0, 0)
    }
    
    EXP_GRADIENT_START = (0, 128, 0)
    EXP_GRADIENT_END = (0, 255, 0)
    EXP_BAR_ALPHA = 200

    MAX_HP = 150
    MIN_HP = 0
    MAX_LEVEL = 169
    EXP_PER_MESSAGE_INTERVAL = 1
    EXP_AMOUNT_PER_INTERVAL = 10
    EXP_PER_MESSAGES_COUNT = 10
    
    LUMCOINS_PER_LEVEL = {
        1: 1, 10: 2, 20: 3, 30: 5,
        50: 8, 100: 15, 150: 25, 169: 50
    }
    WORK_REWARD_MIN = 5
    WORK_REWARD_MAX = 20
    FONT_SIZE_XLARGE = 36
    FONT_SIZE_LARGE = 28
    FONT_SIZE_MEDIUM = 20
    FONT_SIZE_SMALL = 16
    @staticmethod
    def LEVEL_UP_EXP_REQUIREMENT(level: int) -> int:
        """Рассчитывает необходимое количество опыта для достижения следующего уровня"""
        # Пример: 100 опыта для 1 уровня, 200 для 2, 300 для 3 и т.д.
        return level * 100

class WorkConfig:
    WORK_TASKS = {
        "чистил(а) ботинки": 5,
        "поливал(а) цветы": 7,
        "ловил(а) бабочек": 6,
        "собирал(а) ягоды": 8,
        "помогал(а) старушке перейти дорогу": 10,
        "писал(а) стихи": 4,
        "играл(а) на гитаре": 6,
        "готовил(а) обед": 9,
        "читал(а) книгу": 3,
        "смотрел(а) в окно": 2
    }
    COOLDOWN_SECONDS = 15 * 60  # 15 минут в секундах

class AchievementsConfig:
    MESSAGE_MILESTONES = {
        100: "Новичок",
        500: "Активный участник", 
        1000: "Ветеран чата",
        5000: "Легенда"
    }

# В record_message после увеличения total_messages
# for milestone, title in AchievementsConfig.MESSAGE_MILESTONES.items():
#     if total_messages == milestone:
#         # Награда за достижение
#         lumcoins += milestone // 10
#         # Уведомление пользователю
#         await bot.send_message(
#             user_id,
#             f"🏆 Достижение: {title}! Вы отправили {milestone} сообщений. Награда: {milestone // 10} Lumcoins."
#         )