import logging
from datetime import datetime, timedelta
from storage.postgres_storage import get_connection
from config import Config

logger = logging.getLogger(__name__)


class SubscriberRepository:

    def __init__(self):
        pass

    def add_subscriber_from_telethon(self, user_data):
        """
        Специальный метод для добавления подписчиков из Telethon
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Проверяем существующую запись
            cursor.execute(
                'SELECT id, removed, join_date FROM subscribers WHERE user_id = %s AND channel_id = %s',
                (user_data['user_id'], user_data['channel_id'],)
            )
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
            logger.info(
                f"✅ Пользователь {user_data['user_id']}, канал {user_data['channel_id']} {action} через Telethon")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка добавления через Telethon: {e}")
            return False

    def mark_as_removed(self, user_id, channel_id):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE subscribers 
                SET removed = TRUE, removal_date = CURRENT_TIMESTAMP,
                removal_count = removal_count + 1 
                WHERE user_id = %s AND channel_id = %s
            ''', (user_id, channel_id,))
            conn.commit()
            conn.close()
            logger.info(f"Отмечен как удаленный: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка отметки: {e}")
            return False

    def get_subscriber_count(self, channel_id):
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM subscribers WHERE removed = FALSE and channel_id = %s', (channel_id,))
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

            minutes_to_remove = 43200  # ← Тестовое значение - :1 минута 46080
            removal_date = datetime.now() - timedelta(minutes=minutes_to_remove)

            cursor.execute('''
                SELECT user_id, username, first_name, last_name, channel_id 
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
