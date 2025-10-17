import logging
import psycopg2
from config import Config

logger = logging.getLogger(__name__)


def init_db():
    """Инициализация базы данных"""
    conn = None
    try:
        conn = psycopg2.connect(Config.DATABASE_URL)
        cursor = conn.cursor()

        # Основная таблица подписчиков
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscribers (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username VARCHAR(255),
                first_name VARCHAR(255),
                last_name VARCHAR(255),
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                removed BOOLEAN DEFAULT FALSE,
                removal_date TIMESTAMP,
                channel_id BIGINT,
                detection_source VARCHAR(50),
                last_join_date TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                added_by_admin BOOLEAN DEFAULT FALSE,
                manually_added BOOLEAN DEFAULT FALSE,
                removal_count INTEGER DEFAULT 0
            )
        ''')

        # Добавляем недостающие столбцы, если их нет
        additional_columns = [
            ('subscribers', 'detection_source', 'VARCHAR(50)'),
            ('subscribers', 'last_join_date', 'TIMESTAMP'),
            ('subscribers', 'is_active', 'BOOLEAN DEFAULT TRUE'),
        ]

        for table, column, column_type in additional_columns:
            try:
                cursor.execute(f'''
                    ALTER TABLE {table} 
                    ADD COLUMN IF NOT EXISTS {column} {column_type}
                ''')
                logger.info(f"✅ Добавлен столбец {table}.{column}")
            except Exception as e:
                logger.info(f"Столбец {table}.{column} уже существует: {e}")

        # Создаем индексы
        indexes = [
            'CREATE INDEX IF NOT EXISTS idx_user_id ON subscribers(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_join_date ON subscribers(join_date)',
            'CREATE INDEX IF NOT EXISTS idx_removed ON subscribers(removed)',
            'CREATE INDEX IF NOT EXISTS idx_subscribers_channel ON subscribers(channel_id)'
        ]

        for index_sql in indexes:
            try:
                cursor.execute(index_sql)
            except Exception as e:
                logger.error(f"Ошибка создания индекса: {e}")

        conn.commit()
        logger.info("✅ База данных полностью инициализирована")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise
    finally:
        if conn:
            conn.close()


def get_connection():
    """Получить соединение с базой данных"""
    return psycopg2.connect(Config.DATABASE_URL)


# Дополнительные полезные функции
def backup_database():
    """Создание бэкапа базы данных"""
    try:
        import subprocess
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup_{timestamp}.sql"

        # Используем pg_dump для создания бэкапа
        subprocess.run([
            "pg_dump",
            Config.DATABASE_URL,
            "-f", backup_file
        ], check=True)

        logger.info(f"✅ Бэкап создан: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"❌ Ошибка создания бэкапа: {e}")
        return None


def restore_database(backup_file):
    """Восстановление базы данных из бэкапа"""
    try:
        import subprocess

        subprocess.run([
            "psql",
            Config.DATABASE_URL,
            "-f", backup_file
        ], check=True)

        logger.info(f"✅ База данных восстановлена из {backup_file}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка восстановления БД: {e}")
        return False
