import json
from datetime import datetime, timezone, timedelta
import jwt
from urllib.parse import parse_qs
from src.config import settings

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM


def parse_init_data(init_data):
    parsed = parse_qs(init_data)
    if 'user' not in parsed:
        return None

    user_json = parsed['user'][0]
    user_data = json.loads(user_json)
    return {
        "tg_id": user_data.get("id"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
        "username": user_data.get("username"),
        "photo_url": user_data.get("photo_url"),
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