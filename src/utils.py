import json
from datetime import datetime, timezone, timedelta
import jwt
from src.config import settings
from urllib.parse import parse_qs
import requests

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


async def is_admin(tg_id):
    if str(tg_id) in [admin for admin in settings.ADMINS.split(",")]:
        return True
    else:
        return False

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