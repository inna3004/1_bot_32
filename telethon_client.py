import logging
import asyncio
from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from config import Config
from storage.repository import SubscriberRepository

logger = logging.getLogger(__name__)


class TelethonTracker:
    def __init__(self):
        self.client = None
        self.is_connected = False
        self.subscriber_repo = SubscriberRepository()

    def start_sync(self):
        """Синхронный запуск Telethon клиента с улучшенными настройками"""
        try:
            self.client = TelegramClient(
                MemorySession(),
                api_id=Config.TELEGRAM_API_ID,
                api_hash=Config.TELEGRAM_API_HASH,
                receive_updates=True,
                sequential_updates=False,
                connection_retries=10,
                retry_delay=3,
                auto_reconnect=True,
                flood_sleep_threshold=60,
                device_model='Bot Server',
                system_version='1.0',
                app_version='1.0'
            )

            # Запускаем в отдельном потоке
            import threading
            thread = threading.Thread(target=self._run_async)
            thread.daemon = True
            thread.start()

            return True
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации Telethon: {e}")
            return False

    def _run_async(self):
        """Запуск асинхронного цикла в отдельном потоке"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._start())

    async def _start(self):
        """Асинхронный запуск клиента КАК БОТ"""
        try:
            # ЯВНО указываем что это бот с помощью bot_token
            await self.client.start(bot_token=Config.TELEGRAM_TOKEN)
            self.is_connected = True
            logger.info("✅ Telethon клиент подключен как БОТ")

            # Запускаем синхронизацию пользователей
            await self.force_sync_members()

        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telethon: {e}")

    async def force_sync_members(self, safe_mode=False):
        """Принудительная синхронизация всех участников с выбором стратегии"""
        if safe_mode:
            return await self.force_sync_members_safe()
        else:
            # Используем быстрый метод (оригинальный)
            try:
                logger.info("🔁 Запуск БЫСТРОЙ синхронизации участников...")
                added_count = 0
                channel_identifiers = Config.CHANNEL_ID

                for channel_id in channel_identifiers:
                    try:
                        entity = await self.client.get_entity(channel_id)
                        logger.info(f"✅ Канал найден с ID: {channel_id}")
                    except Exception as e:
                        logger.debug(f"❌ Не удалось найти с ID {channel_id}: {e}")
                        continue

                    participants = await self.client.get_participants(entity)
                    for user in participants:
                        if user.bot:
                            continue

                        user_data = {
                            'user_id': user.id,
                            'username': user.username,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'channel_id': channel_id,
                            'added_by_admin': False,
                            'manually_added': False,
                            'detection_source': 'telethon_fast_sync',
                        }

                        if self.subscriber_repo.add_subscriber_from_telethon(user_data):
                            added_count += 1

                logger.info(f"✅ Быстрая синхронизация завершена. Обработано: {added_count} пользователей")
                return f"✅ Быстрая синхронизация завершена. Обработано: {added_count} пользователей"

            except Exception as e:
                # Если быстрый метод упал, пробуем безопасный
                logger.warning(f"⚠️ Быстрая синхронизация упала, пробуем безопасную: {e}")
                return await self.force_sync_members_safe()

    async def get_all_participants_safe(self, entity):
        """Безопасное получение всех участников с паузами (из второго файла)"""
        try:
            all_participants = []
            offset = 0
            limit = 100

            while True:
                participants = await self.client(GetParticipantsRequest(
                    channel=entity,
                    filter=ChannelParticipantsSearch(''),
                    offset=offset,
                    limit=limit,
                    hash=0
                ))

                if not participants.users:
                    break

                all_participants.extend(participants.users)
                offset += len(participants.users)
                logger.info(f"📊 Получено участников: {len(participants.users)}")

                # Пауза чтобы избежать лимитов
                await asyncio.sleep(1)

            logger.info(f"✅ Всего получено участников: {len(all_participants)}")
            return all_participants

        except Exception as e:
            logger.error(f"❌ Ошибка получения участников: {e}")
            return []

    async def force_sync_members_safe(self):
        """Безопасная синхронизация с защитой от лимитов"""
        try:
            logger.info("🔁 Запуск БЕЗОПАСНОЙ синхронизации участников...")
            added_count = 0
            channel_identifiers = Config.CHANNEL_ID

            for channel_id in channel_identifiers:
                try:
                    entity = await self.client.get_entity(channel_id)
                    logger.info(f"✅ Канал найден с ID: {channel_id}")
                except Exception as e:
                    logger.debug(f"❌ Не удалось найти с ID {channel_id}: {e}")
                    continue

                # Используем безопасный метод для больших каналов
                participants = await self.get_all_participants_safe(entity)

                for user in participants:
                    if user.bot:
                        continue

                    user_data = {
                        'user_id': user.id,
                        'username': user.username,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'channel_id': channel_id,
                        'added_by_admin': False,
                        'manually_added': False,
                        'detection_source': 'telethon_safe_sync'
                    }

                    if self.subscriber_repo.add_subscriber_from_telethon(user_data):
                        added_count += 1

            logger.info(f"✅ Безопасная синхронизация завершена. Обработано: {added_count} пользователей")
            return f"✅ Безопасная синхронизация завершена. Обработано: {added_count} пользователей"

        except Exception as e:
            logger.error(f"❌ Ошибка безопасной синхронизации: {e}")

    def force_sync_members_sync_simple(self):
        """Простая версия для периодической синхронизации (без конфликта event loops)"""
        try:
            async def sync_task():
                temp_client = TelegramClient(
                    MemorySession(),
                    Config.TELEGRAM_API_ID,
                    Config.TELEGRAM_API_HASH,
                    connection_retries=5,
                    retry_delay=2,
                    flood_sleep_threshold=60
                )

                try:
                    await temp_client.start(bot_token=Config.TELEGRAM_TOKEN)
                    added_count = 0
                    channel_identifiers = Config.CHANNEL_ID

                    for channel_id in channel_identifiers:
                        try:
                            entity = await self.client.get_entity(channel_id)
                            logger.info(f"✅ Канал найден с ID: {channel_id}")
                        except Exception as e:
                            logger.debug(f"❌ Не удалось найти с ID {channel_id}: {e}")
                            continue

                        participants = await temp_client.get_participants(entity)

                        for user in participants:
                            if user.bot:
                                continue

                            user_data = {
                                'user_id': user.id,
                                'username': user.username,
                                'first_name': user.first_name,
                                'last_name': user.last_name,
                                'channel_id': channel_id,
                                'added_by_admin': False,
                                'manually_added': False,
                                'detection_source': 'telethon_periodic_sync'
                            }
                            if self.subscriber_repo.add_subscriber_from_telethon(user_data):
                                added_count += 1

                    return f"✅ Периодическая синхронизация: {added_count} пользователей"
                finally:
                    await temp_client.disconnect()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(sync_task())
            loop.close()
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка периодической синхронизации: {e}")

    def get_member_count_sync(self, channel_id):
        """Синхронное получение количества участников"""
        try:
            async def sync_task(channel_id):
                temp_client = TelegramClient(
                    MemorySession(),
                    Config.TELEGRAM_API_ID,
                    Config.TELEGRAM_API_HASH,
                    connection_retries=5,
                    retry_delay=2,
                    flood_sleep_threshold=60
                )

                try:
                    await temp_client.start(bot_token=Config.TELEGRAM_TOKEN)
                    try:
                        entity = await self.client.get_entity(channel_id)
                        logger.info(f"✅ Канал найден с ID: {channel_id}")
                    except Exception as e:
                        logger.debug(f"❌ Не удалось найти с ID {channel_id}: {e}")
                        return False

                    participants = await self.client.get_participants(entity)
                    return len([p for p in participants if not p.bot])
                finally:
                    await temp_client.disconnect()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(sync_task(channel_id))
            loop.close()
            return result

        except Exception as e:
            logger.error(f"❌ Ошибка периодической синхронизации: {e}")
            return False


# Глобальный экземпляр
telethon_tracker = TelethonTracker()
