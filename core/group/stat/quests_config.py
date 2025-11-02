# quests_config.py (исправленная версия)

import hashlib
from datetime import datetime, timedelta
import random
from typing import Dict, List, Any

class QuestsConfig:
    """Конфигурация системы заданий с фиксированными заданиями"""
    
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
    def generate_daily_seed(user_id: int) -> int:
        """Генерирует seed на основе user_id и текущей даты"""
        today_str = datetime.now().strftime('%Y-%m-%d')
        seed_str = f"{user_id}_{today_str}"
        return int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)

    @staticmethod
    def generate_weekly_seed(user_id: int) -> int:
        """Генерирует seed на основе user_id и текущей недели"""
        today = datetime.now()
        week_str = today.strftime('%Y-%W')  # Год и номер недели
        seed_str = f"{user_id}_{week_str}"
        return int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)

    @staticmethod
    def generate_quest_id(quest_data: Dict[str, Any], user_id: int) -> str:
        """Генерирует уникальный ID задания для пользователя"""
        base_id = quest_data["id"]
        # Используем дату для дневных заданий, неделю для недельных
        if "daily" in base_id:
            timestamp = datetime.now().strftime('%Y%m%d')
        else:
            timestamp = datetime.now().strftime('%Y%W')
        return f"{user_id}_{base_id}_{timestamp}"

    @staticmethod
    def get_daily_quests_for_user(user_id: int, count: int = DAILY_QUESTS_COUNT) -> List[Dict[str, Any]]:
        """Получает фиксированный набор ежедневных заданий для конкретного пользователя"""
        all_quests = []
        for category in QuestsConfig.DAILY_QUESTS.values():
            all_quests.extend(category)
        
        # Устанавливаем seed для детерминированного выбора заданий
        seed = QuestsConfig.generate_daily_seed(user_id)
        random.seed(seed)
        
        selected_quests = random.sample(all_quests, min(count, len(all_quests)))
        
        # Сбрасываем seed
        random.seed()
        
        # Генерируем конкретные значения для заданий и уникальные ID
        processed_quests = []
        for quest in selected_quests:
            quest_copy = quest.copy()
            
            # Устанавливаем seed для детерминированной генерации требований
            requirement_seed = QuestsConfig.generate_daily_seed(user_id + hash(quest["id"]))
            random.seed(requirement_seed)
            
            for key, value_func in quest_copy["required"].items():
                if callable(value_func):
                    quest_copy["required"][key] = value_func()
            
            # Сбрасываем seed
            random.seed()
                    
            # Заполняем описание конкретными значениями
            quest_copy["description"] = quest_copy["description"].format(**quest_copy["required"])
            
            # Генерируем уникальный ID для пользователя
            quest_copy["user_quest_id"] = QuestsConfig.generate_quest_id(quest_copy, user_id)
            quest_copy["original_id"] = quest_copy["id"]
            
            processed_quests.append(quest_copy)
            
        return processed_quests

    @staticmethod
    def get_weekly_quests_for_user(user_id: int, count: int = WEEKLY_QUESTS_COUNT) -> List[Dict[str, Any]]:
        """Получает фиксированный набор еженедельных заданий для конкретного пользователя"""
        # Устанавливаем seed для детерминированного выбора заданий
        seed = QuestsConfig.generate_weekly_seed(user_id)
        random.seed(seed)
        
        selected_quests = random.sample(QuestsConfig.WEEKLY_QUESTS, min(count, len(QuestsConfig.WEEKLY_QUESTS)))
        
        # Сбрасываем seed
        random.seed()
        
        # Генерируем конкретные значения для заданий и уникальные ID
        processed_quests = []
        for quest in selected_quests:
            quest_copy = quest.copy()
            
            # Устанавливаем seed для детерминированной генерации требований
            requirement_seed = QuestsConfig.generate_weekly_seed(user_id + hash(quest["id"]))
            random.seed(requirement_seed)
            
            for key, value_func in quest_copy["required"].items():
                if callable(value_func):
                    quest_copy["required"][key] = value_func()
            
            # Сбрасываем seed
            random.seed()
                    
            # Заполняем описание конкретными значениями
            quest_copy["description"] = quest_copy["description"].format(**quest_copy["required"])
            
            # Генерируем уникальный ID для пользователя
            quest_copy["user_quest_id"] = QuestsConfig.generate_quest_id(quest_copy, user_id)
            quest_copy["original_id"] = quest_copy["id"]
            
            processed_quests.append(quest_copy)
            
        return processed_quests