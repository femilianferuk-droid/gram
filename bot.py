import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    ChatMember,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
ADMIN_ID = 7973988177  # Замените на свой ID

# Структуры данных в памяти (в продакшене заменить на БД)
users_data: Dict[int, dict] = {}
tasks_data: Dict[str, dict] = {}
ref_codes: Dict[str, int] = {}  # код -> user_id
task_counter = 0

# Инициализация
storage = MemoryStorage()
bot: Optional[Bot] = None
dp = Dispatcher(storage=storage)

# Клавиатуры
def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура меню"""
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🏠 Мой кабинет"))
    builder.add(KeyboardButton(text="💰 Заработать"))
    builder.add(KeyboardButton(text="📢 Создать задание"))
    builder.add(KeyboardButton(text="👥 Рефералы"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def back_button(back_to: str = "main") -> InlineKeyboardMarkup:
    """Кнопка Назад"""
    keyboard = [
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_{back_to}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_cabinet_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура кабинета"""
    keyboard = [
        [InlineKeyboardButton(text="📋 Мои задания", callback_data="my_tasks")],
        [InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_earn_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура заработка"""
    keyboard = [
        [InlineKeyboardButton(text="📢 Подписаться на канал", callback_data="earn_channel")],
        [InlineKeyboardButton(text="👥 Вступить в группу", callback_data="earn_group")],
        [InlineKeyboardButton(text="📰 Смотреть публикации", callback_data="earn_post")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Админ-панель"""
    keyboard = [
        [InlineKeyboardButton(text="💰 Выдать/снять COINS", callback_data="admin_coins")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📋 Логи заданий", callback_data="admin_logs")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# FSM состояния
class CreateTaskStates(StatesGroup):
    """Состояния для создания задания"""
    choosing_type = State()
    providing_link = State()
    providing_reward = State()

class AdminStates(StatesGroup):
    """Состояния для админ-панели"""
    add_coins = State()
    remove_coins = State()
    broadcast = State()

# Вспомогательные функции
def generate_ref_code(user_id: int) -> str:
    """Генерация реферального кода"""
    code = str(uuid.uuid4())[:8]
    ref_codes[code] = user_id
    return code

def get_or_create_user(user_id: int, ref_code: str = None) -> dict:
    """Получить или создать пользователя"""
    if user_id not in users_data:
        users_data[user_id] = {
            "balance": 1000,  # Стартовый бонус
            "ref_code": generate_ref_code(user_id),
            "created_tasks": [],
            "completed_tasks": [],
            "referrals": [],
            "joined_at": datetime.now().isoformat()
        }
        
        # Начисление бонуса рефереру
        if ref_code and ref_code in ref_codes:
            referrer_id = ref_codes[ref_code]
            if referrer_id in users_data:
                users_data[referrer_id]["balance"] += 5000
                users_data[referrer_id]["referrals"].append(user_id)
                logger.info(f"Начислено 5000 COINS рефереру {referrer_id} за приглашение {user_id}")
    
    return users_data[user_id]

def create_task(task_type: str, link: str, reward: int, creator_id: int, chat_id: str = None) -> str:
    """Создание нового задания"""
    global task_counter
    task_counter += 1
    task_id = f"task_{task_counter:03d}"
    
    tasks_data[task_id] = {
        "id": task_id,
        "type": task_type,
        "link": link,
        "chat_id": chat_id,  # ID чата для проверки подписки
        "reward": reward,
        "creator_id": creator_id,
        "completed_by": [],
        "created_at": datetime.now().isoformat(),
        "status": "active"
    }
    
    # Добавляем задание в список созданных пользователем
    if creator_id in users_data:
        users_data[creator_id]["created_tasks"].append(task_id)
    
    return task_id

def get_available_tasks(task_type: str, user_id: int) -> List[dict]:
    """Получить доступные задания для пользователя"""
    available_tasks = []
    
    for task_id, task in tasks_data.items():
        if (task["type"] == task_type and 
            task["status"] == "active" and 
            user_id not in task["completed_by"] and
            task["creator_id"] != user_id):
            available_tasks.append(task)
    
    return available_tasks

def get_task_keyboard(task_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для задания"""
    keyboard = [
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data=f"verify_{task_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_earn")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def extract_chat_id_from_link(link: str, bot: Bot) -> Optional[str]:
    """
    Извлечение ID чата из ссылки
    Возвращает: @username или числовой ID
    """
    try:
        if link.startswith("https://t.me/"):
            # Извлекаем username из ссылки
            username = link.split("https://t.me/")[1].split("/")[0].replace("@", "")
            return f"@{username}"
        elif link.startswith("@"):
            return link
        elif link.isdigit() or (link.startswith("-") and link[1:].isdigit()):
            # Уже числовой ID
            return link
        else:
            # Пробуем получить информацию о чате
            if link.startswith("+"):
                link = link[1:]  # Убираем + для публичных ссылок
            
            try:
                chat = await bot.get_chat(link)
                if chat.username:
                    return f"@{chat.username}"
                else:
                    return str(chat.id)
            except:
                return None
    except Exception as e:
        logger.error(f"Ошибка извлечения chat_id: {e}")
        return None

async def check_user_subscription(user_id: int, chat_identifier: str, bot: Bot) -> bool:
    """
    Проверка подписки пользователя на канал/группу
    chat_identifier: @username или числовой ID
    """
    try:
        # Если это username, пробуем получить chat_id
        if chat_identifier.startswith("@"):
            try:
                chat = await bot.get_chat(chat_identifier)
                chat_id = chat.id
            except Exception as e:
                logger.error(f"Не могу получить чат {chat_identifier}: {e}")
                return False
        else:
            chat_id = int(chat_identifier)
        
        # Проверяем статус пользователя в чате
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        
        # Статусы, которые считаются подпиской
        valid_statuses = [
            "member",  # Обычный участник
            "administrator",  # Администратор
            "creator",  # Создатель
            "restricted"  # Ограниченный (еще может просматривать)
        ]
        
        return member.status in valid_statuses
        
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

# Обработчики команд
@dp.message(CommandStart())
async def cmd_start(message: Message):
    """Обработка команды /start"""
    # Извлекаем реферальный код
    ref_code = None
    if len(message.text.split()) > 1:
        ref_arg = message.text.split()[1]
        if ref_arg.startswith("ref_"):
            ref_code = ref_arg[4:]  # Убираем префикс "ref_"
    
    # Создаем/получаем пользователя
    user = get_or_create_user(message.from_user.id, ref_code)
    
    # Приветственное сообщение
    await message.answer(
        "👋 Добро пожаловать в Pr Monkey!\n\n"
        "🏆 Зарабатывайте COINS, выполняя простые задания\n"
        "📢 Создавайте свои задания для продвижения\n"
        "👥 Приглашайте друзей и получайте бонусы\n\n"
        "Выберите действие в меню ниже:",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    """Админ-панель"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Доступ запрещен")
        return
    
    await message.answer(
        "🛠️ Админ-панель",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "🏠 Мой кабинет")
async def my_cabinet(message: Message):
    """Раздел 'Мой кабинет'"""
    user_id = message.from_user.id
    user = get_or_create_user(user_id)
    
    # Формируем реферальную ссылку
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user['ref_code']}"
    
    await message.answer(
        f"🏠 <b>Мой кабинет</b>\n\n"
        f"💰 Баланс: <code>{user['balance']} COINS</code>\n"
        f"👥 Рефералов: <code>{len(user['referrals'])}</code>\n"
        f"📊 Выполнено заданий: <code>{len(user['completed_tasks'])}</code>\n"
        f"📢 Создано заданий: <code>{len(user['created_tasks'])}</code>\n\n"
        f"🔗 Ваша реферальная ссылка:\n<code>{ref_link}</code>\n\n"
        f"💸 За каждого приглашенного друга вы получаете <b>5000 COINS</b>!",
        reply_markup=get_cabinet_keyboard(),
        parse_mode="HTML"
    )

@dp.message(F.text == "💰 Заработать")
async def earn_menu(message: Message):
    """Раздел 'Заработать'"""
    await message.answer(
        "💰 <b>Заработать COINS</b>\n\n"
        "Выберите тип заданий:",
        reply_markup=get_earn_keyboard(),
        parse_mode="HTML"
    )

@dp.message(F.text == "📢 Создать задание")
async def create_task_start(message: Message, state: FSMContext):
    """Начало создания задания"""
    user_id = message.from_user.id
    user = get_or_create_user(user_id)
    
    if user["balance"] < 1000:
        await message.answer(
            "❌ Недостаточно COINS для создания задания.\n"
            "Минимальная стоимость задания: 1000 COINS",
            reply_markup=get_main_keyboard()
        )
        return
    
    keyboard = [
        [
            InlineKeyboardButton(text="📢 Канал", callback_data="create_channel"),
            InlineKeyboardButton(text="👥 Группа", callback_data="create_group")
        ],
        [
            InlineKeyboardButton(text="📰 Пост", callback_data="create_post")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ]
    
    await message.answer(
        "📢 <b>Создание задания</b>\n\n"
        "1️⃣ Выберите тип задания:\n\n"
        "• 📢 <b>Канал</b> - подписка на канал\n"
        "• 👥 <b>Группа</b> - вступление в группу\n"
        "• 📰 <b>Пост</b> - просмотр и реакция на пост",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await state.set_state(CreateTaskStates.choosing_type)

@dp.message(F.text == "👥 Рефералы")
async def referrals_menu(message: Message):
    """Раздел 'Рефералы'"""
    user_id = message.from_user.id
    user = get_or_create_user(user_id)
    
    # Формируем реферальную ссылку
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user['ref_code']}"
    
    # Статистика рефералов
    ref_count = len(user["referrals"])
    ref_earnings = ref_count * 5000
    
    await message.answer(
        f"👥 <b>Реферальная система</b>\n\n"
        f"🔗 Ваша ссылка:\n<code>{ref_link}</code>\n\n"
        f"📊 Статистика:\n"
        f"• Приглашено друзей: <code>{ref_count}</code>\n"
        f"• Заработано с рефералов: <code>{ref_earnings} COINS</code>\n\n"
        f"🎁 <b>Бонусы:</b>\n"
        f"• За каждого приглашенного: <code>+5000 COINS</code>\n"
        f"• Друг получает: <code>+1000 COINS</code> на старте\n\n"
        f"📢 Делитесь ссылкой с друзьями и зарабатывайте!",
        reply_markup=back_button("main"),
        parse_mode="HTML"
    )

# Callback-обработчики
@dp.callback_query(F.data.startswith("back_"))
async def handle_back(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки Назад"""
    back_to = callback.data.split("_")[1]
    
    if back_to == "main":
        await callback.message.edit_text(
            "Главное меню",
            reply_markup=None
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=get_main_keyboard()
        )
    elif back_to == "earn":
        await callback.message.edit_text(
            "💰 <b>Заработать COINS</b>\n\nВыберите тип заданий:",
            reply_markup=get_earn_keyboard(),
            parse_mode="HTML"
        )
    elif back_to == "cabinet":
        await callback.message.edit_text(
            "🏠 <b>Мой кабинет</b>",
            reply_markup=get_cabinet_keyboard(),
            parse_mode="HTML"
        )
    
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data.startswith("earn_"))
async def handle_earn_type(callback: CallbackQuery):
    """Выбор типа заработка"""
    earn_type = callback.data.split("_")[1]
    type_names = {
        "channel": "📢 Подписаться на канал",
        "group": "👥 Вступить в группу",
        "post": "📰 Смотреть публикации"
    }
    
    user_id = callback.from_user.id
    available_tasks = get_available_tasks(earn_type, user_id)
    
    if not available_tasks:
        await callback.message.edit_text(
            f"{type_names[earn_type]}\n\n"
            "😔 На данный момент нет доступных заданий.\n"
            "Попробуйте позже или выберите другой тип заданий.",
            reply_markup=back_button("earn")
        )
        return
    
    # Показываем первое задание
    task = available_tasks[0]
    task_desc = {
        "channel": f"📢 <b>Канал:</b> {task.get('description', 'Без описания')}",
        "group": f"👥 <b>Группа:</b> {task.get('description', 'Без описания')}",
        "post": f"📰 <b>Пост:</b> {task.get('description', 'Просмотреть публикацию')}"
    }
    
    await callback.message.edit_text(
        f"{type_names[earn_type]}\n\n"
        f"{task_desc[earn_type]}\n"
        f"🔗 Ссылка: {task['link']}\n"
        f"💰 Награда: <code>{task['reward']} COINS</code>\n\n"
        f"1. Перейдите по ссылке выше\n"
        f"2. Подпишитесь/вступите\n"
        f"3. Нажмите кнопку проверки:",
        reply_markup=get_task_keyboard(task['id']),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("verify_"))
async def handle_verify(callback: CallbackQuery):
    """Проверка выполнения задания"""
    task_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    if task_id not in tasks_data:
        await callback.answer("❌ Задание не найдено")
        return
    
    task = tasks_data[task_id]
    
    # Проверяем, не выполнял ли уже пользователь это задание
    if user_id in task["completed_by"]:
        await callback.answer("⚠️ Вы уже выполняли это задание")
        return
    
    # Проверяем, не является ли пользователь создателем
    if user_id == task["creator_id"]:
        await callback.answer("⚠️ Вы не можете выполнять свои задания")
        return
    
    # Проверяем наличие chat_id для проверки
    if task["type"] in ["channel", "group"] and not task.get("chat_id"):
        await callback.answer("❌ Ошибка задания: нет данных для проверки")
        return
    
    # Реальная проверка подписки
    if task["type"] in ["channel", "group"]:
        await callback.message.edit_text(
            "🔍 <b>Проверяю вашу подписку...</b>",
            parse_mode="HTML"
        )
        
        # Проверяем подписку пользователя
        is_subscribed = await check_user_subscription(
            user_id=user_id,
            chat_identifier=task["chat_id"],
            bot=bot
        )
        
        if not is_subscribed:
            await callback.message.edit_text(
                "❌ <b>Подписка не найдена!</b>\n\n"
                "Вы не подписаны на указанный канал/группу.\n\n"
                "Пожалуйста:\n"
                "1. Убедитесь, что перешли по ссылке\n"
                "2. Подпишитесь/вступите\n"
                "3. Нажмите проверку снова",
                reply_markup=get_task_keyboard(task_id),
                parse_mode="HTML"
            )
            await callback.answer("Вы не подписаны")
            return
        
        # Награда за успешную подписку
        await process_task_completion(callback, task, user_id)
        
    elif task["type"] == "post":
        # Для поста - пауза 10 секунд
        await callback.message.edit_text(
            "⏳ <b>Проверка выполнения...</b>\n\n"
            "Ожидайте 10 секунд для начисления награды.",
            parse_mode="HTML"
        )
        
        await asyncio.sleep(10)
        
        await process_task_completion(callback, task, user_id)

async def process_task_completion(callback: CallbackQuery, task: dict, user_id: int):
    """Обработка успешного выполнения задания"""
    # Начисляем награду
    user = get_or_create_user(user_id)
    user["balance"] += task["reward"]
    user["completed_tasks"].append(task["id"])
    
    # Списываем с создателя
    if task["creator_id"] in users_data:
        creator = users_data[task["creator_id"]]
        creator["balance"] -= task["reward"]
    
    # Добавляем пользователя в список выполнивших
    task["completed_by"].append(user_id)
    
    await callback.message.edit_text(
        "✅ <b>Задание выполнено!</b>\n\n"
        f"💰 Начислено: <code>{task['reward']} COINS</code>\n\n"
        f"🎉 Поздравляем!",
        parse_mode="HTML"
    )
    
    await callback.answer(f"+{task['reward']} COINS")
    
    # Кнопка для возврата
    keyboard = [[InlineKeyboardButton(text="🔙 К выбору заданий", callback_data="back_earn")]]
    await callback.message.answer(
        f"💰 Ваш текущий баланс: <code>{user['balance']} COINS</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("create_"))
async def handle_create_task_type(callback: CallbackQuery, state: FSMContext):
    """Выбор типа создаваемого задания"""
    task_type = callback.data.split("_")[1]
    type_names = {
        "channel": "канал",
        "group": "группу",
        "post": "пост"
    }
    
    await state.update_data(task_type=task_type)
    
    instructions = {
        "channel": "📢 <b>Для задания типа КАНАЛ:</b>\n\n"
                   "1. Бот должен быть администратором в вашем канале\n"
                   "2. Отправьте ссылку на канал в формате:\n"
                   "   • @username\n"
                   "   • https://t.me/username\n"
                   "   • -1001234567890 (ID канала)",
        
        "group": "👥 <b>Для задания типа ГРУППА:</b>\n\n"
                 "1. Бот должен быть администратором в вашей группе\n"
                 "2. Отправьте ссылку на группу в формате:\n"
                 "   • @username\n"
                 "   • https://t.me/username\n"
                 "   • -1001234567890 (ID группы)",
        
        "post": "📰 <b>Для задания типа ПОСТ:</b>\n\n"
                "Просто перешлите пост из любого канала"
    }
    
    await callback.message.edit_text(
        f"📢 <b>Создание задания: {type_names[task_type].upper()}</b>\n\n"
        f"{instructions[task_type]}\n\n"
        "Или нажмите 'Назад' для отмены:",
        reply_markup=back_button("main"),
        parse_mode="HTML"
    )
    
    await state.set_state(CreateTaskStates.providing_link)
    await callback.answer()

@dp.message(CreateTaskStates.providing_link)
async def handle_task_link(message: Message, state: FSMContext):
    """Получение ссылки на задание"""
    data = await state.get_data()
    task_type = data.get("task_type")
    
    if task_type == "post":
        # Для поста проверяем, что это пересланное сообщение
        if not message.forward_from_chat:
            await message.answer(
                "❌ Для задания типа 'пост' необходимо переслать сообщение из канала.\n"
                "Попробуйте еще раз или нажмите 'Назад':",
                reply_markup=back_button("main")
            )
            return
        
        # Для поста сохраняем информацию
        chat_id = message.forward_from_chat.id
        link = f"https://t.me/{message.forward_from_chat.username}/{message.forward_from_message_id}" if message.forward_from_chat.username else f"Пост из канала ID: {chat_id}"
        
        await state.update_data(link=link, chat_id=str(chat_id))
        
    else:
        # Для каналов и групп получаем ссылку
        link = message.text
        
        # Извлекаем chat_id из ссылки
        chat_id = await extract_chat_id_from_link(link, bot)
        
        if not chat_id:
            await message.answer(
                "❌ Не удалось распознать ссылку.\n\n"
                "Пожалуйста, используйте один из форматов:\n"
                "• @username\n"
                "• https://t.me/username\n"
                "• -1001234567890 (ID канала/группы)\n\n"
                "Попробуйте еще раз:",
                reply_markup=back_button("main")
            )
            return
        
        # Проверяем, что бот является администратором
        try:
            # Пробуем получить информацию о членстве бота
            bot_member = await bot.get_chat_member(
                chat_id=chat_id if not chat_id.startswith("@") else chat_id,
                user_id=(await bot.get_me()).id
            )
            
            # Проверяем, что бот администратор
            if bot_member.status not in ["administrator", "creator"]:
                await message.answer(
                    f"❌ Бот не является администратором в {link}\n\n"
                    "Пожалуйста:\n"
                    "1. Добавьте бота как администратора\n"
                    "2. Убедитесь, что бот имеет право просматривать участников\n"
                    "3. Попробуйте снова",
                    reply_markup=back_button("main")
                )
                return
                
        except Exception as e:
            await message.answer(
                f"❌ Ошибка доступа к {link}\n\n"
                "Возможные причины:\n"
                "• Бот не добавлен в канал/группу\n"
                "• Бот не администратор\n"
                "• Ссылка неверна\n\n"
                f"Ошибка: {str(e)[:100]}",
                reply_markup=back_button("main")
            )
            return
        
        await state.update_data(link=link, chat_id=chat_id)
    
    # Получаем текущий баланс пользователя
    user = get_or_create_user(message.from_user.id)
    
    await message.answer(
        f"📝 <b>Укажите награду в COINS</b>\n\n"
        f"Минимум: <code>1000 COINS</code>\n"
        f"Ваш баланс: <code>{user['balance']} COINS</code>\n\n"
        f"Введите сумму награды (только цифры):",
        reply_markup=back_button("main"),
        parse_mode="HTML"
    )
    
    await state.set_state(CreateTaskStates.providing_reward)

@dp.message(CreateTaskStates.providing_reward)
async def handle_task_reward(message: Message, state: FSMContext):
    """Получение суммы награды"""
    try:
        reward = int(message.text)
        user_id = message.from_user.id
        user = get_or_create_user(user_id)
        
        if reward < 1000:
            await message.answer("❌ Минимальная награда: 1000 COINS")
            return
        
        if reward > user["balance"]:
            await message.answer("❌ Недостаточно COINS на балансе")
            return
        
        data = await state.get_data()
        task_type = data.get("task_type")
        link = data.get("link")
        chat_id = data.get("chat_id")
        
        # Создаем задание
        task_id = create_task(task_type, link, reward, user_id, chat_id)
        
        # Списываем COINS с баланса создателя
        user["balance"] -= reward
        
        task_info = {
            "channel": "📢 Задание на подписку на канал",
            "group": "👥 Задание на вступление в группу",
            "post": "📰 Задание на просмотр поста"
        }
        
        await message.answer(
            f"✅ <b>Задание создано!</b>\n\n"
            f"{task_info[task_type]}\n"
            f"ID задания: <code>{task_id}</code>\n"
            f"Ссылка: {link}\n"
            f"Награда: <code>{reward} COINS</code>\n\n"
            f"💰 Списано с баланса: <code>{reward} COINS</code>\n"
            f"💳 Ваш баланс: <code>{user['balance']} COINS</code>\n\n"
            f"Теперь другие пользователи смогут выполнить ваше задание.",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
        
        # Логируем создание задания
        logger.info(f"Создано задание {task_id} пользователем {user_id}, тип: {task_type}")
        
    except ValueError:
        await message.answer("❌ Введите корректное число (только цифры)")
        return
    
    await state.clear()

# Админ-обработчики
@dp.callback_query(F.data == "admin_coins")
async def handle_admin_coins(callback: CallbackQuery):
    """Управление COINS"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен")
        return
    
    keyboard = [
        [
            InlineKeyboardButton(text="💰 Выдать", callback_data="admin_add_coins"),
            InlineKeyboardButton(text="📉 Снять", callback_data="admin_remove_coins")
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_admin")]
    ]
    
    await callback.message.edit_text(
        "💰 <b>Управление COINS</b>\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_add_coins")
async def handle_admin_add_coins(callback: CallbackQuery, state: FSMContext):
    """Выдать COINS"""
    await callback.message.edit_text(
        "💰 <b>Выдать COINS</b>\n\n"
        "Введите данные в формате:\n"
        "<code>user_id количество</code>\n\n"
        "Пример: <code>123456789 5000</code>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.add_coins)
    await callback.answer()

@dp.callback_query(F.data == "admin_remove_coins")
async def handle_admin_remove_coins(callback: CallbackQuery, state: FSMContext):
    """Снять COINS"""
    await callback.message.edit_text(
        "📉 <b>Снять COINS</b>\n\n"
        "Введите данные в формате:\n"
        "<code>user_id количество</code>\n\n"
        "Пример: <code>123456789 5000</code>",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.remove_coins)
    await callback.answer()

@dp.message(AdminStates.add_coins)
async def handle_add_coins_execute(message: Message, state: FSMContext):
    """Обработка выдачи COINS"""
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError
        
        user_id = int(parts[0])
        amount = int(parts[1])
        
        user = get_or_create_user(user_id)
        user["balance"] += amount
        
        await message.answer(
            f"✅ Выдано <code>{amount} COINS</code> пользователю <code>{user_id}</code>\n"
            f"Новый баланс: <code>{user['balance']} COINS</code>",
            parse_mode="HTML"
        )
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"🎉 Администратор выдал вам <code>{amount} COINS</code>\n"
                f"Ваш баланс: <code>{user['balance']} COINS</code>",
                parse_mode="HTML"
            )
        except:
            pass
        
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте: user_id количество")
    
    await state.clear()

@dp.message(AdminStates.remove_coins)
async def handle_remove_coins_execute(message: Message, state: FSMContext):
    """Обработка снятия COINS"""
    try:
        parts = message.text.split()
        if len(parts) != 2:
            raise ValueError
        
        user_id = int(parts[0])
        amount = int(parts[1])
        
        if user_id not in users_data:
            await message.answer("❌ Пользователь не найден")
            return
        
        user = users_data[user_id]
        
        if user["balance"] < amount:
            await message.answer("❌ У пользователя недостаточно COINS")
            return
        
        user["balance"] -= amount
        
        await message.answer(
            f"✅ Снято <code>{amount} COINS</code> у пользователя <code>{user_id}</code>\n"
            f"Новый баланс: <code>{user['balance']} COINS</code>",
            parse_mode="HTML"
        )
        
    except (ValueError, IndexError):
        await message.answer("❌ Неверный формат. Используйте: user_id количество")
    
    await state.clear()

@dp.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: CallbackQuery):
    """Статистика"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен")
        return
    
    total_users = len(users_data)
    total_tasks = len(tasks_data)
    
    # Считаем общий оборот COINS
    total_coins = sum(user["balance"] for user in users_data.values())
    tasks_coins = sum(task["reward"] for task in tasks_data.values())
    
    # Активные задания
    active_tasks = sum(1 for task in tasks_data.values() if task["status"] == "active")
    
    # Выполненные задания
    completed_tasks = sum(len(task["completed_by"]) for task in tasks_data.values())
    
    await callback.message.edit_text(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <code>{total_users}</code>\n"
        f"📋 Всего заданий: <code>{total_tasks}</code>\n"
        f"✅ Активных заданий: <code>{active_tasks}</code>\n"
        f"🎯 Выполнено заданий: <code>{completed_tasks}</code>\n"
        f"💰 Всего COINS в системе: <code>{total_coins}</code>\n"
        f"💸 COINS в заданиях: <code>{tasks_coins}</code>\n\n"
        f"📅 Данные на: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        reply_markup=back_button("admin"),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def handle_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Рассылка"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен")
        return
    
    await callback.message.edit_text(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Введите сообщение для рассылки всем пользователям:\n\n"
        "Поддерживается HTML-разметка.",
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.broadcast)
    await callback.answer()

@dp.message(AdminStates.broadcast)
async def handle_broadcast_execute(message: Message, state: FSMContext):
    """Выполнение рассылки"""
    broadcast_text = message.text or message.caption
    total_users = len(users_data)
    successful = 0
    failed = 0
    
    await message.answer(f"⏳ Начинаю рассылку для {total_users} пользователей...")
    
    for user_id in users_data.keys():
        try:
            await bot.send_message(user_id, broadcast_text, parse_mode="HTML")
            successful += 1
            await asyncio.sleep(0.05)  # Задержка чтобы не превысить лимиты
        except Exception as e:
            logger.error(f"Ошибка рассылки пользователю {user_id}: {e}")
            failed += 1
    
    await message.answer(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📊 Статистика:\n"
        f"• Успешно: <code>{successful}</code>\n"
        f"• Не удалось: <code>{failed}</code>\n"
        f"• Всего: <code>{total_users}</code>",
        parse_mode="HTML"
    )
    
    await state.clear()

@dp.callback_query(F.data == "admin_logs")
async def handle_admin_logs(callback: CallbackQuery):
    """Логи заданий"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен")
        return
    
    # Показываем последние 10 заданий
    recent_tasks = sorted(tasks_data.values(), 
                         key=lambda x: x.get("created_at", ""), 
                         reverse=True)[:10]
    
    if not recent_tasks:
        await callback.message.edit_text(
            "📋 <b>Логи заданий</b>\n\n"
            "Заданий еще не создано.",
            reply_markup=back_button("admin"),
            parse_mode="HTML"
        )
        return
    
    logs_text = "📋 <b>Последние 10 заданий:</b>\n\n"
    
    for task in recent_tasks:
        creator_id = task.get("creator_id", "N/A")
        completed = len(task.get("completed_by", []))
        reward = task.get("reward", 0)
        chat_id = task.get("chat_id", "N/A")
        
        logs_text += (
            f"📌 <b>{task['id']}</b>\n"
            f"Тип: {task['type']}\n"
            f"Создатель: <code>{creator_id}</code>\n"
            f"Награда: <code>{reward} COINS</code>\n"
            f"Chat ID: <code>{chat_id}</code>\n"
            f"Выполнили: <code>{completed}</code> чел.\n"
            f"––––––––––––––––––\n"
        )
    
    await callback.message.edit_text(
        logs_text,
        reply_markup=back_button("admin"),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "my_tasks")
async def handle_my_tasks(callback: CallbackQuery):
    """Мои задания"""
    user_id = callback.from_user.id
    user = get_or_create_user(user_id)
    
    created_tasks = user.get("created_tasks", [])
    
    if not created_tasks:
        await callback.message.edit_text(
            "📋 <b>Мои задания</b>\n\n"
            "Вы еще не создавали задания.\n\n"
            "Чтобы создать задание, нажмите 'Создать задание' в главном меню.",
            reply_markup=back_button("cabinet"),
            parse_mode="HTML"
        )
        return
    
    # Показываем последние 5 заданий
    tasks_info = []
    for task_id in created_tasks[-5:]:  # Последние 5
        if task_id in tasks_data:
            task = tasks_data[task_id]
            completed = len(task.get("completed_by", []))
            total_earned = completed * task["reward"]
            
            tasks_info.append(
                f"📌 <b>{task_id}</b>\n"
                f"Тип: {task['type']}\n"
                f"Награда: <code>{task['reward']} COINS</code>\n"
                f"Выполнили: <code>{completed}</code> чел.\n"
                f"Потрачено: <code>{total_earned}/{task['reward']}</code>\n"
                f"––––––––––––––––––\n"
            )
    
    await callback.message.edit_text(
        f"📋 <b>Мои задания</b>\n\n" + "".join(tasks_info),
        reply_markup=back_button("cabinet"),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "withdraw")
async def handle_withdraw(callback: CallbackQuery):
    """Вывод средств"""
    user_id = callback.from_user.id
    user = get_or_create_user(user_id)
    
    if user["balance"] < 10000:
        await callback.message.edit_text(
            "💸 <b>Вывод средств</b>\n\n"
            "❌ Минимальная сумма для вывода: <code>10,000 COINS</code>\n\n"
            f"💰 Ваш баланс: <code>{user['balance']} COINS</code>\n\n"
            "Продолжайте выполнять задания, чтобы накопить необходимую сумму!",
            reply_markup=back_button("cabinet"),
            parse_mode="HTML"
        )
        return
    
    # В реальном боте здесь была бы форма вывода
    await callback.message.edit_text(
        "💸 <b>Вывод средств</b>\n\n"
        f"💰 Доступно для вывода: <code>{user['balance']} COINS</code>\n\n"
        "📊 Курс обмена: <code>1000 COINS = 1 USD</code>\n"
        f"💵 К получению: <code>{user['balance'] / 1000:.2f} USD</code>\n\n"
        "Для оформления вывода свяжитесь с @admin_support",
        reply_markup=back_button("cabinet"),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "back_admin")
async def handle_back_admin(callback: CallbackQuery):
    """Назад в админ-панель"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен")
        return
    
    await callback.message.edit_text(
        "🛠️ Админ-панель",
        reply_markup=get_admin_keyboard()
    )
    await callback.answer()

# Запуск бота
async def main():
    """Основная функция запуска бота"""
    global bot
    # Указываем токен бота
    bot = Bot(token="YOUR_BOT_TOKEN")  # Замените на ваш токен
    
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
