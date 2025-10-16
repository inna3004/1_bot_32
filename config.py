import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

    ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]

    DATABASE_URL = os.getenv('DATABASE_URL')
    CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

    TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
    TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
    TELEGRAM_SESSION_NAME = os.getenv('TELEGRAM_SESSION_NAME', 'bot_session')

    # Пути для Docker  # todo не используются, убрать из конфига
    SESSION_PATH = '/app/bot_session'
    STORAGE_PATH = '/app/storage'
    LOGS_PATH = '/app/logs'

    HIDDEN_COMMANDS = [
        'invite', 'generate_invite', 'active_invites', 'force_add',
        'sync_current', 'user_info', 'active_users', 'used_invites'
    ]