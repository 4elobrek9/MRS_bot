import random
import json
import time
from pathlib import Path
import aiohttp
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

# Путь к кэш-файлу для анекдотов
JOKES_CACHE_FILE = Path("data") / "jokes_cache.json"

class JokesManager:
    def __init__(self):
        self.jokes = []
        self.load_jokes_from_cache()

    def load_jokes_from_cache(self):
        """Загружает анекдоты из кэш-файла, если он существует и не устарел."""
        if JOKES_CACHE_FILE.exists():
            try:
                with open(JOKES_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                # Кэш считается актуальным в течение 12 часов
                if time.time() - cache_data.get('timestamp', 0) < 12 * 3600:
                    self.jokes = cache_data.get('jokes', [])
                    logger.info("Jokes loaded from cache.")
            except Exception as e:
                logger.error(f"Error loading jokes from cache: {e}")

    async def fetch_jokes(self):
        """Загружает анекдоты с сайта и сохраняет их в кэш."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.anekdot.ru/random/anekdot/") as response:
                    response.raise_for_status()
                    html = await response.text()

            soup = BeautifulSoup(html, 'html.parser')
            joke_divs = soup.find_all('div', class_='text')

            self.jokes = [div.get_text(separator="\n").strip() for div in joke_divs if div.get_text(separator="\n").strip()]

            if self.jokes:
                # Сохраняем в кэш
                with open(JOKES_CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'timestamp': time.time(), 'jokes': self.jokes}, f, ensure_ascii=False, indent=4)
                logger.info(f"Fetched and cached {len(self.jokes)} jokes.")
            else:
                logger.warning("No jokes found on anekdot.ru.")
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching jokes: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching jokes: {e}", exc_info=True)

    def get_random_joke(self):
        """Возвращает случайный анекдот из кэша или загружает новые, если кэш пуст."""
        if not self.jokes:
            # Если кэш пуст, загружаем анекдоты синхронно
            self.fetch_jokes_sync()
            if not self.jokes:
                return "Не удалось найти анекдот. Попробуйте позже."

        return random.choice(self.jokes)

    def fetch_jokes_sync(self):
        """Синхронная версия fetch_jokes для использования при пустом кэше."""
        import time
        import aiohttp
        from bs4 import BeautifulSoup

        try:
            with aiohttp.ClientSession() as session:
                response = session.get("https://www.anekdot.ru/random/anekdot/")
                response.raise_for_status()
                html = response.text()

            soup = BeautifulSoup(html, 'html.parser')
            joke_divs = soup.find_all('div', class_='text')

            self.jokes = [div.get_text(separator="\n").strip() for div in joke_divs if div.get_text(separator="\n").strip()]

            if self.jokes:
                # Сохраняем в кэш
                with open(JOKES_CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'timestamp': time.time(), 'jokes': self.jokes}, f, ensure_ascii=False, indent=4)
                logger.info(f"Fetched and cached {len(self.jokes)} jokes.")
            else:
                logger.warning("No jokes found on anekdot.ru.")
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching jokes: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching jokes: {e}", exc_info=True)
