import os
import sys
import json
import asyncio
import logging
import random
import traceback
import hashlib
from datetime import date
import aiohttp  # Added for async HTTP requests to imgbb API

from telethon.sync import TelegramClient
from telethon import events
from telethon.tl.functions.channels import GetParticipantsRequest, JoinChannelRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.errors import FloodWaitError, UserIsBlockedError, UserDeactivatedError, UserDeactivatedBanError, \
    UsernameInvalidError, PeerIdInvalidError, MediaEmptyError, UsernameOccupiedError
from telethon import errors
from telethon.tl.functions.contacts import AddContactRequest
from telethon.tl.types import InputPhoneContact
from telethon.tl.functions.contacts import ImportContactsRequest

from config import api_hash, api_id

BOT_ID = 8136612723

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.join(os.path.dirname(BASE_DIR), "bot")

USERNAMES_FILE = os.path.join(BASE_DIR, "all_usernames.txt")
MESSAGE_DATA_FILE = os.path.join(BASE_DIR, "message_data.json")
STATS_FILE = os.path.join(BASE_DIR, "stats.txt")
DAILY_STATS_FILE = os.path.join(BASE_DIR, "daily_stats.json")
FLAG_FILE = os.path.join(BASE_DIR, "flag.txt")
CHATS_FILE = os.path.join(BASE_DIR, "chats.txt")

FLAG_START = "START"
FLAG_RUNNING = "RUNNING"
FLAG_STOP = "STOP"
FLAG_DONE = "DONE"
FLAG_IDLE = "IDLE"
FLAG_PAUSED_LIMIT = "PAUSED_LIMIT"

MAX_MESSAGES_PER_DAY = 25
MIN_DELAY_SECONDS = 30
MAX_DELAY_SECONDS = 90

# Ліцензія: константи для перевірки
EXPECTED_LICENSE_CODE = "aL8urf1WwxvL9E5hpGdrDWPzgdNky2sm"
LICENSE_CHECK_URL = "https://check-mu-tan.vercel.app/"
LICENSE_CHECK_INTERVAL = 60  # seconds

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("userbot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

client = TelegramClient('userbotsessio1n', api_id, api_hash)  # userbot_111sessio1n - marina


class AppState:
    def __init__(self):
        self.bot_mailing_command_received = False
        self.sending_active = False
        self.target_type = None
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
        logger.info("Флаги стану програми скинуті для завершення роботи.")


logger.info(f"Рабочая директория: {BASE_DIR}")
logger.info(f"Файл с Usernames: {USERNAMES_FILE}")
logger.info(f"Файл данных сообщения: {MESSAGE_DATA_FILE}")
logger.info(f"Файл общей статистики: {STATS_FILE}")
logger.info(f"Файл дневной статистики: {DAILY_STATS_FILE}")
logger.info(f"Файл-флаг: {FLAG_FILE}")
logger.info(f"Файл чатов: {CHATS_FILE}")


async def process_chats():
	# Replaced with a working implementation (mirrors the stable variant)
	if not os.path.exists(CHATS_FILE):
		logger.error(f"Файл {CHATS_FILE} не найден")
		return 0, 0, 0
	usernames = set()
	phones = set()
	processed_chats = 0
	try:
		with open(CHATS_FILE, "r", encoding="utf-8") as f:
			chat_links = [line.strip() for line in f if line.strip()]
	except Exception as e:
		logger.error(f"Ошибка при чтении файла {CHATS_FILE}: {e}")
		return 0, 0, 0
	if not chat_links:
		logger.warning(f"Файл {CHATS_FILE} пустой или не содержит ссылок")
		return 0, 0, 0
	logger.info(f"Найдено {len(chat_links)} ссылок для обработки")
	for i, link in enumerate(chat_links, 1):
		try:
			logger.info(f"[{i}/{len(chat_links)}] Обработка чата: {link}")
			clean_link = link.lstrip('+')
			try:
				entity = await client.get_entity(clean_link)
				processed_chats += 1
				try:
					await client(JoinChannelRequest(entity))
				except Exception:
					pass
				offset = 0
				limit = 200
				max_iterations = 50
				iteration = 0
				while iteration < max_iterations:
					participants = await client(GetParticipantsRequest(
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
				logger.error(f"Ошибка при обработке чата {link}: {e}")
		except Exception as e:
			logger.error(f"Ошибка при получении информации о чате {link}: {e}")
	# Save usernames
	try:
		with open(USERNAMES_FILE, "w", encoding="utf-8") as f:
			for username in sorted(usernames):
				f.write(f"{username}\n")
		logger.info(f"Сохранено {len(usernames)} юзернеймов в файл {USERNAMES_FILE}")
	except Exception as e:
		logger.error(f"Ошибка при сохранении юзернеймов: {e}")
	# Save phones (local fallback)
	try:
		phones_file = os.path.join(BASE_DIR, "all_phones.txt")
		phone_list = sorted(list(phones))
		if phone_list:
			try:
				parent_dir = os.path.dirname(BASE_DIR)
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
		logger.info(f"Обработано {len(phones)} телефонов")
	except Exception as e:
		logger.error(f"Ошибка при сохранении телефонов: {e}")
	return processed_chats, len(usernames), len(phones)


@client.on(events.NewMessage(from_users=BOT_ID))
async def main_bot_command_handler(event):
    logger.info(f"Отримано повідомлення від бота: {event.text}")
    logger.info(f"ID відправника: {event.sender_id}, очікуваний ID бота: {BOT_ID}")

    if event.sender_id != BOT_ID:
        logger.warning(f"Повідомлення від невідомого відправника: {event.sender_id}")
        return
        
    if "[INFO] Розсилку розпочато по юзернеймах" in event.text:
        logger.info("Бот наказав розпочати розсилку по юзернеймах")
        # Перевірка ліцензії перед запуском
        if not await check_license():
            await event.respond("Ліцензія не підтверджена. Розсилка не розпочата.")
            logger.error("Розсилка не розпочата через невірну ліцензію")
            return
        await event.respond("Розсилку розпочато")
        logger.info("Отримано команду на початок розсилки по юзернеймах")
        if hasattr(client, 'app_state'):
            client.app_state.set_mailing_command_received()
            client.app_state.target_type = "usernames"
            client.app_state.target_file = USERNAMES_FILE
            logger.info(f"Установлен тип рассылки: usernames, файл: {USERNAMES_FILE}")
            logger.info(
                f"Статус app_state: mailing_command_received={client.app_state.is_mailing_command_pending()}, target_type={client.app_state.target_type}, target_file={client.app_state.target_file}")
        else:
            logger.error("app_state не инициализирован")
        write_flag(FLAG_START)
        logger.info("Установлен флаг START для юзернеймов")
    elif "[INFO] Розсилку розпочато" in event.text and "юзернеймах" not in event.text:
        logger.info("Бот наказав розпочати розсилку по номерах телефонів")
        # Перевірка ліцензії перед запуском
        if not await check_license():
            await event.respond("Ліцензія не підтверджена. Розсилка не розпочата.")
            logger.error("Розсилка не розпочата через невірну ліцензію")
            return
        await event.respond("Розсилку розпочато")
        logger.info("Отримано команду на початок розсилки по номерах")
        if hasattr(client, 'app_state'):
            client.app_state.set_mailing_command_received()
            client.app_state.target_type = "phones"
            client.app_state.target_file = "all_phones.txt"
            logger.info(f"Установлен тип рассылки: phones, файл: all_phones.txt")
        else:
            logger.error("app_state не инициализирован")
        write_flag(FLAG_START)
        logger.info("Установлен флаг START для номеров")
    elif "[INFO] Розсилку буде зупинено" in event.text:
        logger.info("Отримано команду на зупинку розсилки")
        write_flag(FLAG_STOP)
        if hasattr(client, 'app_state'):
            client.app_state.sending_active = False
            client.app_state.consume_mailing_command()
            logger.info("Скинуто прапори розсилки")
        await event.respond("Розсилку зупинено")
    elif "[INFO] Збір розпочато" in event.text:
        logger.info("Отримано команду на початок збору юзернеймів")
        try:
            # Запускаємо збір безпосередньо тут
            processed_chats, usernames_count, phones_count = await process_chats()
            await event.respond(f"Збір завершено. Оброблено чатів: {processed_chats}, зібрано юзернеймів: {usernames_count}, номерів телефонів: {phones_count}")
        except Exception as e:
            logger.error(f"Помилка при зборі даних: {e}")
            await event.respond(f"Помилка при зборі: {e}")
    elif "[INFO] Сбор начат" in event.text:
        logger.info("Получена команда на начало сбора юзернеймов")
        try:
            # Запускаем сбор непосредственно здесь
            processed_chats, usernames_count, phones_count = await process_chats()
            await event.respond(f"Сбор завершен. Обработано чатов: {processed_chats}, собрано юзернеймов: {usernames_count}, номеров телефонов: {phones_count}")
        except Exception as e:
            logger.error(f"Ошибка при сборе данных: {e}")
            await event.respond(f"Ошибка при сборе: {e}")
    elif "[INFO] Добавить чати" in event.text:
        logger.info("Получена команда на добавление чатов")
        try:
            # Получаем список чатов из сообщения
            chat_links = event.text.split("\n")[1:]  # Пропускаем первую строку с командой
            chat_links = [link.strip() for link in chat_links if link.strip()]

            if not chat_links:
                await event.respond("Не найдено ссылок на чаты")
                return

            # Проверяем и создаем директорию если нужно
            chat_dir = os.path.dirname(CHATS_FILE)
            if chat_dir and not os.path.exists(chat_dir):
                os.makedirs(chat_dir)
                logger.info(f"Создана директория: {chat_dir}")

            # Перезаписываем файл с чатами
            try:
                with open(CHATS_FILE, "w", encoding="utf-8") as f:
                    for link in chat_links:
                        f.write(f"{link}\n")
                logger.info(f"Файл {CHATS_FILE} успешно перезаписан")
            except Exception as e:
                logger.error(f"Ошибка при перезаписи файла {CHATS_FILE}: {e}")
                await event.respond(f"Ошибка при сохранении чатов: {e}")
                return

            await event.respond(f"Добавлено {len(chat_links)} чатов в файл")
            logger.info(f"Добавлено {len(chat_links)} чатов в файл {CHATS_FILE}")
        except Exception as e:
            logger.error(f"Ошибка при добавлении чатов: {e}")
            await event.respond(f"Ошибка при добавлении чатов: {e}")


async def process_mailing(target_type, filename):
    if not os.path.exists(filename):
        logger.error(f"Файл {filename} не найден")
        await client.send_message(BOT_ID, f"Ошибка: файл {filename} не найден")
        return
    with open(filename, "r", encoding="utf-8") as f:
        targets = [line.strip() for line in f if line.strip()]
    if not targets:
        logger.error(f"Файл {filename} пустой")
        await client.send_message(BOT_ID, f"Ошибка: файл {filename} пустой")
        return
    await client.send_message(BOT_ID, f"Начинается рассылка по {len(targets)} {'юзернеймам' if target_type=='usernames' else 'номерам'}")
    sent_count = 0
    failed_count = 0
    for target in targets:
        # Проверка достижения лимита в 50 сообщений
        if sent_count >= 50:
            logger.info("Достигнут лимит в 50 сообщений. Рассылка завершена.")
            await client.send_message(BOT_ID, "Достигнут лимит в 50 сообщений. Рассылка завершена.")
            break
            
        if read_flag() == FLAG_STOP:
            await client.send_message(BOT_ID, "Рассылка остановлена пользователем")
            return
        try:
            message_data = read_message_data()
            if not message_data:
                await client.send_message(BOT_ID, "Ошибка: не удалось получить данные сообщения")
                return
            msg_type = message_data.get("type")
            content = message_data.get("content")
            caption = message_data.get("caption")
            if target_type == "usernames":
                success, error = await send_message_to_username(client, target, msg_type, content, caption)
            else:
                success, error = await send_message_to_phone(client, target, msg_type, content, caption)
            if success:
                sent_count += 1
            else:
                failed_count += 1
                logger.error(f"Ошибка при отправке к {target}: {error}")
            await asyncio.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
        except Exception as e:
            logger.error(f"Ошибка при отправке к {target}: {e}")
            failed_count += 1
    await client.send_message(BOT_ID, f"Рассылка завершена\nУспешно: {sent_count}\nОшибок: {failed_count}")

def read_flag():
	try:
		if os.path.exists(FLAG_FILE):
			with open(FLAG_FILE, "r", encoding="utf-8") as f:
				return f.read().strip().upper()
		else:
			write_flag(FLAG_IDLE)
			return FLAG_IDLE
	except Exception as e:
		logger.error(f"Ошибка чтения файла-флага {FLAG_FILE}: {e}")
		return FLAG_IDLE

def write_flag(status):
	try:
		with open(FLAG_FILE, "w", encoding="utf-8") as f:
			f.write(status)
		logger.info(f"Статус рассылки изменен на {status}")
		return True
	except Exception as e:
		logger.error(f"Ошибка записи в файл-флаг {FLAG_FILE}: {e}")
		return False

def read_usernames():
	usernames = []
	if not os.path.exists(USERNAMES_FILE):
		logger.warning(f"Файл {USERNAMES_FILE} не найден. Возвращаю пустой список.")
		return usernames
	try:
		with open(USERNAMES_FILE, "r", encoding="utf-8") as f:
			for line in f:
				s = line.strip()
				if s:
					usernames.append(s if s.startswith('@') else f"@{s}")
	except Exception as e:
		logger.error(f"Ошибка чтения файла username {USERNAMES_FILE}: {e}")
	return usernames


def read_message_data():
    message_data = None
    if not os.path.exists(MESSAGE_DATA_FILE):
        logger.warning(f"Файл {MESSAGE_DATA_FILE} не найден. Возвращаю None.")
        return message_data
    try:
        with open(MESSAGE_DATA_FILE, "r", encoding="utf-8") as f:
            message_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON в файле {MESSAGE_DATA_FILE}: {e}")
    except Exception as e:
        logger.error(f"Ошибка чтения файла сообщения {MESSAGE_DATA_FILE}: {e}")
    return message_data


def update_total_stats(sent_count):
    current_count = 0
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content.isdigit():
                    current_count = int(content)
                else:
                    logger.warning(
                        f"Файл статистики {STATS_FILE} содержит некорректное значение: '{content}'. Начинаем с 0.")
        else:
            logger.info(f"Файл статистики {STATS_FILE} не найден, будет создан при первой записи.")
    except Exception as e:
        logger.warning(f"Ошибка чтения файла статистики {STATS_FILE}, начинаем с 0: {e}")

    total_count = current_count + sent_count
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            f.write(str(total_count))
        logger.info(f"Общая статистика обновлена: {sent_count} новых сообщений (всего: {total_count}).")
    except Exception as e:
        logger.error(f"Ошибка записи в файл общей статистики {STATS_FILE}: {e}")


def read_daily_stats():
    today_str = date.today().isoformat()
    if os.path.exists(DAILY_STATS_FILE):
        try:
            with open(DAILY_STATS_FILE, "r", encoding="utf-8") as f:
                stats_data = json.load(f)
            if isinstance(stats_data, dict) and stats_data.get("date") == today_str:
                return stats_data.get("sent_today", 0)
        except json.JSONDecodeError:
            logger.error(
                f"Файл дневной статистики {DAILY_STATS_FILE} поврежден или имеет неверный формат. Сбрасываем счетчик на сегодня.")
        except Exception as e:
            logger.error(
                f"Ошибка чтения файла дневной статистики {DAILY_STATS_FILE}: {e}. Сбрасываем счетчик на сегодня.")
    return 0


def update_daily_stats(sent_this_session_count):
    today_str = date.today().isoformat()
    current_sent_today = 0
    if os.path.exists(DAILY_STATS_FILE):
        try:
            with open(DAILY_STATS_FILE, "r", encoding="utf-8") as f:
                stats = json.load(f)
            if isinstance(stats, dict) and stats.get("date") == today_str:
                current_sent_today = stats.get("sent_today", 0)
            else:
                logger.info(f"Дата в {DAILY_STATS_FILE} ({stats.get('date') if isinstance(stats, dict) else 'N/A'}) "
                            f"не совпадает с сегодняшней ({today_str}) или не является словарем. Сбрасываю дневной счетчик.")
        except json.JSONDecodeError:
            logger.warning(f"Файл {DAILY_STATS_FILE} поврежден. Сбрасываю дневной счетчик.")
        except Exception as e:
            logger.warning(f"Ошибка чтения {DAILY_STATS_FILE} ({e}), сбрасываю дневной счетчик для {today_str}.")
            pass

    new_sent_today = current_sent_today + sent_this_session_count

    try:
        with open(DAILY_STATS_FILE, "w", encoding="utf-8") as f:
            json.dump({"date": today_str, "sent_today": new_sent_today}, f)
        logger.info(f"Дневная статистика обновлена: {sent_this_session_count} новых, всего сегодня: {new_sent_today}")
    except Exception as e:
        logger.error(f"Ошибка записи в файл дневной статистики {DAILY_STATS_FILE}: {e}")


def resolve_media_path(media_path):
    """
    Resolves media path to handle both absolute and relative paths.
    Tries multiple possible locations to find the media file.
    """
    # Check if it's an absolute path that exists
    if os.path.isabs(media_path) and os.path.exists(media_path):
        logger.info(f"Використовую абсолютний шлях до медіа: {media_path}")
        return media_path
    
    # If it's a relative path starting with './media/'
    if media_path.startswith('./media/'):
        file_name = os.path.basename(media_path)
        
        # Try relative to current directory
        local_path = os.path.join(BASE_DIR, 'media', file_name)
        if os.path.exists(local_path):
            logger.info(f"Знайдено медіа в локальній папці: {local_path}")
            return local_path
            
        # Try project root media directory
        project_root = os.path.dirname(BASE_DIR)
        root_media_path = os.path.join(project_root, 'media', file_name)
        if os.path.exists(root_media_path):
            logger.info(f"Знайдено медіа в корневій папці проекту: {root_media_path}")
            return root_media_path
    
    # If path is just a filename, try to find it
    if os.path.basename(media_path) == media_path:
        # Check local media directory
        local_media_path = os.path.join(BASE_DIR, 'media', media_path)
        if os.path.exists(local_media_path):
            logger.info(f"Знайдено медіа за ім'ям файлу в локальній папці: {local_media_path}")
            return local_media_path
            
        # Check project root media directory
        project_root = os.path.dirname(BASE_DIR)
        root_media_path = os.path.join(project_root, 'media', media_path)
        if os.path.exists(root_media_path):
            logger.info(f"Знайдено медіа за ім'ям файлу в корневій папці: {root_media_path}")
            return root_media_path
    
    # If all else fails, log error and return original path
    logger.warning(f"Не вдалося знайти медіафайл: {media_path}")
    return media_path


async def upload_to_imgbb(image_path):
    """Uploads an image to imgbb.com and returns the URL."""
    url = "https://api.imgbb.com/1/upload"
    api_key = "ce979babca80641f52db24b816ea2201"
    
    if not os.path.exists(image_path):
        logger.error(f"Image file not found: {image_path}")
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
                    logger.info(f"Image uploaded to imgbb: {img_url}")
                    return img_url
                else:
                    logger.error(f"Failed to upload to imgbb: HTTP {resp.status}")
                    return None
    except Exception as e:
        logger.error(f"Error uploading to imgbb: {e}")
        return None

async def send_message_to_username(app_client: TelegramClient, username: str, message_type, content, caption=None):
    max_retries = 2
    retry_count = 0

    while retry_count < max_retries:
        try:
            me = await app_client.get_me()
            if me.username and username.lower() == f"@{me.username.lower()}":
                logger.error(f"Обнаружена попытка отправить сообщение себе (Username: {username})")
                return False, "Попытка отправить сообщение себе"

            logger.info(f"Начинаю отправку сообщения пользователю: {username} (попытка {retry_count + 1})")

            actual_content = content
            actual_caption = caption

            if message_type in ["photo", "video", "document"]:
                if actual_content and isinstance(actual_content, str):
                    # Read the message data to check for rel_content field
                    message_data = read_message_data()
                    if message_data and "rel_content" in message_data:
                        rel_content = message_data.get("rel_content")
                        if rel_content:
                            logger.info(f"Знайдено відносний шлях в повідомленні: {rel_content}")
                    
                    # Try to resolve media path using our helper function
                    content_path = resolve_media_path(actual_content)
                    
                    if not os.path.isfile(content_path):
                        # If content_path doesn't exist but we have rel_content, try that
                        if message_data and "rel_content" in message_data:
                            rel_content = message_data.get("rel_content")
                            if rel_content:
                                content_path = resolve_media_path(rel_content)
                    
                    if not os.path.isfile(content_path):
                        # Try with just the filename
                        file_name = os.path.basename(actual_content)
                        content_path = resolve_media_path(file_name)
                    
                    if not os.path.isfile(content_path):
                        logger.error(f"Файл не существует: {content_path}")
                        return False, f"Файл не найден: {content_path}"
                        
                    actual_content = content_path
                    try:
                        file_size = os.path.getsize(content_path)
                        logger.info(f"Абсолютний шлях к медиа контенту: {content_path}, Размер: {file_size} байт")
                    except OSError as e:
                        logger.warning(f"Не удалось получить размер файла {content_path}: {e}")
                else:
                    logger.error(
                        f"Для типа {message_type} контент должен быть путем к файлу, получено: {actual_content}")
                    return False, f"Неверный контент для типа {message_type}"

            await asyncio.sleep(random.uniform(5, 15))

            if message_type == "text":
                await app_client.send_message(username, actual_content)
            elif message_type == "photo":
                # Upload to imgbb and send URL instead of local file
                img_url = await upload_to_imgbb(actual_content)
                if img_url:
                    await app_client.send_file(username, img_url, caption=actual_caption)
                else:
                    logger.error(f"Failed to upload photo for {username}")
                    return False, "Failed to upload photo to imgbb"
            elif message_type == "video":
                await app_client.send_file(username, actual_content, caption=actual_caption)
            elif message_type == "document":
                await app_client.send_file(username, actual_content, caption=actual_caption)
            else:
                logger.error(f"Неизвестный тип сообщения: {message_type}")
                return False, f"Неизвестный тип сообщения: {message_type}"

            logger.info(f"{message_type.capitalize()} успешно отправлено пользователю {username}")
            return True, None

        except FloodWaitError as fw:
            wait_time = fw.seconds + random.uniform(10, 30)
            logger.warning(f"FloodWaitError для {username}: необходимо подождать {wait_time:.2f} секунд")
            await asyncio.sleep(wait_time)
            retry_count += 1
            if retry_count >= max_retries:
                return False, f"FloodWaitError после {max_retries} попыток"
            continue
        except errors.RPCError as rpc_e:
            if "Too many requests" in str(rpc_e) or "FLOOD_WAIT" in str(rpc_e):
                wait_time = 120 + random.uniform(30, 60)
                logger.warning(
                    f"Rate limit для {username}: подождем {wait_time:.2f} секунд (попытка {retry_count + 1})")
                await asyncio.sleep(wait_time)
                retry_count += 1
                if retry_count >= max_retries:
                    return False, f"Rate limit после {max_retries} попыток"
                continue
            else:
                logger.error(f"RPC ошибка при отправке {username}: {rpc_e}")
                return False, f"RPC ошибка: {rpc_e}"
        except (UserIsBlockedError, UserDeactivatedError, UserDeactivatedBanError):
            logger.error(f"Пользователь {username} заблокировал бота или аккаунт неактивен/удален.")
            return False, "Пользователь заблокировал бота или аккаунт неактивен"
        except (UsernameOccupiedError, UsernameInvalidError, PeerIdInvalidError):
            logger.error(f"Неправильный или несуществующий username: {username}")
            return False, "Неправильный или несуществующий username"
        except MediaEmptyError:
            logger.error(f"Попытка отправить пустой медиафайл для {username}: {actual_content}")
            return False, "Медиафайл пуст или поврежден"
        except Exception as e:
            error_msg = f"Критическая ошибка в send_message_to_username ({username}): {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            return False, error_msg

    return False, f"Не удалось отправить после {max_retries} попыток"


async def add_contact_by_phone(client, phone_number: str) -> bool:
    """Додає контакт за номером телефону використовуючи правильний API"""
    try:
        # Очищуємо номер від символу +
        clean_phone = phone_number.lstrip('+')
        
        # Генеруємо унікальне ім'я для контакту
        contact_name = f"Contact_{hashlib.md5(phone_number.encode()).hexdigest()[:8]}"
        
        # Створюємо InputPhoneContact
        contact = InputPhoneContact(
            client_id=hash(phone_number) & 0x7FFFFFFF,
            phone=clean_phone,
            first_name=contact_name,
            last_name=""
        )
        
        # Використовуємо ImportContactsRequest
        result = await client(ImportContactsRequest([contact]))
        
        if result.imported:
            logger.info(f"Контакт {phone_number} успішно додано")
            return True
        else:
            logger.warning(f"Не вдалося додати контакт {phone_number}")
            return False
            
    except Exception as e:
        logger.error(f"Помилка при додаванні контакту {phone_number}: {e}")
        return False


async def send_message_to_phone(app_client: TelegramClient, phone: str, message_type, content, caption=None):
    """Відправляє повідомлення на номер телефону з покращеною логікою"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info(f"Спроба відправки повідомлення на номер: {phone} (спроба {retry_count + 1})")

            entity = None
            
            # Спочатку спробуємо знайти користувача безпосередньо
            try:
                entity = await app_client.get_entity(phone)
                logger.info(f"Користувач {phone} знайдений безпосередньо")
            except Exception:
                # Спробуємо додати в контакти
                logger.info(f"Спроба додавання {phone} в контакти")
                contact_added = await add_contact_by_phone(app_client, phone)
                
                if contact_added:
                    await asyncio.sleep(3)
                    try:
                        entity = await app_client.get_entity(phone)
                        logger.info(f"Користувач {phone} знайдений після додавання в контакти")
                    except Exception as e:
                        logger.error(f"Не вдалося знайти користувача {phone} навіть після додавання в контакти: {e}")
                        return False, f"Номер {phone} не знайдений у Telegram"
                else:
                    logger.error(f"Користувач з номером {phone} не знайдений і не вдалося додати в контакти")
                    return False, f"Номер {phone} не знайдений у Telegram або не може бути додан в контакти"

            if entity is None:
                return False, f"Номер {phone} недоступний для відправки"

            actual_content = content
            actual_caption = caption

            if message_type in ["photo", "video", "document"]:
                if actual_content and isinstance(actual_content, str):
                    # Always resolve relative to BASE_DIR if not absolute
                    if not os.path.isabs(actual_content):
                        content_path = os.path.join(BASE_DIR, actual_content)
                    else:
                        content_path = actual_content
                    content_path = os.path.normpath(content_path)
                    if not os.path.isfile(content_path):
                        logger.error(f"Файл не існує: {content_path}")
                        return False, f"Файл не знайдено: {content_path}"
                    actual_content = content_path
                else:
                    logger.error(f"Для типу {message_type} контент повинен бути шляхом до файлу")
                    return False, f"Неправильний контент для типу {message_type}"

            await asyncio.sleep(random.uniform(5, 15))

            if message_type == "text":
                await app_client.send_message(entity, actual_content)
            elif message_type == "photo":
                # Upload to imgbb and send URL instead of local file
                img_url = await upload_to_imgbb(actual_content)
                if img_url:
                    await app_client.send_file(entity, img_url, caption=actual_caption)
                else:
                    logger.error(f"Failed to upload photo for {phone}")
                    return False, "Failed to upload photo to imgbb"
            elif message_type == "video":
                await app_client.send_file(entity, actual_content, caption=actual_caption)
            elif message_type == "document":
                await app_client.send_file(entity, actual_content, caption=actual_caption)
            else:
                logger.error(f"Невідомий тип повідомлення: {message_type}")
                return False, f"Невідомий тип повідомлення: {message_type}"

            logger.info(f"{message_type.capitalize()} успішно відправлено на номер {phone}")
            return True, None

        except FloodWaitError as fw:
            wait_time = fw.seconds + random.uniform(10, 30)
            logger.warning(f"FloodWaitError для {phone}: потрібно почекати {wait_time:.2f} секунд")
            await asyncio.sleep(wait_time)
            retry_count += 1
            if retry_count >= max_retries:
                return False, f"FloodWaitError після {max_retries} спроб"
            continue
        except errors.RPCError as rpc_e:
            if "Too many requests" in str(rpc_e) or "FLOOD_WAIT" in str(rpc_e):
                wait_time = 120 + random.uniform(30, 60)
                logger.warning(f"Rate limit для {phone}: почекаємо {wait_time:.2f} секунд")
                await asyncio.sleep(wait_time)
                retry_count += 1
                if retry_count >= max_retries:
                    return False, f"Rate limit після {max_retries} спроб"
                continue
            else:
                logger.error(f"RPC помилка при відправці {phone}: {rpc_e}")
                return False, f"RPC помилка: {rpc_e}"
        except Exception as e:
            if "Cannot find any entity corresponding to" in str(e) or "Could not find the input entity" in str(e):
                logger.error(f"Користувач з номером {phone} не знайдений у Telegram")
                return False, f"Номер {phone} не зареєстрований у Telegram"
            else:
                logger.error(f"Загальна помилка при відправці на {phone}: {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    return False, f"Помилка: {e}"
                await asyncio.sleep(random.uniform(10, 20))
                continue

    return False, f"Не вдалося відправити після {max_retries} спроб"


async def send_messages_task(app_client: TelegramClient, app_state: AppState):
    logger.info("Задача мониторинга файла-флага і рассилки запущена.")
    while True:
        try:
            flag_status = read_flag()
            # logger.info(f"Поточний статус флага: {flag_status}")

            if flag_status == FLAG_START:
                logger.info("Розпочинаємо нову сесію розсилки")
                if not app_state.sending_active:
                    app_state.sending_active = True
                    write_flag(FLAG_RUNNING)
                    logger.info("Статус розсилки оновлено на RUNNING")
                else:
                    logger.info("Сесія розсилки вже активна, чекаємо завершення...")
                    await asyncio.sleep(10)
                    continue

                try:
                    # Check if we need to process chats again
                    if not os.path.exists(USERNAMES_FILE) or not os.path.exists("all_phones.txt"):
                        logger.info("Файли з юзернеймами або телефонами не знайдені, запускаємо збір нових даних...")
                        write_flag(FLAG_STOP)
                        await asyncio.sleep(5)
                        write_flag(FLAG_START)
                        await asyncio.sleep(5)
                        continue

                    # Main mailing logic
                    if app_state.target_type == "usernames":
                        await process_mailing("usernames", USERNAMES_FILE)
                    elif app_state.target_type == "phones":
                        await process_mailing("phones", "all_phones.txt")
                    else:
                        logger.error(f"Невідомий тип цільової розсилки: {app_state.target_type}")
                        await client.send_message(BOT_ID, f"Невідомий тип цільової розсилки: {app_state.target_type}")
                        write_flag(FLAG_STOP)
                        await asyncio.sleep(5)
                        write_flag(FLAG_START)
                        await asyncio.sleep(5)
                        continue

                    # Update total and daily stats after successful mailing
                    update_total_stats(len(read_usernames()))
                    update_daily_stats(len(read_usernames()))

                    logger.info("Розсилка завершена, оновлюємо статистику")
                    await client.send_message(BOT_ID, "Розсилка завершена, статистику оновлено")
                except Exception as e:
                    logger.error(f"Помилка під час розсилки: {e}")
                    await client.send_message(BOT_ID, f"Помилка під час розсилки: {e}")
                finally:
                    app_state.sending_active = False
                    app_state.consume_mailing_command()
                    write_flag(FLAG_DONE)
                    logger.info("Сесія розсилки завершена")
            elif flag_status == FLAG_STOP:
                logger.info("Розсилку зупинено за запитом")
                app_state.sending_active = False
                app_state.consume_mailing_command()
                write_flag(FLAG_DONE)
                await asyncio.sleep(5)
            else:
                # logger.info(f"Невідомий статус флага: {flag_status}, чекаємо...")
                await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Помилка в задачі моніторингу: {e}")
            await asyncio.sleep(10)


async def check_license():
    """Перевірка ліцензії перед запуском розсилки"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(LICENSE_CHECK_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("license_code") == EXPECTED_LICENSE_CODE:
                        logger.info("Ліцензія підтверджена")
                        return True
                    else:
                        logger.error("Ліцензія невірна")
                        return False
                else:
                    logger.error(f"Помилка перевірки ліцензії: HTTP {resp.status}")
                    return False
    except Exception as e:
        logger.error(f"Помилка при перевірці ліцензії: {e}")
        return False


async def main():
    # Initialize app state
    client.app_state = AppState()

    # Start the client
    async with client:
        logger.info("Клієнт успішно підключено, запускаємо основні задачі...")
        
        # Створити фонову задачу для send_messages_task
        task = asyncio.create_task(send_messages_task(client, client.app_state))
        
        logger.info("Основні задачі запущено, чекаємо повідомлень...")
        # Handle new messages (for commands)
        try:
            await client.run_until_disconnected()
        finally:
            # Скасувати фонову задачу при завершенні
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Критична помилка в основному циклі: {e}")
        traceback.print_exc()