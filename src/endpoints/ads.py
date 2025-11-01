from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import and_, exists, func, select
from starlette.responses import JSONResponse

from src.bot import send_notification_to_user
from src.database.database import (Chat, ChatParticipant, Deal, Fav, Product, User, async_session_maker, TonTransaction)
from src.database.methods import (all_count_unread_messages, get_all_not_digit_categories, get_all_users,
                                  get_product_info_new, get_user_active_deals_count, get_user_info_new)
from src.endpoints._endpoints_config import templates, wmarket_router
from src.utils import can_moderate_products, decode_jwt, get_ton_to_rub_rate, is_admin_new


@wmarket_router.get('/ads/{product_id}')
async def ads_view(product_id: int, request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            product_info = {}

            async with async_session_maker() as session:
                result = await session.execute(
                    select(
                        Product.id.label("product_id"),
                        Product.tg_id,
                        Product.product_name,
                        Product.product_price,
                        Product.product_description,
                        Product.product_image_url,
                        Product.category_name,
                        Product.created_at,
                        exists().where(and_(Fav.tg_id == payload.get("tg_id"), Fav.product_id == Product.id)).label("is_fav"),
                        Product.reserved,
                        Product.reserved_by,
                        Product.reserved_until,
                        Product.reservation_amount,
                        Product.reservation_currency,
                        Product.location
                    ).where(Product.id == product_id)
                )

                if product := result.first():
                    product_info = dict(product._mapping)

            if not product_info:
                return RedirectResponse(url="/store", status_code=303)

            categories = await get_all_not_digit_categories()
            user_info = await get_user_info_new(product_info["tg_id"])
            positive_reviews = user_info["plus_rep"]
            negative_reviews = user_info["minus_rep"]
            reputation = positive_reviews - negative_reviews
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if can_moderate_products(admin_role):
                admin_res= True

            fav_count = 0
            async with async_session_maker() as db:
                try:
                    q = select(Fav).filter_by(product_id=product_id)
                    result = await db.execute(q)
                    fav_count = result.scalars()
                    fav_arr = [fav.tg_id for fav in fav_count]
                    fav_count = len(fav_arr)
                except Exception as exc:
                    print(f"Error: {exc}")

            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

            context = {
                "request": request,
                "product_info": product_info,
                "categories": categories,
                "user_tg_id": payload.get("tg_id"),
                "reputation": reputation,
                "positive_reviews": positive_reviews,
                "negative_reviews": negative_reviews,
                "user_info": user_info,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "fav_count": fav_count,
                "active_deals_count": active_deals_count
            }
            return templates.TemplateResponse("ads.html", context=context)

    return RedirectResponse(url="/store", status_code=303)


#deals__________________________________________________________________________________________________________________
@wmarket_router.get("/check_chat_exists/{product_id}")
async def check_chat_exists(product_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"exists": False}

    payload = await decode_jwt(session_token)
    buyer_id = payload.get("tg_id")

    product = await get_product_info_new(product_id, None)
    if not product:
        return {"exists": False}

    seller_id = product["tg_id"]

    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Chat)
            .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
            .where(Chat.product_id == product_id)
            .where(ChatParticipant.user_id.in_([buyer_id, seller_id]))
            .group_by(Chat.id)
            .having(func.count(ChatParticipant.user_id) == 2)
        )

        exists = result.scalar() is not None
        return {"exists": exists}


@wmarket_router.post("/create_deal")
async def create_deal(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()
    product_id = data.get("product_id")
    amount = data.get("amount")
    currency = data.get("currency")
    rub_amount = data.get("rub_amount")  # Получаем рублевую сумму

    product = await get_product_info_new(product_id, None)
    if not product:
        return JSONResponse({"status": "error", "message": "Product not found"}, status_code=404)

    seller_id = product["tg_id"]
    buyer_id = payload.get("tg_id")

    if seller_id == buyer_id:
        return JSONResponse({"status": "error", "message": "Cannot buy your own product"}, status_code=400)

    async with async_session_maker() as session:
        try:
            user = await session.execute(select(User).where(User.tg_id == buyer_id))
            user = user.scalar_one_or_none()

            # Для рублевой оплаты проверяем залог у продавца
            if currency == 'rub':
                seller = await session.execute(select(User).where(User.tg_id == seller_id))
                seller = seller.scalar_one_or_none()

                # Сумма залога = 100% стоимости товара в TON
                collateral_amount = product["product_price"]

                if seller.ton_balance < collateral_amount:
                    return JSONResponse(
                        {"status": "error",
                         "message": "У продавца недостаточно TON для обеспечения безопасности сделки. Оплата рублями невозможна."},
                        status_code=400
                    )

                # Блокируем залог у продавца
                seller.ton_balance -= collateral_amount

                # Создаем транзакцию для залога продавца
                collateral_transaction = TonTransaction(
                    user_id=seller_id,
                    amount=-collateral_amount,  # Отрицательная сумма - списание
                    transaction_type="collateral_lock",
                    status="completed"
                )
                session.add(collateral_transaction)

                amount = collateral_amount  # Сохраняем сумму в TON как залог

            elif currency == 'ton':
                if user.ton_balance < amount:
                    return JSONResponse(
                        {"status": "error", "message": "Недостаточно средств на TON балансе"},
                        status_code=400
                    )
                user.ton_balance -= amount

                # Создаем транзакцию для оплаты TON покупателем
                payment_transaction = TonTransaction(
                    user_id=buyer_id,
                    amount=-amount,  # Отрицательная сумма - списание
                    transaction_type="purchase_payment",
                    status="completed"
                )
                session.add(payment_transaction)

            deal = Deal(
                product_id=product_id,
                product_name=product["product_name"],
                seller_id=seller_id,
                buyer_id=buyer_id,
                amount=amount,  # Для RUB - сумма залога в TON, для TON - сумма оплаты
                currency=currency,
                status="active",
                created_at=datetime.now(timezone.utc),
                rub_payment_confirmed=False if currency == 'rub' else None,
                collateral_amount=collateral_amount if currency == 'rub' else None,
                rub_amount=rub_amount if currency == 'rub' else None  # Сохраняем рублевую сумму
            )
            session.add(deal)
            await session.commit()

            buyer_info = await get_user_info_new(buyer_id)

            if currency == 'rub':
                await send_notification_to_user(
                    seller_id,
                    f"💰 Товар оплачен рублями, ожидает подтверждения!\n\n"
                    f"📌 Название: {product['product_name']}\n"
                    f"💰 Сумма в рублях: {rub_amount} ₽\n"  # Используем rub_amount
                    f"💎 Залог: {collateral_amount} TON\n"
                    f"👤 Покупатель: {buyer_info['first_name'] or 'без username'}\n\n"
                    f"После получения рублевого платежа подтвердите оплату в разделе 'Сделки'."
                )

                await send_notification_to_user(
                    buyer_id,
                    f"💰 Сделка создана! Оплата рублями.\n\n"
                    f"📌 Товар: {product['product_name']}\n"
                    f"💰 Сумма: {rub_amount} ₽\n"  # Используем rub_amount
                    f"💎 Залог продавца: {collateral_amount} TON\n\n"
                    f"Переведите средства продавцу по реквизитам из чата и ожидайте подтверждения оплаты."
                )
            else:
                await send_notification_to_user(
                    seller_id,
                    f"💰 Товар оплачен в TON, и ждёт подтверждения!\n\n"
                    f"📌 Название: {product['product_name']}\n"
                    f"💰 Сумма: {amount} TON\n"
                    f"👤 Покупатель: {buyer_info['first_name'] or 'без username'}\n\n"
                    f"Выдайте товар покупателю, чтобы он мог подтвердить сделку."
                )

            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error creating deal: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.post("/reserve_product")
async def reserve_product(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()
    product_id = data.get("product_id")
    amount = data.get("amount")
    currency = data.get("currency")

    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Product).where(Product.id == product_id))
            product = result.scalar_one_or_none()

            if not product:
                return JSONResponse({"status": "error", "message": "Product not found"}, status_code=404)

            if product.reserved and product.reserved_until > datetime.now(timezone.utc):
                return JSONResponse(
                    {"status": "error", "message": "Product is already reserved"},
                    status_code=400
                )

            user = await session.execute(select(User).where(User.tg_id == payload.get("tg_id")))
            user = user.scalar_one_or_none()

            if not user:
                return JSONResponse({"status": "error", "message": "User not found"}, status_code=404)

            if currency == 'ton':
                if user.ton_balance < amount:
                    return JSONResponse(
                        {"status": "error", "message": "Insufficient TON balance"},
                        status_code=400
                    )
                user.ton_balance -= amount

                # Создаем транзакцию для бронирования
                reservation_transaction = TonTransaction(
                    user_id=payload.get("tg_id"),
                    amount=-amount,
                    transaction_type="reservation_payment",
                    status="completed"
                )
                session.add(reservation_transaction)

            product.reserved = True
            product.reserved_until = datetime.now(timezone.utc) + timedelta(hours=48)
            product.reserved_by = payload.get("tg_id")
            product.reservation_amount = amount
            product.reservation_currency = currency

            # Для бронирования используем TON как основную валюту
            deal_amount = product.product_price  # Основная цена в TON

            deal = Deal(
                product_id=product.id,
                product_name=product.product_name,
                seller_id=product.tg_id,
                buyer_id=payload.get("tg_id"),
                amount=deal_amount,
                currency='ton',  # Всегда TON для бронированных сделок
                status="reserved",
                is_reserved=True,
                reservation_amount=amount,
                reservation_until=datetime.now(timezone.utc) + timedelta(hours=48),
                created_at=datetime.now(timezone.utc)
            )
            session.add(deal)

            await session.commit()

            await send_notification_to_user(
                product.tg_id,
                f"🔒 Ваш товар '{product.product_name}' был забронирован!\n\n"
                f"👤 Покупатель: {user.first_name or 'без username'}\n"
                f"💰 Сумма брони: {amount} TON\n"
                f"⏳ Бронь действует до: {product.reserved_until.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"В течение 48 часов покупатель должен завершить сделку."
            )

            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error reserving product: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.get("/get_ton_to_rub_rate")
async def get_ton_to_rub_rate_endpoint():
    rate = await get_ton_to_rub_rate()
    if rate:
        return JSONResponse({"rate": rate})
    else:
        return JSONResponse({"status": "error", "message": "Не удалось получить курс TON/RUB"}, status_code=500)
#_______________________________________________________________________________________________________________________