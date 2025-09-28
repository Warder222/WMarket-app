import os

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    COMMISSION: float

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    )

    def get_db_url(self):
        return (f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@"
                f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}")

settings = Settings()