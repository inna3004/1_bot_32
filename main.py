# todo если какие-то импорты не используются - убирай их, соблюдай чистоту кода. тут сама удалила
import logging
from datetime import datetime, timedelta
from telegram import Update, ChatMember
from storage.repository import SubscriberRepository, InviteRepository
from telegram.ext import Updater, CallbackContext, ChatMemberHandler, MessageHandler, Filters, ChatJoinRequestHandler
from storage.postgres_storage import get_connection
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
invite_repo = InviteRepository()

# ОСНОВНЫЕ ОБРАБОТЧИКИ
def track_chat_member(update: Update, context: CallbackContext):
    """Отслеживание когда пользователи присоединяются или покидают канал"""
    try:
        chat_member = update.chat_member
        new_status = chat_member.new_chat_member.status
        old_status = chat_member.old_chat_member.status
        user = chat_member.new_chat_member.user
        chat_id = chat_member.chat.id

        logger.info(f"🔄 Статус пользователя {user.id}: {old_status} -> {new_status}")

        # Устанавливаем CHANNEL_ID если не установлен
        if Config.CHANNEL_ID is None:
            Config.CHANNEL_ID = chat_id
            logger.info(f"Установлен ID канала: {chat_id}")

        # КОГДА ПОЛЬЗОВАТЕЛЬ СТАНОВИТСЯ УЧАСТНИКОМ
        if (old_status in [ChatMember.LEFT, ChatMember.KICKED, ChatMember.RESTRICTED, ChatMember.BANNED] and
                new_status == ChatMember.MEMBER):

            logger.info(f"🎉 ПОЛЬЗОВАТЕЛЬ {user.id} ВСТУПИЛ В КАНАЛ!")

            user_data = {
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'channel_id': chat_id,
                'added_by_admin': False,
                'manually_added': False
            }

            # Проверяем, является ли добавляющий админом
            try:
                admins = context.bot.get_chat_administrators(chat_id)
                admin_ids = [admin.user.id for admin in admins]

                # Если изменение сделал админ, отмечаем это
                if update.chat_member.from_user.id in admin_ids:
                    user_data['added_by_admin'] = True
                    user_data['manually_added'] = True
                    logger.info(f"👨‍💼 Пользователь {user.id} добавлен админом")
                else:
                    logger.info(f"🔗 Пользователь {user.id} вступил по инвайт-ссылке")
            except Exception as e:
                logger.error(f"Ошибка проверки админов: {e}")

            # СОХРАНЯЕМ В БАЗУ
            if subscriber_repo.add_or_renew_subscriber(user_data, "chat_member"):
                logger.info(f"✅ ПОЛЬЗОВАТЕЛЬ {user.id} УСПЕШНО ДОБАВЛЕН В БАЗУ!")

                # Уведомляем админов в ЛС
                admin_message = (
                    f"👤 Новый пользователь в группе:\n"
                    f"🆔 ID: {user.id}\n"
                    f"📛 Имя: {user.first_name} {user.last_name or ''}\n"
                    f"🔗 @{user.username or 'нет'}\n"
                    f"👨‍💼 Добавлен админом: {'Да' if user_data['added_by_admin'] else 'Нет'}\n"
                    f"⏰ Отсчет 32 дней начат!"
                )

                for admin_id in Config.ADMIN_IDS:
                    try:
                        context.bot.send_message(chat_id=admin_id, text=admin_message)
                    except Exception as e:
                        logger.error(f"Не удалось уведомить админа {admin_id}: {e}")
            else:
                logger.error(f"❌ НЕ УДАЛОСЬ ДОБАВИТЬ ПОЛЬЗОВАТЕЛЯ {user.id} В БАЗУ!")

        # КОГДА ПОЛЬЗОВАТЕЛЬ ПОКИДАЕТ/УДАЛЯЕТСЯ
        elif (old_status == ChatMember.MEMBER and
              new_status in [ChatMember.LEFT, ChatMember.KICKED]):
            logger.info(f"❌ ПОЛЬЗОВАТЕЛЬ {user.id} ПОКИНУЛ КАНАЛ")
            if subscriber_repo.mark_as_removed(user.id):
                logger.info(f"✅ Пользователь {user.id} помечен как удаленный")
            else:
                logger.error(f"❌ Не удалось пометить пользователя {user.id} как удаленного")

    except Exception as e:
        logger.error(f"❌ Ошибка отслеживания участников: {e}")

# ДОБАВЬ эту новую функцию для обработки вступлений по инвайтам:
def handle_chat_join_request(update: Update, context: CallbackContext):
    """Обработка запросов на вступление по инвайт-ссылкам"""
    try:
        if not update.chat_join_request:
            return

        user = update.chat_join_request.from_user
        chat_id = update.chat_join_request.chat.id
        invite_link = update.chat_join_request.invite_link

        logger.info(f"🔗 Запрос на вступление: пользователь {user.id} в чат {chat_id}")

        # Автоматически принимаем запрос
        try:
            update.chat_join_request.approve()
            logger.info(f"✅ Запрос на вступление одобрен для {user.id}")
        except Exception as e:
            logger.error(f"❌ Не удалось принять запрос: {e}")
            return

        # Регистрируем пользователя
        user_data = {
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'channel_id': chat_id,
            'added_by_admin': False,
            'manually_added': False
        }

        if subscriber_repo.add_or_renew_subscriber(user_data, "chat_member"):
            logger.info(f"✅ Пользователь {user.id} зарегистрирован через инвайт")

            # Если была использована инвайт-ссылка, отмечаем это
            if invite_link:
                invite_repo.mark_invite_used(invite_link.invite_link, user.id)
                logger.info(f"🔗 Инвайт-ссылка использована пользователем {user.id}")

            # Уведомление админам
            admin_message = (
                f"👤 Новый пользователь по инвайту:\n"
                f"🆔 ID: {user.id}\n"
                f"📛 Имя: {user.first_name} {user.last_name or ''}\n"
                f"🔗 @{user.username or 'нет'}\n"
                f"⏰ Отсчет 32 дней начат!"
            )

            for admin_id in Config.ADMIN_IDS:
                try:
                    context.bot.send_message(chat_id=admin_id, text=admin_message)
                except Exception as e:
                    logger.error(f"Не удалось уведомить админа {admin_id}: {e}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки запроса вступления: {e}")

# ФУНКЦИИ ИНВАЙТ-СИСТЕМЫ
def generate_simple_invite(context: CallbackContext, chat_id: int, admin_id: int):
    """Сгенерировать инвайт-ссылку без привязки к конкретному пользователю"""
    try:
        # Создаем инвайт-ссылку (действует 24 часа)
        invite_link = context.bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"invite_{int(datetime.now().timestamp())}",
            expire_date=datetime.now() + timedelta(hours=24),
            member_limit=1
        )

        # Сохраняем в базу как "общую" ссылку
        invite_repo.save_general_invite(invite_link.invite_link, admin_id)

        logger.info(f"🔗 Сгенерирована общая инвайт-ссылка админом {admin_id}")

        return (f"✅ Инвайт-ссылка сгенерирована!\n\n"
                f"🔗 {invite_link.invite_link}\n\n"
                f"📋 Отправьте эту ссылку оплатившему пользователю\n"
                f"⏰ Действует: 24 часа\n"
                f"👥 Использований: 1 раз\n\n"
                f"💡 Система автоматически зафиксирует нового участника!")

    except Exception as e:
        logger.error(f"❌ Ошибка генерации инвайта: {e}")
        return f"❌ Ошибка генерации ссылки: {e}"

def generate_invite_link(user_id: int, context: CallbackContext, chat_id: int):
    """Сгенерировать персональную инвайт-ссылку"""
    try:
        # Создаем инвайт-ссылку с именем, содержащим ID пользователя
        invite_link = context.bot.create_chat_invite_link(
            chat_id=chat_id,
            name=f"personal_invite_{user_id}_{int(datetime.now().timestamp())}",
            expire_date=datetime.now() + timedelta(hours=24),
            member_limit=1
        )

        # Сохраняем в базу
        success = invite_repo.save_invite_link(user_id, invite_link.invite_link)

        if success:
            logger.info(f"🔗 Сгенерирована персональная инвайт-ссылка для {user_id}: {invite_link.invite_link}")
            return (f"✅ Персональная инвайт-ссылка для пользователя {user_id}:\n\n"
                    f"🔗 {invite_link.invite_link}\n\n"
                    f"⏰ Действует: 24 часа\n"
                    f"👥 Использований: 1 раз\n"
                    f"📝 Тип: Персональная")
        else:
            return f"❌ Ошибка сохранения ссылки в базу данных для пользователя {user_id}"

    except Exception as e:
        logger.error(f"❌ Ошибка генерации персонального инвайта для {user_id}: {e}")
        return f"❌ Ошибка генерации персональной ссылки: {e}"

def get_active_invites_list():
    """Получить список активных инвайт-ссылок"""
    try:
        invites = invite_repo.get_active_invites()

        if not invites:
            return "📭 Нет активных инвайт-ссылок"

        result = "🔗 Активные инвайт-ссылки:\n\n"
        for invite in invites:
            user_id, link, created_at, used, is_general = invite
            hours_left = 24 - (datetime.now() - created_at).total_seconds() / 3600

            if is_general:
                user_info = "👤 Общая ссылка"
            else:
                user_info = f"👤 Для: {user_id}"

            status = "✅ Использован" if used else "⏳ Ожидает"

            result += f"{user_info}\n"
            result += f"🔗 {link[:30]}...\n"
            result += f"📊 {status} | ⏰ {hours_left:.1f}ч осталось\n\n"

        return result

    except Exception as e:
        return f"❌ Ошибка: {e}"

def get_used_invites_list():
    """Получить список использованных инвайтов"""
    try:
        invites = invite_repo.get_used_invites()

        if not invites:
            return "📭 Нет использованных инвайт-ссылок"

        result = "📋 Последние использованные инвайты:\n\n"
        for invite in invites:
            link, used_by, used_at, is_general = invite
            result += f"👤 Пользователь: {used_by}\n"
            result += f"🔗 {link[:25]}...\n"
            result += f"🕒 Использован: {used_at.strftime('%d.%m %H:%M')}\n\n"

        return result

    except Exception as e:
        return f"❌ Ошибка: {e}"

def force_add_user(user_id: int, chat_id: int, context: CallbackContext):
    """Принудительно добавить пользователя"""
    try:
        try:
            chat_member = context.bot.get_chat_member(chat_id, user_id)
            user = chat_member.user
        except:
            user = type('User', (), {'id': user_id, 'username': 'unknown', 'first_name': 'Unknown', 'last_name': ''})()

        user_data = {
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'channel_id': chat_id,
            'added_by_admin': True,
            'manually_added': True
        }

        if subscriber_repo.add_or_renew_subscriber(user_data, "chat_member"):
            return f"✅ Пользователь {user_id} принудительно добавлен!\n⏰ Отсчет 32 дней начат"
        else:
            return f"❌ Ошибка добавления пользователя {user_id}"

    except Exception as e:
        return f"❌ Ошибка: {e}"

def sync_current_members(update: Update, context: CallbackContext):
    """Синхронизировать всех текущих участников группы"""
    try:
        chat_id = update.effective_chat.id
        added_count = 0

        admins = context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot:
                user_data = {
                    'user_id': admin.user.id,
                    'username': admin.user.username,
                    'first_name': admin.user.first_name,
                    'last_name': admin.user.last_name,
                    'channel_id': chat_id,
                    'added_by_admin': True,
                    'manually_added': True
                }
                if subscriber_repo.add_or_renew_subscriber(user_data, "chat_member"):
                    added_count += 1

        try:
            for message in context.bot.get_chat_history(chat_id, limit=100):
                if message.from_user and not message.from_user.is_bot:
                    user_data = {
                        'user_id': message.from_user.id,
                        'username': message.from_user.username,
                        'first_name': message.from_user.first_name,
                        'last_name': message.from_user.last_name,
                        'channel_id': chat_id,
                        'added_by_admin': True,
                        'manually_added': True
                    }
                    if subscriber_repo.add_or_renew_subscriber(user_data, "chat_member"):
                        added_count += 1
        except Exception as e:
            logger.warning(f"Не удалось получить историю: {e}")

        return f"✅ Синхронизировано пользователей: {added_count}\n⏰ Отсчет времени начат для всех"

    except Exception as e:
        return f"❌ Ошибка синхронизации: {e}"

def get_user_info(user_id: int):
    """Получить информацию о пользователе"""
    try:
        user_info = subscriber_repo.get_user_info(user_id)

        if not user_info:
            return f"❌ Пользователь {user_id} не найден в базе"

        username, first_name, last_name, join_date, removed, removal_count = user_info

        status = "✅ Активен" if not removed else "❌ Удален"
        days_in_group = (datetime.now() - join_date).days if join_date else 0

        return (f"👤 Информация о пользователе:\n"
                f"🆔 ID: {user_id}\n"
                f"📛 Имя: {first_name} {last_name}\n"
                f"🔗 Username: @{username}\n"
                f"📊 Статус: {status}\n"
                f"🔢 Удалений: {removal_count}\n"
                f"📅 В группе: {days_in_group} дней\n"
                f"⏰ Осталось дней: {32 - days_in_group}")

    except Exception as e:
        return f"❌ Ошибка: {e}"

def get_active_users_list():
    """Получить список активных пользователей"""
    try:
        users = subscriber_repo.get_active_users()

        if not users:
            return "📊 Нет активных пользователей"

        result = "📊 Активные пользователи:\n\n"
        for user in users[:20]:
            user_id, username, first_name, last_name, join_date = user
            days_in_group = (datetime.now() - join_date).days
            result += f"🆔 {user_id} - {first_name} {last_name}\n"
            result += f"   📅 В группе: {days_in_group} дней\n"
            result += f"   ⏰ Осталось: {32 - days_in_group} дней\n\n"

        return result

    except Exception as e:
        return f"❌ Ошибка: {e}"

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

    # Получаем аргументы
    args = parts[1:] if len(parts) > 1 else []

    # ДЕТАЛЬНАЯ ОТЛАДКА КОМАНДЫ
    logger.info(f"🔍 Команда '{command}' от пользователя {user_id} (@{username})")
    logger.info(f"🔍 Аргументы команды: {args}")
    logger.info(f"🔍 Полный текст: '{message_text}'")
    logger.info(f"🔍 ADMIN_IDS: {Config.ADMIN_IDS}")
    logger.info(f"🔍 user_id in ADMIN_IDS: {user_id in Config.ADMIN_IDS}")

    # Проверяем права для команд
    if user_id not in Config.ADMIN_IDS:
        # Для команды /join разрешаем доступ всем
        if command != 'join':
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
        response = ""

        if command == 'start':
            count = subscriber_repo.get_subscriber_count()
            response = f"🤖 Бот активен\n📊 Подписчиков: {count}"

        elif command == 'stats':
            count = subscriber_repo.get_subscriber_count()
            response = f"📊 Статистика:\n• Подписчиков: {count}\n• ID канала: {Config.CHANNEL_ID or 'Не установлен'}"

        elif command == 'get_id':
            chat_id = update.effective_chat.id
            response = f"🆔 ID этой группы: `{chat_id}`"

        # 🎫 СКРЫТЫЕ КОМАНДЫ ИНВАЙТ-СИСТЕМЫ (только для админов)
        elif command == 'invite':
            if user_id in Config.ADMIN_IDS:
                response = generate_simple_invite(context, update.effective_chat.id, user_id)
            else:
                response = "⛔ Нет прав доступа"


        elif command == 'sync_telethon':
            if user_id in Config.ADMIN_IDS:
                context.bot.send_message(
                    chat_id=user_id,
                    text="🔄 Запуск принудительной синхронизации Telethon..."
                )
                result = telethon_tracker.force_sync_members_sync()
                context.bot.send_message(
                    chat_id=user_id,
                    text=result
                )
            else:
                response = "⛔ Нет прав доступа"
        elif command == 'telethon_stats':
            if user_id in Config.ADMIN_IDS:
                try:
                    # Получаем статистику через Telethon
                    member_count = telethon_tracker.get_member_count_sync()
                    db_count = subscriber_repo.get_subscriber_count()
                    response = (
                        f"📊 Статистика Telethon:\n"
                        f"👥 Участников в канале: {member_count}\n"
                        f"💾 В базе данных: {db_count}\n"
                        f"🔗 Telethon подключен: {telethon_tracker.is_connected()}\n"
                        f"📡 Мониторинг активен: {telethon_tracker.is_monitoring}\n"
                        f"📝 Разница: {member_count - db_count}"
                    )
                except Exception as e:
                    response = f"❌ Ошибка получения статистики: {e}"
            else:
                response = "⛔ Нет прав доступа"
        elif command == 'active_invites':
            if user_id in Config.ADMIN_IDS:
                response = get_active_invites_list()
            else:
                response = "⛔ Нет прав доступа"

        elif command == 'check_user':
            if user_id in Config.ADMIN_IDS:
                if args and len(args) > 0:
                    try:
                        user_id_to_check = int(args[0])
                        # Проверяем в базе
                        user_info = subscriber_repo.get_user_info(user_id_to_check)
                        if user_info:
                            response = f"✅ Пользователь {user_id_to_check} найден в базе"
                        else:
                            response = f"❌ Пользователь {user_id_to_check} НЕ найден в базе"

                        # Проверяем через Telegram API
                        try:
                            chat_member = context.bot.get_chat_member(update.effective_chat.id, user_id_to_check)
                            response += f"\n📱 В канале: ДА (статус: {chat_member.status})"
                        except:
                            response += f"\n📱 В канале: НЕТ"
                    except ValueError:
                        response = "❌ Неверный формат ID"
                else:
                    response = "❌ Укажите ID пользователя: /check_user 123456"
            else:
                response = "⛔ Нет прав доступа"

        elif command == 'db_status':
            if user_id in Config.ADMIN_IDS:
                try:
                    # Используем существующие репозитории вместо прямого доступа к БД
                    subs_count = subscriber_repo.get_subscriber_count()

                    # Получаем активных пользователей для отображения последних
                    active_users = subscriber_repo.get_active_users()

                    # Получаем активные инвайты
                    active_invites = invite_repo.get_active_invites()

                    response = f"📊 СТАТУС БАЗЫ ДАННЫХ:\n"
                    response += f"👥 Всего подписчиков: {subs_count}\n"
                    response += f"🔗 Активных инвайтов: {len(active_invites)}\n\n"

                    if active_users:
                        response += f"📋 Последние активные подписчики:\n"
                        for user in active_users[:5]:  # Показываем только 5 последних
                            user_id_sub, username, first_name, last_name, join_date = user
                            days_in_group = (datetime.now() - join_date).days
                            response += f"🆔 {user_id_sub} - {first_name} - {days_in_group}д\n"
                    else:
                        response += "📋 Нет активных подписчиков\n"

                    if active_invites:
                        response += f"\n🔗 Последние активные инвайты:\n"
                        for invite in active_invites[:3]:
                            user_id_inv, link, created_at, used, is_general = invite
                            hours_left = 24 - (datetime.now() - created_at).total_seconds() / 3600
                            type_str = "Общая" if is_general else "Персональная"
                            response += f"• {type_str} ({user_id_inv}) - {hours_left:.1f}ч\n"

                except Exception as e:
                    response = f"❌ Ошибка проверки БД: {e}"
                    logger.error(f"❌ Ошибка в db_status: {e}")
            else:
                response = "⛔ Нет прав доступа"

        elif command == 'force_add':
            if user_id in Config.ADMIN_IDS:
                if args and len(args) > 0:
                    try:
                        user_id_to_add = int(args[0])
                        response = force_add_user(user_id_to_add, update.effective_chat.id, context)
                    except ValueError:
                        response = "❌ Неверный формат ID пользователя. Используйте цифры: /force_add 123456"
                else:
                    response = "❌ Укажите ID пользователя: /force_add 123456"
            else:
                response = "⛔ Нет прав доступа"

        elif command == 'sync_current':
            if user_id in Config.ADMIN_IDS:
                response = sync_current_members(update, context)
            else:
                response = "⛔ Нет прав доступа"

        elif command == 'user_info':
            if user_id in Config.ADMIN_IDS:
                if args and len(args) > 0:
                    try:
                        user_id_info = int(args[0])
                        response = get_user_info(user_id_info)
                    except ValueError:
                        response = "❌ Неверный формат ID пользователя. Используйте цифры: /user_info 123456"
                else:
                    response = "❌ Укажите ID пользователя: /user_info 123456"
            else:
                response = "⛔ Нет прав доступа"

        elif command == 'active_users':
            if user_id in Config.ADMIN_IDS:
                response = get_active_users_list()
            else:
                response = "⛔ Нет прав доступа"

        elif command == 'used_invites':
            if user_id in Config.ADMIN_IDS:
                response = get_used_invites_list()
            else:
                response = "⛔ Нет прав доступа"

        # 🌐 ОТКРЫТАЯ КОМАНДА (для всех)
        elif command == 'join':
            response = (
                "🤔 Как присоединиться к платной группе?\n\n"
                "1. 💰 Оплатите доступ\n"
                "2. 📞 Сообщите админу об оплате\n"
                "3. 🔗 Получите персональную инвайт-ссылку\n"
                "4. 🎉 Перейдите по ссылке для вступления\n"
                "5. ⏰ Наслаждайтесь контентом 32 дня!\n\n"
                "📞 Контакты админа: @YourAdminUsername"
            )

        else:
            response = "❌ Неизвестная команда"

        logger.info(f"✅ Команда '{command}' выполнена, ответ: {response[:50]}...")

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

# def remove_old_subscribers(context: CallbackContext):
#     """Автоматическое удаление через 32 дня"""
#     try:
#         subscribers_to_remove = subscriber_repo.get_subscribers_to_remove()
#         logger.info(f"🔍 Найдено для удаления: {len(subscribers_to_remove)} подписчиков")
#
#         if not subscribers_to_remove:
#             return
#
#         for subscriber in subscribers_to_remove:
#             user_id, username, first_name, last_name = subscriber
#
#             if user_id in Config.ADMIN_IDS:
#                 logger.info(f"👑 Пропускаем админа: {user_id}")
#                 continue
#
#             try:
#                 logger.info(f"🔄 Пытаюсь удалить {user_id} из чата {Config.CHANNEL_ID}")
#
#                 context.bot.ban_chat_member(
#                     chat_id=Config.CHANNEL_ID,
#                     user_id=user_id
#                 )
#
#                 subscriber_repo.mark_as_removed(user_id)
#                 logger.info(f"✅ Удален подписчик: {user_id}")
#
#             except Exception as e:
#                 logger.error(f"❌ Ошибка удаления {user_id}: {e}")
#                 subscriber_repo.mark_as_removed(user_id)
#
#     except Exception as e:
#         logger.error(f"❌ Ошибка в задаче удаления: {e}")

def remove_old_subscribers(context: CallbackContext):
    """Автоматическое удаление через 32 дня с детальным логированием разблокировки"""
    try:
        subscribers_to_remove = subscriber_repo.get_subscribers_to_remove()
        logger.info(f"🔍 Найдено для удаления: {len(subscribers_to_remove)} подписчиков")

        if not subscribers_to_remove:
            return

        for subscriber in subscribers_to_remove:
            user_id, username, first_name, last_name = subscriber

            if user_id in Config.ADMIN_IDS:
                logger.info(f"👑 Пропускаем админа: {user_id}")
                continue

            try:
                logger.info(f"🔄 Начинаем процесс удаления пользователя {user_id}")

                # 1. БАН на 1 секунду (удаление из канала)
                logger.info(f"⏳ Выполняем бан пользователя {user_id} на 1 секунду...")
                from datetime import datetime, timedelta
                context.bot.ban_chat_member(
                    chat_id=Config.CHANNEL_ID,
                    user_id=user_id,
                    until_date=datetime.now() + timedelta(seconds=1)
                )
                logger.info(f"✅ Пользователь {user_id} забанен (удален из канала)")

                # 2. МГНОВЕННАЯ РАЗБЛОКИРОВКА (убираем из ЧС)
                logger.info(f"⏳ Выполняем РАЗБЛОКИРОВКУ пользователя {user_id}...")
                try:
                    context.bot.unban_chat_member(
                        chat_id=Config.CHANNEL_ID,
                        user_id=user_id,
                        only_if_banned=True
                    )
                    logger.info(f"🎉 УСПЕХ: Пользователь {user_id} РАЗБЛОКИРОВАН и убран из черного списка!")
                except Exception as unban_error:
                    logger.error(f"❌ ОШИБКА РАЗБЛОКИРОВКИ {user_id}: {unban_error}")
                    # Продолжаем выполнение даже при ошибке разблокировки

                # 3. Отмечаем в БД
                subscriber_repo.mark_as_removed(user_id)
                logger.info(f"📊 Пользователь {user_id} помечен как удаленный в БД")

                logger.info(f"🎯 ЗАВЕРШЕНО: Пользователь {user_id} полностью обработан")

            except Exception as e:
                logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА для {user_id}: {e}")
                # Все равно помечаем как удаленного, даже если была ошибка
                try:
                    subscriber_repo.mark_as_removed(user_id)
                    logger.info(f"📊 Пользователь {user_id} помечен как удаленный несмотря на ошибку")
                except Exception as db_error:
                    logger.error(f"🗄️ Ошибка БД для {user_id}: {db_error}")

    except Exception as e:
        logger.error(f"💥 ОБЩАЯ ОШИБКА в задаче удаления: {e}")


def debug_invites(update: Update, context: CallbackContext):
    """Функция для отладки инвайт-системы"""
    user_id = update.effective_user.id
    if user_id not in Config.ADMIN_IDS:
        return "⛔ Нет прав доступа"

    try:
        # Проверяем активные инвайты
        active_invites = invite_repo.get_active_invites()

        result = f"🔧 ДЕБАГ ИНВАЙТ-СИСТЕМЫ:\n"
        result += f"📊 Активных инвайтов: {len(active_invites)}\n\n"

        for i, invite in enumerate(active_invites[:5], 1):
            user_id_inv, link, created_at, used, is_general = invite
            result += f"{i}. User: {user_id_inv} | General: {is_general}\n"
            result += f"   Link: {link[:30]}...\n"
            result += f"   Used: {used} | Created: {created_at.strftime('%H:%M')}\n\n"

        return result

    except Exception as e:
        return f"❌ Ошибка отладки: {e}"

def debug_invite_flow(update: Update, context: CallbackContext):
    """Test function to debug invite flow"""
    test_link = "your_test_invite_link_here"

    # Test saving
    invite_repo.save_general_invite(test_link, update.effective_user.id)

    # Test retrieval
    active_invites = invite_repo.get_active_invites()
    logger.info(f"Active invites in DB: {len(active_invites)}")

    # Test marking as used
    invite_repo.mark_invite_used(test_link, update.effective_user.id)

    update.message.reply_text(f"Debug completed. Check logs for details.")

def debug_invites_detailed(update: Update, context: CallbackContext):
    """Get detailed debug information about invites"""
    user_id = update.effective_user.id
    if user_id not in Config.ADMIN_IDS:
        return

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Check general invites
        cursor.execute('''
            SELECT COUNT(*) as total, 
                   SUM(CASE WHEN used = TRUE THEN 1 ELSE 0 END) as used_count
            FROM invite_links 
            WHERE is_general = TRUE
        ''')
        general_stats = cursor.fetchone()

        # Check personal invites
        cursor.execute('''
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN used = TRUE THEN 1 ELSE 0 END) as used_count
            FROM invite_links 
            WHERE is_general = FALSE
        ''')
        personal_stats = cursor.fetchone()

        # Get recent used invites
        cursor.execute('''
            SELECT invite_link, used_by, used_at, is_general
            FROM invite_links 
            WHERE used = TRUE 
            ORDER BY used_at DESC 
            LIMIT 5
        ''')
        recent_used = cursor.fetchall()

        conn.close()

        response = (
            f"📊 ДЕТАЛЬНАЯ СТАТИСТИКА ИНВАЙТОВ:\n\n"
            f"👥 ОБЩИЕ инвайты:\n"
            f"   • Всего: {general_stats[0]}\n"
            f"   • Использовано: {general_stats[1]}\n\n"
            f"👤 ПЕРСОНАЛЬНЫЕ инвайты:\n"
            f"   • Всего: {personal_stats[0]}\n"
            f"   • Использовано: {personal_stats[1]}\n\n"
            f"🕒 Последние использованные:\n"
        )

        for invite in recent_used:
            link, used_by, used_at, is_general = invite
            response += f"   • {link[:15]}... - user:{used_by} - general:{is_general}\n"

        context.bot.send_message(chat_id=user_id, text=response)

    except Exception as e:
        logger.error(f"❌ Ошибка детальной отладки: {e}")


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
    application.add_handler(ChatMemberHandler(track_chat_member))  # Для админских действий
    application.add_handler(MessageHandler(Filters.all, handle_all_messages))
    application.add_handler(ChatJoinRequestHandler(handle_chat_join_request))

    # ⏰ Планировщик заданий
    job_queue = updater.job_queue
    if job_queue:
        job_queue.run_repeating(remove_old_subscribers, interval=300, first=10)

        # 🔄 ПЕРИОДИЧЕСКАЯ СИНХРОНИЗАЦИЯ TELETHON (каждые 2 часа)
        job_queue.run_repeating(sync_telethon_periodically, interval=7200, first=30)

        logger.info("✅ JobQueue запущен с Telethon синхронизацией")

    return updater


# def sync_telethon_periodically(context: CallbackContext):
#     """Периодическая синхронизация через Telethon"""
#     try:
#         logger.info("🔄 Запуск периодической синхронизации Telethon...")
#         result = telethon_tracker.force_sync_members_sync()
#         logger.info(f"📊 Результат синхронизации: {result}")
#     except Exception as e:
#         logger.error(f"❌ Ошибка периодической синхронизации: {e}")


def sync_telethon_periodically(context: CallbackContext):
    """Периодическая синхронизация через Telethon"""
    try:
        logger.info("🔄 Запуск периодической синхронизации Telethon...")

        # Используем простую версию синхронизации
        result = telethon_tracker.force_sync_members_sync_simple()
        logger.info(f"📊 Результат синхронизации: {result}")

    except Exception as e:
        logger.error(f"❌ Ошибка периодической синхронизации: {e}")


# todo дубликат, уже есть в postgres_storage.py
# def get_connection():
#     """Получить соединение с базой данных с обработкой ошибок."""
#     try:
#         conn = psycopg2.connect(Config.DATABASE_URL)
#         conn.autocommit = False
#         return conn
#     except Exception as e:
#         logger.error(f"❌ Ошибка подключения к БД: {e}")
#         raise

# def main():
#     """Упрощенный запуск бота для Windows."""
#     try:
#         # Простой запуск для Windows
#         updater = setup_application()
#         logger.info("🔄 Бот запускается...")
#         updater.start_polling()
#         updater.idle()
#     except KeyboardInterrupt:
#         print("Бот остановлен пользователем")
#     except Exception as e:
#         logger.error(f"Критическая ошибка: {e}")
#         raise

