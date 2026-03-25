import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
CHANNEL_ID = os.getenv('CHANNEL_ID')
BOT_USERNAME = 'testStmalina_bot'

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./bot.db')  # fallback на SQLite для теста

TWITCH_ENABLED = os.getenv('TWITCH_ENABLED', 'False').lower() == 'true'
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')
TWITCH_FOLLOW_SCOPE = 'user:read:follows'

MEDIA_DIR = '/app/media'

# Проверки
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN required!")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL required!")
