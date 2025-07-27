from core.group.RP.rmain import *

class RPActions:
    INTIMATE_ACTIONS: Dict[str, Dict[str, Dict[str, any]]] = {
        "добрые": {
            "поцеловать": {"verb": "поцеловал(а)", "hp_change_target": +10, "hp_change_sender": +1},
            "обнять": {"verb": "обнял(а)", "hp_change_target": +15, "hp_change_sender": +5},
            "погладить": {"verb": "погладил(а)", "hp_change_target": +5, "hp_change_sender": +2},
            "романтический поцелуй": {"verb": "совершил(а) романтический поцелуй с", "hp_change_target": +20, "hp_change_sender": +10},
            "трахнуть": {"verb": "трахнул(а)", "hp_change_target": +30, "hp_change_sender": +15},
            "поцеловать в щёчку": {"verb": "поцеловал(а) в щёчку", "hp_change_target": +7, "hp_change_sender": +3},
            "прижать к себе": {"verb": "прижал(а) к себе", "hp_change_target": +12, "hp_change_sender": +6},
            "покормить": {"verb": "покормил(а)", "hp_change_target": +9, "hp_change_sender": -2},
            "напоить": {"verb": "напоил(а)", "hp_change_target": +6, "hp_change_sender": -1},
            "сделать массаж": {"verb": "сделал(а) массаж", "hp_change_target": +15, "hp_change_sender": +3},
            "спеть песню": {"verb": "спел(а) песню для", "hp_change_target": +5, "hp_change_sender": +1},
            "подарить цветы": {"verb": "подарил(а) цветы", "hp_change_target": +12, "hp_change_sender": -12},
            "подрочить": {"verb": "подрочил(а)", "hp_change_target": +12, "hp_change_sender": 0},
            "полечить": {"verb": "полечил(а)", "hp_change_target": +25, "hp_change_sender": -5},
        },
        "нейтральные": {
            "толкнуть": {"verb": "толкнул(а)", "hp_change_target": 0, "hp_change_sender": 0},
            "схватить": {"verb": "схватил(а)", "hp_change_target": 0, "hp_change_sender": 0},
            "помахать": {"verb": "помахал(а)", "hp_change_target": 0, "hp_change_sender": 0},
            "кивнуть": {"verb": "кивнул(а)", "hp_change_target": 0, "hp_change_sender": 0},
            "похлопать": {"verb": "похлопал(а)", "hp_change_target": 0, "hp_change_sender": 0},
            "постучать": {"verb": "постучал(а)", "hp_change_target": 0, "hp_change_sender": 0},
            "попрощаться": {"verb": "попрощался(-ась) с", "hp_change_target": 0, "hp_change_sender": 0},
            "шепнуть": {"verb": "шепнул(а)", "hp_change_target": 0, "hp_change_sender": 0},
            "почесать спинку": {"verb": "почесал(а) спинку", "hp_change_target": +5, "hp_change_sender": 0},
            "успокоить": {"verb": "успокоил(а)", "hp_change_target": +5, "hp_change_sender": +1},
            "заплакать": {"verb": "заплакал(а)"}, 
            "засмеяться": {"verb": "засмеялся(-ась)"}, 
            "удивиться": {"verb": "удивился(-ась)"}, 
            "подмигнуть": {"verb": "подмигнул(а)"},
        },
        "злые": {
            "уебать": {"verb": "уебал(а)", "hp_change_target": -20, "hp_change_sender": -2},
            "схватить за шею": {"verb": "схватил(а) за шею", "hp_change_target": -25, "hp_change_sender": -3},
            "ударить": {"verb": "ударил(а)", "hp_change_target": -10, "hp_change_sender": -1},
            "укусить": {"verb": "укусил(а)", "hp_change_target": -15, "hp_change_sender": 0},
            "шлепнуть": {"verb": "шлепнул(а)", "hp_change_target": -8, "hp_change_sender": 0},
            "пощечина": {"verb": "дал(а) пощечину", "hp_change_target": -12, "hp_change_sender": -1},
            "пнуть": {"verb": "пнул(а)", "hp_change_target": -10, "hp_change_sender": 0},
            "ущипнуть": {"verb": "ущипнул(а)", "hp_change_target": -7, "hp_change_sender": 0},
            "толкнуть сильно": {"verb": "сильно толкнул(а)", "hp_change_target": -9, "hp_change_sender": -1},
            "обозвать": {"verb": "обозвал(а)", "hp_change_target": -5, "hp_change_sender": 0},
            "плюнуть": {"verb": "плюнул(а) в", "hp_change_target": -6, "hp_change_sender": 0},
            "превратить": {"verb": "превратил(а)", "hp_change_target": -80, "hp_change_sender": -10},
            "обидеть": {"verb": "обидел(а)", "hp_change_target": -7, "hp_change_sender": 0},
            "разозлиться": {"verb": "разозлился(-ась)"},
            "испугаться": {"verb": "испугался(-ась)"},
            "издеваться": {"verb": "издевался(-ась) над", "hp_change_target": -10, "hp_change_sender": -1},
        }
    }
    ALL_ACTION_DATA: Dict[str, Dict[str, int]] = {
        action: data if data else {}
        for category_actions in INTIMATE_ACTIONS.values()
        for action, data in category_actions.items()
    }
    SORTED_COMMANDS_FOR_PARSING: List[str] = sorted(
        ALL_ACTION_DATA.keys(), key=len, reverse=True
    )
    ALL_ACTIONS_LIST_BY_CATEGORY: Dict[str, List[str]] = {
        "Добрые действия ❤️": list(INTIMATE_ACTIONS["добрые"].keys()),
        "Нейтральные действия 😐": list(INTIMATE_ACTIONS["нейтральные"].keys()),
        "Злые действия 💀": list(INTIMATE_ACTIONS["злые"].keys())
    }
