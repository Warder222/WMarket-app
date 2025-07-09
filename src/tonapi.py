import asyncio
import time
from typing import Dict, Any
import httpx
import logging
from fastapi import HTTPException
from pytoniq import LiteBalancer, WalletV4R2

from src.config import settings

logger = logging.getLogger(__name__)


class TonapiClient:
    def __init__(self, api_key: str, base_url: str = "https://tonapi.io/"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/') + '/'
        self.client = httpx.AsyncClient(timeout=30.0)
        self.max_retries = 3
        self.rate_limit_delay = 0.5  # Задержка между запросами в секундах

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        await self.client.aclose()

    async def _make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None,
                            json: Dict[str, Any] = None):
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }

        for attempt in range(self.max_retries):
            try:
                # logger.debug(f"Request attempt {attempt + 1} to {url}")
                await asyncio.sleep(10)
                response = await self.client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json
                )

                if response.status_code == 404:
                    logger.debug("Resource not found (404)")
                    return None

                response
                return response.json()

            except httpx.HTTPStatusError as e:
                # logger.warning(f"HTTP error {e.response.status_code}: {e}")
                if attempt == self.max_retries - 1:
                    raise HTTPException(
                        status_code=502,
                        detail=f"TonAPI error: {e.response.text}"
                    )

            except httpx.RequestError as e:
                # logger.warning(f"Request error: {e}")
                if attempt == self.max_retries - 1:
                    raise HTTPException(
                        status_code=503,
                        detail="TonAPI unavailable"
                    )

            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                if attempt == self.max_retries - 1:
                    raise HTTPException(
                        status_code=500,
                        detail="Internal server error"
                    )

            await asyncio.sleep(self.rate_limit_delay * (attempt + 1))

        return None


async def withdraw_ton_request(wallet_address, amount):
    provider = None
    wallet = None
    try:
        mnemonic = settings.WALLET_MNEMONIC.split()

        # Настраиваем логгирование для pytoniq
        logging.getLogger('pytoniq').setLevel(logging.WARNING)

        # Подключаемся с таймаутом
        provider = LiteBalancer.from_mainnet_config(trust_level=2)
        await provider.start_up()

        # Создаем кошелек с таймаутом
        wallet = await asyncio.wait_for(
            WalletV4R2.from_mnemonic(provider, mnemonics=mnemonic),
            timeout=30
        )

        # Проверяем баланс кошелька с учетом комиссии (добавляем 0.1 TON для комиссии)
        balance = await asyncio.wait_for(wallet.get_balance(), timeout=30)
        current_balance = balance / 1e9

        # Минимальная сумма для вывода с учетом комиссии
        min_amount_with_fee = amount + 0.1

        if current_balance < min_amount_with_fee:
            logger.warning(f"Insufficient wallet balance: {current_balance} < {min_amount_with_fee}")
            return False

        # Отправляем TON (переводим в нанотоны)
        amount_nano = int(amount * 1e9)
        await asyncio.wait_for(
            wallet.transfer(
                destination=wallet_address,
                amount=amount_nano,
                body="",
            ),
            timeout=60
        )

        return True

    except asyncio.TimeoutError:
        logger.error("TON operation timed out")
        return False
    except Exception as e:
        logger.error(f"Error in withdraw_ton_request: {e}")
        return False
    finally:
        if wallet:
            try:
                await wallet.provider.close_all()
            except:
                pass
        if provider:
            try:
                await provider.close_all()
            except:
                pass

async def connect_wallet(mnemonic):
    try:
        for _ in range(5):
            try:
                print(f"Попытка №{_ + 1}")
                provider = LiteBalancer.from_mainnet_config(trust_level=2)
                await provider.start_up()
                wallet = await WalletV4R2.from_mnemonic(provider, mnemonics=mnemonic)
                print("Подключился")
                return wallet
            except Exception as e:
                print(f"Ошибка подключения: {e}")
                time.sleep(1)
    except Exception as e:
        print(f"Не удалось подключиться после нескольких попыток ({e})")

async def check_balance(wallet):
    balance = await wallet.get_balance()
    return "{:.2f}".format(balance / 1e9)

async def send_ton(wallet, destination_address: str, amount_ton: float):
    try:
        amount_nano = int(amount_ton * 1e9)
        print(f"Попытка отправки {amount_ton} TON на адрес {destination_address}")

        await wallet.transfer(
            destination=destination_address,
            amount=amount_nano,
            body="",
        )

        print(f"Успешно отправлено {amount_ton} TON на адрес {destination_address}")
    except Exception as e:
        print(f"Ошибка при отправке TON: {e}")
        raise