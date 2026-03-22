# # Optional: for deep-links like https://t.me/<BOT_USERNAME>?start=twitch

# import os
# from dotenv import load_dotenv

# load_dotenv()

# # Telegram
# BOT_TOKEN = os.getenv('5073738381:AAG2kYzHXd603ZPMiNqqQd90Zz0mIcGLvZk')
# ADMIN_IDS = [int(id.strip()) for id in os.getenv('ADMIN_IDS', '').split(',') if id.strip()]
# CHANNEL_ID = os.getenv('')

# BOT_USERNAME = 'testStmalina_bot'

# # Database
# DATABASE_URL = os.getenv('postgresql+psycopg2://randomgod:randomgod@db:5432/randomgod')

# # Twitch
# TWITCH_ENABLED = False

# TWITCH_CLIENT_ID = os.getenv('jbojui9nai523rntvwzkbyjq2208wg')
# TWITCH_CLIENT_SECRET = os.getenv('by9ij5fsmyf6wwi90ik9zeepq1nf4q')
# TWITCH_FOLLOW_SCOPE = 'user:read:follows'

# # Другие настройки
# MEDIA_DIR = '/app/media'


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
