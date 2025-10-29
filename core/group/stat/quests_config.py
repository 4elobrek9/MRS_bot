from typing import Dict, List, Any
from datetime import timedelta
import random

class QuestsConfig:
    """Конфигурация системы заданий"""
    
    # Количество ежедневных заданий
    DAILY_QUESTS_COUNT = 3
    
    # Количество еженедельных заданий
    WEEKLY_QUESTS_COUNT = 2
    
    # Базовые награды для ежедневных заданий
    DAILY_QUEST_REWARDS = {
        "easy": {"lumcoins": 50, "exp": 100},
        "medium": {"lumcoins": 100, "exp": 200},
        "hard": {"lumcoins": 200, "exp": 400}
    }
    
    # Награды за еженедельные задания (в PLUM)
    WEEKLY_QUEST_PLUM_REWARDS = {
        "medium": 500,
        "hard": 1000
    }

    # Ежедневные задания
    DAILY_QUESTS = {
        # Социальные задания
        "social_interactions": [
            {
                "id": "daily_chat_messages",
                "name": "Общительный",
                "description": "Отправить {count} сообщений в чат",
                "type": "message_count",
                "difficulty": "easy",
                "required": {"count": lambda: random.randint(10, 20)}
            },
            {
                "id": "daily_rp_actions",
                "name": "Ролевик",
                "description": "Использовать {count} RP-действий",
                "type": "rp_actions",
                "difficulty": "medium",
                "required": {"count": lambda: random.randint(5, 10)}
            },
            {
                "id": "daily_reactions",
                "name": "Эмоциональный",
                "description": "Использовать {count} разных эмоций (обнять, погладить и т.д.)",
                "type": "unique_rp_actions",
                "difficulty": "medium",
                "required": {"count": lambda: random.randint(3, 5)}
            }
        ],
        
        # Экономические задания
        "economy": [
            {
                "id": "daily_market_listings",
                "name": "Торговец",
                "description": "Выставить {count} предметов на рынок",
                "type": "market_listings",
                "difficulty": "medium",
                "required": {"count": lambda: random.randint(2, 4)}
            },
            {
                "id": "daily_market_purchases",
                "name": "Покупатель",
                "description": "Купить {count} предметов на рынке",
                "type": "market_purchases",
                "difficulty": "medium",
                "required": {"count": lambda: random.randint(1, 3)}
            },
            {
                "id": "daily_crafting",
                "name": "Мастер",
                "description": "Создать {count} предметов на верстаке",
                "type": "crafting",
                "difficulty": "hard",
                "required": {"count": lambda: random.randint(2, 4)}
            }
        ],
        
        # Игровые задания
        "gaming": [
            {
                "id": "daily_casino_games",
                "name": "Азартный",
                "description": "Сыграть {count} раз в казино",
                "type": "casino_games",
                "difficulty": "easy",
                "required": {"count": lambda: random.randint(3, 5)}
            },
            {
                "id": "daily_casino_wins",
                "name": "Везунчик",
                "description": "Выиграть {count} раз в казино",
                "type": "casino_wins",
                "difficulty": "hard",
                "required": {"count": lambda: random.randint(2, 3)}
            }
        ],
        
        # Работа и прокачка
        "progression": [
            {
                "id": "daily_work",
                "name": "Работяга",
                "description": "Поработать {count} раз",
                "type": "work",
                "difficulty": "easy",
                "required": {"count": lambda: random.randint(3, 5)}
            },
            {
                "id": "daily_exp_gain",
                "name": "Ученик",
                "description": "Получить {count} опыта",
                "type": "exp_gain",
                "difficulty": "medium",
                "required": {"count": lambda: random.randint(500, 1000)}
            }
        ]
    }

    # Еженедельные задания
    WEEKLY_QUESTS = [
        {
            "id": "weekly_market_profit",
            "name": "Бизнесмен",
            "description": "Заработать {count} LUM на рынке",
            "type": "market_profit",
            "difficulty": "hard",
            "required": {"count": lambda: random.randint(1000, 2000)}
        },
        {
            "id": "weekly_casino_profit",
            "name": "Профессиональный игрок",
            "description": "Выиграть {count} LUM в казино",
            "type": "casino_profit",
            "difficulty": "hard",
            "required": {"count": lambda: random.randint(2000, 3000)}
        },
        {
            "id": "weekly_rp_master",
            "name": "Мастер RP",
            "description": "Использовать {count} уникальных RP-действий",
            "type": "unique_rp_actions_total",
            "difficulty": "medium",
            "required": {"count": lambda: random.randint(15, 20)}
        },
        {
            "id": "weekly_social_star",
            "name": "Звезда чата",
            "description": "Набрать {count} очков активности",
            "type": "activity_score",
            "difficulty": "hard",
            "required": {"count": lambda: random.randint(5000, 7000)}
        },
        {
            "id": "weekly_craftsman",
            "name": "Мастер-ремесленник",
            "description": "Создать {count} редких или эпических предметов",
            "type": "rare_crafting",
            "difficulty": "medium",
            "required": {"count": lambda: random.randint(5, 8)}
        }
    ]

    @staticmethod
    def get_daily_quests(count: int = DAILY_QUESTS_COUNT) -> List[Dict[str, Any]]:
        """Получает случайный набор ежедневных заданий"""
        all_quests = []
        for category in QuestsConfig.DAILY_QUESTS.values():
            all_quests.extend(category)
            
        selected_quests = random.sample(all_quests, min(count, len(all_quests)))
        
        # Генерируем конкретные значения для заданий
        for quest in selected_quests:
            for key, value_func in quest["required"].items():
                if callable(value_func):
                    quest["required"][key] = value_func()
                    
            # Заполняем описание конкретными значениями
            quest["description"] = quest["description"].format(**quest["required"])
            
        return selected_quests

    @staticmethod
    def get_weekly_quests(count: int = WEEKLY_QUESTS_COUNT) -> List[Dict[str, Any]]:
        """Получает случайный набор еженедельных заданий"""
        selected_quests = random.sample(QuestsConfig.WEEKLY_QUESTS, min(count, len(QuestsConfig.WEEKLY_QUESTS)))
        
        # Генерируем конкретные значения для заданий
        for quest in selected_quests:
            for key, value_func in quest["required"].items():
                if callable(value_func):
                    quest["required"][key] = value_func()
                    
            # Заполняем описание конкретными значениями
            quest["description"] = quest["description"].format(**quest["required"])
            
        return selected_quests