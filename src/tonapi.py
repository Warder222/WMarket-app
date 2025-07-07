import asyncio
from typing import Dict, Any
import httpx
import logging
from fastapi import HTTPException

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
                await asyncio.sleep(15)
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