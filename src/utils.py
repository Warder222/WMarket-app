import json
from datetime import datetime, timezone, timedelta
import jwt
from sqlalchemy import select

from src.config import settings
from urllib.parse import parse_qs
import requests

from src.database.database import async_session_maker, AdminRole

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM


def parse_init_data(init_data):
    parsed = parse_qs(init_data)
    if 'user' not in parsed:
        return None
    try:
        start_param = parsed.get("start_param", [None])[0][4:]
    except TypeError as exc:
        start_param = None
        print(exc)
    user_json = parsed['user'][0]
    user_data = json.loads(user_json)
    return {
        "tg_id": user_data.get("id"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
        "username": user_data.get("username"),
        "photo_url": user_data.get("photo_url"),
        "ref_code": start_param
    }


async def encode_jwt(data: dict):
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    data.update({"exp": expire})
    return jwt.encode(data, key=SECRET_KEY, algorithm=ALGORITHM)


async def decode_jwt(token):
    try:
        return jwt.decode(token, key=SECRET_KEY, algorithms=ALGORITHM)
    except Exception as e:
        return {"sub": str(e)}


async def get_ton_to_rub_rate():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": "the-open-network",
        "vs_currencies": "rub"
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()
        rate = data["the-open-network"]["rub"]
        return rate
    except Exception as e:
        print("Ошибка при получении данных:", e)
        return None


async def is_admin_new(tg_id):
    """Возвращает роль админа: founder, chat_moderator и т.д. или None"""
    tg_id = int(tg_id)

    # Проверяем, является ли пользователь founder (из .env)
    if str(tg_id) in [admin.strip() for admin in settings.ADMINS.split(",") if admin.strip()]:
        return "founder"

    # Проверяем базу данных
    async with async_session_maker() as session:
        result = await session.execute(select(AdminRole).where(AdminRole.user_id == tg_id))
        role = result.scalar_one_or_none()
        return role.role if role else None


def can_moderate_chats(role):
    return role in ["founder", "chat_moderator"]

def can_moderate_products(role):
    return role in ["founder", "product_moderator"]

def can_moderate_reviews(role):
    return role in ["founder", "review_moderator"]

def can_moderate_deals(role):
    return role in ["founder", "deal_moderator"]

def can_manage_admins(role):
    return role == "founder"