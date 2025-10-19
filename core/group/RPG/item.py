class ItemSystem:
    SHOP_ITEMS = {
        "wood": {"name": "🪵 Дерево", "type": "material", "rarity": "common", "cost": 10, "description": "Обычная древесина для крафта"},
        "iron_ore": {"name": "⛏️ Железная руда", "type": "material", "rarity": "common", "cost": 25, "description": "Руда для выплавки железа"},
        "health_potion": {"name": "🧪 Зелье здоровья", "type": "consumable", "rarity": "uncommon", "cost": 50, "description": "Восстанавливает 30 HP", "effect": {"heal": 30}},
        "magic_crystal": {"name": "💎 Магический кристалл", "type": "material", "rarity": "rare", "cost": 150, "description": "Редкий магический компонент"},
        "energy_drink": {"name": "⚡ Энергетик", "type": "consumable", "rarity": "common", "cost": 30, "description": "Восстанавливает энергию", "effect": {"energy": 20}},
        "gold_ingot": {"name": "🥇 Золотой слиток", "type": "material", "rarity": "rare", "cost": 200, "description": "Ценный металл для крафта"},
        "lucky_charm": {"name": "🍀 Талисман удачи", "type": "equipment", "rarity": "epic", "cost": 500, "description": "Увеличивает удачу", "stats": {"luck": 10}},
        "dragon_scale": {"name": "🐉 Чешуя дракона", "type": "material", "rarity": "legendary", "cost": 1000, "description": "Легендарный материал"}
    }

    CRAFT_RECIPES = {
        "iron_ingot": {
            "name": "🔩 Железный слиток", 
            "result": "iron_ingot", 
            "result_name": "🔩 Железный слиток", 
            "cost": 25, 
            "materials": {"iron_ore": 3}, 
            "description": "Выплавленный железный слиток"
        },
        "basic_sword": {
            "name": "⚔️ Обычный меч", 
            "result": "basic_sword", 
            "result_name": "⚔️ Обычный меч", 
            "cost": 50, 
            "materials": {"wood": 2, "iron_ingot": 1}, 
            "description": "Надёжный железный меч", 
            "stats": {"attack": 5}
        },
        "advanced_potion": {
            "name": "🧪 Улучшенное зелье", 
            "result": "advanced_potion", 
            "result_name": "🧪 Улучшенное зелье здоровья", 
            "cost": 100, 
            "materials": {"health_potion": 2, "magic_crystal": 1}, 
            "description": "Восстанавливает 60 HP", 
            "effect": {"heal": 60}
        }
    }

    CRAFTED_ITEMS = {
        "iron_ingot": {"name": "🔩 Железный слиток", "type": "material", "rarity": "uncommon", "description": "Выплавленный железный слиток"},
        "basic_sword": {"name": "⚔️ Обычный меч", "type": "equipment", "rarity": "uncommon", "description": "Надёжный железный меч", "stats": {"attack": 5}},
        "advanced_potion": {"name": "🧪 Улучшенное зелье здоровья", "type": "consumable", "rarity": "rare", "description": "Восстанавливает 60 HP", "effect": {"heal": 60}}
    }

    @classmethod
    def get_sorted_shop_items(cls) -> list[tuple]:
        return sorted(cls.SHOP_ITEMS.items(), key=lambda x: x[1]['cost'])

    @classmethod
    def get_item_sell_price(cls, item_key: str) -> int:
        if item_key in cls.SHOP_ITEMS:
            return max(1, cls.SHOP_ITEMS[item_key]['cost'] // 2)
        elif item_key in cls.CRAFTED_ITEMS:
            base_prices = {
                "iron_ingot": 12,
                "basic_sword": 25,
                "advanced_potion": 50
            }
            return base_prices.get(item_key, 10)
        else:
            return 5
