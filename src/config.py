import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import WebSocket
from typing import Dict


class Settings(BaseSettings):
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str

    ALGORITHM: str
    SECRET_KEY: str

    ADMINS: str

    TG_BOT_TOKEN: str
    BOT_USERNAME: str
    MINI_APP_URL: str

    TONAPI_KEY: str
    WALLET_ADDRESS: str
    WALLET_CHECK_ADDRESS: str
    WALLET_MNEMONIC: str

    TON_MANIFEST_URL: str

    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    UPLOAD_DIR: str = os.path.join(BASE_DIR, "static/uploads")

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    )

    def get_db_url(self):
        return (f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@"
                f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}")


settings = Settings()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections.values():
            await connection.send_text(message)

    def is_connected(self, user_id: str) -> bool:
        """Проверяет, подключен ли пользователь к WebSocket"""
        return user_id in self.active_connections

manager = ConnectionManager()