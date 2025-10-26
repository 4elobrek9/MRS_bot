from typing import Dict, Any, Optional

# Иконки для редкостей
RARITY_ICONS = {
    "Легендарная": "⭐",
    "Мифическая": "✨"
}

class PlumShopConfig:
    """Конфигурация П-Магазина, предметы, продающиеся за PLUMcoins."""
    
    # URL для иконки магазина (для использования в будущем)
    SHOP_ICON_URL = "https://placehold.co/100x100/3A003A/FFFFFF/png?text=P-Shop"
    
    # Словарь с предметами: {key: {name, price, rarity, description, icon, inventory_key}}
    PLUM_SHOP_ITEMS: Dict[str, Dict[str, Any]] = {
        "handcuffs_legendary": {
            "name": "Наручники",
            "price": 1000,
            "rarity": "Легендарная",
            "description": "Специальные наручники для ролевых игр. Крайне надежны.",
            "icon": "🔗",
            "inventory_key": "наручники" # Ключ, под которым предмет будет храниться в инвентаре
        },
        "gag_mythic": {
            "name": "Кляп",
            "price": 5000,
            "rarity": "Мифическая",
            "description": "Позволяет заставить собеседника замолчать в RP.",
            "icon": "🤐",
            "inventory_key": "кляп"
        },
        "whip_mythic": {
            "name": "Плётка",
            "price": 5000,
            "rarity": "Мифическая",
            "description": "Мощный инструмент для доминирования в ролевых играх.",
            "icon": "鞭", 
            "inventory_key": "плётка"
        }
    }
    
    # Ключ для данных callback-запроса о покупке
    BUY_ITEM_CALLBACK_DATA = "plum_buy_item"
    
    @staticmethod
    def get_item_by_key(key: str) -> Optional[Dict[str, Any]]:
        """Получает данные предмета по его ключу."""
        return PlumShopConfig.PLUM_SHOP_ITEMS.get(key)