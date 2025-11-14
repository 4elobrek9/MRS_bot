import asyncio
from aiogram import Bot, types
from core.group.stat.manager import ProfileManager
from core.group.stat.config import ProfileConfig
import logging

logging.basicConfig(level=logging.INFO)

API_TOKEN = 'YOUR_API_TOKEN_HERE'  # Replace with your actual API token

async def main():
    bot = Bot(token=API_TOKEN)
    profile_manager = ProfileManager()

    # Connect to the database
    await profile_manager.connect()

    # Create a mock user
    user = types.User(
        id=123456789,
        is_bot=False,
        first_name="Test",
        last_name="User",
        username="testuser",
        language_code="en"
    )

    # Create a mock profile
    profile = {
        'user_id': user.id,
        'level': 1,
        'exp': 50,
        'lumcoins': 10,
        'plumcoins': 5,
        'daily_messages': 10,
        'total_messages': 100,
        'flames': 5,
        'last_activity_date': '2023-01-01',
        'active_background': 'default'
    }

    # Generate the profile image
    image_bytes = await profile_manager.generate_profile_image(user, profile, bot)

    # Save the image to a file for inspection
    with open('test_profile_image.png', 'wb') as f:
        f.write(image_bytes.getvalue())

    print("Profile image generated successfully!")

    # Close the database connection
    await profile_manager.close()

if __name__ == '__main__':
    asyncio.run(main())
