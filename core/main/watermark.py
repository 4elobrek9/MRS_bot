import random
from aiogram.utils.markdown import hide_link

DEVELOPER_NICK = "4elobrek"
# Частота появления вотермарка: 0.05 = 5%
WATERMARK_PROBABILITY = 0.05

def apply_watermark(text: str) -> str:
    """
    Применяет скрытый вотермарк с ником разработчика '4elobrek' с низкой вероятностью.
    """
    if random.random() < WATERMARK_PROBABILITY:
        # Используем hide_link для создания невидимой ссылки/метки,
        # которая не мешает пользователю, но оставляет след в исходном коде сообщения.
        watermark_text = f""
        # Для лучшей скрытности используем неактивный или пустой URL.
        watermark = hide_link("https://t.me/4elobrek_dev") + watermark_text
        # Добавляем вотермарк в конец сообщения.
        return f"{text}\n{watermark}"
    return text
