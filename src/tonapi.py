import asyncio
from typing import Optional, Dict, Any
import httpx
from datetime import datetime, timedelta
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

    # async def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
    #     """Get transaction details by hash"""
    #     try:
    #         logger.info(f"Fetching transaction {tx_hash}")
    #
    #         # Сначала пробуем новый API
    #         result = await self._make_request(
    #             "GET",
    #             f"v2/blockchain/transactions/{tx_hash}"
    #         )
    #
    #         if result is None:
    #             logger.debug("Trying v1 API as fallback")
    #             result = await self._make_request(
    #                 "GET",
    #                 f"v1/blockchain/transactions/{tx_hash}"
    #             )
    #
    #         return result
    #
    #     except Exception as e:
    #         logger.error(f"Error getting transaction: {e}")
    #         return None
    #
    # async def parse_transaction_boc(self, boc: str) -> Optional[Dict[str, Any]]:
    #     """Parse raw transaction BOC"""
    #     try:
    #         logger.info("Parsing transaction BOC")
    #         return await self._make_request(
    #             "POST",
    #             "v2/blockchain/transactions/parse",
    #             json={"boc": boc}
    #         )
    #     except Exception as e:
    #         logger.error(f"Error parsing BOC: {e}")
    #         return None

    # async def get_account_transactions(self, address: str, limit: int = 10, min_lt: int = None) -> Optional[
    #     Dict[str, Any]]:
    #     """Get transactions for an account"""
    #     try:
    #         params = {
    #             "limit": limit,
    #             "sort": "desc"  # Сначала новые транзакции
    #         }
    #
    #         if min_lt:
    #             params["min_lt"] = min_lt
    #
    #         logger.info(f"Fetching transactions for {address}")
    #         return await self._make_request(
    #             "GET",
    #             f"v2/accounts/{address}/transactions",
    #             params=params
    #         )
    #     except Exception as e:
    #         logger.error(f"Error getting account transactions: {e}")
    #         return None

    async def get_last_transaction_lt(self, address: str) -> Optional[int]:
        """Get the last transaction lt for an account"""
        try:
            await asyncio.sleep(10)
            logger.info(f"Fetching last LT for {address}")
            result = await self._make_request(
                "GET",
                f"v2/blockchain/accounts/{address}/transactions?limit=1&sort_order=desc"
            )
            print(f"\n\n{result}\n\n")
            if result:
                return result.get('last_activity_lt')

            return None

        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None

    # async def verify_transaction(
    #         self,
    #         recipient: str,
    #         amount: float,
    #         tx_hash: str = None,
    #         boc: str = None,
    #         memo: str = None
    # ) -> Dict[str, Any]:
    #     """
    #     Verify transaction with multiple fallback methods
    #     Returns:
    #         {
    #             "status": "found|pending|not_found",
    #             "tx_data": {...}  # transaction details if found
    #         }
    #     """
    #     try:
    #         # 1. Попробуем найти по BOC
    #         if boc:
    #             parsed = await self.parse_transaction_boc(boc)
    #             if parsed:
    #                 return {
    #                     "status": "found",
    #                     "tx_data": parsed
    #                 }
    #
    #         # 2. Попробуем найти по хешу
    #         if tx_hash:
    #             tx_info = await self.get_transaction(tx_hash)
    #             if tx_info:
    #                 return {
    #                     "status": "found",
    #                     "tx_data": tx_info
    #                 }
    #
    #         # 3. Проверим последние транзакции получателя
    #         last_lt = await self.get_last_transaction_lt(recipient)
    #         txs = await self.get_account_transactions(
    #             recipient,
    #             limit=5,
    #             min_lt=last_lt
    #         )
    #
    #         if txs and 'transactions' in txs:
    #             for tx in txs['transactions']:
    #                 # Проверяем совпадение по сумме и мемо
    #                 tx_amount = float(tx.get('transaction', {}).get('total', 0)) / 1e9
    #
    #                 if (abs(tx_amount - amount) < 0.01 and  # Допуск 0.01 TON
    #                         (not memo or tx.get('memo') == memo)):
    #                     return {
    #                         "status": "found",
    #                         "tx_data": tx
    #                     }
    #
    #         return {"status": "not_found"}
    #
    #     except Exception as e:
    #         logger.error(f"Verification error: {e}")
    #         return {"status": "error", "message": str(e)}