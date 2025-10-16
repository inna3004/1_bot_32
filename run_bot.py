#!/usr/bin/env python3
"""
Запуск для PTB 13.15
"""

import logging
import sys
import os

from storage.postgres_storage import init_db

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    from main import setup_application

    updater = None
    try:
        logger.info("🚀 Инициализация БД")
        init_db()

        updater = setup_application()
        logger.info("🚀 Запуск бота (PTB 13.15)...")

        updater = setup_application()

        logger.info("✅ Бот запущен. Используйте Ctrl+C для остановки")
        updater.start_polling()
        updater.idle()  # Блокирующий вызов

    except KeyboardInterrupt:
        logger.info("⏹️ Остановка бота...")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        if updater:
            updater.stop()
        # Останавливаем Telethon - ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЙ ТРЕКЕР
        from telethon_client import telethon_tracker
        telethon_tracker.stop_sync()
        logger.info("🛑 Бот и Telethon остановлены")


if __name__ == "__main__":
    main()