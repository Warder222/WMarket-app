from datetime import datetime, timezone

from fastapi import Request, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from starlette.responses import JSONResponse

from src.bot import send_notification_to_user
from src.config import settings
from src.database.database import async_session_maker, User, TonTransaction
from src.database.methods import (get_all_users, all_count_unread_messages, get_current_currency, set_current_currency, get_balance_user_info,
                                  add_ton_balance, get_user_ton_transactions, create_ton_transaction, get_user_active_deals_count)
from src.endpoints._endpoints_config import wmarket_router, templates
from src.tonapi import TonapiClient, withdraw_ton_request
from src.utils import decode_jwt, is_admin_new

tonapi = TonapiClient(api_key=settings.TONAPI_KEY)


@wmarket_router.get("/wallet")
async def wallet_page(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

            context = {
                "request": request,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "is_chat_page": True,
                "tg_id": payload.get("tg_id"),
                "recipient_address": settings.WALLET_ADDRESS,
                "ton_manifest_url": settings.TON_MANIFEST_URL,
                "active_deals_count": active_deals_count
            }
            return templates.TemplateResponse("wallet.html", context=context)

    response = RedirectResponse(url="/", status_code=303)
    return response


@wmarket_router.get("/get_wallet_balance")
async def get_wallet_balance(request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    try:
        payload = await decode_jwt(session_token)
        user_data = await get_balance_user_info(payload.get('tg_id'))
        if not user_data:
            return JSONResponse({"status": "error", "message": "User not found"}, status_code=404)

        rub_balance = float(user_data[0]) if user_data[0] is not None else 0.0
        ton_balance = float(user_data[1]) if user_data[1] is not None else 0.0
        currency = user_data[2] if user_data[2] else 'rub'

        return JSONResponse({
            "status": "success",
            "rub_balance": rub_balance,
            "ton_balance": ton_balance,
            "balance": rub_balance if currency == 'rub' else ton_balance,
            "currency": currency
        })
    except Exception as e:
        print(f"Error getting wallet balance: {e}")
        return JSONResponse({"status": "error", "message": "Server error"}, status_code=500)


@wmarket_router.post("/set_currency")
async def set_currency(request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()
    currency = data.get("currency")

    if currency not in ['rub', 'ton']:
        return JSONResponse({"status": "error", "message": "Invalid currency"}, status_code=400)

    await set_current_currency(payload.get("tg_id"), currency)
    return JSONResponse({"status": "success"})


@wmarket_router.get("/get_currency")
async def get_currency(request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    currency = await get_current_currency(payload.get("tg_id"))

    return JSONResponse({
        "status": "success",
        "currency": currency
    })


@wmarket_router.get("/get_ton_transactions")
async def get_ton_transactions(request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    transactions = await get_user_ton_transactions(payload.get("tg_id"))

    return JSONResponse({
        "status": "success",
        "transactions": [
            {
                "id": tx.id,
                "amount": tx.amount,
                "type": tx.transaction_type,
                "status": tx.status,
                "created_at": tx.created_at.isoformat(),
            }
            for tx in transactions
        ]
    })


#payment$ton____________________________________________________________________________________________________________
@wmarket_router.post("/deposit_ton")
async def deposit_ton(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()
    amount = float(data.get("amount", 0))

    if amount <= 0:
        return JSONResponse({"status": "error", "message": "Invalid amount"}, status_code=400)

    async with async_session_maker() as session:
        try:
            transaction = await create_ton_transaction(
                payload.get("tg_id"),
                amount,
                "deposit"
            )

            tx_info = await tonapi._make_request(
                "GET",
                f"v2/blockchain/accounts/{settings.WALLET_ADDRESS}/transactions",
                params={
                    "limit": 1,
                    "sort_order": "desc"
                }
            )

            tx_found = False
            for tx in tx_info['transactions']:
                if tx["account"]["address"] == settings.WALLET_CHECK_ADDRESS:
                    if abs(tx['credit_phase']["credit"] - (amount * 1000000000)) <= 0.01:
                        tx_found = True

            if not tx_found:
                return JSONResponse(
                    {
                        "status": "pending",
                        "message": "Transaction not yet confirmed. Your balance will update automatically."
                    },
                    status_code=202
                )

            user = await session.execute(select(User).where(User.tg_id == payload.get("tg_id")))
            user = user.scalar_one_or_none()
            await add_ton_balance(payload.get("tg_id"), amount)

            await session.execute(
                update(TonTransaction)
                .where(TonTransaction.id == transaction.id)
                .values(status="completed")
            )
            await session.commit()

            await send_notification_to_user(
                payload.get("tg_id"),
                f"💰 На ваш счёт WMarket поступили средства: {amount} TON"
            )

            return JSONResponse({
                "status": "success",
                "new_balance": user.ton_balance
            })

        except Exception as e:
            print(f"Error processing TON deposit: {e}")
            await session.rollback()
            return JSONResponse(
                {"status": "error", "message": "Transaction processing error"},
                status_code=500
            )


@wmarket_router.post("/withdraw_ton")
async def withdraw_ton(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    try:
        payload = await decode_jwt(session_token)
        data = await request.json()
        amount = float(data.get("amount", 0))
        address = data.get("address", "")

        async with async_session_maker() as session:
            try:
                tx = await create_ton_transaction(
                    payload.get("tg_id"),
                    amount,
                    "withdraw"
                )

                user = await session.execute(select(User).where(User.tg_id == payload.get("tg_id")))
                user = user.scalar_one_or_none()

                if not user:
                    return JSONResponse({"status": "error", "message": "User not found"}, status_code=404)

                if user.ton_balance < amount:
                    return JSONResponse(
                        {"status": "error", "message": "Недостаточно средств на балансе"},
                        status_code=400
                    )

                withdraw_result = await withdraw_ton_request(address, amount)

                if not withdraw_result or not withdraw_result.get("status"):
                    error_msg = withdraw_result.get("error", "Неизвестная ошибка")
                    await session.execute(
                        update(TonTransaction)
                        .where(TonTransaction.id == tx.id)
                        .values(status="failed")
                    )
                    await session.commit()
                    return JSONResponse({
                        "status": "failed",
                        "message": f"Не удалось выполнить вывод: {error_msg}"
                    })

                user.ton_balance -= amount

                await session.execute(
                    update(TonTransaction)
                    .where(TonTransaction.id == tx.id)
                    .values(status="completed")
                )

                await session.commit()

                await send_notification_to_user(
                    payload.get("tg_id"),
                    f"✅ {amount} TON успешно отправлены на адрес {address[:6]}...{address[-4:]}"
                )

                return JSONResponse({
                    "status": "success",
                    "message": "Средства успешно отправлены"
                })

            except Exception as e:
                await session.rollback()
                print(f"Error processing withdrawal: {e}")
                return JSONResponse({
                    "status": "error",
                    "message": "Внутренняя ошибка сервера"
                }, status_code=500)

    except ValueError:
        return JSONResponse(
            {"status": "error", "message": "Неверный формат суммы"},
            status_code=400
        )
    except Exception as e:
        print(f"Error in withdraw_ton endpoint: {e}")
        return JSONResponse(
            {"status": "error", "message": "Internal server error"},
            status_code=500
        )
#_______________________________________________________________________________________________________________________