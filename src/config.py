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

    @property
    def RUSSIAN_CITIES(self) -> list[str]:
        cities_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cities.txt")
        try:
            with open(cities_file, 'r', encoding='utf-8') as file:
                cities = [line.strip() for line in file if line.strip()]
            return cities
        except FileNotFoundError:
            print(f"Файл {cities_file} не найден. Используется список городов по умолчанию.")
            return self._get_default_cities()
        except Exception as e:
            print(f"Ошибка при чтении файла городов: {e}. Используется список городов по умолчанию.")
            return self._get_default_cities()

    def _get_default_cities(self) -> list[str]:
        """Возвращает список городов по умолчанию"""
        return [
            "Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань",
            "Нижний Новгород", "Челябинск", "Самара", "Омск", "Ростов-на-Дону",
            "Уфа", "Красноярск", "Воронеж", "Пермь", "Волгоград",
            "Краснодар", "Саратов", "Тюмень", "Тольятти", "Ижевск",
            "Барнаул", "Ульяновск", "Иркутск", "Хабаровск", "Ярославль",
            "Владивосток", "Махачкала", "Томск", "Оренбург", "Кемерово",
            "Новокузнецк", "Рязань", "Астрахань", "Набережные Челны", "Пенза",
            "Киров", "Липецк", "Чебоксары", "Балашиха", "Калининград",
            "Тула", "Курск", "Севастополь", "Сочи", "Ставрополь",
            "Улан-Удэ", "Тверь", "Магнитогорск", "Иваново", "Брянск",
            "Белгород", "Сургут", "Владимир", "Нижний Тагил", "Архангельск",
            "Чита", "Калуга", "Симферополь", "Смоленск", "Волжский",
            "Саранск", "Череповец", "Курган", "Орёл", "Вологда",
            "Владикавказ", "Якутск", "Подольск", "Грозный", "Мурманск",
            "Тамбов", "Петрозаводск", "Нижневартовск", "Кострома", "Новороссийск",
            "Йошкар-Ола", "Химки", "Таганрог", "Сыктывкар", "Нальчик",
            "Шахты", "Дзержинск", "Орск", "Братск", "Ангарск",
            "Энгельс", "Благовещенск", "Старый Оскол", "Великий Новгород", "Королёв",
            "Псков", "Бийск", "Южно-Сахалинск", "Прокопьевск", "Рыбинск",
            "Балаково", "Армавир", "Люберцы", "Северодвинск", "Абакан"
        ]

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