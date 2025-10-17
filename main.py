import logging
from telegram import Update

from storage.repository import SubscriberRepository
from telegram.ext import Updater, CallbackContext, MessageHandler, Filters
from config import Config
from telethon_client import telethon_tracker

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# ОТЛАДКА: Выводим конфиг при запуске
logger.info(f"🔧 Загружен конфиг: ADMIN_IDS = {Config.ADMIN_IDS}")
logger.info(f"🔧 TELEGRAM_TOKEN = {Config.TELEGRAM_TOKEN[:10]}...")
logger.info(f"🔧 CHANNEL_ID = {Config.CHANNEL_ID}")

# Инициализация репозиториев
subscriber_repo = SubscriberRepository()


def handle_all_messages(update: Update, context: CallbackContext):
    """Универсальный обработчик для команд (все ответы в ЛС)"""
    # Проверяем, что это сообщение с командой
    if not update.message or not update.message.text:
        return

    message_text = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or "без username"

    # Проверяем, начинается ли сообщение с команды
    if not message_text.startswith('/'):
        return

    # Разбираем команду и аргументы
    parts = message_text.split()
    command_full = parts[0][1:]  # Убираем / в начале
    command = command_full.split('@')[0]  # Убираем @username если есть

    # ДЕТАЛЬНАЯ ОТЛАДКА КОМАНДЫ
    logger.info(f"🔍 Команда '{command}' от пользователя {user_id} (@{username})")
    logger.info(f"🔍 Полный текст: '{message_text}'")
    logger.info(f"🔍 ADMIN_IDS: {Config.ADMIN_IDS}")
    logger.info(f"🔍 user_id in ADMIN_IDS: {user_id in Config.ADMIN_IDS}")

    # Проверяем права для команд
    if user_id not in Config.ADMIN_IDS:
        logger.warning(f"🚫 ДОСТУП ЗАПРЕЩЕН: {user_id} не в списке админов")
        try:
            update.message.delete()
            logger.info(f"✅ Сообщение от не-админа {user_id} удалено")
        except Exception as e:
            logger.error(f"❌ Не удалось удалить сообщение: {e}")
        return

    # Для админов - выполняем команду но удаляем исходное сообщение
    if user_id in Config.ADMIN_IDS:
        try:
            update.message.delete()
            logger.info(f"✅ Сообщение админа {user_id} удалено из чата")
        except Exception as e:
            logger.error(f"❌ Не удалось удалить сообщение админа: {e}")

    # Логика выполнения команд
    try:
        if command == 'start':
            response = "🤖 Бот активен\n\n\n/stats - Статистика по каналам/группам"

        elif command == 'stats':
            try:
                context.bot.send_message(
                    chat_id=user_id,
                    text="🔄 Собираем статистику..."
                )
                channel_identifiers = Config.CHANNEL_ID
                data = {}
                for channel_identifier in channel_identifiers:
                    db_count = subscriber_repo.get_subscriber_count(channel_identifier)
                    data.update(
                            {
                                channel_identifier: db_count
                            }
                        )
                response = f"📊 Статистика:\n🔗 Telethon подключен: {telethon_tracker.is_connected}"
                if data:
                    for key, value in data.items():
                        response += "\n\nКанал {channel}:\n👥 Участников в канале: {db_count}".format(
                            channel=key, db_count=value
                        )
            except Exception as e:
                response = f"❌ Ошибка получения статистики: {e}"
        else:
            response = "❌ Неизвестная команда"

        # Отправляем ответ в ЛИЧНЫЕ сообщения
        context.bot.send_message(
            chat_id=user_id,
            text=response
        )
        logger.info(f"✅ Ответ отправлен в ЛС пользователю {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка в команде {command} для пользователя {user_id}: {e}")
        context.bot.send_message(
            chat_id=user_id,
            text=f"❌ Ошибка в команде {command}: {e}"
        )


def remove_old_subscribers(context: CallbackContext):
    """Автоматическое удаление через 32 дня с детальным логированием разблокировки"""
    try:
        subscribers_to_remove = subscriber_repo.get_subscribers_to_remove()
        logger.info(f"🔍 Найдено для удаления: {len(subscribers_to_remove)} подписчиков")

        if not subscribers_to_remove:
            return

        for subscriber in subscribers_to_remove:
            user_id, username, first_name, last_name, channel_id = subscriber

            try:
                logger.info(f"🔄 Начинаем процесс удаления пользователя {user_id}")

                # 1. БАН на 1 секунду (удаление из канала)
                logger.info(f"⏳ Выполняем бан пользователя {user_id} на 1 секунду...")
                from datetime import datetime, timedelta
                context.bot.ban_chat_member(
                    chat_id=channel_id,
                    user_id=user_id,
                    until_date=datetime.now() + timedelta(seconds=1)
                )
                logger.info(f"✅ Пользователь {user_id} забанен (удален из канала)")

                # 2. МГНОВЕННАЯ РАЗБЛОКИРОВКА (убираем из ЧС)
                logger.info(f"⏳ Выполняем РАЗБЛОКИРОВКУ пользователя {user_id}...")
                try:
                    context.bot.unban_chat_member(
                        chat_id=channel_id,
                        user_id=user_id,
                        only_if_banned=True
                    )
                    logger.info(f"🎉 УСПЕХ: Пользователь {user_id} РАЗБЛОКИРОВАН и убран из черного списка!")
                except Exception as unban_error:
                    logger.error(f"❌ ОШИБКА РАЗБЛОКИРОВКИ {user_id}: {unban_error}")
                    # Продолжаем выполнение даже при ошибке разблокировки

                # 3. Отмечаем в БД
                subscriber_repo.mark_as_removed(user_id, channel_id)
                logger.info(f"📊 Пользователь {user_id} помечен как удаленный в БД")

                logger.info(f"🎯 ЗАВЕРШЕНО: Пользователь {user_id} полностью обработан")

            except Exception as e:
                logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА для {user_id}: {e}")
                # Все равно помечаем как удаленного, даже если была ошибка
                try:
                    subscriber_repo.mark_as_removed(user_id, channel_id)
                    logger.info(f"📊 Пользователь {user_id} помечен как удаленный несмотря на ошибку")
                except Exception as db_error:
                    logger.error(f"🗄️ Ошибка БД для {user_id}: {db_error}")

    except Exception as e:
        logger.error(f"💥 ОБЩАЯ ОШИБКА в задаче удаления: {e}")


def setup_application():
    # 🎯 ОСНОВНОЙ ЗАПУСК TELETHON ТРЕКЕРА
    logger.info("🔄 Запуск Telethon трекера как основного монитора...")
    telethon_success = telethon_tracker.start_sync()

    if telethon_success:
        logger.info("✅ Telethon трекер запущен как основной монитор участников")
    else:
        logger.error("❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось запустить Telethon трекер!")
        # Можно продолжить работу, но с ограниченным функционалом

    # 🎯 Bot API для команд и уведомлений
    updater = Updater(Config.TELEGRAM_TOKEN, use_context=True)
    application = updater.dispatcher

    # 📝 Обработчики Bot API (дополнительные к Telethon)
    application.add_handler(MessageHandler(Filters.all, handle_all_messages))

    # ⏰ Планировщик заданий
    job_queue = updater.job_queue
    if job_queue:
        job_queue.run_repeating(remove_old_subscribers, interval=300, first=10)

        # 🔄 ПЕРИОДИЧЕСКАЯ СИНХРОНИЗАЦИЯ TELETHON (каждый час)
        job_queue.run_repeating(sync_telethon_periodically, interval=600, first=30)

        logger.info("✅ JobQueue запущен с Telethon синхронизацией")

    return updater


def sync_telethon_periodically(context: CallbackContext):
    """Периодическая синхронизация через Telethon"""
    try:
        logger.info("🔄 Запуск периодической синхронизации Telethon...")

        # Используем простую версию синхронизации
        result = telethon_tracker.force_sync_members_sync_simple()
        logger.info(f"📊 Результат синхронизации: {result}")

    except Exception as e:
        logger.error(f"❌ Ошибка периодической синхронизации: {e}")
