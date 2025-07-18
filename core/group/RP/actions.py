from core.group.RP.rmain import *

class RPActions:
    INTIMATE_ACTIONS: Dict[str, Dict[str, Dict[str, int]]] = {
        "добрые": {
            "поцеловать": {"hp_change_target": +10, "hp_change_sender": +1},
            "обнять": {"hp_change_target": +15, "hp_change_sender": +5},
            "погладить": {"hp_change_target": +5, "hp_change_sender": +2},
            "романтический поцелуй": {"hp_change_target": +20, "hp_change_sender": +10},
            "трахнуть": {"hp_change_target": +30, "hp_change_sender": +15},
            "поцеловать в щёчку": {"hp_change_target": +7, "hp_change_sender": +3},
            "прижать к себе": {"hp_change_target": +12, "hp_change_sender": +6},
            "покормить": {"hp_change_target": +9, "hp_change_sender": -2},
            "напоить": {"hp_change_target": +6, "hp_change_sender": -1},
            "сделать массаж": {"hp_change_target": +15, "hp_change_sender": +3},
            "спеть песню": {"hp_change_target": +5, "hp_change_sender": +1},
            "подарить цветы": {"hp_change_target": +12, "hp_change_sender": -12},
            "подрочить": {"hp_change_target": +12, "hp_change_sender": 0},
            "полечить": {"hp_change_target": +25, "hp_change_sender": -5},
        },
        "нейтральные": {
            "толкнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "схватить": {"hp_change_target": 0, "hp_change_sender": 0},
            "помахать": {"hp_change_target": 0, "hp_change_sender": 0},
            "кивнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "похлопать": {"hp_change_target": 0, "hp_change_sender": 0},
            "постучать": {"hp_change_target": 0, "hp_change_sender": 0},
            "попрощаться": {"hp_change_target": 0, "hp_change_sender": 0},
            "шепнуть": {"hp_change_target": 0, "hp_change_sender": 0},
            "почесать спинку": {"hp_change_target": +5, "hp_change_sender": 0},
            "успокоить": {"hp_change_target": +5, "hp_change_sender": +1},
            "заплакать": {}, "засмеяться": {}, "удивиться": {}, "подмигнуть": {},
        },
        "злые": {
            "уебать": {"hp_change_target": -20, "hp_change_sender": -2},
            "схватить за шею": {"hp_change_target": -25, "hp_change_sender": -3},
            "ударить": {"hp_change_target": -10, "hp_change_sender": -1},
            "укусить": {"hp_change_target": -15, "hp_change_sender": 0},
            "шлепнуть": {"hp_change_target": -8, "hp_change_sender": 0},
            "пощечина": {"hp_change_target": -12, "hp_change_sender": -1},
            "пнуть": {"hp_change_target": -10, "hp_change_sender": 0},
            "ущипнуть": {"hp_change_target": -7, "hp_change_sender": 0},
            "толкнуть сильно": {"hp_change_target": -9, "hp_change_sender": -1},
            "обозвать": {"hp_change_target": -5, "hp_change_sender": 0},
            "плюнуть": {"hp_change_target": -6, "hp_change_sender": 0},
            "превратить": {"hp_change_target": -80, "hp_change_sender": -10},
            "обидеть": {"hp_change_target": -7, "hp_change_sender": 0},
            "разозлиться": {"hp_change_target": -2, "hp_change_sender": -1},
            "испугаться": {"hp_change_target": -1, "hp_change_sender": 0},
            "издеваться": {"hp_change_target": -10, "hp_change_sender": -1},
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
