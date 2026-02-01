import asyncio
import logging
import random
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import aiohttp
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Константы для Crypto Bot
CRYPTO_BOT_TOKEN = "452163:AAGTJBJKe7YvufexfRN78tFhnTdGywQyUMSX"

# Константы для Loiz Merchant
LOLZ_OAUTH_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzUxMiJ9.eyJzdWliOjkyOTY2MTgsImlzcyl6Imx6dClsImlhdC16MTc2OTI3NTQ4OSwianRpljoiOTE4NzUyliwic2NvcGUiOiJiYXNpYyByZWdKIHBvc3QgY29udmVyc2F0ZSBwYXIzW50IGludm9pY2UgyY2hhdGJveCBTYXJzXQiLCJleHAiOjE5MjY5NTU0ODI9.JThMp8zSReWs1VOWxqX6SMai3ybodmWEvxuvZ6Ss_qEkexp2IUiqv6cj1zV6HX5TjbPo0lQeUZfEyqLllq2I3vLzgYOTI3FIQYOMHJVosBIFQSVEc8H8hBARWJ96mexLjNgkBAbxkGW-yF3pr0uSApxk_15m_lxOeZftU_rCN0"
LOLZ_MERCHANT_SECRET = "453db3e7d3df220871a3b34491c38fce6e646277b903b848e18a467e99aed49d"
LOLZ_MERCHANT_ID = "1947"

# URL для callback nocne onlathu B Loiz
LOLZ_SUCCESS_URL = "https://t.me/monkeynumberbot"
SUPPORT_USERNAME = "@MonkeyNumberSupport"
CHANNEL_USERNAME = "@MonkeyNumber"

# Кypc TON
TON_RATE = 120  # 1 TON = 120 P

# Администраторы
ADMIN_IDS = [7973988177]  # Ваш Telegram ID
router = Router()
temp_payments = {}
user_profiles = {}
promo_codes = {}  # {"PROMO10": {"type": "discount", "value": 10, "used_by": [], "max_uses": 100}}
bot_stats = {
    "total_users": 0,
    "total_purchases": 0,
    "total_revenue": 0,
    "start_date": datetime.now()
}

# Словарь для хранения активных заказов
active_orders = {}  # {order_id: {user_id, country, payment_data, status, phone_number, sms_code}}

# Страны для покупки аккаунтов (разные цены)
COUNTRIES = [
    {"code": "US", "name": "США", "price": 150, "currency": "₽"},
    {"code": "RU", "name": "Россия", "price": 100, "currency": "₽"},
    {"code": "KZ", "name": "Казахстан", "price": 120, "currency": "₽"},
    {"code": "UA", "name": "Украина", "price": 110, "currency": "₽"},
    {"code": "BY", "name": "Беларусь", "price": 130, "currency": "₽"},
    {"code": "IN", "name": "Индия", "price": 90, "currency": "₽"},
]

# Страны для аренды аккаунтов (цена за 1 час)
RENT_COUNTRIES = [
    {"code": "US_RENT", "name": "США (аренда)", "price_per_hour": 50, "currency": "₽", "max_hours": 3},
    {"code": "RU_RENT", "name": "Россия (аренда)", "price_per_hour": 30, "currency": "₽", "max_hours": 3},
    {"code": "KZ_RENT", "name": "Казахстан (аренда)", "price_per_hour": 35, "currency": "₽", "max_hours": 3},
    {"code": "UA_RENT", "name": "Украина (аренда)", "price_per_hour": 32, "currency": "₽", "max_hours": 3},
    {"code": "BY_RENT", "name": "Беларусь (аренда)", "price_per_hour": 38, "currency": "₽", "max_hours": 3},
    {"code": "IN_RENT", "name": "Индия (аренда)", "price_per_hour": 25, "currency": "₽", "max_hours": 3},
]

# Словарь для хранения активных аренд
active_rents = {}  # {rent_id: {user_id, country, hours, total_price, payment_data, status, phone_number, start_time, end_time}}

# Состояния FSM
class DonateStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_currency = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_price = State()
    waiting_for_country_price = State()
    waiting_for_phone = State()
    waiting_for_sms = State()
    waiting_for_user_id = State()
    waiting_for_balance_amount = State()
    waiting_for_user_id_for_balance = State()
    waiting_for_promo_type = State()
    waiting_for_promo_value = State()
    waiting_for_promo_uses = State()

class UserStates(StatesGroup):
    waiting_for_promo_code = State()

class RentStates(StatesGroup):
    waiting_for_hours = State()

class CryptoBotAPI:
    """Класс для работы с Crypto Bot API"""

    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://pay.crypt.bot/api"
        self.headers = {
            "Crypto-Pay-API-Token": token,
            "Content-Type": "application/json"
        }

    async def create_invoice(self, asset: str, amount: float, description: str = "", hidden_message: str = "") -> Dict[str, Any]:
        """Создание инвойса"""
        url = f"{self.base_url}/createInvoice"
        data = {
            "asset": asset,
            "amount": str(amount),
            "description": description,
            "hidden_message": hidden_message
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=self.headers) as response:
                result = await response.json()
                if result.get("ok"):
                    return result.get("result")
                else:
                    error_msg = result.get("error", {}).get("name", "Unknown error")
                    raise Exception(f"Crypto Bot API Error: {error_msg}")

    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Получение информации об инвойсе"""
        url = f"{self.base_url}/getInvoice"
        params = {"invoice_ids": invoice_id}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=self.headers) as response:
                result = await response.json()
                if result.get("ok") and result.get("result", {}).get("items"):
                    return result.get("result", {}).get("items")[0]
                else:
                    raise Exception(f"API Error: {result.get('error', {}).get('name', 'Unknown error')}")


class LolzMerchantAPI:
    """Класс для работы с Lolz Merchant API"""

    def __init__(self, oauth_token: str, merchant_secret: str, merchant_id: str):
        self.oauth_token = oauth_token
        self.merchant_secret = merchant_secret
        self.merchant_id = int(merchant_id)
        self.base_url = "https://api.lzt.market"
        self.headers = {
            "Authorization": f"Bearer {oauth_token}",
            "Content-Type": "application/json"
        }

    async def test_connection(self) -> Dict[str, Any]:
        """Проверка подключения к API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/me", headers=self.headers) as response:
                    result = await response.json()
                    logger.info(f"Тест подключения Lolz API: статус {response.status}")
                    return result
        except Exception as e:
            logger.error(f"Ошибка теста подключения: {str(e)}")
            raise Exception(f"Ошибка подключения к Lolz API: {str(e)}")

    async def create_invoice(self, amount: int, user_id: int, username: str, description: str = "") -> Dict[str, Any]:
        """Создание инвойса через Lolz Merchant API"""
        try:
            # Генерируем уникальный payment_id
            timestamp = int(datetime.now().timestamp())
            payment_id = f"monkey_{user_id}_{timestamp}"

            # Подготавливаем данные для запроса
            data = {
                "currency": "rub",
                "amount": float(amount),
                "payment_id": payment_id,
                "comment": description or f"Покупка от @{username}",
                "url_success": LOLZ_SUCCESS_URL,
                "merchant_id": self.merchant_id,
                "lifetime": 3600,  # 1 час
                "is_test": False
            }

            logger.info(f"Отправка запроса на создание инвойса: {data}")

            # Отправляем запрос
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/invoice", json=data, headers=self.headers) as response:
                    response_text = await response.text()
                    logger.info(f"Ответ от Lolz API: статус {response.status}, тело: {response_text}")

                    if response.status == 200:
                        result = json.loads(response_text)
                        if "invoice" in result:
                            invoice_data = result["invoice"]
                            invoice_id = invoice_data.get("invoice_id")
                            invoice_url = invoice_data.get("url", f"https://lzt.market/invoice/{invoice_id}")

                            return {
                                "payment_id": payment_id,
                                "invoice_id": invoice_id,
                                "pay_url": invoice_url,
                                "amount": amount,
                                "currency": "RUB",
                                "invoice_data": invoice_data,
                                "description": description
                            }
                        else:
                            raise Exception(f"API вернул неожиданный ответ: {result}")
                    else:
                        raise Exception(f"HTTP {response.status}: {response_text}")
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}")
            raise Exception(f"Ошибка формата ответа от API")
        except Exception as e:
            logger.error(f"Ошибка создания инвойса: {str(e)}")
            raise Exception(f"Ошибка создания платежа: {str(e)}")

    async def get_invoice_status(self, invoice_id: int) -> Dict[str, Any]:
        """Получение статуса инвойса по его ID"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/me/invoices", headers=self.headers, params={"limit": 50}) as response:
                    if response.status == 200:
                        result = await response.json()
                        if "invoices" in result:
                            for invoice in result["invoices"]:
                                if invoice.get("invoice_id") == invoice_id:
                                    return invoice
                            raise Exception(f"Инвойс с ID {invoice_id} не найден")
                    else:
                        response_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {response_text}")
        except Exception as e:
            logger.error(f"Ошибка получения статуса инвойса: {str(e)}")
            raise Exception(f"Ошибка проверки платежа: {str(e)}")

    async def check_payment_by_external_id(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Проверка платежа по внешнему ID (payment_id)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/me/invoices", headers=self.headers, params={"limit": 100}) as response:
                    if response.status == 200:
                        result = await response.json()
                        if "invoices" in result:
                            for invoice in result["invoices"]:
                                if invoice.get("payment_id") == payment_id:
                                    return invoice
                    else:
                        response_text = await response.text()
                        raise Exception(f"HTTP {response.status}: {response_text}")
            return None
        except Exception as e:
            logger.error(f"Ошибка поиска платежа: {str(e)}")
            return None


# Инициализация API клиентов
crypto_api = CryptoBotAPI(CRYPTO_BOT_TOKEN)
lolz_api = LolzMerchantAPI(LOLZ_OAUTH_TOKEN, LOLZ_MERCHANT_SECRET, LOLZ_MERCHANT_ID)


# =========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===========

def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in ADMIN_IDS


def convert_rub_to_ton(amount_rub: float) -> float:
    """Конвертация рублей в ТОН"""
    return round(amount_rub / TON_RATE, 4)


def convert_ton_to_rub(amount_ton: float) -> float:
    """Конвертация ТОН в рубли"""
    return round(amount_ton * TON_RATE, 2)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Купить аккаунт", callback_data="buy_account"),
            InlineKeyboardButton(text="Арендовать аккаунт", callback_data="rent_account")
        ],
        [
            InlineKeyboardButton(text="Профиль", callback_data="profile"),
            InlineKeyboardButton(text="Донат", callback_data="donate")
        ],
        [
            InlineKeyboardButton(text="О нас", callback_data="about")
        ]
    ])


def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню администратора"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="Рассылка", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton(text="💰 Изменить цены", callback_data="admin_prices"),
            InlineKeyboardButton(text="🌍 Цены по странам", callback_data="admin_country_prices")
        ],
        [
            InlineKeyboardButton(text="👤 Управление балансом", callback_data="admin_balance"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="🎫 Управление промокодами", callback_data="admin_promocodes"),
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")
        ]
    ])


def get_admin_promocodes_keyboard() -> InlineKeyboardMarkup:
    """Меню управления промокодами"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo"),
            InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin_list_promos")
        ],
        [
            InlineKeyboardButton(text="🗑️ Удалить промокод", callback_data="admin_delete_promo"),
            InlineKeyboardButton(text="📊 Статистика промокодов", callback_data="admin_promo_stats")
        ],
        [
            InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_menu")
        ]
    ])


def get_admin_balance_keyboard() -> InlineKeyboardMarkup:
    """Меню управления балансом"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="admin_add_balance"),
            InlineKeyboardButton(text="➖ Списать баланс", callback_data="admin_remove_balance")
        ],
        [
            InlineKeyboardButton(text="👀 Просмотр баланса", callback_data="admin_view_balance"),
            InlineKeyboardButton(text="📋 Список пользователей", callback_data="admin_users_list")
        ],
        [
            InlineKeyboardButton(text="⬅️ В админку", callback_data="admin_menu"),
            InlineKeyboardButton(text="🏠 На главную", callback_data="back_to_main")
        ]
    ])


def get_balance_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура возврата для операций с балансом"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_balance")]
    ])


def get_countries_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    """Клавиатура с выбором страны"""
    buttons = []
    for i in range(0, len(COUNTRIES), 2):
        row = []
        if i < len(COUNTRIES):
            country = COUNTRIES[i]
            row.append(InlineKeyboardButton(
                text=f"{country['name']} - {country['price']}{country['currency']}",
                callback_data=f"country_{country['code']}"
            ))
        if i + 1 < len(COUNTRIES):
            country = COUNTRIES[i + 1]
            row.append(InlineKeyboardButton(
                text=f"{country['name']} - {country['price']}{country['currency']}",
                callback_data=f"country_{country['code']}"
            ))
        buttons.append(row)

    # Добавляем кнопку "Баланс" если у пользователя есть баланс
    if user_id and user_id in user_profiles and user_profiles[user_id].get("balance", 0) > 0:
        user_balance = user_profiles[user_id]["balance"]
        buttons.append([InlineKeyboardButton(
            text=f"💳 Оплатить балансом ({user_balance} ₽)",
            callback_data="pay_with_balance"
        )])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_rent_countries_keyboard(user_id: int = None) -> InlineKeyboardMarkup:
    """Клавиатура с выбором страны для аренды"""
    buttons = []
    for i in range(0, len(RENT_COUNTRIES), 2):
        row = []
        if i < len(RENT_COUNTRIES):
            country = RENT_COUNTRIES[i]
            row.append(InlineKeyboardButton(
                text=f"{country['name']} - {country['price_per_hour']}{country['currency']}/час",
                callback_data=f"rent_country_{country['code']}"
            ))
        if i + 1 < len(RENT_COUNTRIES):
            country = RENT_COUNTRIES[i + 1]
            row.append(InlineKeyboardButton(
                text=f"{country['name']} - {country['price_per_hour']}{country['currency']}/час",
                callback_data=f"rent_country_{country['code']}"
            ))
        buttons.append(row)

    # Добавляем кнопку "Баланс" если у пользователя есть баланс
    if user_id and user_id in user_profiles and user_profiles[user_id].get("balance", 0) > 0:
        user_balance = user_profiles[user_id]["balance"]
        buttons.append([InlineKeyboardButton(
            text=f"💳 Оплатить балансом ({user_balance} ₽)",
            callback_data="rent_pay_with_balance"
        )])

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_method_keyboard(country_code: str, user_id: int = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора способа оплаты для покупки аккаунта"""
    country = next((c for c in COUNTRIES if c["code"] == country_code), COUNTRIES[0])
    buttons = []
    
    # Добавляем кнопку оплаты балансом если есть достаточный баланс
    if user_id and user_id in user_profiles:
        user_balance = user_profiles[user_id].get("balance", 0)
        if user_balance >= country["price"]:
            buttons.append([InlineKeyboardButton(
                text=f"💳 Оплатить балансом ({user_balance} ₽)",
                callback_data=f"pay_balance_{country_code}"
            )])
    
    # Стандартные способы оплаты
    buttons.extend([
        [
            InlineKeyboardButton(text="💎 Crypto Bot", callback_data=f"buy_crypto_{country_code}"),
            InlineKeyboardButton(text="🛒 Lolz Merchant", callback_data=f"buy_lolz_{country_code}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"country_{country_code}")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_rent_payment_method_keyboard(country_code: str, hours: int, total_price: float, user_id: int = None) -> InlineKeyboardMarkup:
    """Клавиатура выбора способа оплаты для аренды аккаунта"""
    country = next((c for c in RENT_COUNTRIES if c["code"] == country_code), RENT_COUNTRIES[0])
    buttons = []
    
    # Добавляем кнопку оплаты балансом если есть достаточный баланс
    if user_id and user_id in user_profiles:
        user_balance = user_profiles[user_id].get("balance", 0)
        if user_balance >= total_price:
            buttons.append([InlineKeyboardButton(
                text=f"💳 Оплатить балансом ({user_balance} ₽)",
                callback_data=f"rent_pay_balance_{country_code}_{hours}"
            )])
    
    # Стандартные способы оплаты
    buttons.extend([
        [
            InlineKeyboardButton(text="💎 Crypto Bot", callback_data=f"rent_buy_crypto_{country_code}_{hours}"),
            InlineKeyboardButton(text="🛒 Lolz Merchant", callback_data=f"rent_buy_lolz_{country_code}_{hours}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rent_country_{country_code}")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_crypto_currency_keyboard(country_code: str) -> InlineKeyboardMarkup:
    """Клавиатура выбора валюты Crypto Bot"""
    country = next((c for c in COUNTRIES if c["code"] == country_code), COUNTRIES[0])
    price_ton = convert_rub_to_ton(country["price"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"💵 USDT", callback_data=f"crypto_usdt_{country_code}"),
            InlineKeyboardButton(text=f"⚡ TON ({price_ton} TON)", callback_data=f"crypto_ton_{country_code}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"country_{country_code}")]
    ])


def get_rent_crypto_currency_keyboard(country_code: str, hours: int, total_price: float) -> InlineKeyboardMarkup:
    """Клавиатура выбора валюты Crypto Bot для аренды"""
    price_ton = convert_rub_to_ton(total_price)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"💵 USDT", callback_data=f"rent_crypto_usdt_{country_code}_{hours}"),
            InlineKeyboardButton(text=f"⚡ TON ({price_ton} TON)", callback_data=f"rent_crypto_ton_{country_code}_{hours}")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rent_country_{country_code}")]
    ])


def get_donate_currency_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора валюты для доната"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 RUB (1-1000 ₽)", callback_data="donate_rub"),
            InlineKeyboardButton(text="🇺🇸 USDT (0.01-1000 USDT)", callback_data="donate_usdt")
        ],
        [
            InlineKeyboardButton(text="⚡ TON (0.01-1000 TON)", callback_data="donate_ton")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])


def get_donate_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура возврата для доната"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="donate")]
    ])


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения рассылки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_broadcast")
        ]
    ])


def get_order_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для заказа"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Получить номер", callback_data=f"get_phone_{order_id}")],
        [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
    ])


def get_rent_order_keyboard(rent_id: str) -> InlineKeyboardMarkup:
    """Клавиатура для аренды"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Получить номер", callback_data=f"get_rent_phone_{rent_id}")],
        [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
    ])


def get_phone_received_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """Клавиатура после получения номера"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Получить SMS-код", callback_data=f"get_sms_{order_id}")],
        [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
    ])


def get_rent_phone_received_keyboard(rent_id: str) -> InlineKeyboardMarkup:
    """Клавиатура после получения номера для аренды"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Получить SMS-код", callback_data=f"get_rent_sms_{rent_id}")],
        [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
    ])


def get_admin_confirm_sms_keyboard(order_id: str, user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения отправки SMS"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправил код", callback_data=f"admin_sms_sent_{order_id}"),
            InlineKeyboardButton(text="📱 Отправить номер", callback_data=f"admin_send_phone_{order_id}")
        ],
        [InlineKeyboardButton(text="👤 Перейти к пользователю", url=f"tg://user?id={user_id}")]
    ])


def get_admin_confirm_rent_sms_keyboard(rent_id: str, user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения отправки SMS для аренды"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправил код", callback_data=f"admin_rent_sms_sent_{rent_id}"),
            InlineKeyboardButton(text="📱 Отправить номер", callback_data=f"admin_send_rent_phone_{rent_id}")
        ],
        [InlineKeyboardButton(text="👤 Перейти к пользователю", url=f"tg://user?id={user_id}")]
    ])


def generate_promo_code(length=8):
    """Генерация промокода"""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choice(chars) for _ in range(length))


# ============= ОСНОВНЫЕ КОМАНДЫ =============

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Главная команда"""
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    # Создаем профиль пользователя если его нет
    if user_id not in user_profiles:
        user_profiles[user_id] = {
            "username": username,
            "joined_date": datetime.now(),
            "total_purchases": 0,
            "total_spent": 0,
            "balance": 0,
            "balance_history": [],
            "purchases": [],
            "rents": [],
            "used_promocodes": [],
            "last_seen": datetime.now(),
            "is_admin": is_admin(user_id)
        }
        bot_stats["total_users"] += 1
    else:
        user_profiles[user_id]["last_seen"] = datetime.now()
    
    welcome_text = (
        "🐵 *Добро пожаловать в Monkey Number!*\n\n"
        "*Мы предлагаем:*\n"
        "• Telegram аккаунты из разных стран\n"
        "• Аренда аккаунтов на время\n"
        "• Быстрые и безопасные платежи\n"
        "• Гарантия качества и анонимности\n"
        "• Моментальная доставка после оплаты\n"
        "• Оплата балансом - пополняйте и оплачивайте быстро!\n\n"
        "*TON курс:* 1 TON = 120 ₽\n\n"
        "*Способы оплаты:*\n"
        "• Баланс - быстро и удобно\n"
        "• Crypto Bot: USDT, TON\n"
        "• Lolz Merchant: Рубли, Гривны, Тенге, Скины Steam, и др.\n\n"
        f"*Поддержка:* {SUPPORT_USERNAME}\n"
        f"*Канал:* {CHANNEL_USERNAME}\n\n"
        "*Выберите действие в меню ниже:*"
    )
    
    keyboard = get_main_menu_keyboard()
    if is_admin(user_id):
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_menu")])
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Помощь"""
    help_text = (
        "❓ *Помощь по боту Monkey Number*\n\n"
        "*Основные команды:*\n"
        "/start - Главное меню\n"
        "/profile - Ваш профиль\n"
        "/buy - Купить аккаунт\n"
        "/rent - Арендовать аккаунт\n"
        "/donate - Поддержать проект\n"
        "/balance - Ваш баланс\n"
        "/help - Помощь\n\n"
        "*Как купить аккаунт:*\n"
        "1. Нажмите *Купить аккаунт*\n"
        "2. Выберите страну\n"
        "3. Выберите способ оплаты:\n"
        "   • Баланс (если есть средства)\n"
        "   • Crypto Bot (USDT/TON)\n"
        "   • Lolz Merchant (Рубли, Гривны, Тенге, Скины Steam, и др.)\n"
        "4. Оплатите счет\n"
        "5. Получите данные аккаунта\n\n"
        "*Как арендовать аккаунт:*\n"
        "1. Нажмите *Арендовать аккаунт*\n"
        "2. Выберите страну\n"
        "3. Выберите количество часов (1-3 часа)\n"
        "4. Выберите способ оплаты\n"
        "5. Оплатите счет\n"
        "6. Получите данные аккаунта на указанное время\n\n"
        "*TON курс:* 1 TON = 120 ₽\n\n"
        f"*Поддержка:* {SUPPORT_USERNAME}\n"
        f"*Канал:* {CHANNEL_USERNAME}\n\n"
        "*Важно:*\n"
        "• Все аккаунты проверены\n"
        "• Гарантия 24 часа\n"
        "• Моментальная доставка"
    )
    
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Баланс пользователя"""
    user_id = message.from_user.id
    if user_id not in user_profiles:
        await message.answer("❌ Ваш профиль не найден. Нажмите /start")
        return
    
    balance = user_profiles[user_id].get("balance", 0)
    balance_history = user_profiles[user_id].get("balance_history", [])
    
    balance_text = (
        f"💰 *Ваш баланс:* {balance} ₽\n\n"
        f"*Балансом можно оплатить покупку или аренду аккаунтов!*\n\n"
    )
    
    if balance_history:
        balance_text += "*История операций:*\n"
        for i, operation in enumerate(balance_history[-10:], 1):
            date = operation["date"].strftime("%d.%m.%Y %H:%M")
            amount = operation["amount"]
            type_text = "Списание" if amount < 0 else "Пополнение"
            reason = operation.get("reason", "")
            balance_text += f"{i}. {type_text}: {abs(amount)} ₽ ({date}) {reason}\n"
    
    balance_text += "\n*Пополнить баланс:* в Админ-панели (только для админа)\n*Купить аккаунт:* /buy\n*Арендовать аккаунт:* /rent"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Купить аккаунт", callback_data="buy_account"),
            InlineKeyboardButton(text="Арендовать аккаунт", callback_data="rent_account")
        ],
        [
            InlineKeyboardButton(text="Донат", callback_data="donate")
        ],
        [InlineKeyboardButton(text="На главную", callback_data="back_to_main")]
    ])
    
    await message.answer(balance_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


# ========== ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ ==========

@router.callback_query(F.data == "back_to_main")
async def handle_back_to_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    user_id = callback.from_user.id
    
    welcome_text = (
        "🐵 *Добро пожаловать в Monkey Number!*\n\n"
        "*Мы предлагаем:*\n"
        "• Telegram аккаунты из разных стран\n"
        "• Аренда аккаунтов на время\n"
        "• Быстрые и безопасные платежи\n"
        "• Гарантия качества и анонимности\n"
        "• Моментальная доставка после оплаты\n"
        "• Оплата балансом - пополняйте и оплачивайте быстро!\n\n"
        "*TON курс:* 1 TON = 120 ₽\n\n"
        "*Способы оплаты:*\n"
        "• Баланс - быстро и удобно\n"
        "• Crypto Bot: USDT, TON\n"
        "• Lolz Merchant: Рубли, Гривны, Тенге, Скины Steam, Qiwi, ЮMoney, Криптовалюта\n\n"
        f"*Поддержка:* {SUPPORT_USERNAME}\n"
        f"*Канал:* {CHANNEL_USERNAME}\n\n"
        "*Выберите действие в меню ниже:*"
    )
    
    keyboard = get_main_menu_keyboard()
    if is_admin(user_id):
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_menu")])
    
    await callback.message.edit_text(welcome_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@router.callback_query(F.data == "buy_account")
async def handle_buy_account(callback: CallbackQuery):
    """Покупка аккаунта"""
    user_id = callback.from_user.id
    await show_countries_selection_callback(callback, user_id)


@router.callback_query(F.data == "rent_account")
async def handle_rent_account(callback: CallbackQuery):
    """Аренда аккаунта"""
    user_id = callback.from_user.id
    await show_rent_countries_selection_callback(callback, user_id)


async def show_countries_selection_callback(callback: CallbackQuery, user_id: int):
    """Показать выбор стран"""
    countries_text = (
        f"🌍 *Выберите страну для покупки аккаунта:*\n\n"
        f"*TON курс:* 1 TON = {TON_RATE} ₽\n\n"
    )
    
    # Показываем баланс пользователя если есть
    if user_id in user_profiles:
        balance = user_profiles[user_id].get("balance", 0)
        if balance > 0:
            countries_text += f"💰 *Ваш баланс:* {balance} ₽\n\n"
    
    countries_text += "*Доступные страны:*\n"
    
    countries_list = "\n".join([f"• {c['name']} - {c['price']} {c['currency']} (~{convert_rub_to_ton(c['price'])} TON)" for c in COUNTRIES])
    
    full_text = f"{countries_text}\n{countries_list}"
    
    await callback.message.edit_text(
        full_text,
        reply_markup=get_countries_keyboard(user_id),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


async def show_rent_countries_selection_callback(callback: CallbackQuery, user_id: int):
    """Показать выбор стран для аренды"""
    countries_text = (
        f"⏰ *Выберите страну для аренды аккаунта:*\n\n"
        f"*Максимальное время аренды:* 3 часа\n"
        f"*TON курс:* 1 TON = {TON_RATE} ₽\n\n"
    )
    
    # Показываем баланс пользователя если есть
    if user_id in user_profiles:
        balance = user_profiles[user_id].get("balance", 0)
        if balance > 0:
            countries_text += f"💰 *Ваш баланс:* {balance} ₽\n\n"
    
    countries_text += "*Доступные страны для аренды:*\n"
    
    countries_list = "\n".join([f"• {c['name']} - {c['price_per_hour']} {c['currency']}/час (макс. {c['max_hours']} часа)" for c in RENT_COUNTRIES])
    
    full_text = f"{countries_text}\n{countries_list}"
    
    await callback.message.edit_text(
        full_text,
        reply_markup=get_rent_countries_keyboard(user_id),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@router.callback_query(F.data == "profile")
async def handle_profile(callback: CallbackQuery):
    """Профиль пользователя"""
    await show_profile(callback.from_user.id, callback=callback)


async def show_profile(user_id: int, message: Message = None, callback: CallbackQuery = None):
    """Показать профиль"""
    if user_id not in user_profiles:
        if message:
            await message.answer("❌ Ваш профиль не найден. Нажмите /start")
        elif callback:
            await callback.answer("❌ Профиль не найден", show_alert=True)
        return
    
    profile = user_profiles[user_id]
    balance = profile.get("balance", 0)
    
    profile_text = (
        f"👤 *Профиль пользователя*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"📛 Имя: @{profile['username']}\n"
        f"💰 Баланс: *{balance} ₽*\n"
        f"📅 Зарегистрирован: {profile['joined_date'].strftime('%d.%m.%Y')}\n\n"
        f"📊 *Статистика покупок:*\n"
        f"• Всего покупок: {profile['total_purchases']}\n"
        f"• Всего потрачено: {profile['total_spent']} ₽\n\n"
        f"⏰ *Статистика аренды:*\n"
        f"• Всего аренд: {len(profile.get('rents', []))}\n\n"
        f"📝 *Последние покупки:*\n"
    )
    
    if profile["purchases"]:
        for i, purchase in enumerate(profile["purchases"][-3:], 1):
            purchase_date = purchase["date"].strftime("%d.%m.%Y %H:%M")
            profile_text += f"{i}. {purchase['country']} - {purchase['amount']} {purchase['currency']} ({purchase_date})\n"
    else:
        profile_text += "Пока нет покупок\n"
    
    profile_text += f"\n*Купить аккаунт:* /buy\n*Арендовать аккаунт:* /rent\n*Баланс:* /balance"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Купить аккаунт", callback_data="buy_account"),
            InlineKeyboardButton(text="Арендовать аккаунт", callback_data="rent_account")
        ],
        [
            InlineKeyboardButton(text="💰 Баланс", callback_data="profile_balance"),
            InlineKeyboardButton(text="🎫 Ввести промокод", callback_data="enter_promocode")
        ],
        [
            InlineKeyboardButton(text="🔄 Обновить", callback_data="profile"),
            InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")
        ]
    ])
    
    if message:
        await message.answer(profile_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    elif callback:
        await callback.message.edit_text(profile_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()


@router.callback_query(F.data == "enter_promocode")
async def handle_enter_promocode(callback: CallbackQuery, state: FSMContext):
    """Ввод промокода"""
    user_id = callback.from_user.id
    
    await callback.message.edit_text(
        "🎫 *Ввод промокода*\n\n"
        "Введите промокод для получения скидки или пополнения баланса:\n\n"
        "Пример: `SUMMER2024` или `MONKEY50`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]
        ])
    )
    await state.set_state(UserStates.waiting_for_promo_code)
    await callback.answer()


@router.message(StateFilter(UserStates.waiting_for_promo_code))
async def handle_promocode_input(message: Message, state: FSMContext):
    """Обработка введенного промокода"""
    user_id = message.from_user.id
    promocode = message.text.strip().upper()
    
    if promocode not in promo_codes:
        await message.answer(
            "❌ *Промокод не найден!*\n\n"
            "Проверьте правильность написания промокода и попробуйте снова.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]
            ])
        )
        return
    
    promo_data = promo_codes[promocode]
    
    # Проверяем использовал ли уже пользователь этот промокод
    if user_id in promo_data["used_by"]:
        await message.answer(
            "❌ *Вы уже использовали этот промокод!*\n\n"
            "Каждый промокод можно использовать только один раз.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]
            ])
        )
        return
    
    # Проверяем максимальное количество использований
    if promo_data["max_uses"] > 0 and promo_data["max_uses"] <= len(promo_data["used_by"]):
        await message.answer(
            "❌ *Промокод больше не действителен!*\n\n"
            "Лимит использований исчерпан.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]
            ])
        )
        return
    
    # Применяем промокод
    if promo_data["type"] == "balance":
        amount = promo_data["value"]
        user_profiles[user_id]["balance"] += amount
        
        # Добавляем в историю баланса
        user_profiles[user_id].setdefault("balance_history", []).append({
            "date": datetime.now(),
            "amount": amount,
            "reason": f"Промокод {promocode}",
            "promocode": promocode
        })
        
        await message.answer(
            f"✅ *Промокод активирован!*\n\n"
            f"🎫 Промокод: `{promocode}`\n"
            f"💰 Сумма: *{amount} ₽*\n"
            f"💳 Новый баланс: *{user_profiles[user_id]['balance']} ₽*\n\n"
            f"Теперь вы можете использовать баланс для покупки или аренды аккаунтов!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Купить аккаунт", callback_data="buy_account")],
                [InlineKeyboardButton(text="Арендовать аккаунт", callback_data="rent_account")],
                [InlineKeyboardButton(text="⬅️ В профиль", callback_data="profile")]
            ])
        )
        
    elif promo_data["type"] == "discount":
        # Сохраняем активный промокод для скидки
        user_profiles[user_id]["active_promocode"] = {
            "code": promocode,
            "discount": promo_data["value"],
            "type": "discount"
        }
        
        await message.answer(
            f"✅ *Промокод активирован!*\n\n"
            f"🎫 Промокод: `{promocode}`\n"
            f"🎁 Скидка: *{promo_data['value']}%*\n\n"
            f"Теперь при покупке или аренде аккаунта вам будет применена скидка!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Купить аккаунт", callback_data="buy_account")],
                [InlineKeyboardButton(text="Арендовать аккаунт", callback_data="rent_account")],
                [InlineKeyboardButton(text="⬅️ В профиль", callback_data="profile")]
            ])
        )
    
    # Добавляем пользователя в список использовавших
    promo_data["used_by"].append(user_id)
    await state.clear()


@router.callback_query(F.data == "profile_balance")
async def handle_profile_balance(callback: CallbackQuery):
    """Баланс из профиля"""
    user_id = callback.from_user.id
    
    if user_id not in user_profiles:
        await callback.answer("❌ Профиль не найден", show_alert=True)
        return
    
    await cmd_balance_short(callback)


async def cmd_balance_short(callback: CallbackQuery):
    """Короткая версия команды баланса"""
    user_id = callback.from_user.id
    balance = user_profiles[user_id].get("balance", 0)
    
    balance_text = (
        f"💰 *Ваш баланс:* {balance} ₽\n\n"
        f"*Балансом можно оплатить покупку или аренду аккаунтов!*\n\n"
        f"*Пополнение баланса:* доступно только через администратора"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Купить аккаунт", callback_data="buy_account"),
            InlineKeyboardButton(text="Арендовать аккаунт", callback_data="rent_account")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]
    ])
    
    await callback.message.edit_text(balance_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


@router.callback_query(F.data == "donate")
async def handle_donate(callback: CallbackQuery):
    """Донат - выбор валюты"""
    donate_text = (
        "❤️ *Поддержать проект Monkey Number*\n\n"
        "*Выберите валюту для доната:*\n\n"
        "🇷🇺 RUB - от 1 до 1000 ₽ (через Lolz Merchant)\n"
        "🇺🇸 USDT - от 0.01 до 1000 USDT (через Crypto Bot)\n"
        "⚡ TON - от 0.01 до 1000 TON (через Crypto Bot)\n\n"
        "*Спасибо за вашу поддержку!*\n"
        f"*Поддержка:* {SUPPORT_USERNAME}"
    )
    
    await callback.message.edit_text(
        donate_text,
        reply_markup=get_donate_currency_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@router.callback_query(F.data == "about")
async def handle_about(callback: CallbackQuery):
    """О нас"""
    about_text = (
        "🐵 *Monkey Number*\n\n"
        "*О нас:*\n"
        "Мы специализируемся на продаже Telegram аккаунтов из разных стран мира. "
        "Все аккаунты проверены и готовы к использованию.\n\n"
        "*Доступные страны:*\n"
        "🇺🇸 США - 🇷🇺 Россия - 🇰🇿 Казахстан\n"
        "🇺🇦 Украина - 🇧🇾 Беларусь - 🇮🇳 Индия\n\n"
        "*Доступные страны для аренды:*\n"
        "🇺🇸 США (аренда) - 🇷🇺 Россия (аренда)\n"
        "🇰🇿 Казахстан (аренда) - 🇺🇦 Украина (аренда)\n"
        "🇧🇾 Беларусь (аренда) - 🇮🇳 Индия (аренда)\n\n"
        "*Способы оплаты:*\n"
        "• Баланс - быстро и удобно\n"
        "• Crypto Bot: USDT, TON\n"
        "• Lolz Merchant: Рубли, Гривны, Тенге, Скины Steam, Qiwi, ЮMoney, Криптовалюта\n\n"
        "*Наши преимущества:*\n"
        "• Гарантия качества и анонимности\n"
        "• Моментальная доставка\n"
        "• Оплата балансом - быстро и удобно\n"
        "• Поддержка 24/7\n\n"
        f"*Поддержка:* {SUPPORT_USERNAME}\n"
        f"*Канал:* {CHANNEL_USERNAME}\n\n"
        "*Спасибо, что выбираете нас!*"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить аккаунт", callback_data="buy_account")],
        [InlineKeyboardButton(text="Арендовать аккаунт", callback_data="rent_account")],
        [InlineKeyboardButton(text="Донат", callback_data="donate")],
        [InlineKeyboardButton(text="На главную", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(about_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    await callback.answer()


# ============== ОПЛАТА БАЛАНСОМ ==============

@router.callback_query(F.data == "pay_with_balance")
async def handle_pay_with_balance(callback: CallbackQuery):
    """Оплата балансом - выбор страны"""
    user_id = callback.from_user.id
    if user_id not in user_profiles:
        await callback.answer("❌ Профиль не найден", show_alert=True)
        return
    
    balance = user_profiles[user_id].get("balance", 0)
    # Проверяем минимальную цену среди всех стран
    min_price = min(country["price"] for country in COUNTRIES)
    
    if balance < min_price:
        await callback.answer(f"❌ Недостаточно средств. Минимальная цена: {min_price} ₽, ваш баланс: {balance} ₽", show_alert=True)
        return
    
    await show_countries_selection_callback(callback, user_id)


@router.callback_query(F.data.startswith("pay_balance_"))
async def handle_pay_balance(callback: CallbackQuery):
    """Оплата конкретного аккаунта балансом"""
    try:
        country_code = callback.data.replace("pay_balance_", "")
        country = next((c for c in COUNTRIES if c["code"] == country_code), COUNTRIES[0])
        user_id = callback.from_user.id
        username = callback.from_user.username or f"user_{user_id}"
        
        if user_id not in user_profiles:
            await callback.answer("❌ Профиль не найден", show_alert=True)
            return
        
        # Проверяем активный промокод
        final_price = country["price"]
        discount = 0
        promocode = None
        
        if "active_promocode" in user_profiles[user_id]:
            promo_data = user_profiles[user_id]["active_promocode"]
            discount = (final_price * promo_data["discount"]) // 100
            final_price -= discount
            promocode = promo_data["code"]
        
        balance = user_profiles[user_id].get("balance", 0)
        
        if balance < final_price:
            await callback.answer(f"❌ Недостаточно средств. Нужно: {final_price} ₽, у вас: {balance} ₽", show_alert=True)
            return
        
        # Создаем заказ
        order_id = f"order_{user_id}_{int(datetime.now().timestamp())}"
        
        # Вычитаем сумму из баланса
        user_profiles[user_id]["balance"] -= final_price
        
        # Добавляем запись в историю баланса
        user_profiles[user_id].setdefault("balance_history", []).append({
            "date": datetime.now(),
            "amount": -final_price,
            "reason": f"Покупка аккаунта {country['name']}",
            "order_id": order_id,
            "promocode": promocode,
            "discount": discount
        })
        
        # Удаляем использованный промокод
        if "active_promocode" in user_profiles[user_id]:
            del user_profiles[user_id]["active_promocode"]
        
        # Обновляем статистику профиля
        user_profiles[user_id]["total_purchases"] += 1
        user_profiles[user_id]["total_spent"] += final_price
        
        # Создаем активный заказ
        active_orders[order_id] = {
            "user_id": user_id,
            "country": country,
            "payment_data": {
                "amount": final_price,
                "currency": "RUB",
                "method": "balance",
                "status": "paid",
                "original_price": country["price"],
                "discount": discount,
                "promocode": promocode
            },
            "status": "waiting_for_phone",
            "created_at": datetime.now(),
            "username": username
        }
        
        # Обновляем общую статистику
        bot_stats["total_purchases"] += 1
        bot_stats["total_revenue"] += final_price
        
        # Создаем уведомление для админа
        for admin_id in ADMIN_IDS:
            try:
                admin_text = (
                    f"🛒 *Новый заказ оплачен балансом!*\n\n"
                    f"👤 *Пользователь:* @{username}\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"🌍 *Страна:* {country['name']}\n"
                )
                
                if discount > 0:
                    admin_text += f"💰 *Цена:* {country['price']} ₽ → *{final_price} ₽*\n"
                    admin_text += f"🎫 *Промокод:* {promocode} (-{discount} ₽)\n"
                else:
                    admin_text += f"💰 *Сумма:* {final_price} ₽\n"
                
                admin_text += f"📋 *ID заказа:* `{order_id}`\n"
                admin_text += f"💳 *Способ оплаты:* Баланс\n\n"
                admin_text += f"*Заказ ожидает выдачи номера*"
                
                await callback.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_admin_confirm_sms_keyboard(order_id, user_id)
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {str(e)}")
        
        # Сообщение пользователю
        success_text = (
            f"✅ *Оплата прошла успешно!*\n\n"
            f"🛒 *Товар:* Telegram аккаунт {country['name']}\n"
        )
        
        if discount > 0:
            success_text += f"💰 *Цена:* {country['price']} ₽ → *{final_price} ₽*\n"
            success_text += f"🎫 *Промокод:* {promocode} (-{discount} ₽)\n"
        else:
            success_text += f"💰 *Сумма:* {final_price} ₽ (списано с баланса)\n"
        
        success_text += f"📋 *ID заказа:* `{order_id}`\n\n"
        success_text += f"⏳ *Ожидайте получения номера...*\n"
        success_text += f"Администратор скоро отправит вам номер телефона."
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Получить номер", callback_data=f"get_phone_{order_id}")],
            [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(success_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer("✅ Оплачено балансом!", show_alert=True)
        
    except Exception as e:
        logger.error(f"Ошибка при оплате балансом: {str(e)}")
        await callback.answer("❌ Ошибка при оплате балансом", show_alert=True)


# ============== АРЕНДА АККАУНТОВ ==============

@router.callback_query(F.data.startswith("rent_country_"))
async def handle_rent_country_selection(callback: CallbackQuery, state: FSMContext):
    """Выбор страны для аренды"""
    country_code = callback.data.replace("rent_country_", "")
    country = next((c for c in RENT_COUNTRIES if c["code"] == country_code), None)
    
    if not country:
        await callback.answer("❌ Страна не найдена", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    # Сохраняем выбранную страну в состоянии
    await state.set_state(RentStates.waiting_for_hours)
    await state.update_data(country_code=country_code, country_name=country['name'], price_per_hour=country['price_per_hour'])
    
    selection_text = (
        f"⏰ *Аренда аккаунта {country['name']}*\n\n"
        f"💰 *Цена:* {country['price_per_hour']} {country['currency']}/час\n"
        f"⏱️ *Максимальное время:* {country['max_hours']} часа\n\n"
        f"Введите количество часов для аренды (от 1 до {country['max_hours']}):\n\n"
        f"Пример: `1` или `2` или `3`"
    )
    
    await callback.message.edit_text(
        selection_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="rent_account")]
        ])
    )
    await callback.answer()


@router.message(StateFilter(RentStates.waiting_for_hours))
async def handle_rent_hours(message: Message, state: FSMContext):
    """Обработка количества часов для аренды"""
    try:
        data = await state.get_data()
        country_code = data.get("country_code")
        country_name = data.get("country_name")
        price_per_hour = data.get("price_per_hour")
        
        country = next((c for c in RENT_COUNTRIES if c["code"] == country_code), None)
        if not country:
            await message.answer("❌ Страна не найдена")
            await state.clear()
            return
        
        hours = int(message.text.strip())
        
        if hours < 1 or hours > country['max_hours']:
            await message.answer(
                f"❌ *Неверное количество часов!*\n\n"
                f"Введите число от 1 до {country['max_hours']}.\n\n"
                f"Пример: `1` или `2` или `3`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rent_country_{country_code}")]
                ])
            )
            return
        
        total_price = price_per_hour * hours
        
        # Проверяем активный промокод
        user_id = message.from_user.id
        final_price = total_price
        discount = 0
        promocode = None
        
        if user_id in user_profiles and "active_promocode" in user_profiles[user_id]:
            promo_data = user_profiles[user_id]["active_promocode"]
            discount = (total_price * promo_data["discount"]) // 100
            final_price = total_price - discount
            promocode = promo_data["code"]
        
        selection_text = (
            f"⏰ *Аренда аккаунта {country_name}*\n\n"
            f"💰 *Цена за час:* {price_per_hour} {country['currency']}\n"
            f"⏱️ *Количество часов:* {hours}\n"
            f"💰 *Общая стоимость:* {total_price} {country['currency']}\n"
        )
        
        if discount > 0:
            selection_text += f"🎫 *Скидка:* {promocode} (-{discount} {country['currency']})\n"
            selection_text += f"💰 *Итоговая цена:* *{final_price} {country['currency']}*\n\n"
        else:
            selection_text += f"\n💰 *Итоговая цена:* *{final_price} {country['currency']}*\n\n"
        
        selection_text += f"*Выберите способ оплаты:*"
        
        keyboard = get_rent_payment_method_keyboard(country_code, hours, final_price, user_id)
        
        await message.answer(selection_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await state.clear()
        
    except ValueError:
        await message.answer(
            "❌ *Неверный формат!*\n\n"
            "Введите число. Например: `1` или `2` или `3`\n\n"
            "Введите правильное количество часов:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rent_country_{country_code}")]
            ])
        )


@router.callback_query(F.data == "rent_pay_with_balance")
async def handle_rent_pay_with_balance(callback: CallbackQuery):
    """Оплата аренды балансом - выбор страны"""
    user_id = callback.from_user.id
    if user_id not in user_profiles:
        await callback.answer("❌ Профиль не найден", show_alert=True)
        return
    
    balance = user_profiles[user_id].get("balance", 0)
    # Проверяем минимальную цену среди всех стран (1 час минимальной цены)
    min_price = min(country["price_per_hour"] for country in RENT_COUNTRIES)
    
    if balance < min_price:
        await callback.answer(f"❌ Недостаточно средств. Минимальная цена за час: {min_price} ₽, ваш баланс: {balance} ₽", show_alert=True)
        return
    
    await show_rent_countries_selection_callback(callback, user_id)


@router.callback_query(F.data.startswith("rent_pay_balance_"))
async def handle_rent_pay_balance(callback: CallbackQuery):
    """Оплата аренды балансом"""
    try:
        # Извлекаем данные из callback_data: rent_pay_balance_{country_code}_{hours}
        data_parts = callback.data.replace("rent_pay_balance_", "").split("_")
        if len(data_parts) < 2:
            await callback.answer("❌ Ошибка формата данных", show_alert=True)
            return
        
        country_code = data_parts[0]
        hours = int(data_parts[1])
        
        country = next((c for c in RENT_COUNTRIES if c["code"] == country_code), None)
        if not country:
            await callback.answer("❌ Страна не найдена", show_alert=True)
            return
        
        user_id = callback.from_user.id
        username = callback.from_user.username or f"user_{user_id}"
        
        if user_id not in user_profiles:
            await callback.answer("❌ Профиль не найден", show_alert=True)
            return
        
        # Рассчитываем сумму
        total_price = country["price_per_hour"] * hours
        final_price = total_price
        discount = 0
        promocode = None
        
        # Проверяем активный промокод
        if "active_promocode" in user_profiles[user_id]:
            promo_data = user_profiles[user_id]["active_promocode"]
            discount = (total_price * promo_data["discount"]) // 100
            final_price = total_price - discount
            promocode = promo_data["code"]
        
        balance = user_profiles[user_id].get("balance", 0)
        
        if balance < final_price:
            await callback.answer(f"❌ Недостаточно средств. Нужно: {final_price} ₽, у вас: {balance} ₽", show_alert=True)
            return
        
        # Создаем аренду
        rent_id = f"rent_{user_id}_{int(datetime.now().timestamp())}"
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=hours)
        
        # Вычитаем сумму из баланса
        user_profiles[user_id]["balance"] -= final_price
        
        # Добавляем запись в историю баланса
        user_profiles[user_id].setdefault("balance_history", []).append({
            "date": datetime.now(),
            "amount": -final_price,
            "reason": f"Аренда аккаунта {country['name']} на {hours} часов",
            "rent_id": rent_id,
            "promocode": promocode,
            "discount": discount
        })
        
        # Удаляем использованный промокод
        if "active_promocode" in user_profiles[user_id]:
            del user_profiles[user_id]["active_promocode"]
        
        # Обновляем статистику профиля
        user_profiles[user_id].setdefault("rents", []).append({
            "date": datetime.now(),
            "country": country['name'],
            "hours": hours,
            "amount": final_price,
            "currency": "RUB",
            "rent_id": rent_id
        })
        
        # Создаем активную аренду
        active_rents[rent_id] = {
            "user_id": user_id,
            "country": country,
            "hours": hours,
            "total_price": total_price,
            "final_price": final_price,
            "payment_data": {
                "amount": final_price,
                "currency": "RUB",
                "method": "balance",
                "status": "paid",
                "original_price": total_price,
                "discount": discount,
                "promocode": promocode
            },
            "status": "waiting_for_phone",
            "created_at": datetime.now(),
            "start_time": start_time,
            "end_time": end_time,
            "username": username
        }
        
        # Обновляем общую статистику
        bot_stats["total_purchases"] += 1
        bot_stats["total_revenue"] += final_price
        
        # Создаем уведомление для админа
        for admin_id in ADMIN_IDS:
            try:
                admin_text = (
                    f"⏰ *Новая аренда оплачена балансом!*\n\n"
                    f"👤 *Пользователь:* @{username}\n"
                    f"🆔 ID: `{user_id}`\n"
                    f"🌍 *Страна:* {country['name']}\n"
                    f"⏱️ *Часы:* {hours} час(а/ов)\n"
                )
                
                if discount > 0:
                    admin_text += f"💰 *Цена:* {total_price} ₽ → *{final_price} ₽*\n"
                    admin_text += f"🎫 *Промокод:* {promocode} (-{discount} ₽)\n"
                else:
                    admin_text += f"💰 *Сумма:* {final_price} ₽\n"
                
                admin_text += f"📋 *ID аренды:* `{rent_id}`\n"
                admin_text += f"🕐 *Начало:* {start_time.strftime('%d.%m.%Y %H:%M')}\n"
                admin_text += f"🕔 *Конец:* {end_time.strftime('%d.%m.%Y %H:%M')}\n"
                admin_text += f"💳 *Способ оплаты:* Баланс\n\n"
                admin_text += f"*Аренда ожидает выдачи номера*"
                
                await callback.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_admin_confirm_rent_sms_keyboard(rent_id, user_id)
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {str(e)}")
        
        # Сообщение пользователю
        success_text = (
            f"✅ *Оплата прошла успешно!*\n\n"
            f"⏰ *Услуга:* Аренда Telegram аккаунта {country['name']}\n"
            f"⏱️ *Период:* {hours} час(а/ов)\n"
            f"🕐 *Начало:* {start_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"🕔 *Конец:* {end_time.strftime('%d.%m.%Y %H:%M')}\n"
        )
        
        if discount > 0:
            success_text += f"💰 *Цена:* {total_price} ₽ → *{final_price} ₽*\n"
            success_text += f"🎫 *Промокод:* {promocode} (-{discount} ₽)\n"
        else:
            success_text += f"💰 *Сумма:* {final_price} ₽ (списано с баланса)\n"
        
        success_text += f"📋 *ID аренды:* `{rent_id}`\n\n"
        success_text += f"⏳ *Ожидайте получения номера...*\n"
        success_text += f"Администратор скоро отправит вам номер телефона.\n\n"
        success_text += f"*Внимание:* Аккаунт будет доступен только до {end_time.strftime('%d.%m.%Y %H:%M')}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Получить номер", callback_data=f"get_rent_phone_{rent_id}")],
            [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(success_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer("✅ Аренда оплачена балансом!", show_alert=True)
        
    except Exception as e:
        logger.error(f"Ошибка при оплате аренды балансом: {str(e)}")
        await callback.answer("❌ Ошибка при оплате аренды", show_alert=True)


@router.callback_query(F.data.startswith("rent_buy_crypto_"))
async def handle_rent_buy_crypto(callback: CallbackQuery):
    """Аренда через Crypto Bot - выбор валюты"""
    try:
        # Извлекаем данные из callback_data: rent_buy_crypto_{country_code}_{hours}
        data_parts = callback.data.replace("rent_buy_crypto_", "").split("_")
        if len(data_parts) < 2:
            await callback.answer("❌ Ошибка формата данных", show_alert=True)
            return
        
        country_code = data_parts[0]
        hours = int(data_parts[1])
        
        country = next((c for c in RENT_COUNTRIES if c["code"] == country_code), None)
        if not country:
            await callback.answer("❌ Страна не найдена", show_alert=True)
            return
        
        # Рассчитываем сумму с учетом промокода
        user_id = callback.from_user.id
        total_price = country["price_per_hour"] * hours
        final_price = total_price
        discount = 0
        promocode = None
        
        if user_id in user_profiles and "active_promocode" in user_profiles[user_id]:
            promo_data = user_profiles[user_id]["active_promocode"]
            discount = (total_price * promo_data["discount"]) // 100
            final_price = total_price - discount
            promocode = promo_data["code"]
        
        price_ton = convert_rub_to_ton(final_price)
        
        selection_text = (
            f"⏰ *Оплата аренды через Crypto Bot*\n\n"
            f"🌍 *Аккаунт:* {country['name']}\n"
            f"⏱️ *Часы:* {hours} час(а/ов)\n"
        )
        
        if discount > 0:
            selection_text += f"💰 *Цена:* {total_price} ₽ → *{final_price} ₽*\n"
            selection_text += f"🎫 *Промокод:* {promocode} (-{discount} ₽)\n"
        else:
            selection_text += f"💰 *Цена:* {final_price} ₽\n"
        
        selection_text += f"⚡ *Цена в TON:* {price_ton} TON\n\n"
        selection_text += f"*TON курс:* 1 TON = {TON_RATE} ₽\n\n"
        selection_text += f"*Выберите валюту для оплаты:*"
        
        await callback.message.edit_text(
            selection_text,
            reply_markup=get_rent_crypto_currency_keyboard(country_code, hours, final_price),
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при выборе валюты Crypto Bot для аренды: {str(e)}")
        await callback.answer("❌ Ошибка!", show_alert=True)


@router.callback_query(F.data.startswith("rent_crypto_usdt_"))
async def handle_rent_crypto_usdt(callback: CallbackQuery):
    """Аренда через Crypto Bot в USDT"""
    await handle_rent_crypto_purchase(callback, "USDT")


@router.callback_query(F.data.startswith("rent_crypto_ton_"))
async def handle_rent_crypto_ton(callback: CallbackQuery):
    """Аренда через Crypto Bot в TON"""
    await handle_rent_crypto_purchase(callback, "TON")


async def handle_rent_crypto_purchase(callback: CallbackQuery, asset: str):
    """Общая функция аренды через Crypto Bot"""
    try:
        # Извлекаем данные из callback_data
        if asset == "TON":
            data_parts = callback.data.replace("rent_crypto_ton_", "").split("_")
        else:
            data_parts = callback.data.replace("rent_crypto_usdt_", "").split("_")
        
        if len(data_parts) < 2:
            await callback.answer("❌ Ошибка формата данных", show_alert=True)
            return
        
        country_code = data_parts[0]
        hours = int(data_parts[1])
        
        country = next((c for c in RENT_COUNTRIES if c["code"] == country_code), None)
        if not country:
            await callback.answer("❌ Страна не найдена", show_alert=True)
            return
        
        user_id = callback.from_user.id
        username = callback.from_user.username or f"user_{user_id}"
        
        # Рассчитываем сумму с учетом промокода
        total_price = country["price_per_hour"] * hours
        final_price = total_price
        discount = 0
        promocode = None
        
        if user_id in user_profiles and "active_promocode" in user_profiles[user_id]:
            promo_data = user_profiles[user_id]["active_promocode"]
            discount = (total_price * promo_data["discount"]) // 100
            final_price = total_price - discount
            promocode = promo_data["code"]
        
        # Конвертируем в выбранную валюту
        if asset == "TON":
            amount_asset = convert_rub_to_ton(final_price)
            original_amount_asset = convert_rub_to_ton(total_price)
        else:
            # Для USDT используем примерный курс, можно изменить
            amount_asset = round(final_price / 70, 4)  # Примерный курс
            original_amount_asset = round(total_price / 70, 4)
        
        description = f"Аренда Telegram аккаунта {country['name']} на {hours} часов - Monkey Number"
        if promocode:
            description += f" (Промокод: {promocode})"
        
        logger.info(f"Аренда Crypto Bot аккаунта {country['name']} для {username}: {amount_asset} {asset}")
        
        # Создаем инвойс
        invoice = await crypto_api.create_invoice(
            asset=asset,
            amount=amount_asset,
            description=description,
            hidden_message=f"После оплаты вы получите данные аккаунта {country['name']} на {hours} часов"
        )
        
        payment_id = invoice.get("invoice_id")
        pay_url = invoice.get("pay_url")
        
        # Сохраняем информацию о платеже
        temp_payments[payment_id] = {
            "user_id": user_id,
            "amount": amount_asset,
            "currency": asset,
            "method": "crypto",
            "created_at": datetime.now(),
            "username": username,
            "pay_url": pay_url,
            "type": "rent",
            "country": country,
            "hours": hours,
            "description": description,
            "original_price": total_price,
            "final_price": final_price,
            "discount": discount,
            "promocode": promocode
        }
        
        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💎 Оплатить {amount_asset} {asset}", url=pay_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_rent_crypto_{payment_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rent_country_{country_code}")]
        ])
        
        response_text = (
            f"💎 *Оплата через Crypto Bot*\n\n"
            f"⏰ *Услуга:* Аренда Telegram аккаунта {country['name']}\n"
            f"⏱️ *Часы:* {hours} час(а/ов)\n"
        )
        
        if discount > 0:
            response_text += f"💰 *Цена:* {total_price} ₽ → *{final_price} ₽*\n"
            response_text += f"🎫 *Промокод:* {promocode} (-{discount} ₽)\n"
        else:
            response_text += f"💰 *Цена:* {final_price} ₽\n"
        
        if asset == "TON":
            response_text += f"⚡ *В TON:* {original_amount_asset} → {amount_asset} TON\n"
        else:
            response_text += f"💵 *В USDT:* {original_amount_asset} → {amount_asset} USDT\n"
        
        response_text += f"📋 *ID платежа:* `{payment_id}`\n\n"
        response_text += f"*Инструкция:*\n"
        response_text += f"1. Нажмите *Оплатить {amount_asset} {asset}*\n"
        response_text += f"2. Оплатите в @CryptoBot\n"
        response_text += f"3. Нажмите *Проверить оплату*\n"
        response_text += f"4. После оплаты получите данные аккаунта\n\n"
        response_text += f"_Платеж обрабатывается через @CryptoBot_"
        
        await callback.message.edit_text(response_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при создании платежа Crypto Bot для аренды: {str(e)}")
        error_text = (
            "❌ *Не удалось создать платеж*\n\n"
            f"Ошибка: {str(e)}\n\n"
            "Попробуйте позже или выберите другой способ оплаты."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=callback.data)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rent_country_{country_code}")]
        ])
        
        await callback.message.edit_text(error_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer("❌ Ошибка!", show_alert=True)


@router.callback_query(F.data.startswith("rent_buy_lolz_"))
async def handle_rent_buy_lolz(callback: CallbackQuery):
    """Аренда через Lolz Merchant"""
    try:
        # Извлекаем данные из callback_data: rent_buy_lolz_{country_code}_{hours}
        data_parts = callback.data.replace("rent_buy_lolz_", "").split("_")
        if len(data_parts) < 2:
            await callback.answer("❌ Ошибка формата данных", show_alert=True)
            return
        
        country_code = data_parts[0]
        hours = int(data_parts[1])
        
        country = next((c for c in RENT_COUNTRIES if c["code"] == country_code), None)
        if not country:
            await callback.answer("❌ Страна не найдена", show_alert=True)
            return
        
        user_id = callback.from_user.id
        username = callback.from_user.username or f"user_{user_id}"
        
        # Рассчитываем сумму с учетом промокода
        total_price = country["price_per_hour"] * hours
        final_price = total_price
        discount = 0
        promocode = None
        
        if user_id in user_profiles and "active_promocode" in user_profiles[user_id]:
            promo_data = user_profiles[user_id]["active_promocode"]
            discount = (total_price * promo_data["discount"]) // 100
            final_price = total_price - discount
            promocode = promo_data["code"]
        
        description = f"Аренда Telegram аккаунта {country['name']} на {hours} часов - Monkey Number"
        if promocode:
            description += f" (Промокод: {promocode})"
        
        logger.info(f"Аренда Lolz Merchant аккаунта {country['name']} для {username}: {final_price} RUB")
        
        # Создаем инвойс
        payment = await lolz_api.create_invoice(
            amount=int(final_price),
            user_id=user_id,
            username=username,
            description=description
        )
        
        payment_id = payment.get("payment_id")
        invoice_id = payment.get("invoice_id")
        pay_url = payment.get("pay_url")
        
        # Сохраняем информацию о платеже
        temp_payments[payment_id] = {
            "user_id": user_id,
            "amount": final_price,
            "currency": "RUB",
            "method": "lolz",
            "created_at": datetime.now(),
            "username": username,
            "pay_url": pay_url,
            "invoice_id": invoice_id,
            "invoice_data": payment.get("invoice_data", {}),
            "type": "rent",
            "country": country,
            "hours": hours,
            "description": description,
            "original_price": total_price,
            "discount": discount,
            "promocode": promocode
        }
        
        # Создаем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🛒 Оплатить {final_price} ₽", url=pay_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_rent_lolz_{payment_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rent_country_{country_code}")]
        ])
        
        response_text = (
            f"🛒 *Оплата через Lolz Merchant*\n\n"
            f"⏰ *Услуга:* Аренда Telegram аккаунта {country['name']}\n"
            f"⏱️ *Часы:* {hours} час(а/ов)\n"
        )
        
        if discount > 0:
            response_text += f"💰 *Цена:* {total_price} ₽ → *{final_price} ₽*\n"
            response_text += f"🎫 *Промокод:* {promocode} (-{discount} ₽)\n"
        else:
            response_text += f"💰 *Цена:* {final_price} ₽\n"
        
        response_text += f"📋 *ID платежа:* `{payment_id}`\n"
        response_text += f"📋 *ID счета Lolz:* `{invoice_id}`\n\n"
        response_text += f"*Инструкция по оплате:*\n"
        response_text += f"1. Зайдите на сайт lzt.market\n"
        response_text += f"   • Зарегистрируйтесь на сайте\n"
        response_text += f"   • Или войдите в свой аккаунт\n\n"
        response_text += f"2. Пополните баланс на нужную сумму\n"
        response_text += f"   • Банковская карта\n"
        response_text += f"   • Qiwi\n"
        response_text += f"   • ЮMoney\n"
        response_text += f"   • Мобильный платеж\n"
        response_text += f"   • Криптовалюта\n\n"
        response_text += f"3. Перейдите по ссылке ниже и оплатите счет\n\n"
        response_text += f"*После оплаты нажмите 🔄 Проверить оплату*"
        
        await callback.message.edit_text(response_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Ошибка при создании платежа Lolz для аренды: {str(e)}")
        error_text = (
            "❌ *Не удалось создать платеж*\n\n"
            f"Ошибка: {str(e)}\n\n"
            "Попробуйте позже или выберите другой способ оплаты."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=callback.data)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rent_country_{country_code}")]
        ])
        
        await callback.message.edit_text(error_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        await callback.answer("❌ Ошибка!", show_alert=True)


# =============== ПРОВЕРКА ОПЛАТЫ АРЕНДЫ ===============

@router.callback_query(F.data.startswith("check_rent_crypto_"))
async def handle_check_rent_crypto(callback: CallbackQuery):
    """Проверка оплаты аренды через Crypto Bot"""
    await handle_rent_payment_check(callback, "crypto")


@router.callback_query(F.data.startswith("check_rent_lolz_"))
async def handle_check_rent_lolz(callback: CallbackQuery):
    """Проверка оплаты аренды через Lolz Merchant"""
    await handle_rent_payment_check(callback, "lolz")


async def handle_rent_payment_check(callback: CallbackQuery, method: str):
    """Обработка проверки платежа за аренду"""
    try:
        if method == "crypto":
            payment_id = callback.data.replace("check_rent_crypto_", "")
        else:
            payment_id = callback.data.replace("check_rent_lolz_", "")
        
        if payment_id not in temp_payments:
            await callback.answer("❌ Платеж не найден", show_alert=True)
            return
        
        payment_data = temp_payments[payment_id]
        country = payment_data.get("country")
        hours = payment_data.get("hours", 1)
        
        if method == "crypto":
            # Проверяем статус платежа через Crypto Bot
            invoice = await crypto_api.get_invoice(payment_id)
            status = invoice.get("status")
            
            if status == "paid":
                # Удаляем использованный промокод
                if payment_data.get("promocode") and payment_data["user_id"] in user_profiles:
                    if "active_promocode" in user_profiles[payment_data["user_id"]]:
                        del user_profiles[payment_data["user_id"]]["active_promocode"]
                
                # Создаем аренду
                rent_id = f"rent_{payment_data['user_id']}_{int(datetime.now().timestamp())}"
                start_time = datetime.now()
                end_time = start_time + timedelta(hours=hours)
                
                # Обновляем профиль пользователя
                user_id = payment_data["user_id"]
                if user_id in user_profiles:
                    # Конвертируем в рубли для статистики
                    amount_rub = payment_data.get("final_price", payment_data.get("amount"))
                    if payment_data["currency"] == "TON":
                        amount_rub = convert_ton_to_rub(amount_rub)
                    elif payment_data["currency"] == "USDT":
                        amount_rub = amount_rub * 70  # Примерный курс
                    
                    user_profiles[user_id].setdefault("rents", []).append({
                        "date": datetime.now(),
                        "country": country['name'],
                        "hours": hours,
                        "amount": amount_rub,
                        "currency": "RUB",
                        "rent_id": rent_id
                    })
                    
                    # Создаем активную аренду
                    active_rents[rent_id] = {
                        "user_id": user_id,
                        "country": country,
                        "hours": hours,
                        "total_price": payment_data.get("original_price", 0),
                        "final_price": payment_data.get("final_price", payment_data.get("amount")),
                        "payment_data": payment_data,
                        "status": "waiting_for_phone",
                        "created_at": datetime.now(),
                        "start_time": start_time,
                        "end_time": end_time,
                        "username": payment_data["username"]
                    }
                    
                    # Обновляем общую статистику
                    amount_rub = payment_data.get("final_price", payment_data.get("amount"))
                    if payment_data["currency"] == "TON":
                        amount_rub = convert_ton_to_rub(payment_data["amount"])
                    elif payment_data["currency"] == "USDT":
                        amount_rub = amount_rub * 70  # Примерный курс
                    
                    bot_stats["total_purchases"] += 1
                    bot_stats["total_revenue"] += amount_rub
                    
                    # Удаляем из временного хранилища
                    del temp_payments[payment_id]
                    
                    # Создаем уведомление для админа
                    for admin_id in ADMIN_IDS:
                        try:
                            admin_text = (
                                f"⏰ *Новая аренда!*\n\n"
                                f"👤 *Пользователь:* @{payment_data['username']}\n"
                                f"🆔 ID: `{user_id}`\n"
                                f"🌍 *Страна:* {country['name']}\n"
                                f"⏱️ *Часы:* {hours} час(а/ов)\n"
                            )
                            
                            if payment_data.get("discount", 0) > 0:
                                admin_text += f"💰 *Цена:* {payment_data.get('original_price', 0)} ₽ → *{payment_data.get('final_price', 0)} ₽*\n"
                                admin_text += f"🎫 *Промокод:* {payment_data.get('promocode', '')} (-{payment_data.get('discount', 0)} ₽)\n"
                            else:
                                admin_text += f"💰 *Сумма:* {payment_data['amount']} {payment_data['currency']}\n"
                            
                            admin_text += f"📋 *ID аренды:* `{rent_id}`\n"
                            admin_text += f"🕐 *Начало:* {start_time.strftime('%d.%m.%Y %H:%M')}\n"
                            admin_text += f"🕔 *Конец:* {end_time.strftime('%d.%m.%Y %H:%M')}\n"
                            admin_text += f"💎 *Способ оплаты:* Crypto Bot\n\n"
                            admin_text += f"*Аренда ожидает выдачи номера*"
                            
                            await callback.bot.send_message(
                                chat_id=admin_id,
                                text=admin_text,
                                parse_mode=ParseMode.MARKDOWN,
                                reply_markup=get_admin_confirm_rent_sms_keyboard(rent_id, user_id)
                            )
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления админу {admin_id}: {str(e)}")
                    
                    # Сообщение пользователю
                    success_text = (
                        f"✅ *Оплата прошла успешно!*\n\n"
                        f"⏰ *Услуга:* Аренда Telegram аккаунта {country['name']}\n"
                        f"⏱️ *Часы:* {hours} час(а/ов)\n"
                        f"🕐 *Начало:* {start_time.strftime('%d.%m.%Y %H:%M')}\n"
                        f"🕔 *Конец:* {end_time.strftime('%d.%m.%Y %H:%M')}\n"
                    )
                    
                    if payment_data.get("discount", 0) > 0:
                        success_text += f"💰 *Цена:* {payment_data.get('original_price', 0)} ₽ → *{payment_data.get('final_price', 0)} ₽*\n"
                        success_text += f"🎫 *Промокод:* {payment_data.get('promocode', '')} (-{payment_data.get('discount', 0)} ₽)\n"
                    else:
                        success_text += f"💰 *Сумма:* {payment_data['amount']} {payment_data['currency']}\n"
                    
                    success_text += f"📋 *ID аренды:* `{rent_id}`\n\n"
                    success_text += f"⏳ *Ожидайте получения номера...*\n"
                    success_text += f"Администратор скоро отправит вам номер телефона.\n\n"
                    success_text += f"*Внимание:* Аккаунт будет доступен только до {end_time.strftime('%d.%m.%Y %H:%M')}"
                    
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📱 Получить номер", callback_data=f"get_rent_phone_{rent_id}")],
                        [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
                    ])
                    
                    await callback.message.edit_text(success_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
                    await callback.answer("✅ Оплата подтверждена! Ожидайте номер.", show_alert=True)
                else:
                    await callback.answer(f"Статус платежа: {status}", show_alert=True)
        
        else:  # method == "lolz"
            # Проверяем статус платежа через Lolz API
            invoice_info = await lolz_api.check_payment_by_external_id(payment_id)
            if invoice_info:
                status = invoice_info.get("status")
                if status == "paid":
                    # Удаляем использованный промокод
                    if payment_data.get("promocode") and payment_data["user_id"] in user_profiles:
                        if "active_promocode" in user_profiles[payment_data["user_id"]]:
                            del user_profiles[payment_data["user_id"]]["active_promocode"]
                    
                    # Создаем аренду
                    rent_id = f"rent_{payment_data['user_id']}_{int(datetime.now().timestamp())}"
                    start_time = datetime.now()
                    end_time = start_time + timedelta(hours=hours)
                    
                    # Обновляем профиль пользователя
                    user_id = payment_data["user_id"]
                    if user_id in user_profiles:
                        user_profiles[user_id].setdefault("rents", []).append({
                            "date": datetime.now(),
                            "country": country['name'],
                            "hours": hours,
                            "amount": payment_data["amount"],
                            "currency": "RUB",
                            "rent_id": rent_id
                        })
                        
                        # Создаем активную аренду
                        active_rents[rent_id] = {
                            "user_id": user_id,
                            "country": country,
                            "hours": hours,
                            "total_price": payment_data.get("original_price", 0),
                            "final_price": payment_data["amount"],
                            "payment_data": payment_data,
                            "status": "waiting_for_phone",
                            "created_at": datetime.now(),
                            "start_time": start_time,
                            "end_time": end_time,
                            "username": payment_data["username"]
                        }
                        
                        # Обновляем общую статистику
                        bot_stats["total_purchases"] += 1
                        bot_stats["total_revenue"] += payment_data["amount"]
                        
                        # Удаляем из временного хранилища
                        del temp_payments[payment_id]
                        
                        # Создаем уведомление для админа
                        for admin_id in ADMIN_IDS:
                            try:
                                admin_text = (
                                    f"⏰ *Новая аренда!*\n\n"
                                    f"👤 *Пользователь:* @{payment_data['username']}\n"
                                    f"🆔 ID: `{user_id}`\n"
                                    f"🌍 *Страна:* {country['name']}\n"
                                    f"⏱️ *Часы:* {hours} час(а/ов)\n"
                                )
                                
                                if payment_data.get("discount", 0) > 0:
                                    admin_text += f"💰 *Цена:* {payment_data.get('original_price', 0)} ₽ → *{payment_data['amount']} ₽*\n"
                                    admin_text += f"🎫 *Промокод:* {payment_data.get('promocode', '')} (-{payment_data.get('discount', 0)} ₽)\n"
                                else:
                                    admin_text += f"💰 *Сумма:* {payment_data['amount']} {payment_data['currency']}\n"
                                
                                admin_text += f"📋 *ID аренды:* `{rent_id}`\n"
                                admin_text += f"🕐 *Начало:* {start_time.strftime('%d.%m.%Y %H:%M')}\n"
                                admin_text += f"🕔 *Конец:* {end_time.strftime('%d.%m.%Y %H:%M')}\n"
                                admin_text += f"🛒 *Способ оплаты:* Lolz Merchant\n\n"
                                admin_text += f"*Аренда ожидает выдачи номера*"
                                
                                await callback.bot.send_message(
                                    chat_id=admin_id,
                                    text=admin_text,
                                    parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=get_admin_confirm_rent_sms_keyboard(rent_id, user_id)
                                )
                            except Exception as e:
                                logger.error(f"Ошибка отправки уведомления админу {admin_id}: {str(e)}")
                        
                        # Сообщение пользователю
                        success_text = (
                            f"✅ *Оплата прошла успешно!*\n\n"
                            f"⏰ *Услуга:* Аренда Telegram аккаунта {country['name']}\n"
                            f"⏱️ *Часы:* {hours} час(а/ов)\n"
                            f"🕐 *Начало:* {start_time.strftime('%d.%m.%Y %H:%M')}\n"
                            f"🕔 *Конец:* {end_time.strftime('%d.%m.%Y %H:%M')}\n"
                        )
                        
                        if payment_data.get("discount", 0) > 0:
                            success_text += f"💰 *Цена:* {payment_data.get('original_price', 0)} ₽ → *{payment_data['amount']} ₽*\n"
                            success_text += f"🎫 *Промокод:* {payment_data.get('promocode', '')} (-{payment_data.get('discount', 0)} ₽)\n"
                        else:
                            success_text += f"💰 *Сумма:* {payment_data['amount']} {payment_data['currency']}\n"
                        
                        success_text += f"📋 *ID аренды:* `{rent_id}`\n\n"
                        success_text += f"⏳ *Ожидайте получения номера...*\n"
                        success_text += f"Администратор скоро отправит вам номер телефона.\n\n"
                        success_text += f"*Внимание:* Аккаунт будет доступен только до {end_time.strftime('%d.%m.%Y %H:%M')}"
                        
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="📱 Получить номер", callback_data=f"get_rent_phone_{rent_id}")],
                            [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
                        ])
                        
                        await callback.message.edit_text(success_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
                        await callback.answer("✅ Оплата подтверждена! Ожидайте номер.", show_alert=True)
                    elif status == "active" or status == "pending":
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="💎 Оплатить", url=payment_data["pay_url"])],
                            [InlineKeyboardButton(text="🔄 Проверить снова", callback_data=f"check_rent_{method}_{payment_id}")],
                            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"rent_country_{country['code']}")]
                        ])
                        
                        await callback.message.edit_text(
                            f"⏳ *Платеж ожидает оплаты*\n\n"
                            f"⏰ Услуга: Аренда Telegram аккаунта {country['name']}\n"
                            f"⏱️ Часы: {hours} час(а/ов)\n"
                            f"💰 Сумма: {payment_data['amount']} {payment_data['currency']}\n"
                            f"📊 Статус: Ожидает оплаты\n\n"
                            f"Нажмите на кнопку оплаты выше или проверьте позже.",
                            reply_markup=keyboard,
                            parse_mode=ParseMode.MARKDOWN
                        )
                        await callback.answer("⏳ Платеж еще не оплачен", show_alert=True)
                    else:
                        await callback.answer(f"Статус платежа: {status}", show_alert=True)
                else:
                    await callback.answer("❌ Платеж не найден в системе", show_alert=True)
    
    except Exception as e:
        logger.error(f"Ошибка при проверке платежа за аренду: {str(e)}")
        await callback.answer("❌ Ошибка при проверке платежа", show_alert=True)


# =============== ВЫДАЧА НОМЕРОВ ДЛЯ АРЕНДЫ ===============

@router.callback_query(F.data.startswith("get_rent_phone_"))
async def handle_get_rent_phone(callback: CallbackQuery):
    """Запрос номера телефона для аренды"""
    rent_id = callback.data.replace("get_rent_phone_", "")
    
    if rent_id not in active_rents:
        await callback.answer("❌ Аренда не найдена", show_alert=True)
        return
    
    rent = active_rents[rent_id]
    
    if rent["status"] != "waiting_for_phone":
        await callback.answer("❌ Номер уже был запрошен", show_alert=True)
        return
    
    # Отправляем уведомление админу
    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"📱 *Запрос номера телефона для аренды*\n\n"
                f"👤 Пользователь: @{rent['username']}\n"
                f"🆔 ID: `{rent['user_id']}`\n"
                f"🌍 Страна: {rent['country']['name']}\n"
                f"⏱️ Часы: {rent['hours']} час(а/ов)\n"
                f"🕐 Начало: {rent['start_time'].strftime('%d.%m.%Y %H:%M')}\n"
                f"🕔 Конец: {rent['end_time'].strftime('%d.%m.%Y %H:%M')}\n"
                f"📋 ID аренды: `{rent_id}`\n"
            )
            
            if rent["payment_data"].get("promocode"):
                admin_text += f"🎫 Промокод: `{rent['payment_data']['promocode']}`\n"
            
            admin_text += f"\n*Отправьте номер телефона этому пользователю:*"
            
            await callback.bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="📱 Отправить номер", callback_data=f"admin_send_rent_phone_{rent_id}"),
                        InlineKeyboardButton(text="👤 Перейти к пользователю", url=f"tg://user?id={rent['user_id']}")
                    ]
                ])
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу {admin_id}: {str(e)}")
    
    # Сообщение пользователю
    await callback.message.edit_text(
        "📱 *Запрос номера отправлен администратору*\n\n"
        "⏳ *Ожидайте...*\n"
        "Администратор скоро отправит вам номер телефона.\n\n"
        "Как только получите номер, нажмите кнопку ниже.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить", callback_data=f"get_rent_phone_{rent_id}")],
            [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
        ])
    )
    await callback.answer("📱 Запрос отправлен админу")


@router.callback_query(F.data.startswith("admin_send_rent_phone_"))
async def handle_admin_send_rent_phone(callback: CallbackQuery, state: FSMContext):
    """Админ отправляет номер телефона для аренды"""
    rent_id = callback.data.replace("admin_send_rent_phone_", "")
    
    if rent_id not in active_rents:
        await callback.answer("❌ Аренда не найдена", show_alert=True)
        return
    
    rent = active_rents[rent_id]
    
    admin_text = (
        f"📱 *Отправка номера телефона для аренды*\n\n"
        f"👤 Пользователь: @{rent['username']}\n"
        f"🌍 Страна: {rent['country']['name']}\n"
        f"⏱️ Часы: {rent['hours']} час(а/ов)\n"
        f"🕐 Начало: {rent['start_time'].strftime('%d.%m.%Y %H:%M')}\n"
        f"🕔 Конец: {rent['end_time'].strftime('%d.%m.%Y %H:%M')}\n"
        f"📋 ID аренды: `{rent_id}`\n"
    )
    
    if rent["payment_data"].get("promocode"):
        admin_text += f"🎫 Промокод: `{rent['payment_data']['promocode']}`\n"
    
    admin_text += f"\nВведите номер телефона для этой аренды:\n\n"
    admin_text += f"Пример: `+79123456789`"
    
    await callback.message.edit_text(admin_text, parse_mode=ParseMode.MARKDOWN)
    await state.set_state(AdminStates.waiting_for_phone)
    await state.update_data(rent_id=rent_id, user_id=rent["user_id"], is_rent=True)
    await callback.answer()


@router.callback_query(F.data.startswith("get_rent_sms_"))
async def handle_get_rent_sms(callback: CallbackQuery):
    """Запрос SMS-кода для аренды"""
    rent_id = callback.data.replace("get_rent_sms_", "")
    
    if rent_id not in active_rents:
        await callback.answer("❌ Аренда не найдена", show_alert=True)
        return
    
    rent = active_rents[rent_id]
    
    if rent["status"] != "waiting_for_sms":
        await callback.answer("❌ SMS-код уже был запрошен", show_alert=True)
        return
    
    # Отправляем уведомление админу
    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"📱 *Запрос SMS-кода для аренды*\n\n"
                f"👤 Пользователь: @{rent['username']}\n"
                f"🆔 ID: `{rent['user_id']}`\n"
                f"🌍 Страна: {rent['country']['name']}\n"
                f"⏱️ Часы: {rent['hours']} час(а/ов)\n"
                f"📱 Номер: `{rent.get('phone_number', 'Не указан')}`\n"
                f"🕐 Начало: {rent['start_time'].strftime('%d.%m.%Y %H:%M')}\n"
                f"🕔 Конец: {rent['end_time'].strftime('%d.%m.%Y %H:%M')}\n"
                f"📋 ID аренды: `{rent_id}`\n"
            )
            
            if rent["payment_data"].get("promocode"):
                admin_text += f"🎫 Промокод: `{rent['payment_data']['promocode']}`\n"
            
            admin_text += f"\n*Отправьте SMS-код этому пользователю:*"
            
            await callback.bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="📱 Отправить SMS-код", callback_data=f"admin_send_rent_sms_{rent_id}"),
                        InlineKeyboardButton(text="👤 Перейти к пользователю", url=f"tg://user?id={rent['user_id']}")
                    ]
                ])
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу {admin_id}: {str(e)}")
    
    # Сообщение пользователю
    await callback.message.edit_text(
        "📱 *Запрос SMS-кода отправлен администратору*\n\n"
        "⏳ *Ожидайте...*\n"
        "Администратор скоро отправит вам SMS-код.\n\n"
        "Как только получите код, введите его в Telegram для завершения регистрации.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить", callback_data=f"get_rent_sms_{rent_id}")],
            [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]
        ])
    )
    await callback.answer("📱 Запрос SMS-кода отправлен админу")


@router.callback_query(F.data.startswith("admin_send_rent_sms_"))
async def handle_admin_send_rent_sms(callback: CallbackQuery, state: FSMContext):
    """Админ отправляет SMS-код для аренды"""
    rent_id = callback.data.replace("admin_send_rent_sms_", "")
    
    if rent_id not in active_rents:
        await callback.answer("❌ Аренда не найдена", show_alert=True)
        return
    
    rent = active_rents[rent_id]
    
    admin_text = (
        f"📱 *Отправка SMS-кода для аренды*\n\n"
        f"👤 Пользователь: @{rent['username']}\n"
        f"🌍 Страна: {rent['country']['name']}\n"
        f"⏱️ Часы: {rent['hours']} час(а/ов)\n"
        f"📱 Номер: `{rent.get('phone_number', 'Не указан')}`\n"
        f"🕐 Начало: {rent['start_time'].strftime('%d.%m.%Y %H:%M')}\n"
        f"🕔 Конец: {rent['end_time'].strftime('%d.%m.%Y %H:%M')}\n"
        f"📋 ID аренды: `{rent_id}`\n"
    )
    
    if rent["payment_data"].get("promocode"):
        admin_text += f"🎫 Промокод: `{rent['payment_data']['promocode']}`\n"
    
    admin_text += f"\nВведите SMS-код для этой аренды:\n\n"
    admin_text += f"Пример: `123456`"
    
    await callback.message.edit_text(admin_text, parse_mode=ParseMode.MARKDOWN)
    await state.set_state(AdminStates.waiting_for_sms)
    await state.update_data(rent_id=rent_id, user_id=rent["user_id"], is_rent=True)
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_for_sms))
async def handle_sms_code(message: Message, state: FSMContext):
    """Обработка введенного SMS-кода"""
    try:
        data = await state.get_data()
        is_rent = data.get("is_rent", False)
        
        if is_rent:
            rent_id = data.get("rent_id")
            user_id = data.get("user_id")
            
            if rent_id not in active_rents:
                await message.answer("❌ Аренда не найдена")
                await state.clear()
                return
            
            sms_code = message.text.strip()
            
            # Сохраняем SMS-код в аренде
            active_rents[rent_id]["sms_code"] = sms_code
            active_rents[rent_id]["status"] = "completed"
            
            # Отправляем SMS-код пользователю
            try:
                await message.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ *SMS-код получен!*\n\n"
                        f"🌍 Страна: {active_rents[rent_id]['country']['name']}\n"
                        f"⏱️ Часы: {active_rents[rent_id]['hours']} час(а/ов)\n"
                        f"📱 Номер: {active_rents[rent_id].get('phone_number', 'Не указан')}\n"
                        f"🔢 *SMS-код:* `{sms_code}`\n\n"
                        f"*Инструкция:*\n"
                        f"1. Используйте этот номер и код для регистрации в Telegram\n"
                        f"2. Аккаунт будет доступен до {active_rents[rent_id]['end_time'].strftime('%d.%m.%Y %H:%M')}\n\n"
                        f"*Внимание:*\n"
                        f"• Не публикуйте номер публично\n"
                        f"• Используйте его только для регистрации\n"
                        f"• Аккаунт автоматически станет недоступен после окончания времени аренды"
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Ошибка отправки SMS-кода пользователю {user_id}: {str(e)}")
                await message.answer(f"❌ Ошибка отправки SMS-кода пользователю: {str(e)}")
                return
            
            # Сообщение админу
            await message.answer(
                f"✅ *SMS-код отправлен пользователю!*\n\n"
                f"🔢 *Код:* `{sms_code}`\n"
                f"👤 Пользователь: @{active_rents[rent_id]['username']}\n"
                f"🌍 Страна: {active_rents[rent_id]['country']['name']}\n"
                f"⏱️ Часы: {active_rents[rent_id]['hours']} час(а/ов)\n"
                f"📋 ID аренды: `{rent_id}`\n\n"
                f"*Аренда завершена успешно!*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Новый заказ", callback_data="admin_menu")],
                    [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
                ])
            )
        
        else:
            order_id = data.get("order_id")
            user_id = data.get("user_id")
            
            if order_id not in active_orders:
                await message.answer("❌ Заказ не найден")
                await state.clear()
                return
            
            sms_code = message.text.strip()
            
            # Сохраняем SMS-код в заказе
            active_orders[order_id]["sms_code"] = sms_code
            active_orders[order_id]["status"] = "completed"
            
            # Отправляем SMS-код пользователю
            try:
                await message.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"✅ *SMS-код получен!*\n\n"
                        f"🌍 Страна: {active_orders[order_id]['country']['name']}\n"
                        f"📱 Номер: {active_orders[order_id].get('phone_number', 'Не указан')}\n"
                        f"🔢 *SMS-код:* `{sms_code}`\n\n"
                        f"*Инструкция:*\n"
                        f"1. Используйте этот номер и код для регистрации в Telegram\n\n"
                        f"*Внимание:*\n"
                        f"• Не публикуйте номер публично\n"
                        f"• Используйте его только для регистрации"
                    ),
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Ошибка отправки SMS-кода пользователю {user_id}: {str(e)}")
                await message.answer(f"❌ Ошибка отправки SMS-кода пользователю: {str(e)}")
                return
            
            # Сообщение админу
            await message.answer(
                f"✅ *SMS-код отправлен пользователю!*\n\n"
                f"🔢 *Код:* `{sms_code}`\n"
                f"👤 Пользователь: @{active_orders[order_id]['username']}\n"
                f"🌍 Страна: {active_orders[order_id]['country']['name']}\n"
                f"📋 ID заказа: `{order_id}`\n\n"
                f"*Заказ завершен успешно!*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Новый заказ", callback_data="admin_menu")],
                    [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
                ])
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка обработки SMS-кода: {str(e)}")
        await message.answer("❌ Ошибка обработки SMS-кода")


@router.callback_query(F.data.startswith("admin_rent_sms_sent_"))
async def handle_admin_rent_sms_sent(callback: CallbackQuery):
    """Админ подтверждает отправку SMS-кода для аренды"""
    rent_id = callback.data.replace("admin_rent_sms_sent_", "")
    
    if rent_id not in active_rents:
        await callback.answer("❌ Аренда не найден", show_alert=True)
        return
    
    rent = active_rents[rent_id]
    
    # Помечаем аренду как завершенную
    active_rents[rent_id]["status"] = "completed"
    
    # Уведомление админу
    admin_text = (
        f"✅ *SMS-код отправлен пользователю!*\n\n"
        f"👤 Пользователь: @{rent['username']}\n"
        f"🌍 Страна: {rent['country']['name']}\n"
        f"⏱️ Часы: {rent['hours']} час(а/ов)\n"
        f"📋 ID аренды: `{rent_id}`\n"
    )
    
    if rent["payment_data"].get("promocode"):
        admin_text += f"🎫 Промокод: `{rent['payment_data']['promocode']}`\n"
    
    admin_text += f"\n*Аренда завершена успешно!*"
    
    await callback.message.edit_text(
        admin_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Новый заказ", callback_data="admin_menu")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
        ])
    )
    await callback.answer("✅ SMS-код отправлен")


# =============== ОСТАЛЬНЫЕ ФУНКЦИИ (без изменений) ===============

# Остальной код остается без изменений, включая:
# - Донат с вводом суммы
# - Обработка покупок через Crypto Bot и Lolz Merchant
# - Админ панель
# - Очистка старых данных
# - Запуск бота

# ... (остальной код без изменений, так как он уже предоставлен в оригинальном файле)

# Примечание: В оригинальном коде есть еще много функций, которые я не включил
# в этот ответ из-за ограничения длины. Основные изменения для добавления
# аренды аккаунтов я внес выше. Остальной код должен остаться без изменений.

# Важно: Не забудьте добавить обработку аренды в функцию cleanup_old_data():
# Нужно добавить очистку истекших аренд (где end_time < текущее время)

async def cleanup_old_data():
    """Очистка старых данных"""
    while True:
        try:
            now = datetime.now()
            
            # Очистка старых платежей (старше 24 часов)
            expired_payments = []
            for payment_id, payment_data in temp_payments.items():
                if now - payment_data["created_at"] > timedelta(hours=24):
                    expired_payments.append(payment_id)
            
            for payment_id in expired_payments:
                del temp_payments[payment_id]
            
            if expired_payments:
                logger.info(f"Очищено {len(expired_payments)} просроченных платежей")
            
            # Очистка старых заказов (старше 7 дней)
            expired_orders = []
            for order_id, order_data in active_orders.items():
                if now - order_data["created_at"] > timedelta(days=7):
                    expired_orders.append(order_id)
            
            for order_id in expired_orders:
                del active_orders[order_id]
            
            if expired_orders:
                logger.info(f"Очищено {len(expired_orders)} старых заказов")
            
            # Очистка истекших аренд (где end_time < текущее время)
            expired_rents = []
            for rent_id, rent_data in active_rents.items():
                if rent_data.get("end_time") and now > rent_data["end_time"]:
                    expired_rents.append(rent_id)
            
            for rent_id in expired_rents:
                del active_rents[rent_id]
            
            if expired_rents:
                logger.info(f"Очищено {len(expired_rents)} истекших аренд")
            
        except Exception as e:
            logger.error(f"Ошибка очистки данных: {str(e)}")
        
        await asyncio.sleep(3600)  # Проверяем каждый час


async def main():
    """Запуск бота"""
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("❌ Ошибка: Не установлен BOT_TOKEN в переменных окружения!")
        logger.info("Установите токен командой: export BOT_TOKEN='ваш_token'")
        return
    
    storage = MemoryStorage()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    dp.include_router(router)
    
    # Запускаем фоновые задачи
    asyncio.create_task(cleanup_old_data())
    
    logger.info("🚀 Monkey Number Bot запускается...")
    logger.info(f"   💎 Crypto Bot токен: {CRYPTO_BOT_TOKEN[:10]}...")
    logger.info(f"   🛒 Lolz Merchant ID: {LOLZ_MERCHANT_ID}")
    logger.info(f"   ⚡ Курс: 1 TON = {TON_RATE} ₽")
    logger.info(f"   👑 Администраторы: {ADMIN_IDS}")
    logger.info(f"   🌍 Доступно стран для покупки: {len(COUNTRIES)}")
    logger.info(f"   ⏰ Доступно стран для аренды: {len(RENT_COUNTRIES)}")
    
    try:
        test_result = await lolz_api.test_connection()
        logger.info(f"   ✅ Lolz API подключение успешно! Пользователь: {test_result.get('user_id')}")
    except Exception as e:
        logger.warning(f"   ⚠️ Lolz API недоступен: {str(e)}")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
