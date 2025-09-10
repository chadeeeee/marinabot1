import os
import sys
import json
import asyncio
import logging
import random
import traceback
import hashlib
from datetime import date
import aiohttp

from telethon.sync import TelegramClient
from telethon import events
from telethon.tl.functions.channels import GetParticipantsRequest, JoinChannelRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.errors import FloodWaitError, UserIsBlockedError, UserDeactivatedError, UserDeactivatedBanError, \
    UsernameInvalidError, PeerIdInvalidError, MediaEmptyError, UsernameOccupiedError
from telethon import errors
from telethon.tl.types import InputPhoneContact
from telethon.tl.functions.contacts import ImportContactsRequest

from config import api_hash, api_id


class AppState:
    def __init__(self):
        self.bot_mailing_command_received = False
        self.sending_active = False
        self.target_type = None  # Keep as None, to be set by command
        self.target_file = None

    def set_mailing_command_received(self):
        self.bot_mailing_command_received = True

    def is_mailing_command_pending(self):
        return self.bot_mailing_command_received

    def consume_mailing_command(self):
        self.bot_mailing_command_received = False

    def reset_for_shutdown(self):
        self.bot_mailing_command_received = False
        self.sending_active = False
        self.target_type = None
        self.target_file = None
        logging.getLogger(__name__).info("Флаги стану програми скинуті для завершення роботи.")


class TelegramBot:
    def __init__(self, api_id, api_hash):
        self.api_id = api_id
        self.api_hash = api_hash
        self.client = TelegramClient('userbotsessio1n', self.api_id, self.api_hash)
        self.BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        self.BOT_DIR = os.path.join(os.path.dirname(self.BASE_DIR), "bot")
        self.USERNAMES_FILE = os.path.join(self.BASE_DIR, "all_usernames.txt")
        self.MESSAGE_DATA_FILE = os.path.join(self.BASE_DIR, "message_data.json")
        self.STATS_FILE = os.path.join(self.BASE_DIR, "stats.txt")
        self.DAILY_STATS_FILE = os.path.join(self.BASE_DIR, "daily_stats.json")
        self.FLAG_FILE = os.path.join(self.BASE_DIR, "flag.txt")
        self.CHATS_FILE = os.path.join(self.BASE_DIR, "chats.txt")
        self.FLAG_START = "START"
        self.FLAG_RUNNING = "RUNNING"
        self.FLAG_STOP = "STOP"
        self.FLAG_DONE = "DONE"
        self.FLAG_IDLE = "IDLE"
        self.FLAG_PAUSED_LIMIT = "PAUSED_LIMIT"
        self.MAX_MESSAGES_PER_DAY = 25
        self.MIN_DELAY_SECONDS = 30
        self.MAX_DELAY_SECONDS = 90
        self.EXPECTED_LICENSE_CODE = "aL8urf1WwxvL9E5hpGdrDWPzgdNky2sm"
        self.LICENSE_CHECK_URL = "https://check-mu-tan.vercel.app/"
        self.LICENSE_CHECK_INTERVAL = 60
        self.BOT_ID = 8136612723
        self.ADMIN_ID = 5197139803
        self.logger = logging.getLogger(__name__)
        self.client.message_data = None
        self.app_state = AppState()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler("userbot.log", encoding="utf-8")
            ]
        )

    def setup_handlers(self):
        @self.client.on(events.NewMessage(from_users=(self.BOT_ID, self.ADMIN_ID)))
        async def main_bot_command_handler(event):
            await self._main_bot_command_handler(event)

        @self.client.on(events.NewMessage(from_users=self.BOT_ID))
        async def forward_bot_messages_to_admin(event):
            await self._forward_bot_messages_to_admin(event)

    async def _main_bot_command_handler(self, event):
        self.logger.info(f"DEBUG: Handler triggered for message from {event.sender_id}: {event.text}")
        self.logger.info(f"Отримано повідомлення від бота: {event.text}")
        self.logger.info(f"ID відправника: {event.sender_id}, очікуваний ID бота: {self.BOT_ID} або ADMIN_ID: {self.ADMIN_ID}")

        if not self._is_bot_or_admin(event.sender_id):
            self.logger.warning(f"Повідомлення від невідомого відправника: {event.sender_id}")
            return

        if "[INFO] Розсилку розпочато" in event.text: # This will now exclusively trigger phone mailing
            self.logger.info("Бот наказав розпочати розсилку по номерах телефонів")
            # if not await self._check_license():
            #     await event.respond("Ліцензія не підтверджена. Розсилка не розпочата.")
            #     self.logger.error("Розсилка не розпочата через невірну ліцензію")
            #     return
            await event.respond("Розсилку розпочато")
            self.logger.info("Отримано команду на початок розсилки по номерах")
            self.app_state.set_mailing_command_received()
            self.app_state.target_type = "phones"
            phones_file = os.path.join(self.BASE_DIR, "all_phones.txt")
            self.app_state.target_file = phones_file
            self.logger.info(f"Установлен тип рассылки: phones, файл: {phones_file}")
            self._write_flag(self.FLAG_START)
            self.logger.info("Установлен флаг START для номеров")
        elif "[INFO] Розсилку буде зупинено" in event.text:
            self.logger.info("Отримано команду на зупинку розсилки")
            self._write_flag(self.FLAG_STOP)
            self.app_state.sending_active = False
            self.app_state.consume_mailing_command()
            self.logger.info("Скинуто прапори розсилки")
            await event.respond("Розсилку зупинено")
        elif "[INFO] Збір розпочато" in event.text:
            self.logger.info("Отримано команду на початок збору юзернеймів")
            try:
                processed_chats, usernames_count, phones_count = await self._process_chats()
                await event.respond(f"Збір завершено. Оброблено чатів: {processed_chats}, зібрано юзернеймів: {usernames_count}, номерів телефонів: {phones_count}")
            except Exception as e:
                self.logger.error(f"Помилка при зборі даних: {e}")
                await event.respond(f"Помилка при зборі: {e}")
        elif "[INFO] Сбор начат" in event.text:
            self.logger.info("Получена команда на начало сбора юзернеймов")
            try:
                processed_chats, usernames_count, phones_count = await self._process_chats()
                await event.respond(f"Сбор завершен. Обработано чатов: {processed_chats}, собрано юзернеймов: {usernames_count}, номеров телефонов: {phones_count}")
            except Exception as e:
                self.logger.error(f"Ошибка при сборе данных: {e}")
                await event.respond(f"Ошибка при сборе: {e}")
        elif "[INFO] Добавить чати" in event.text:
            self.logger.info("Получена команда на добавление чатов")
            try:
                chat_links = event.text.split("\n")[1:]
                chat_links = [link.strip() for link in chat_links if link.strip()]

                if not chat_links:
                    await event.respond("Не найдено ссылок на чати")
                    return

                chat_dir = os.path.dirname(self.CHATS_FILE)
                if chat_dir and not os.path.exists(chat_dir):
                    os.makedirs(chat_dir)
                    self.logger.info(f"Создана директория: {chat_dir}")

                try:
                    with open(self.CHATS_FILE, "w", encoding="utf-8") as f:
                        for link in chat_links:
                            f.write(f"{link}\n")
                    self.logger.info(f"Файл {self.CHATS_FILE} успешно перезаписан")
                except Exception as e:
                    self.logger.error(f"Ошибка при перезаписи файла {self.CHATS_FILE}: {e}")
                    await event.respond(f"Ошибка при сохранении чатов: {e}")
                    return

                await event.respond(f"Добавлено {len(chat_links)} чатов в файл")
                self.logger.info(f"Добавлено {len(chat_links)} чатов в файл {self.CHATS_FILE}")
            except Exception as e:
                self.logger.error(f"Ошибка при добавлении чатов: {e}")
                await event.respond(f"Ошибка при добавлении чатов: {e}")
        elif "[MESSAGE_UPDATE] text:" in event.text:
            text = event.text.replace("[MESSAGE_UPDATE] text: ", "")
            message_data = {"type": "text", "content": text, "caption": None}
            self.client.message_data = message_data
            # Сохраняем в файл
            try:
                with open(self.MESSAGE_DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(message_data, f, ensure_ascii=False, indent=2)
                self.logger.info("Updated message_data from text update and saved to file")
            except Exception as e:
                self.logger.error(f"Ошибка сохранения message_data в файл: {e}")
        elif "You need to post:" in event.text:
            lines = event.text.split('\n')
            if len(lines) >= 2:
                caption = lines[0].replace("You need to post: ", "")
                imgbb_link = lines[1]
                
                # Создаем message_data с поддержкой как imgbb ссылки, так и локального файла
                message_data = {
                    "type": "photo", 
                    "content": imgbb_link,  # Сначала пробуем imgbb ссылку
                    "caption": caption,
                    "local_content": "D:\\Code\\marinabot1\\media\\photo.jpg",  # Резервный локальный путь
                    "rel_content": "./media/photo.jpg"  # Относительный путь
                }
                self.client.message_data = message_data
                # Сохраняем в файл
                try:
                    with open(self.MESSAGE_DATA_FILE, "w", encoding="utf-8") as f:
                        json.dump(message_data, f, ensure_ascii=False, indent=2)
                    self.logger.info("Updated message_data from photo notification and saved to file")
                except Exception as e:
                    self.logger.error(f"Ошибка сохранения message_data в файл: {e}")

    async def _forward_bot_messages_to_admin(self, event):
        try:
            await self.client.forward_messages(self.ADMIN_ID, event.message)
            self.logger.info(f"Переслано повідомлення від BOT_ID адміну: {event.text}")
        except Exception as e:
            self.logger.error(f"Не вдалося переслати повідомлення адміну: {e}")

    def _is_bot_or_admin(self, sender_id):
        return sender_id in (self.BOT_ID, self.ADMIN_ID)

    async def _process_chats(self):
        if not os.path.exists(self.CHATS_FILE):
            self.logger.error(f"Файл {self.CHATS_FILE} не найден")
            return 0, 0, 0
        usernames = set()
        phones = set()
        processed_chats = 0
        try:
            with open(self.CHATS_FILE, "r", encoding="utf-8") as f:
                chat_links = [line.strip() for line in f if line.strip()]
        except Exception as e:
            self.logger.error(f"Ошибка при чтении файла {self.CHATS_FILE}: {e}")
            return 0, 0, 0
        if not chat_links:
            self.logger.warning(f"Файл {self.CHATS_FILE} пустой або не містить посилань")
            return 0, 0, 0
        self.logger.info(f"Знайдено {len(chat_links)} посилань для обробки")
        for i, link in enumerate(chat_links, 1):
            try:
                self.logger.info(f"[{i}/{len(chat_links)}] Обробка чата: {link}")
                clean_link = link.lstrip('+')
                try:
                    entity = await self.client.get_entity(clean_link)
                    processed_chats += 1
                    try:
                        await self.client(JoinChannelRequest(entity))
                    except Exception:
                        pass
                    offset = 0
                    limit = 200
                    max_iterations = 50
                    iteration = 0
                    while iteration < max_iterations:
                        participants = await self.client(GetParticipantsRequest(
                            channel=entity,
                            filter=ChannelParticipantsSearch(''),
                            offset=offset,
                            limit=limit,
                            hash=0
                        ))
                        if not participants.users:
                            break
                        for user in participants.users:
                            if getattr(user, 'bot', False) or getattr(user, 'deleted', False) or getattr(user, 'fake', False):
                                continue
                            if user.username:
                                u = user.username
                                ul = u.lower()
                                if not any(b in ul for b in ['bot', '_bot', 'robot']):
                                    usernames.add(u)
                            if user.phone:
                                phones.add(user.phone)
                        offset += len(participants.users)
                        iteration += 1
                        await asyncio.sleep(2)
                        if len(participants.users) < limit:
                            break
                    await asyncio.sleep(3)
                except Exception as e:
                    self.logger.error(f"Ошибка при обработке чата {link}: {e}")
            except Exception as e:
                self.logger.error(f"Ошибка при отриманні інформації про чат {link}: {e}")
        try:
            with open(self.USERNAMES_FILE, "w", encoding="utf-8") as f:
                for username in sorted(usernames):
                    f.write(f"{username}\n")
            self.logger.info(f"Збережено {len(usernames)} юзернеймів у файл {self.USERNAMES_FILE}")
        except Exception as e:
            self.logger.error(f"Помилка при збереженні юзернеймів: {e}")
        try:
            phones_file = os.path.join(self.BASE_DIR, "all_phones.txt")
            phone_list = sorted(list(phones))
            if phone_list:
                try:
                    parent_dir = os.path.dirname(self.BASE_DIR)
                    if parent_dir not in sys.path:
                        sys.path.append(parent_dir)
                    from phone_distributor_enhanced import add_phones_and_redistribute
                    success = add_phones_and_redistribute(phone_list)
                    if not success:
                        with open(phones_file, "w", encoding="utf-8") as f:
                            for phone in phone_list:
                                f.write(f"{phone}\n")
                except Exception:
                    with open(phones_file, "w", encoding="utf-8") as f:
                        for phone in phone_list:
                            f.write(f"{phone}\n")
            self.logger.info(f"Оброблено {len(phones)} телефонів")
        except Exception as e:
            self.logger.error(f"Помилка при збереженні телефонів: {e}")
        return processed_chats, len(usernames), len(phones)

    async def _ensure_bot_entity(self):
        """Ensures that the bot entity is available before sending messages with improved error handling"""
        try:
            # First try to get by ID
            try:
                bot_entity = await self.client.get_entity(self.BOT_ID)
                self.logger.info(f"Bot entity found by ID: {self.BOT_ID}")
                return bot_entity
            except errors.RPCError as e:
                self.logger.warning(f"Could not find bot entity by ID: {e}")
            
            # Try with string ID format
            try:
                bot_entity = await self.client.get_entity(str(self.BOT_ID))
                self.logger.info(f"Bot entity found by string ID: {self.BOT_ID}")
                return bot_entity
            except errors.RPCError as e:
                self.logger.warning(f"Could not find bot entity by string ID: {e}")
            
            # Try to get recent dialogs and find the bot
            dialogs = await self.client.get_dialogs(limit=50)
            for dialog in dialogs:
                if dialog.entity.id == self.BOT_ID:
                    self.logger.info(f"Bot entity found in recent dialogs: {self.BOT_ID}")
                    return dialog.entity
            
            self.logger.error(f"Bot entity with ID {self.BOT_ID} not found in any known method")
            return None
        except Exception as e:
            self.logger.error(f"General error finding bot entity: {e}")
            return None

    async def _initialize_bot_contact(self):
        """Initializes contact with the bot to ensure entity is available"""
        try:
            # Try to send a dummy message to the bot first to establish contact
            try:
                # Use a direct approach first
                await self.client.send_message(self.BOT_ID, "Initializing connection")
                self.logger.info("Successfully initialized connection with bot")
                return True
            except Exception as e:
                self.logger.warning(f"Failed direct initialization with bot: {e}")
                
                # Try to search for the bot in dialogs
                dialogs = await self.client.get_dialogs(limit=50)
                for dialog in dialogs:
                    if dialog.entity.id == self.BOT_ID:
                        await self.client.send_message(dialog.entity, "Initializing connection")
                        self.logger.info("Successfully initialized connection with bot via dialog")
                        return True
            
            self.logger.error(f"Could not initialize connection with bot {self.BOT_ID}")
            return False
        except Exception as e:
            self.logger.error(f"Error initializing bot contact: {e}")
            return False

    async def _send_message_to_bot_and_admin(self, message, **kwargs):
        # Добавляем timeout для предотвращения зависания
        timeout = 30
        try:
            await asyncio.wait_for(self.client.send_message(self.BOT_ID, message, **kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout при отправке сообщения боту (BOT_ID)")
        except Exception as e:
            self.logger.error(f"Не вдалося відправити повідомлення боту: {e}")
        try:
            await asyncio.wait_for(self.client.send_message(self.ADMIN_ID, message, **kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout при отправке сообщения админу (ADMIN_ID)")
        except Exception as e:
            self.logger.error(f"Не вдалося відправити повідомлення адміну: {e}")

    async def _safe_send_message_to_bot(self, message_text, retry_attempt=0):
        """Safely sends a message to the bot with improved retry logic and fallbacks"""
        max_retries = 2
        
        if retry_attempt > max_retries:
            self.logger.error(f"Maximum retry attempts ({max_retries}) reached. Giving up sending message to bot.")
            return False
        
        try:
            # Try with entity resolution first
            try:
                bot_entity = await self._ensure_bot_entity()
                if bot_entity:
                    await self._send_message_to_bot_and_admin(message_text)
                    return True
            except Exception as e:
                self.logger.warning(f"Error in primary bot message send method: {e}")
            
            # Try with direct ID as fallback
            try:
                await self._send_message_to_bot_and_admin(message_text)
                self.logger.info("Message sent directly to bot by ID")
                return True
            except Exception as e:
                self.logger.warning(f"Error sending message to bot directly: {e}")
                
                # If first attempt, try initializing contact first
                if retry_attempt == 0:
                    self.logger.info("Attempting to initialize bot contact before retrying")
                    if await self._initialize_bot_contact():
                        # Wait a moment for the connection to establish
                        await asyncio.sleep(2)
                        return await self._safe_send_message_to_bot(message_text, retry_attempt + 1)
                        
            # Log the message locally as a last resort
            self.logger.info(f"UNSENT BOT MESSAGE: {message_text}")
            return False
        except Exception as e:
            self.logger.error(f"General error in safe_send_message_to_bot: {e}")
            return False

    async def _process_mailing(self, target_type, filename):
        if not os.path.isabs(filename):
            filename = os.path.join(self.BASE_DIR, filename)
            self.logger.info(f"Перетворено відносний шлях до абсолютного: {filename}")

        self.logger.info(f"Перевірка файлу {filename} перед початком розсилки")
        targets = []  # Initialize targets variable

        if not os.path.exists(filename):
            self.logger.error(f"Файл {filename} не знайдено")
            try:
                await self._send_message_to_bot_and_admin(f"Помилка: файл {filename} не знайдено")
            except Exception as e:
                self.logger.error(f"Не вдалося відправити повідомлення боту: {e}")
            
            # Continue with collection anyway
            self.logger.info("Attempting to collect data despite missing file")
            try:
                processed_chats, usernames_count, phones_count = await self._process_chats()
                self.logger.info(f"Collection complete: {processed_chats} chats, {usernames_count} usernames, {phones_count} phones")
                
                # Check if file exists now after collection
                if os.path.exists(filename):
                    self.logger.info(f"File {filename} now exists after collection")
                    # Read the targets from the newly created file
                    with open(filename, "r", encoding="utf-8") as f:
                        targets = [line.strip() for line in f if line.strip()]
                    self.logger.info(f"Loaded {len(targets)} targets from file after collection")
                else:
                    self.logger.error(f"File {filename} still doesn't exist after collection")
                    return  # Exit function if file still doesn't exist
            except Exception as e:
                self.logger.error(f"Error collecting data: {e}")
                return  # Exit function if collection fails
        else:
            # File exists, read targets normally
            with open(filename, "r", encoding="utf-8") as f:
                targets = [line.strip() for line in f if line.strip()]
            self.logger.info(f"Loaded {len(targets)} targets from existing file")

        if not targets:
            target_type_name = "номерів телефонів"
            self.logger.warning(f"Файл {filename} порожній або не містить цільових номерів")
            try:
                await self._send_message_to_bot_and_admin(f"Файл {filename} порожній. Неможливо розпочати розсилку.")
            except Exception as e:
                self.logger.error(f"Не вдалося відправити повідомлення боту: {e}")
            return  # Exit function if no targets

        # Continue with mailing process since we have targets
        self.logger.info(f"Починаю розсилку по {len(targets)} {'номерах телефонів'}")
        try:
            await self._send_message_to_bot_and_admin(f"Починаю розсилку по {len(targets)} {'номерах телефонів'}")
        except Exception as e:
            self.logger.error(f"Could not notify bot about mailing start: {e}")
            # Continue mailing even if notification fails
        
        sent_count = 0
        failed_count = 0
        for target in targets:
            self.logger.info(f"Обрабатываю цель {sent_count + failed_count + 1}/{len(targets)}: {target}")
            
            if sent_count >= 50:
                self.logger.info("Достигнут лимит в 50 сообщений. Рассылка завершена.")
                try:
                    await self._send_message_to_bot_and_admin("Достигнут лимит в 50 сообщений. Рассылка завершена.")
                except Exception as e:
                    self.logger.error(f"Не удалось отправить уведомление о лимите: {e}")
                break

            if self._read_flag() == self.FLAG_STOP:
                try:
                    await self._send_message_to_bot_and_admin("Рассылка остановлена пользователем")
                except Exception as e:
                    self.logger.error(f"Не удалось отправить уведомление об остановке: {e}")
                return
            try:
                if self.client.message_data is None:
                    self.client.message_data = self._read_message_data()
                if not self.client.message_data:
                    try:
                        await self._send_message_to_bot_and_admin("Ошибка: не удалось получить данные сообщения")
                    except Exception as e:
                        self.logger.error(f"Не удалось отправить уведомление об ошибке данных: {e}")
                    return
                msg_type = self.client.message_data.get("type")
                content = self.client.message_data.get("content")
                caption = self.client.message_data.get("caption")
                
                # Логируем данные сообщения для отладки
                self.logger.info(f"Данные сообщения: тип={msg_type}, контент={content}, заголовок={caption}")
                
                # Если content пустой, попробуем использовать резервные варианты
                if not content:
                    if "local_content" in self.client.message_data:
                        content = self.client.message_data.get("local_content")
                        self.logger.info(f"Используем local_content: {content}")
                    elif "rel_content" in self.client.message_data:
                        content = self.client.message_data.get("rel_content")
                        self.logger.info(f"Используем rel_content: {content}")

                success, error = await self._send_message_to_phone(self.client, target, msg_type, content, caption)
                if success:
                    sent_count += 1
                    self.logger.info(f"Сообщение успешно отправлено на {target}. Всего отправлено: {sent_count}")
                    # Отправляем уведомление только каждые 5 сообщений для избежания rate limit
                    if sent_count % 5 == 0:
                        try:
                            await self._send_message_to_bot_and_admin(f"Отправлено сообщений: {sent_count}/{len(targets)}")
                        except Exception as e:
                            self.logger.error(f"Не удалось отправить промежуточное уведомление: {e}")
                else:
                    failed_count += 1
                    self.logger.error(f"Ошибка при отправке к {target}: {error}")
                await asyncio.sleep(random.uniform(self.MIN_DELAY_SECONDS, self.MAX_DELAY_SECONDS))
            except Exception as e:
                self.logger.error(f"Ошибка при отправке к {target}: {e}")
                failed_count += 1
        
        # Отправляем финальное уведомление
        final_message = f"Рассылка завершена\nУспешно: {sent_count}\nОшибок: {failed_count}"
        self.logger.info(final_message)
        try:
            await self._send_message_to_bot_and_admin(final_message)
        except Exception as e:
            self.logger.error(f"Не удалось отправить финальное уведомление: {e}")

    def _read_flag(self):
        try:
            if os.path.exists(self.FLAG_FILE):
                with open(self.FLAG_FILE, "r", encoding="utf-8") as f:
                    return f.read().strip().upper()
            else:
                self._write_flag(self.FLAG_IDLE)
                return self.FLAG_IDLE
        except Exception as e:
            self.logger.error(f"Ошибка чтения файла-флага {self.FLAG_FILE}: {e}")
            return self.FLAG_IDLE

    def _write_flag(self, status):
        try:
            with open(self.FLAG_FILE, "w", encoding="utf-8") as f:
                f.write(status)
            self.logger.info(f"Статус рассылки изменен на {status}")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка записи в файл-флаг {self.FLAG_FILE}: {e}")
            return False

    def _read_usernames(self):
        usernames = []
        if not os.path.exists(self.USERNAMES_FILE):
            self.logger.warning(f"Файл {self.USERNAMES_FILE} не найден. Возвращаю пустой список.")
            return usernames
        try:
            with open(self.USERNAMES_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s:
                        usernames.append(s if s.startswith('@') else f"@{s}")
        except Exception as e:
            self.logger.error(f"Ошибка чтения файла username {self.USERNAMES_FILE}: {e}")
        return usernames

    def _read_message_data(self):
        message_data = None
        if not os.path.exists(self.MESSAGE_DATA_FILE):
            self.logger.warning(f"Файл {self.MESSAGE_DATA_FILE} не найден. Возвращаю None.")
            return message_data
        try:
            with open(self.MESSAGE_DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    self.logger.warning(f"Файл {self.MESSAGE_DATA_FILE} пустой.")
                    return None
                message_data = json.loads(content)
        except json.JSONDecodeError as e:
            self.logger.error(f"Ошибка декодирования JSON в файле {self.MESSAGE_DATA_FILE}: {e}")
            self.logger.error(f"Содержимое файла: {content[:100] if 'content' in locals() else 'не удалось прочитать'}")
            return None
        except Exception as e:
            self.logger.error(f"Ошибка чтения файла сообщения {self.MESSAGE_DATA_FILE}: {e}")
            return None
        return message_data

    def _update_total_stats(self, sent_count):
        current_count = 0
        try:
            if os.path.exists(self.STATS_FILE):
                with open(self.STATS_FILE, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content.isdigit():
                        current_count = int(content)
                    else:
                        self.logger.warning(
                            f"Файл статистики {self.STATS_FILE} содержит некорректное значение: '{content}'. Начинаем с 0.")
        except Exception as e:
            self.logger.warning(f"Ошибка чтения файла статистики {self.STATS_FILE}, начинаем с 0: {e}")

        total_count = current_count + sent_count
        try:
            with open(self.STATS_FILE, "w", encoding="utf-8") as f:
                f.write(str(total_count))
            self.logger.info(f"Общая статистика обновлена: {sent_count} новых сообщений (всего: {total_count}).")
        except Exception as e:
            self.logger.error(f"Ошибка записи в файл общей статистики {self.STATS_FILE}: {e}")

    def _read_daily_stats(self):
        today_str = date.today().isoformat()
        if os.path.exists(self.DAILY_STATS_FILE):
            try:
                with open(self.DAILY_STATS_FILE, "r", encoding="utf-8") as f:
                    stats_data = json.load(f)
                if isinstance(stats_data, dict) and stats_data.get("date") == today_str:
                    return stats_data.get("sent_today", 0)
            except json.JSONDecodeError:
                self.logger.error(
                    f"Файл дневной статистики {self.DAILY_STATS_FILE} пошкоджений або має неверний формат. Скидаємо лічильник на сьогодні.")
            except Exception as e:
                self.logger.error(
                    f"Помилка читання файлу дневної статистики {self.DAILY_STATS_FILE}: {e}. Скидаємо лічильник на сьогодні.")
        return 0

    def _update_daily_stats(self, sent_this_session_count):
        today_str = date.today().isoformat()
        current_sent_today = 0
        if os.path.exists(self.DAILY_STATS_FILE):
            try:
                with open(self.DAILY_STATS_FILE, "r", encoding="utf-8") as f:
                    stats = json.load(f)
                if isinstance(stats, dict) and stats.get("date") == today_str:
                    current_sent_today = stats.get("sent_today", 0)
                else:
                    self.logger.info(f"Дата в {self.DAILY_STATS_FILE} ({stats.get('date') if isinstance(stats, dict) else 'N/A'}) "
                                    f"не збігається з сьогоднішньою ({today_str}) або не є словником. Скидаю денний лічильник.")
            except json.JSONDecodeError:
                self.logger.warning(f"Файл {self.DAILY_STATS_FILE} пошкоджений. Скидаю денний лічильник.")
            except Exception as e:
                self.logger.warning(f"Помилка читання {self.DAILY_STATS_FILE} ({e}), скидаю денний лічильник для {today_str}.")
                pass

        new_sent_today = current_sent_today + sent_this_session_count

        try:
            with open(self.DAILY_STATS_FILE, "w", encoding="utf-8") as f:
                json.dump({"date": today_str, "sent_today": new_sent_today}, f)
            self.logger.info(f"Денна статистика оновлена: {sent_this_session_count} нових, всього сьогодні: {new_sent_today}")
        except Exception as e:
            self.logger.error(f"Помилка запису в файл денній статистики {self.DAILY_STATS_FILE}: {e}")

    def _resolve_media_path(self, media_path):
        if os.path.isabs(media_path) and os.path.exists(media_path):
            self.logger.info(f"Використовую абсолютний шлях до медіа: {media_path}")
            return media_path

        if media_path.startswith('./media/'):
            file_name = os.path.basename(media_path)

            local_path = os.path.join(self.BASE_DIR, 'media', file_name)
            if os.path.exists(local_path):
                self.logger.info(f"Знайдено медіа в локальній папці: {local_path}")
                return local_path

            project_root = os.path.dirname(self.BASE_DIR)
            root_media_path = os.path.join(project_root, 'media', file_name)
            if os.path.exists(root_media_path):
                self.logger.info(f"Знайдено медіа в корневій папці проекту: {root_media_path}")
                return root_media_path

        if os.path.basename(media_path) == media_path:
            local_media_path = os.path.join(self.BASE_DIR, 'media', media_path)
            if os.path.exists(local_media_path):
                self.logger.info(f"Знайдено медіа за ім'ям файлу в локальній папці: {local_media_path}")
                return local_media_path

            project_root = os.path.dirname(self.BASE_DIR)
            root_media_path = os.path.join(project_root, 'media', media_path)
            if os.path.exists(root_media_path):
                self.logger.info(f"Знайдено медіа за ім'ям файлу в корневій папці: {root_media_path}")
                return root_media_path

        self.logger.warning(f"Не вдалося знайти медіафайл: {media_path}")
        return media_path

    async def _upload_to_imgbb(self, image_path):
        url = "https://api.imgbb.com/1/upload"
        api_key = "ce979babca80641f52db24b816ea2201"

        if not os.path.exists(image_path):
            self.logger.error(f"Image file not found: {image_path}")
            return None

        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()

            data = aiohttp.FormData()
            data.add_field('key', api_key)
            data.add_field('image', image_data, filename=os.path.basename(image_path))

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        img_url = result['data']['url']
                        self.logger.info(f"Image uploaded to imgbb: {img_url}")
                        return img_url
                    else:
                        self.logger.error(f"Failed to upload to imgbb: HTTP {resp.status}")
                        return None
        except Exception as e:
            self.logger.error(f"Error uploading to imgbb: {e}")
            return None

    async def _send_message_to_username(self, username: str, message_type, content, caption=None):
        self.logger.error("Відправка повідомлень по юзернеймах відключена.")
        return False, "Відправка повідомлень по юзернеймах відключена."

    async def _add_contact_by_phone(self, phone_number: str) -> bool:
        try:
            clean_phone = phone_number.lstrip('+')
            contact_name = f"Contact_{hashlib.md5(phone_number.encode()).hexdigest()[:8]}"
            contact = InputPhoneContact(
                client_id=hash(phone_number) & 0x7FFFFFFF,
                phone=clean_phone,
                first_name=contact_name,
                last_name=""
            )
            result = await self.client(ImportContactsRequest([contact]))

            if result.imported:
                self.logger.info(f"Контакт {phone_number} успішно додано")
                return True
            else:
                self.logger.warning(f"Не вдалося додати контакт {phone_number}")
                return False

        except Exception as e:
            self.logger.error(f"Помилка при додаванні контакту {phone_number}: {e}")
            return False

    async def _send_message_to_phone(self, app_client: TelegramClient, phone: str, message_type, content, caption=None):
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                self.logger.info(f"Спроба відправки повідомлення на номер: {phone} (спроба {retry_count + 1})")

                entity = None

                try:
                    entity = await app_client.get_entity(phone)
                    self.logger.info(f"Користувач {phone} знайдений безпосередньо")
                except Exception:
                    self.logger.info(f"Спроба додавання {phone} в контакти")
                    contact_added = await self._add_contact_by_phone(phone)

                    if contact_added:
                        await asyncio.sleep(3)
                        try:
                            entity = await app_client.get_entity(phone)
                            self.logger.info(f"Користувач {phone} знайдений після додавання в контакти")
                        except Exception as e:
                            self.logger.error(f"Не вдалося знайти користувача {phone} навіть після додавання в контакти: {e}")
                            return False, f"Номер {phone} не знайдений у Telegram"
                    else:
                        self.logger.error(f"Користувач з номером {phone} не знайдений і не вдалося додати в контакти")
                        return False, f"Номер {phone} не знайдений у Telegram або не може бути додан в контакти"

                if entity is None:
                    return False, f"Номер {phone} недоступний для відправки"

                actual_content = content
                actual_caption = caption

                if message_type in ["photo", "video", "document"]:
                    if actual_content and isinstance(actual_content, str):
                        if not os.path.isabs(actual_content):
                            content_path = os.path.join(self.BASE_DIR, actual_content)
                        else:
                            content_path = actual_content
                        content_path = os.path.normpath(content_path)
                        if not os.path.isfile(content_path):
                            self.logger.error(f"Файл не існує: {content_path}")
                            return False, f"Файл не знайдено: {content_path}"
                        actual_content = content_path
                    else:
                        self.logger.error(f"Для типу {message_type} контент повинен бути шляхом до файлу")
                        return False, f"Неправильний контент для типу {message_type}"

                await asyncio.sleep(random.uniform(5, 15))

                if message_type == "text":
                    await app_client.send_message(entity, actual_content)
                elif message_type == "photo":
                    img_url = await self._upload_to_imgbb(actual_content)
                    if img_url:
                        await app_client.send_file(entity, img_url, caption=actual_caption)
                    else:
                        self.logger.error(f"Failed to upload photo for {phone}")
                        return False, "Failed to upload photo to imgbb"
                elif message_type == "video":
                    await app_client.send_file(entity, actual_content, caption=actual_caption)
                elif message_type == "document":
                    await app_client.send_file(entity, actual_content, caption=actual_caption)
                else:
                    self.logger.error(f"Невідомий тип повідомлення: {message_type}")
                    return False, f"Невідомий тип повідомлення: {message_type}"

                self.logger.info(f"{message_type.capitalize()} успішно відправлено на номер {phone}")
                await self._send_message_to_bot_and_admin(f"Відправлено повідомлення на номер: {phone}")
                return True, None

            except FloodWaitError as fw:
                wait_time = fw.seconds + random.uniform(10, 30)
                self.logger.warning(f"FloodWaitError для {phone}: потрібно почекати {wait_time:.2f} секунд")
                await asyncio.sleep(wait_time)
                retry_count += 1
                if retry_count >= max_retries:
                    return False, f"FloodWaitError після {max_retries} спроб"
                continue
            except errors.RPCError as rpc_e:
                if "Too many requests" in str(rpc_e) or "FLOOD_WAIT" in str(rpc_e):
                    wait_time = 120 + random.uniform(30, 60)
                    self.logger.warning(f"Rate limit для {phone}: почекаємо {wait_time:.2f} секунд")
                    await asyncio.sleep(wait_time)
                    retry_count += 1
                    if retry_count >= max_retries:
                        return False, f"Rate limit після {max_retries} спроб"
                    continue
                else:
                    self.logger.error(f"RPC помилка при відправці {phone}: {rpc_e}")
                    return False, f"RPC помилка: {rpc_e}"
            except Exception as e:
                if "Cannot find any entity corresponding to" in str(e) or "Could not find the input entity" in str(e):
                    self.logger.error(f"Користувач з номером {phone} не знайдений у Telegram")
                    return False, f"Номер {phone} не зареєстрований у Telegram"
                else:
                    self.logger.error(f"Загальна помилка при відправці на {phone}: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        return False, f"Помилка: {e}"
                    await asyncio.sleep(random.uniform(10, 20))
                    continue

        return False, f"Не вдалося відправити після {max_retries} спроб"

    def _count_phones(self):
        phones_file = os.path.join(self.BASE_DIR, "all_phones.txt")
        try:
            if not os.path.exists(phones_file):
                self.logger.warning(f"Файл {phones_file} не знайдено при підрахунку телефонів")
                return 0

            with open(phones_file, "r", encoding="utf-8") as f:
                phones = [line.strip() for line in f if line.strip()]
                self.logger.info(f"Знайдено {len(phones)} телефонів у файлі {phones_file}")
                return len(phones)
        except Exception as e:
            self.logger.error(f"Помилка при підрахунку телефонів: {e}")
            return 0

    async def _send_messages_task(self):
        self.logger.info("Задача мониторинга файла-флага і рассилки запущена.")
        while True:
            try:
                flag_status = self._read_flag()
                if flag_status == self.FLAG_START:
                    self.logger.info("Розпочинаємо нову сесію розсилки")
                    if not self.app_state.sending_active:
                        self.app_state.sending_active = True
                        self._write_flag(self.FLAG_RUNNING)
                        self.logger.info("Статус розсилки оновлено на RUNNING")
                        
                        # Always ensure target_type is set to phones when starting
                        if self.app_state.target_type is None:
                            self.app_state.target_type = "phones"
                            self.app_state.target_file = os.path.join(self.BASE_DIR, "all_phones.txt")
                            self.logger.info(f"Target type був None. Автоматично встановлюю тип на: phones, файл: {self.app_state.target_file}")
                    else:
                        self.logger.info("Сесія розсилки вже активна, чекаємо завершення...")
                        await asyncio.sleep(10)
                        continue

                    try:
                        # Target type should be set by now, but double check
                        if self.app_state.target_type is None:
                            self.app_state.target_type = "phones"  # Default to phones
                            self.app_state.target_file = os.path.join(self.BASE_DIR, "all_phones.txt")
                            self.logger.info(f"Встановлюю тип за замовчуванням: phones, файл: {self.app_state.target_file}")

                        # Processing can now proceed without waiting
                        if self.app_state.target_type == "phones":
                            target_file = self.app_state.target_file if self.app_state.target_file else os.path.join(self.BASE_DIR, "all_phones.txt")
                            self.logger.info(f"Запускаємо розсилку по номерах з файлу: {target_file}")
                            await self._process_mailing("phones", target_file)
                        else:
                            # For any other type, including "usernames", redirect to phones
                            self.logger.warning(f"Тип '{self.app_state.target_type}' не підтримується. Перемикаємо на телефони.")
                            self.app_state.target_type = "phones"
                            target_file = os.path.join(self.BASE_DIR, "all_phones.txt")
                            self.app_state.target_file = target_file
                            await self._process_mailing("phones", target_file)
                        
                        phones_count = self._count_phones()
                        self._update_total_stats(phones_count)
                        self._update_daily_stats(phones_count)
                        self.logger.info(f"Оновлено статистику після розсилки по {phones_count} телефонах")

                        self.logger.info("Розсилка завершена, оновлюємо статистику")
                        try:
                            await self._send_message_to_bot_and_admin("Розсилка завершена, статистику оновлено")
                        except Exception as e:
                            self.logger.error(f"Не вдалося відправити повідомлення боту: {e}")
                    except Exception as e:
                        self.logger.error(f"Помилка під час розсилки: {e}")
                        try:
                            await self._send_message_to_bot_and_admin(f"Помилка під час розсилки: {e}")
                        except Exception as send_e:
                            self.logger.error(f"Не вдалося відправити повідомлення боту: {send_e}")
                    finally:
                        self.app_state.sending_active = False
                        self.app_state.consume_mailing_command()
                        self._write_flag(self.FLAG_DONE)
                        self.logger.info("Сесія розсилки завершена")
                elif flag_status == self.FLAG_STOP:
                    self.logger.info("Розсилку зупинено за запитом")
                    self.app_state.sending_active = False
                    self.app_state.consume_mailing_command()
                    self._write_flag(self.FLAG_DONE)
                    await asyncio.sleep(5)
                else:
                    await asyncio.sleep(10)
            except Exception as e:
                self.logger.error(f"Помилка в задачі моніторингу: {e}")
                await asyncio.sleep(10)

    async def _check_license(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.LICENSE_CHECK_URL) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("license_code") == self.EXPECTED_LICENSE_CODE:
                            self.logger.info("Ліцензія підтверджена")
                            return True
                        else:
                            self.logger.error("Ліцензія невірна")
                            return False
                    else:
                        self.logger.error(f"Помилка перевірки ліцензії: HTTP {resp.status}")
                        return False
        except Exception as e:
            self.logger.error(f"Помилка при перевірці ліцензії: {e}")
            return False

    async def run(self):
        self.setup_logging()
        self.setup_handlers()
        self.logger.info(f"Рабочая директория: {self.BASE_DIR}")
        self.logger.info(f"Файл с Usernames: {self.USERNAMES_FILE}")
        self.logger.info(f"Файл данных сообщения: {self.MESSAGE_DATA_FILE}")
        self.logger.info(f"Файл общей статистики: {self.STATS_FILE}")
        self.logger.info(f"Файл дневной статистики: {self.DAILY_STATS_FILE}")
        self.logger.info(f"Файл-флаг: {self.FLAG_FILE}")
        self.logger.info(f"Файл чатов: {self.CHATS_FILE}")

        async with self.client:
            self.logger.info("Клієнт успішно підключено, запускаємо основні задачі...")
            # Надіслати адміну повідомлення про запуск
            try:
                await self.client.send_message(self.ADMIN_ID, "Юзербот запущений")
            except Exception as e:
                self.logger.error(f"Не вдалося надіслати адміну повідомлення про запуск: {e}")
            # Initialize bot contact at startup
            try:
                await self._initialize_bot_contact()
            except Exception as e:
                self.logger.warning(f"Failed to initialize bot contact at startup: {e}")
            task = asyncio.create_task(self._send_messages_task())
            self.logger.info("Основні задачі запущено, чекаємо повідомлень...")
            try:
                await self.client.run_until_disconnected()
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


async def main():
    bot = TelegramBot(api_id, api_hash)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())