import logging
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import MemorySession
from telethon.tl.types import Channel, Chat
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from config import Config
from storage.repository import SubscriberRepository

logger = logging.getLogger(__name__)


class TelethonTracker:
    def __init__(self):
        self.client = None
        self.is_connected = False
        self.is_monitoring = False
        self.subscriber_repo = SubscriberRepository()

    def start_sync(self):
        """Синхронный запуск Telethon клиента с улучшенными настройками"""
        try:
            # Используем улучшенные настройки подключения из второго файла
            self.client = TelegramClient(
                MemorySession(),
                Config.TELEGRAM_API_ID,
                Config.TELEGRAM_API_HASH,
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

            # Получаем информацию о канале
            await self._validate_channel()

            # Запускаем мониторинг
            await self._setup_handlers()
            await self.force_sync_members()

        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telethon: {e}")

    async def _validate_channel(self):
        """Проверяем доступ к каналу"""
        try:
            # Пробуем разные форматы ID
            channel_identifiers = [
                int(Config.CHANNEL_ID),  # как число: -1002908805172
                int(str(Config.CHANNEL_ID).replace('-100', '')),  # без префикса: 2908805172
            ]

            entity = None
            for identifier in channel_identifiers:
                try:
                    entity = await self.client.get_entity(identifier)
                    logger.info(f"✅ Канал найден с ID: {identifier}")
                    break
                except Exception as e:
                    logger.debug(f"❌ Не удалось найти с ID {identifier}: {e}")
                    continue

            if entity:
                logger.info(f"✅ Канал: {getattr(entity, 'title', 'Unknown')} (ID: {entity.id})")
                return True
            else:
                logger.error(f"❌ Не удалось найти канал {Config.CHANNEL_ID}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка валидации канала: {e}")
            return False

    async def force_sync_members(self, safe_mode=False):
        """Принудительная синхронизация всех участников с выбором стратегии"""
        if safe_mode:
            return await self.force_sync_members_safe()
        else:
            # Используем быстрый метод (оригинальный)
            try:
                logger.info("🔁 Запуск БЫСТРОЙ синхронизации участников...")

                channel_id = int(Config.CHANNEL_ID)
                entity = await self.client.get_entity(channel_id)
                participants = await self.client.get_participants(entity)

                added_count = 0
                for user in participants:
                    if user.bot:
                        continue

                    user_data = {
                        'user_id': user.id,
                        'username': user.username,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'channel_id': Config.CHANNEL_ID,
                        'added_by_admin': False,
                        'manually_added': False,
                        'detection_source': 'telethon_fast_sync'
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

            # Получаем канал
            channel_id = int(Config.CHANNEL_ID)
            entity = await self.client.get_entity(channel_id)

            # Используем безопасный метод для больших каналов
            participants = await self.get_all_participants_safe(entity)

            added_count = 0
            for user in participants:
                if user.bot:
                    continue

                user_data = {
                    'user_id': user.id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'channel_id': Config.CHANNEL_ID,
                    'added_by_admin': False,
                    'manually_added': False,
                    'detection_source': 'telethon_safe_sync'
                }

                if self.subscriber_repo.add_subscriber_from_telethon(user_data):
                    added_count += 1

            logger.info(f"✅ Безопасная синхронизация завершена. Обработано: {added_count} пользователей")
            return f"✅ Безопасная синхронизация завершена. Обработано: {added_count} пользователей"

        except Exception as e:
            error_msg = f"❌ Ошибка безопасной синхронизации: {e}"
            logger.error(error_msg)
            return error_msg

    def force_sync_members_sync_simple(self):
        """Простая версия для периодической синхронизации (без конфликта event loops)"""
        try:
            import asyncio
            from telethon import TelegramClient
            from telethon.sessions import MemorySession

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

                    channel_id = int(Config.CHANNEL_ID)
                    entity = await temp_client.get_entity(channel_id)
                    participants = await temp_client.get_participants(entity)

                    added_count = 0
                    for user in participants:
                        if user.bot:
                            continue
                        user_data = {
                            'user_id': user.id,
                            'username': user.username,
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'channel_id': Config.CHANNEL_ID,
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
            return f"❌ Ошибка периодической синхронизации: {e}"

    def force_sync_members_sync(self):
        """Основная синхронная версия для обратной совместимости"""
        return self.force_sync_members_sync_simple()

    async def _setup_handlers(self):
        """Настройка обработчиков событий"""

        @self.client.on(events.ChatAction)
        async def handler(event):
            """Обработчик вступлений и выходов"""
            try:
                channel_id = int(Config.CHANNEL_ID)
                if event.chat_id != channel_id:
                    return

                # Новый участник
                if event.user_joined:
                    user = await event.get_user()
                    await self._handle_new_member(user)

                # Участник вышел
                elif event.user_left:
                    user = await event.get_user()
                    await self._handle_left_member(user)

            except Exception as e:
                logger.error(f"❌ Ошибка обработки события: {e}")

        self.is_monitoring = True
        logger.info("✅ Обработчики Telethon настроены")

    async def _handle_new_member(self, user):
        """Обработка нового участника"""
        try:
            if user.bot:
                return

            user_data = {
                'user_id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'channel_id': Config.CHANNEL_ID,
                'added_by_admin': False,
                'manually_added': False,
                'detection_source': 'telethon'
            }

            if self.subscriber_repo.add_subscriber_from_telethon(user_data):
                logger.info(f"✅ Telethon: добавлен пользователь {user.id}")
            else:
                logger.error(f"❌ Telethon: не удалось добавить пользователя {user.id}")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки нового участника {user.id}: {e}")

    async def _handle_left_member(self, user):
        """Обработка вышедшего участника"""
        try:
            if user.bot:
                return

            if self.subscriber_repo.mark_as_removed(user.id):
                logger.info(f"✅ Telethon: пользователь {user.id} помечен как удаленный")
            else:
                logger.error(f"❌ Telethon: не удалось пометить пользователя {user.id} как удаленного")

        except Exception as e:
            logger.error(f"❌ Ошибка обработки вышедшего участника {user.id}: {e}")

    def get_member_count_sync(self):
        """Синхронное получение количества участников"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._get_member_count())
            loop.close()
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества участников: {e}")
            return 0

    async def _get_member_count(self):
        """Асинхронное получение количества участников"""
        try:
            channel_id = int(Config.CHANNEL_ID)
            entity = await self.client.get_entity(channel_id)
            participants = await self.client.get_participants(entity)
            return len([p for p in participants if not p.bot])
        except Exception as e:
            logger.error(f"❌ Ошибка подсчета участников: {e}")
            return 0

    def is_connected(self):
        """Проверка подключения"""
        return self.is_connected


# Глобальный экземпляр
telethon_tracker = TelethonTracker()