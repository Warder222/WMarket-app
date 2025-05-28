import json
import jwt
from urllib.parse import parse_qs

from src.config import settings

key = settings.SECRET_KEY
algorithm = settings.ALGORITHM


async def encode_jwt(data: dict):
    return jwt.encode(data, key=key, algorithm=algorithm)


async def decode_jwt(token):
    try:
        return jwt.decode(token, key=key, algorithms=algorithm)
    except Exception as e:
        return {"sub": str(e)}


def parse_init_data(init_data):
    parsed = parse_qs(init_data)
    if 'user' not in parsed:
        return None

    user_json = parsed['user'][0]
    user_data = json.loads(user_json)
    return {
        "id": user_data.get("id"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
        "username": user_data.get("username"),
        "photo_url": user_data.get("photo_url"),
    }