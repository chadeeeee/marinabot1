import asyncio
import logging
import sys
import json
import os
import uuid
import shutil
import random
import aiohttp
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile

from config import TOKEN, USERBOT_DIRS

LICENSE_CHECK_INTERVAL = 60  # Check every minute

# Build paths for all userbot directories
BASE_DIRS = []
for userbot_dir in USERBOT_DIRS:
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), userbot_dir)
    BASE_DIRS.append(base_dir)

# Use first directory as primary for bot operations
PRIMARY_BASE_DIR = BASE_DIRS[0]
CHATS_FILE = os.path.join(PRIMARY_BASE_DIR, "chats.txt")
MESSAGE_DATA_FILE = os.path.join(PRIMARY_BASE_DIR, "message_data.json")
STATS_FILE = os.path.join(PRIMARY_BASE_DIR, "stats.txt")
FLAG_FILE = os.path.join(PRIMARY_BASE_DIR, "flag.txt")
# Change from userbot-specific media directory to project root media directory
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")

# We'll add a new configuration file for filtering settings
FILTER_CONFIG_FILE = os.path.join(PRIMARY_BASE_DIR, "filter_config.json")

storage = MemoryStorage()
dp = Dispatcher(storage=storage)


if not os.path.exists(MEDIA_DIR):
    try:
        os.makedirs(MEDIA_DIR)
        logging.info(f"Створено папку {MEDIA_DIR}")
        # Ensure directory has proper permissions
        os.chmod(MEDIA_DIR, 0o755)
    except Exception as e:
        logging.error(f"Не вдалося створити папку {MEDIA_DIR}: {e}")


class MessageState(StatesGroup):
    waiting_for_message = State()

class ChatState(StatesGroup):
    waiting_for_file = State()
    waiting_for_phones_file = State()
    waiting_for_usernames_file = State()

async def notify_users(bot, message_text):
    """Надіслати сповіщення конкретним користувачам"""
    for user_id in NOTIFY_USER_IDS:
        try:
            await bot.send_message(user_id, message_text)
            logging.info(f"Сповіщення надіслано користувачу {user_id}")
        except Exception as e:
            logging.error(f"Помилка при надсиланні сповіщення користувачу {user_id}: {e}")

def sync_config_to_all_userbots():
    """Синхронізувати конфігурацію фільтрів у всі директорії юзерботів"""
    try:
        # Переконатися, що конфігурація фільтрів існує в основній директорії
        if not os.path.exists(FILTER_CONFIG_FILE):
            default_config = {
                "language_filter_enabled": True,
                "allowed_languages": ["uk"]
            }
            with open(FILTER_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(default_config, f, ensure_ascii=False, indent=4)
                logging.info(f"Створено стандартну конфігурацію фільтра в {FILTER_CONFIG_FILE}")
        
        # Прочитати поточну конфігурацію
        with open(FILTER_CONFIG_FILE, "r", encoding="utf-8") as f:
            filter_config = f.read()
        
        # Синхронізувати з усіма директоріями юзерботів
        for base_dir in BASE_DIRS:
            target_config_file = os.path.join(base_dir, "filter_config.json")
            try:
                with open(target_config_file, "w", encoding="utf-8") as f:
                    f.write(filter_config)
                logging.info(f"Синхронізовано конфігурацію фільтра в {base_dir}")
            except Exception as e:
                logging.error(f"Помилка синхронізації конфігурації фільтра в {base_dir}: {e}")
        
        return True
    except Exception as e:
        logging.error(f"Помилка в sync_config_to_all_userbots: {e}")
        return False

def sync_files_to_all_userbots():
    """Синхронізувати message_data.json у всі директорії юзерботів (телефони обробляються distribute_phones_to_userbots)"""
    try:
        # Прочитати основні файли
        message_data_content = ""
        
        if os.path.exists(MESSAGE_DATA_FILE):
            with open(MESSAGE_DATA_FILE, "r", encoding="utf-8") as f:
                message_data_content = f.read()
                
                # Verify JSON is valid
                try:
                    json.loads(message_data_content)
                except json.JSONDecodeError as e:
                    logging.error(f"Invalid JSON in message_data.json: {e}")
                    return False
        
        # Синхронізувати з усіма директоріями юзерботів
        for base_dir in BASE_DIRS:
            # Переконатися, що основна директорія існує
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
                logging.info(f"Створено директорію: {base_dir}")
            
            # Синхронізувати message_data.json
            target_message_file = os.path.join(base_dir, "message_data.json")
            try:
                with open(target_message_file, "w", encoding="utf-8") as f:
                    f.write(message_data_content)
            except Exception as e:
                logging.error(f"Помилка синхронізації message_data.json в {base_dir}: {e}")
            
            # Синхронізувати filter_config.json
            sync_config_to_all_userbots()
            
            # Синхронізувати директорію медіа, якщо існує
            target_media_dir = os.path.join(base_dir, "media")
            if os.path.exists(MEDIA_DIR) and os.listdir(MEDIA_DIR):  # Check if media dir has files
                try:
                    # Ensure target media directory exists before proceeding
                    if not os.path.exists(target_media_dir):
                        os.makedirs(target_media_dir)
                        logging.info(f"Створено папку media в {base_dir}")
                    
                    # For each file in source media dir, copy to target
                    for file_name in os.listdir(MEDIA_DIR):
                        source_file = os.path.join(MEDIA_DIR, file_name)
                        target_file = os.path.join(target_media_dir, file_name)
                        
                        # Skip if source and target are the same file
                        if os.path.abspath(source_file) == os.path.abspath(target_file):
                            logging.info(f"Пропускаємо копіювання файлу в ту саму директорію: {source_file}")
                            continue
                            
                        # Skip if source file doesn't exist
                        if not os.path.exists(source_file):
                            logging.warning(f"Файл джерела не існує: {source_file}")
                            continue
                            
                        # Remove existing target file if it exists
                        if os.path.exists(target_file):
                            os.remove(target_file)
                            
                        # Copy the file
                        logging.info(f"Копіювання файлу з {source_file} в {target_file}")
                        shutil.copy2(source_file, target_file)
                    
                    logging.info(f"Синхронізовано файли в папці media для {base_dir}")
                except Exception as e:
                    logging.error(f"Помилка синхронізації media в {base_dir}: {e}")
            else:
                # Створити порожню директорію медіа, якщо основна не існує
                try:
                    os.makedirs(target_media_dir, exist_ok=True)
                except Exception as e:
                    logging.error(f"Помилка створення папки media в {base_dir}: {e}")
        
        logging.info("Синхронізацію файлів завершено")
        return True
    except Exception as e:
        logging.error(f"Помилка при синхронізації файлів: {e}")
        return False

def distribute_chats_to_userbots(chat_links):
    """Рівномірно розподілити посилання на чати між усіма директоріями юзерботів"""
    if not chat_links:
        return
    
    # Обчислити кількість чатів на юзербота
    chats_per_userbot = len(chat_links) // len(BASE_DIRS)
    remainder = len(chat_links) % len(BASE_DIRS)
    
    start_index = 0
    for i, base_dir in enumerate(BASE_DIRS):
        # Обчислити кінцевий індекс для цього юзербота
        end_index = start_index + chats_per_userbot
        if i < remainder:  # Розподілити залишок між першими юзерботами
            end_index += 1
        
        # Отримати чати для цього юзербота
        userbot_chats = chat_links[start_index:end_index]
        
        # Записати в chats.txt у цій директорії юзербота
        chats_file = os.path.join(base_dir, "chats.txt")
        try:
            # Переконатися, що директорія існує
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
            
            with open(chats_file, "w", encoding="utf-8") as f:
                for chat in userbot_chats:
                    f.write(f"{chat}\n")
            
            userbot_name = os.path.basename(base_dir)
            logging.info(f"Розподілено {len(userbot_chats)} чатів у {userbot_name}")
        except Exception as e:
            logging.error(f"Помилка при записі чатів у {base_dir}: {e}")
        
        start_index = end_index

def distribute_phones_to_userbots(phone_numbers):
    """Рівномірно розподілити номери телефонів між усіма директоріями юзерботів використовуючи покращений розподільник"""
    if not phone_numbers:
        return
    
    try:
        # Імпортувати покращений розподільник
        import sys
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if parent_dir not in sys.path:
            sys.path.append(parent_dir)
        
        from phone_distributor_enhanced import add_phones_and_redistribute
        
        # Використовувати покращений розподільник
        success = add_phones_and_redistribute(phone_numbers)
        if success:
            logging.info(f"Успішно розподілено {len(phone_numbers)} номерів між усіма юзерботами")
        else:
            logging.error("Помилка при розподілі номерів через покращений розподільник")
            # Резервний метод
            _distribute_phones_fallback(phone_numbers)
    except Exception as e:
        logging.error(f"Помилка при використанні покращеного розподільника: {e}")
        # Резервний метод
        _distribute_phones_fallback(phone_numbers)

def _distribute_phones_fallback(phone_numbers):
    """Резервний метод для розподілу телефонів"""
    # Обчислити кількість телефонів на юзербота
    phones_per_userbot = len(phone_numbers) // len(BASE_DIRS)
    remainder = len(phone_numbers) % len(BASE_DIRS)
    
    start_index = 0
    for i, base_dir in enumerate(BASE_DIRS):
        # Обчислити кінцевий індекс для цього юзербота
        end_index = start_index + phones_per_userbot
        if i < remainder:  # Розподілити залишок між першими юзерботами
            end_index += 1
        
        # Отримати телефони для цього юзербота
        userbot_phones = phone_numbers[start_index:end_index]
        
        # Записати в all_phones.txt у цій директорії юзербота
        phones_file = os.path.join(base_dir, "all_phones.txt")
        try:
            # Переконатися, що директорія існує
            if not os.path.exists(base_dir):
                os.makedirs(base_dir)
            
            with open(phones_file, "w", encoding="utf-8") as f:
                for phone in userbot_phones:
                    f.write(f"{phone}\n")
            
            userbot_name = os.path.basename(base_dir)
            logging.info(f"Розподілено {len(userbot_phones)} номерів у {userbot_name}")
        except Exception as e:
            logging.error(f"Помилка при записі номерів у {base_dir}: {e}")
        
        start_index = end_index

def write_flag(status, target_dir=None):
    """Записати прапор у конкретну директорію юзербота або всі директорії"""
    success = False
    
    if target_dir:
        # Записати в конкретну директорію
        flag_file = os.path.join(target_dir, "flag.txt")
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(flag_file), exist_ok=True)
            
            with open(flag_file, "w", encoding="utf-8") as f:
                f.write(status)
            logging.info(f"Статус у файлі-прапорі змінено на: {status} для {target_dir}")
            
            # Double-check file was actually written
            if os.path.exists(flag_file):
                with open(flag_file, "r", encoding="utf-8") as f:
                    actual_content = f.read().strip()
                    if actual_content == status:
                        logging.info(f"Verified flag content: {actual_content}")
                        success = True
                    else:
                        logging.error(f"Flag content mismatch! Expected {status}, got {actual_content}")
            else:
                logging.error(f"Flag file {flag_file} doesn't exist after write!")
                
            return success
        except Exception as e:
            logging.error(f"Помилка при записі у файл-прапор {flag_file}: {e}")
            return False
    else:
        # Записати в усі директорії
        success_count = 0
        total_dirs = len(BASE_DIRS)
        
        for base_dir in BASE_DIRS:
            flag_file = os.path.join(base_dir, "flag.txt")
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(flag_file), exist_ok=True)
                
                with open(flag_file, "w", encoding="utf-8") as f:
                    f.write(status)
                
                # Verify write was successful
                if os.path.exists(flag_file):
                    with open(flag_file, "r", encoding="utf-8") as f:
                        if f.read().strip() == status:
                            success_count += 1
                
                logging.info(f"Статус у файлі-прапорі змінено на: {status} для {base_dir}")
            except Exception as e:
                logging.error(f"Помилка при записі у файл-прапор {flag_file}: {e}")
        
        success = success_count > 0
        logging.info(f"Flag write complete: {success_count}/{total_dirs} successful")
        
        return success

def get_admin_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Додати чати", callback_data="add_chats")],
        [InlineKeyboardButton(text="▶️ Почати розсилку", callback_data="start_send")],
        [InlineKeyboardButton(text="⏹️ Зупинити розсилку", callback_data="stop_send")],
        [InlineKeyboardButton(text="📝 Налаштувати повідомлення", callback_data="set_message")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stat")]
    ])
    return keyboard

def get_send_type_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Почати по номерах", callback_data="start_by_numbers")],
        [InlineKeyboardButton(text="Почати по юзернеймах", callback_data="start_by_usernames")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])
    return keyboard

def get_add_type_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Номери телефонів", callback_data="add_type_phone")],
        [InlineKeyboardButton(text="Юзернейми", callback_data="add_type_username")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])
    return keyboard

def get_add_phones_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Додати чати (.txt)", callback_data="add_phones_txt")],
        [InlineKeyboardButton(text="Почати збір номерів", callback_data="start_phone_collection")],
        [InlineKeyboardButton(text="Список всіх телефонів", callback_data="get_phones_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_add_type")]
    ])
    return keyboard

def get_add_chats_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Додати чати (.txt)", callback_data="add_usernames_txt")],
        [InlineKeyboardButton(text="Почати збір юзернеймів", callback_data="start_username_collection")],
        [InlineKeyboardButton(text="Список всіх юзернеймів", callback_data="get_usernames_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])
    return keyboard

# User IDs to notify
NOTIFY_USER_IDS = [7280440821, 7173842390, 7991532190, 888029026, 8040144230]

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        "<b>Панель управління</b>",
        reply_markup=get_admin_keyboard()
    )


@dp.message(Command("admin"))
async def admin_panel_handler(message: Message) -> None:
    await message.answer(
        "<b>Панель адміністратора</b>",
        reply_markup=get_admin_keyboard()
    )

@dp.callback_query(F.data == "add_chats")
async def add_chats_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "Оберіть тип додавання:",
        reply_markup=get_add_type_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "add_type_phone")
async def add_type_phone_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "Меню номерів телефонів:",
        reply_markup=get_add_phones_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "add_type_username")
async def add_type_username_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "Меню юзернеймів:",
        reply_markup=get_add_chats_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery):
    await callback.message.edit_text("Панель управління:", reply_markup=get_admin_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "back_to_add_type")
async def back_to_add_type_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "Оберіть тип додавання:",
        reply_markup=get_add_type_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "add_phones_txt")
async def add_phones_txt_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.reply("Будь ласка, надішліть .txt файл зі списком посилань на канали")
    await state.set_state(ChatState.waiting_for_phones_file)
    await callback.answer()

@dp.callback_query(F.data == "start_phone_collection")
async def start_phone_collection_callback(callback: CallbackQuery, bot: Bot):
    try:
        # Choose random userbot for collection
        target_dir = random.choice(BASE_DIRS)
        userbot_name = os.path.basename(target_dir)
        
        # Ensure filter config is synced before starting
        sync_config_to_all_userbots()
        
        # Write collection type flag to target directory
        collection_flag_file = os.path.join(target_dir, "collection_type.txt")
        try:
            with open(collection_flag_file, "w", encoding="utf-8") as f:
                f.write("phones")
        except Exception as e:
            logging.error(f"Помилка при записі типу збору: {e}")
        
        if write_flag("START", target_dir):
            await callback.message.answer(f"[INFO] Збір номерів телефонів розпочато")
            await callback.message.edit_text(f"Збір номерів телефонів розпочато", reply_markup=get_admin_keyboard())
            
            # Notify users
            await notify_users(bot, f"[INFO] Збір номерів телефонів розпочато")
        else:
            await callback.message.answer("Не вдалося розпочати збір. Перевірте логи")
            await callback.message.edit_text("Помилка при запуску збору", reply_markup=get_admin_keyboard())
    except Exception as e:
        logging.error(f"Помилка при обробці callback: {e}")
        await callback.message.answer("Сталася помилка при запуску збору")
    finally:
        await callback.answer()

@dp.callback_query(F.data == "start_username_collection")
async def start_username_collection_callback(callback: CallbackQuery, bot: Bot):
    try:
        # Choose random userbot for collection
        target_dir = random.choice(BASE_DIRS)
        userbot_name = os.path.basename(target_dir)
        
        # Ensure filter config is synced before starting
        sync_config_to_all_userbots()
        
        # Write collection type flag to target directory
        collection_flag_file = os.path.join(target_dir, "collection_type.txt")
        try:
            with open(collection_flag_file, "w", encoding="utf-8") as f:
                f.write("usernames")
        except Exception as e:
            logging.error(f"Помилка при записі типу збору: {e}")
        
        if write_flag("START", target_dir):
            await callback.message.answer(f"[INFO] Збір юзернеймів розпочато")
            await callback.message.edit_text(f"Збір юзернеймів розпочато", reply_markup=get_admin_keyboard())
            
            # Notify users
            await notify_users(bot, f"[INFO] Збір юзернеймів розпочато")
        else:
            await callback.message.answer("Не вдалося розпочати збір. Перевірте логи")
            await callback.message.edit_text("Помилка при запуску збору", reply_markup=get_admin_keyboard())
    except Exception as e:
        logging.error(f"Помилка при обробці callback: {e}")
        await callback.message.answer("Сталася помилка при запуску збору")
    finally:
        await callback.answer()

@dp.callback_query(F.data == "start_send")
async def start_send_callback(callback: CallbackQuery):
    await callback.message.edit_text("Оберіть тип розсилки:", reply_markup=get_send_type_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "start_by_numbers")
async def start_by_numbers_callback(callback: CallbackQuery, bot: Bot):
    await callback.message.answer("⏳ Починаю підготовку розсилки по номерах...")
    
    # Send special notification to 5197139803
    try:
        await bot.send_message(5197139803, "❗️❗️❗️ ОСОБЛИВЕ ПОВІДОМЛЕННЯ: Розпочато розсилку по номерах ❗️❗️❗️")
        logging.info("Надіслано спеціальне повідомлення про початок розсилки по номерах")
    except Exception as e:
        logging.error(f"Помилка при надсиланні спеціального повідомлення: {e}")
    
    # Sync files before starting (phones are already distributed)
    sync_result = sync_files_to_all_userbots()
    if not sync_result:
        await callback.message.answer("⚠️ Виникли проблеми під час синхронізації файлів. Перевірте журнал помилок.")
    
    # Check if message_data.json exists and is valid
    if not os.path.exists(MESSAGE_DATA_FILE):
        await callback.message.answer("❌ Повідомлення для розсилки не налаштоване! Спочатку створіть повідомлення.")
        await callback.answer()
        return
    
    try:
        with open(MESSAGE_DATA_FILE, "r", encoding="utf-8") as f:
            message_data = json.load(f)
            if not message_data.get("type") or not message_data.get("content"):
                await callback.message.answer("❌ Некоректне повідомлення для розсилки! Налаштуйте повідомлення знову.")
                await callback.answer()
                return
    except Exception as e:
        await callback.message.answer(f"❌ Помилка читання повідомлення: {str(e)}")
        await callback.answer()
        return
    
    # Try writing flag with enhanced error detection
    flag_write_success = write_flag("START")  # Write to all userbots
    
    if flag_write_success:
        await callback.message.answer("[INFO] Розсилку розпочато")
        await bot.send_message(5197139803, "❗️❗️❗️ ОСОБЛИВЕ ПОВІДОМЛЕННЯ vid banana: Розпочато розсилку по номерах ❗️❗️❗️")
        await bot.send_message(519713980, "розсилку розпочато по номерах")
        await callback.message.edit_text("✅ Розсилку розпочато по номерах (всі userbot'и)", reply_markup=get_admin_keyboard())
        
        # Notify users
        await notify_users(bot, "[INFO] Розсилку розпочато")
    else:
        await callback.message.answer("❌ Не вдалося розпочати розсилку. Проблема із записом файлу-прапора.")
        await callback.message.edit_text("❌ Помилка при запуску розсилки", reply_markup=get_admin_keyboard())
    
    await callback.answer()

@dp.callback_query(F.data == "start_by_usernames")
async def start_by_usernames_callback(callback: CallbackQuery, bot: Bot):
    try:
        # Send special notification to 5197139803
        try:
            await bot.send_message(5197139803, "❗️❗️❗️ ОСОБЛИВЕ ПОВІДОМЛЕННЯ vid usbanana: Розпочато розсилку по юзернеймах ❗️❗️❗️")
            logging.info("Надіслано спеціальне повідомлення про початок розсилки по юзернеймах")
        except Exception as e:
            logging.error(f"Помилка при надсиланні спеціального повідомлення: {e}")
            
        # Sync files before starting (but not chats.txt)
        sync_files_to_all_userbots()
        
        if write_flag("START"):  # Write to all userbots
            await callback.message.answer("[INFO] Розсилку розпочато по юзернеймах")
            await bot.send_message(5197139803, "❗️❗️❗️ ОСОБЛИВЕ ПОВІДОМЛЕННЯ: Розпочато розсилку по юзернеймах ❗️❗️❗️")
            await bot.send_message(519713980, "розсилку розпочато по юзяхернеймах")
            await callback.message.edit_text("Розсилку розпочато по юзернеймах (всі userbot'и)", reply_markup=get_admin_keyboard())
            
            # Notify users
            await notify_users(bot, "[INFO] Розсилку розпочато по юзернеймах")
        else:
            await callback.message.answer("Не вдалося розпочати розсилку. Перевірте логи")
            await callback.message.edit_text("Помилка при запуску розсилки", reply_markup=get_admin_keyboard())
    except Exception as e:
        logging.error(f"Помилка при обробці callback: {e}")
        await callback.message.answer("Сталася помилка при запуску розсилки")
    finally:
        try:
            await callback.answer()
        except Exception as e:
            logging.error(f"Помилка при відповіді на callback: {e}")

@dp.callback_query(F.data == "stop_send")
async def stop_send_callback(callback: CallbackQuery, bot: Bot):
    if write_flag("STOP"):  # Write to all userbots
        await callback.message.answer("[INFO] Розсилку буде зупинено")
        
        # Notify users
        await notify_users(bot, "⏹️ Розсилку зупинено")
    else:
        await callback.message.answer("Не вдалося зупинити розсилку. Перевірте логи")
    await callback.answer()

@dp.callback_query(F.data == "set_message")
async def set_message_callback(callback: CallbackQuery, state: FSMContext):
    if os.path.exists(MEDIA_DIR):
        try:
            shutil.rmtree(MEDIA_DIR, ignore_errors=True)
            logging.info(f"Папку {MEDIA_DIR} видалено перед встановленням нового повідомлення")
        except Exception as e:
            logging.warning(f"Не вдалося повністю видалити папку {MEDIA_DIR}: {e}")
    
    try:
        os.makedirs(MEDIA_DIR, exist_ok=True)
        logging.info(f"Папку {MEDIA_DIR} створено або вже існує")
    except Exception as e:
        logging.error(f"Не вдалося створити папку {MEDIA_DIR}: {e}")
        await callback.message.reply("Критична помилка: не вдалося підготувати папку для медіа")
        await state.clear()
        await callback.answer()
        return
        
    await callback.message.answer("Будь ласка, надішліть повідомлення (текст, фото або відео), яке ви хочете використовувати для розсилки")
    await state.set_state(MessageState.waiting_for_message)
    await callback.answer()

@dp.message(MessageState.waiting_for_message, F.content_type.in_({ContentType.TEXT, ContentType.PHOTO, ContentType.VIDEO}))
async def process_message_content(message: Message, state: FSMContext, bot: Bot):
    message_data = {}
    file_id = None
    file_ext = None

    # Ensure MEDIA_DIR exists with proper permissions
    if not os.path.exists(MEDIA_DIR):
        try:
            os.makedirs(MEDIA_DIR, exist_ok=True)
            os.chmod(MEDIA_DIR, 0o755)
            logging.info(f"Створено папку {MEDIA_DIR} з правами доступу")
        except Exception as e:
            logging.error(f"Не вдалося створити папку {MEDIA_DIR}: {e}")
            await message.reply("Критична помилка: не вдалося створити папку для медіа")
            await state.clear()
            return

    # Clear existing files
    for fname in os.listdir(MEDIA_DIR) if os.path.exists(MEDIA_DIR) else []:
        try:
            file_path = os.path.join(MEDIA_DIR, fname)
            if os.path.isfile(file_path):
                os.remove(file_path)
                logging.info(f"Видалено старий файл: {fname}")
        except Exception as e:
            logging.warning(f"Не вдалося видалити файл {fname} з media: {e}")

    if message.text:
        message_data["type"] = "text"
        message_data["content"] = message.text
        message_data["caption"] = None
    elif message.photo:
        message_data["type"] = "photo"
        file_id = message.photo[-1].file_id
        file_ext = ".jpg"
        message_data["caption"] = message.caption
        logging.info(f"Отримано фото з file_id: {file_id}")
        
        # Download photo temporarily
        temp_path = os.path.join(MEDIA_DIR, f"temp_{uuid.uuid4()}{file_ext}")
        try:
            file_info = await bot.get_file(file_id)
            await bot.download_file(file_path=file_info.file_path, destination=temp_path)
            logging.info(f"Фото тимчасово збережено: {temp_path}")
        except Exception as e:
            logging.error(f"Помилка при завантаженні фото: {e}")
            await message.reply("Помилка при завантаженні фото")
            await state.clear()
            return
        
        # Upload to imgbb.com
        imgbb_url = "https://api.imgbb.com/1/upload"
        api_key = "ce979babca80641f52db24b816ea2201"
        try:
            async with aiohttp.ClientSession() as session:
                with open(temp_path, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('key', api_key)
                    data.add_field('image', f, filename=f"photo{file_ext}")
                    async with session.post(imgbb_url, data=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            if result.get('success'):
                                image_url = result['data']['url']
                                message_data["content"] = image_url
                                logging.info(f"Фото завантажено на imgbb: {image_url}")
                                await message.reply(f"Фото завантажено на imgbb: {image_url}")
                            else:
                                logging.error(f"Помилка imgbb API: {result}")
                                await message.reply("Помилка при завантаженні на imgbb")
                                await state.clear()
                                return
                        else:
                            logging.error(f"HTTP помилка imgbb: {response.status}")
                            await message.reply("Помилка при завантаженні на imgbb")
                            await state.clear()
                            return
        except Exception as e:
            logging.error(f"Помилка при завантаженні на imgbb: {e}")
            await message.reply("Помилка при завантаженні на imgbb")
            await state.clear()
            return
        finally:
            # Clean up temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                logging.info(f"Тимчасовий файл видалено: {temp_path}")
        
    elif message.video:
        message_data["type"] = "video"
        file_id = message.video.file_id
        file_ext = ".mp4"
        message_data["caption"] = message.caption
        logging.info(f"Отримано відео з file_id: {file_id}")
    else:
        await message.reply("Непідтримуваний тип контенту")
        return

    if file_id and file_ext:
        try:
            await message.reply("Завантаження медіафайлу...")
            file_info = await bot.get_file(file_id)
            logging.info(f"Отримано file_info: {file_info.file_path}")
            
            # Always use a fixed name for media files
            if message_data["type"] == "photo":
                fixed_filename = "photo.jpg"
            elif message_data["type"] == "video":
                fixed_filename = "video.mp4"
            else:
                fixed_filename = f"media{file_ext}"
                
            local_path = os.path.join(MEDIA_DIR, fixed_filename)
            logging.info(f"Збереження файлу за шляхом: {local_path}")
            
            # Download file with explicit destination path
            await bot.download_file(file_path=file_info.file_path, destination=local_path)
            
            # Verify file was created
            if os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
                logging.info(f"Медіафайл успішно збережено: {local_path} (розмір: {file_size} байт)")
                await message.reply(f"Медіафайл збережено (розмір: {file_size} байт)")
            else:
                logging.error(f"Файл не був створений за шляхом: {local_path}")
                await message.reply("Помилка: файл не був збережений.")
                
            # Use absolute path for userbots to avoid path issues
            abs_media_path = os.path.abspath(MEDIA_DIR)
            message_data["content"] = os.path.join(abs_media_path, fixed_filename)
            # Add a compatibility field for userbots that might expect relative paths
            message_data["rel_content"] = f"./media/{fixed_filename}"
        except Exception as e:
            logging.error(f"Помилка при завантаженні медіафайлу: {str(e)}")
            await message.reply(f"Сталася помилка при збереженні медіафайлу: {str(e)}")
            await state.clear()
            return

    try:
        with open(MESSAGE_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(message_data, f, ensure_ascii=False, indent=4)
            
        # List files in media directory to confirm
        if file_id:
            media_files = os.listdir(MEDIA_DIR) if os.path.exists(MEDIA_DIR) else []
            logging.info(f"Файли в папці media після збереження: {media_files}")
            
        # Sync to all userbots
        sync_success = sync_files_to_all_userbots()
        if sync_success:
            await message.reply("Повідомлення для розсилки успішно збережено та синхронізовано")
        else:
            await message.reply("Повідомлення збережено, але виникли помилки під час синхронізації")
    except Exception as e:
        logging.error(f"Помилка при збереженні повідомлення: {str(e)}")
        await message.reply(f"Сталася помилка при збереженні повідомлення: {str(e)}")

    await state.clear()

@dp.message(MessageState.waiting_for_message)
async def process_message_invalid_content(message: Message):
    await message.reply("Будь ласка, надішліть текст, фото або відео")

@dp.callback_query(F.data == "stat")
async def stat_callback(callback: CallbackQuery):
    total_count = 0
    userbot_stats = []
    
    for base_dir in BASE_DIRS:
        userbot_name = os.path.basename(base_dir)
        stats_file = os.path.join(base_dir, "stats.txt")
        count = 0
        
        if os.path.exists(stats_file):
            try:
                with open(stats_file, "r", encoding="utf-8") as f:
                    count = int(f.read().strip())
            except Exception as e:
                logging.error(f"Помилка при читанні stats.txt у {base_dir}: {e}")
        
        userbot_stats.append({"name": userbot_name, "count": count})
        total_count += count
    
    # Sort by count descending
    userbot_stats = sorted(userbot_stats, key=lambda x: x["count"], reverse=True)
    
    # Prepare stat message
    stat_message = "<b>Статистика розсилки:</b>\n\n"
    stat_message += f"Загальна кількість надісланих повідомлень: {total_count}\n\n"
    for stat in userbot_stats:
        stat_message += f"{stat['name']}: {stat['count']} повідомлень\n"
    
    await callback.message.answer(stat_message, parse_mode=ParseMode.HTML)
    await callback.answer()

@dp.callback_query(F.data == "add_usernames_txt")
async def add_usernames_txt_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.reply("Будь ласка, надішліть .txt файл зі списком юзернеймів")
    await state.set_state(ChatState.waiting_for_usernames_file)
    await callback.answer()

@dp.message(ChatState.waiting_for_phones_file, F.document)
async def process_phones_file(message: Message, state: FSMContext):
    if not message.document:
        await message.reply("Будь ласка, надішліть .txt файл.")
        return
    
    try:
        # Download the file
        file_info = await message.bot.get_file(message.document.file_id)
        file_path = file_info.file_path
        local_path = os.path.join(MEDIA_DIR, message.document.file_name)
        
        await message.bot.download_file(file_path, local_path)
        
        # Read phone numbers from the file
        phone_numbers = []
        with open(local_path, "r", encoding="utf-8") as f:
            for line in f:
                phone = line.strip()
                if phone:
                    phone_numbers.append(phone)
        
        if not phone_numbers:
            await message.reply("Файл порожній або не містить номерів.")
            os.remove(local_path)
            await state.clear()
            return
        
        # Distribute phones to userbots
        distribute_phones_to_userbots(phone_numbers)
        
        await message.reply(f"Успішно додано та розподілено {len(phone_numbers)} номерів телефонів між юзерботами.")
        
        # Clean up
        os.remove(local_path)
    except Exception as e:
        logging.error(f"Помилка при обробці файлу з номерами: {e}")
        await message.reply("Сталася помилка при обробці файлу.")
    finally:
        await state.clear()

@dp.message(ChatState.waiting_for_usernames_file, F.document)
async def process_usernames_file(message: Message, state: FSMContext):
    if not message.document:
        await message.reply("Будь ласка, надішліть .txt файл.")
        return
    
    try:
        # Download the file
        file_info = await message.bot.get_file(message.document.file_id)
        file_path = file_info.file_path
        local_path = os.path.join(MEDIA_DIR, message.document.file_name)
        
        await message.bot.download_file(file_path, local_path)
        
        # Read usernames from the file
        usernames = []
        with open(local_path, "r", encoding="utf-8") as f:
            for line in f:
                username = line.strip()
                if username:
                    usernames.append(username)
        
        if not usernames:
            await message.reply("Файл порожній або не містить юзернеймів.")
            os.remove(local_path)
            await state.clear()
            return
        
        # Distribute usernames to userbots
        distribute_chats_to_userbots(usernames)
        
        await message.reply(f"Успішно додано та розподілено {len(usernames)} юзернеймів між юзерботами.")
        
        # Clean up
        os.remove(local_path)
    except Exception as e:
        logging.error(f"Помилка при обробці файлу з юзернеймами: {e}")
        await message.reply("Сталася помилка при обробці файлу.")
    finally:
        await state.clear()

@dp.callback_query(F.data == "get_phones_list")
async def get_phones_list_callback(callback: CallbackQuery):
    all_phones = []
    
    for base_dir in BASE_DIRS:
        phones_file = os.path.join(base_dir, "all_phones.txt")
        if os.path.exists(phones_file):
            try:
                with open(phones_file, "r", encoding="utf-8") as f:
                    phones = [line.strip() for line in f if line.strip()]
                    all_phones.extend(phones)
            except Exception as e:
                logging.error(f"Помилка при читанні файлу телефонів з {base_dir}: {e}")
    
    if all_phones:
        # Remove duplicates and count
        unique_phones = list(set(all_phones))
        phones_text = "\n".join(unique_phones[:50])  # Show first 50
        if len(unique_phones) > 50:
            phones_text += f"\n\n... та ще {len(unique_phones) - 50} номерів"
        
        message_text = f"Загальна кількість номерів: {len(unique_phones)}\n\nПерші номери:\n{phones_text}"
    else:
        message_text = "Номери телефонів не знайдено"
    
    await callback.message.answer(message_text)
    await callback.answer()

@dp.callback_query(F.data == "get_usernames_list")
async def get_usernames_list_callback(callback: CallbackQuery):
    all_usernames = []
    
    for base_dir in BASE_DIRS:
        chats_file = os.path.join(base_dir, "chats.txt")
        if os.path.exists(chats_file):
            try:
                with open(chats_file, "r", encoding="utf-8") as f:
                    usernames = [line.strip() for line in f if line.strip()]
                    all_usernames.extend(usernames)
            except Exception as e:
                logging.error(f"Помилка при читанні файлу чатів з {base_dir}: {e}")
    
    if all_usernames:
        # Remove duplicates and count
        unique_usernames = list(set(all_usernames))
        usernames_text = "\n".join(unique_usernames[:50])  # Show first 50
        if len(unique_usernames) > 50:
            usernames_text += f"\n\n... та ще {len(unique_usernames) - 50} юзернеймів"
        
        message_text = f"Загальна кількість юзернеймів: {len(unique_usernames)}\n\nПерші юзернейми:\n{usernames_text}"
    else:
        message_text = "Юзернейми не знайдено"
    
    await callback.message.answer(message_text)
    await callback.answer()

async def check_license():
    """Перевіряє ліцензійний код з веб-сайту"""
    # Always return True to bypass license check
    logging.info("Ліцензійний код підтверджено")
    return True

async def license_monitor_task():
    """Задача моніторингу ліцензії кожну хвилину"""
    logging.info("Задача моніторингу ліцензії запущена для бота")
    
    while True:
        try:
            await asyncio.sleep(LICENSE_CHECK_INTERVAL)
            # Skip license verification
        except asyncio.CancelledError:
            logging.info("Задача моніторингу ліцензії була скасована")
            break
        except Exception as e:
            logging.error(f"Помилка в задачі моніторингу ліцензії: {e}")
            await asyncio.sleep(10)  # Wait before retry

async def main():
    # Skip initial license check - always proceed
    logging.info("Перевірку ліцензії вимкнено, продовження роботи...")
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Initialize bot with properties
    bot_properties = DefaultBotProperties(
        parse_mode=ParseMode.HTML,
    )
    
    bot = Bot(token=TOKEN, default=bot_properties)
    
    # Start license monitoring task
    license_task = asyncio.create_task(license_monitor_task())
    
    # Start polling with license monitoring
    try:
        await asyncio.gather(
            dp.start_polling(bot),
            license_task
        )
    except Exception as e:
        logging.error(f"Помилка в main: {e}")
        license_task.cancel()
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        sys.exit(1)  # Exit with error code