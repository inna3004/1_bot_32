import logging
from datetime import datetime, timedelta
from storage.postgres_storage import get_connection
from config import Config
logger = logging.getLogger(__name__)


class SubscriberRepository:
    def __init__(self):
        pass

    def add_or_renew_subscriber(self, user_data, renewal_type="new"):
        """
        Универсальный метод для добавления или обновления подписчика
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Сначала проверяем существующую запись
            cursor.execute('SELECT id, removed FROM subscribers WHERE user_id = %s', (user_data['user_id'],))
            existing = cursor.fetchone()

            if existing:
                # 🔄 СУЩЕСТВУЮЩИЙ ПОЛЬЗОВАТЕЛЬ - ОБНОВЛЯЕМ
                cursor.execute('''
                    UPDATE subscribers 
                    SET username = %s, first_name = %s, last_name = %s,
                        removed = FALSE, removal_date = NULL,
                        join_date = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                ''', (
                    user_data.get('username'),
                    user_data.get('first_name'),
                    user_data.get('last_name'),
                    user_data['user_id']
                ))
                action = "обновлен"
            else:
                # ✨ НОВЫЙ ПОЛЬЗОВАТЕЛЬ - СОЗДАЕМ
                cursor.execute('''
                    INSERT INTO subscribers (
                        user_id, username, first_name, last_name, channel_id, 
                        added_by_admin, manually_added
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    user_data['user_id'],
                    user_data.get('username'),
                    user_data.get('first_name'),
                    user_data.get('last_name'),
                    user_data.get('channel_id'),
                    user_data.get('added_by_admin', False),
                    user_data.get('manually_added', False)
                ))
                action = "добавлен"

            conn.commit()
            conn.close()
            logger.info(f"✅ Пользователь {user_data['user_id']} {action} (тип: {renewal_type})")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка добавления/обновления пользователя {user_data['user_id']}: {e}")
            return False

    def add_subscriber_from_telethon(self, user_data):
        """
        Специальный метод для добавления подписчиков из Telethon
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Проверяем существующую запись
            cursor.execute('SELECT id, removed, join_date FROM subscribers WHERE user_id = %s', (user_data['user_id'],))
            existing = cursor.fetchone()

            if existing:
                id, removed, old_join_date = existing

                if removed:
                    # 🔄 ПОЛЬЗОВАТЕЛЬ БЫЛ УДАЛЕН - обновляем join_date (новое вступление)
                    logger.info(f"🔍 ОТЛАДКА: Пользователь был удален, старая join_date: {old_join_date}")

                    cursor.execute('''
                        UPDATE subscribers 
                        SET username = %s, first_name = %s, last_name = %s,
                            removed = FALSE, 
                            removal_date = NULL,
                            join_date = CURRENT_TIMESTAMP,  -- ⚠️ ОБНОВЛЯЕМ ДАТУ ТОЛЬКО ЕСЛИ БЫЛ УДАЛЕН
                            last_join_date = CURRENT_TIMESTAMP
                        WHERE user_id = %s
                        RETURNING join_date
                    ''', (
                        user_data.get('username'),
                        user_data.get('first_name'),
                        user_data.get('last_name'),
                        user_data['user_id']
                    ))

                    new_join_date = cursor.fetchone()[0]
                    logger.info(f"🔍 ОТЛАДКА: Новая join_date после удаления: {new_join_date}")
                    action = "обновлен (снята пометка удаления, обновлена дата)"
                else:
                    # 🔄 ПОЛЬЗОВАТЕЛЬ АКТИВЕН - НЕ обновляем join_date (просто синхронизация)
                    logger.info(f"🔍 ОТЛАДКА: Пользователь активен, сохраняем join_date: {old_join_date}")

                    cursor.execute('''
                        UPDATE subscribers 
                        SET username = %s, first_name = %s, last_name = %s,
                            last_join_date = CURRENT_TIMESTAMP
                        WHERE user_id = %s
                    ''', (
                        user_data.get('username'),
                        user_data.get('first_name'),
                        user_data.get('last_name'),
                        user_data['user_id']
                    ))
                    action = "обновлен (только информация)"

            else:
                # ✨ НОВЫЙ ПОЛЬЗОВАТЕЛЬ - СОЗДАЕМ
                cursor.execute('''
                    INSERT INTO subscribers (
                        user_id, username, first_name, last_name, channel_id,
                        added_by_admin, manually_added, detection_source
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    user_data['user_id'],
                    user_data.get('username'),
                    user_data.get('first_name'),
                    user_data.get('last_name'),
                    user_data.get('channel_id'),
                    user_data.get('added_by_admin', False),
                    user_data.get('manually_added', False),
                    user_data.get('detection_source', 'telethon')
                ))
                action = "добавлен"

            conn.commit()
            conn.close()
            logger.info(f"✅ Пользователь {user_data['user_id']} {action} через Telethon")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка добавления через Telethon: {e}")
            return False


    def add_subscriber(self, user_data):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO subscribers (user_id, username, first_name, last_name, channel_id, added_by_admin, manually_added)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                removed = FALSE,
                removal_date = NULL,
                added_by_admin = EXCLUDED.added_by_admin,
                manually_added = EXCLUDED.manually_added,
                removal_count = 0,
                join_date = CURRENT_TIMESTAMP
            ''', (
                user_data['user_id'],
                user_data.get('username'),
                user_data.get('first_name'),
                user_data.get('last_name'),
                user_data.get('channel_id'),
                user_data.get('added_by_admin', True),
                user_data.get('manually_added', True)
            ))
            conn.commit()
            conn.close()
            logger.info(f"Добавлен подписчик: {user_data['user_id']}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления: {e}")
            return False

    def mark_as_removed(self, user_id):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE subscribers 
                SET removed = TRUE, removal_date = CURRENT_TIMESTAMP,
                removal_count = removal_count + 1 
                WHERE user_id = %s
            ''', (user_id,))
            conn.commit()
            conn.close()
            logger.info(f"Отмечен как удаленный: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отметки: {e}")
            return False

    def get_subscriber_count(self):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM subscribers WHERE removed = FALSE')
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Ошибка подсчета: {e}")
            return 0

    def get_subscribers_to_remove(self):
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # 🔧 ДЛЯ ТЕСТИРОВАНИЯ - удаление через 1 минуту вместо 32 дней
            minutes_to_remove = 43200  # ← Тестовое значение - :1 минута 46080
            removal_date = datetime.now() - timedelta(minutes=minutes_to_remove)

            # ДОБАВЬТЕ ЭТОТ ЗАПРОС ДЛЯ ОТЛАДКИ
            cursor.execute('''
                SELECT user_id, username, join_date, removed 
                FROM subscribers 
                WHERE user_id = 5451598505
            ''')

            debug_info = cursor.fetchone()
            if debug_info:
                user_id, username, join_date, removed = debug_info
                logger.info(f"🔍 ОТЛАДКА: Пользователь {user_id} - join_date: {join_date}, removed: {removed}")

            cursor.execute('''
                SELECT user_id, username, first_name, last_name 
                FROM subscribers 
                WHERE join_date < %s 
                AND removed = FALSE 
                AND user_id NOT IN %s
            ''', (removal_date, tuple(Config.ADMIN_IDS)))

            result = cursor.fetchall()
            conn.close()

            logger.info(f"⏰ Поиск подписчиков старше {minutes_to_remove} минут")
            return result
        except Exception as e:
            logger.error(f"Ошибка получения: {e}")
            return []

    def get_user_info(self, user_id):
        """Получить информацию о пользователе"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT username, first_name, last_name, join_date, removed, removal_count 
                FROM subscribers WHERE user_id = %s
            ''', (user_id,))

            result = cursor.fetchone()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка получения информации о пользователе: {e}")
            return None

    def get_active_users(self):
        """Получить список активных пользователей"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, first_name, last_name, join_date 
                FROM subscribers 
                WHERE removed = FALSE 
                ORDER BY join_date DESC
            ''')

            result = cursor.fetchall()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"Ошибка получения активных пользователей: {e}")
            return []


class InviteRepository:
    def __init__(self):
        pass

    def save_invite_link(self, user_id: int, invite_link: str):
        """Сохранить инвайт-ссылку в базу"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO invite_links (user_id, invite_link)
                VALUES (%s, %s)
            ''', (user_id, invite_link))
            conn.commit()
            conn.close()
            logger.info(f"✅ Сохранена инвайт-ссылка для пользователя {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения инвайта: {e}")
            return False

    def save_general_invite(self, invite_link: str, admin_id: int):
        """Сохранить общую инвайт-ссылку в базу"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO invite_links (user_id, invite_link, is_general, created_by)
                VALUES (%s, %s, %s, %s)
            ''', (0, invite_link, True, admin_id))
            conn.commit()
            conn.close()
            logger.info(f"✅ Сохранена общая инвайт-ссылка админом {admin_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения общей инвайт-ссылки: {e}")
            return False

    def get_active_invites(self):
        """Получить активные инвайт-ссылки"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, invite_link, created_at, used, is_general
                FROM invite_links 
                WHERE expired = FALSE 
                ORDER BY created_at DESC
            ''')
            result = cursor.fetchall()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения инвайтов: {e}")
            return []

    def get_used_invites(self):
        """Получить список использованных инвайтов"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT invite_link, used_by, used_at, is_general
                FROM invite_links 
                WHERE used = TRUE 
                ORDER BY used_at DESC
                LIMIT 10
            ''')

            result = cursor.fetchall()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения использованных инвайтов: {e}")
            return []

    def mark_invite_used(self, invite_link: str, used_by: int):
        """Пометить инвайт как использованный"""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Ищем инвайт по полному совпадению или частичному
            cursor.execute('''
                UPDATE invite_links 
                SET used = TRUE, used_by = %s, used_at = CURRENT_TIMESTAMP,
                    expired = TRUE
                WHERE invite_link = %s
            ''', (used_by, invite_link))

            conn.commit()
            conn.close()
            logger.info(f"✅ Инвайт-ссылка использована пользователем {used_by}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка обновления инвайта: {e}")
            return False