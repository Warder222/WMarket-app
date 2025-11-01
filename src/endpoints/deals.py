from datetime import datetime, timezone

from fastapi import Cookie, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from starlette.responses import JSONResponse

from src.bot import send_notification_to_user
from src.config import settings
from src.database.database import Deal, Product, Review, User, async_session_maker, TonTransaction
from src.database.methods import (all_count_unread_messages, archive_product_post, get_all_users,
                                  get_user_active_deals, get_user_active_deals_count, get_user_info_new)
from src.endpoints._endpoints_config import templates, wmarket_router
from src.utils import decode_jwt, is_admin_new


@wmarket_router.get("/deals")
async def deals(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            tab = request.query_params.get('tab', 'active')

            active_deals = await get_user_active_deals(payload.get("tg_id"))

            completed_deals = []
            async with async_session_maker() as session:
                query_user_id = payload.get("tg_id")
                result = await session.execute(
                    select(Deal)
                    .where(
                        (Deal.seller_id == query_user_id) | (Deal.buyer_id == query_user_id),
                        Deal.status.in_(["completed", "completed_by_admin", "cancelled", "cancelled_by_admin"])
                    )
                    .order_by(desc(Deal.completed_at if Deal.completed_at is not None else Deal.created_at))
                )
                deals = result.scalars().all()

                deal_list = []
                for deal in deals:
                    amount = deal.amount
                    if deal.currency == 'meet':
                        product = await session.execute(select(Product).where(Product.id == deal.product_id))
                        product = product.scalar_one_or_none()
                        if product:
                            amount = product.product_price

                    seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
                    seller = seller.scalar_one_or_none()
                    buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
                    buyer = buyer.scalar_one_or_none()

                    status_text = ""
                    if deal.status == 'completed':
                        if deal.admin_decision == 'for_seller':
                            status_text = "Завершена администратором (в пользу продавца)"
                        else:
                            status_text = "Завершена"
                    else:
                        if deal.admin_decision == 'for_buyer':
                            status_text = "Отменена администратором (в пользу покупателя)"
                        else:
                            status_text = "Отменена"

                    deal_list.append({
                        "id": deal.id,
                        "product_name": deal.product_name,
                        "seller_id": deal.seller_id,
                        "buyer_id": deal.buyer_id,
                        "seller_username": seller.first_name if seller else "Unknown",
                        "buyer_username": buyer.first_name if buyer else "Unknown",
                        "currency": deal.currency,
                        "amount": deal.rub_amount if deal.currency == 'rub' and deal.rub_amount else deal.amount,
                        "status": deal.status,
                        "status_text": status_text,
                        "created_at": deal.created_at,
                        "completed_at": deal.completed_at,
                        "is_reserved": deal.is_reserved,
                        "reservation_amount": deal.reservation_amount,
                        "admin_decision": deal.admin_decision,
                        "original_amount": deal.amount  # Сохраняем оригинальную сумму для внутренних расчетов
                    })

                completed_deals = deal_list

            reserved_deals = None
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Deal)
                    .where(Deal.is_reserved == True)
                    .where(
                        (Deal.buyer_id == payload.get("tg_id")) |
                        (Deal.seller_id == payload.get("tg_id"))
                    )
                    .order_by(Deal.reservation_until)
                )
                reserved_deals = result.scalars().all()

            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

            context = {
                "request": request,
                "active_deals": active_deals,
                "completed_deals": completed_deals,
                "reserved_deals": reserved_deals,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "current_tab": tab,
                "user_tg_id": payload.get("tg_id"),
                "active_deals_count": active_deals_count
            }
            return templates.TemplateResponse("deals.html", context=context)

    response = RedirectResponse(url="/", status_code=303)
    return response


@wmarket_router.post("/confirm_deal")
async def confirm_deal(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()
    deal_id = data.get("deal_id")
    review_text = data.get("review")
    rating = data.get("rating")

    if rating == "plus":
        rating = 1
    else:
        rating = -1

    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Deal).where(Deal.id == int(deal_id)))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if deal.buyer_id != payload.get("tg_id"):
                return JSONResponse(
                    {"status": "error", "message": "Only buyer can confirm deal"},
                    status_code=403
                )

            if deal.status != "active":
                return JSONResponse(
                    {"status": "error", "message": "Deal is not active"},
                    status_code=400
                )

            # Для рублевых сделок проверяем подтверждение оплаты
            if deal.currency == 'rub' and not deal.rub_payment_confirmed:
                return JSONResponse(
                    {"status": "error", "message": "Wait for seller to confirm rub payment"},
                    status_code=400
                )

            comsa = settings.COMMISSION

            if deal.currency == 'rub':
                seller_amount = deal.amount * comsa
                market_fee = deal.amount * (1 - comsa)

                # Возвращаем залог продавцу (частично, с учетом комиссии)
                seller_refund = seller_amount

                # Создаем транзакцию для возврата залога продавцу
                refund_transaction = TonTransaction(
                    user_id=deal.seller_id,
                    amount=seller_refund,
                    transaction_type="collateral_refund",
                    status="completed"
                )
                session.add(refund_transaction)

            else:
                seller_amount = deal.amount * comsa
                market_fee = deal.amount * (1 - comsa)

                # Переводим средства продавцу
                seller_payment_transaction = TonTransaction(
                    user_id=deal.seller_id,
                    amount=seller_amount,
                    transaction_type="sale_revenue",
                    status="completed"
                )
                session.add(seller_payment_transaction)

            deal.status = "completed"
            deal.completed_at = datetime.now(timezone.utc)

            seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
            seller = seller.scalar_one_or_none()

            if deal.currency == 'rub':
                seller.ton_balance += seller_amount
            elif deal.currency == 'ton':
                if seller.earned_ton is None:
                    seller.earned_ton = 0.0
                seller.earned_ton += seller_amount
                seller.ton_balance += seller_amount

            review = Review(
                deal_id=deal.id,
                from_user_id=deal.buyer_id,
                to_user_id=deal.seller_id,
                product_id=deal.product_id,
                rating=rating,
                text=review_text
            )
            session.add(review)

            await session.commit()
            await archive_product_post(deal.product_id)

            buyer_info_arr = await get_user_info_new(deal.buyer_id)
            seller_info_arr = await get_user_info_new(deal.seller_id)

            await send_notification_to_user(
                deal.seller_id,
                f"✅ Сделка завершена!\n\n"
                f"📌 Товар: {deal.product_name}\n"
                f"💰 {"Залог возвращен" if deal.currency == 'rub' else "Сумма"}: {seller_amount:.4f} TON (комиссия: {market_fee:.4f})\n"
                f"👤 {buyer_info_arr["first_name"]} подтвердил получение товара.\n\n"
                f"Средства зачислены на ваш баланс!"
            )

            await send_notification_to_user(
                deal.buyer_id,
                f"✅ Вы подтвердили сделку!\n\n"
                f"📌 Товар: {deal.product_name}\n"
                f"💰 Сумма: {deal.amount} {"TON" if deal.currency == 'ton' else "₽"}\n"
                f"👤 Продавец: {seller_info_arr["first_name"] if seller_info_arr else 'неизвестен'}\n\n"
                f"Ваш отзыв отправлен на модерацию."
            )

            return {"status": "success"}

        except Exception as e:
            await session.rollback()
            print(f"Error confirming deal: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.post("/confirm_rub_payment")
async def confirm_rub_payment(
    request: Request,
    session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()
    deal_id = data.get("deal_id")

    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Deal).where(Deal.id == int(deal_id)))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if deal.seller_id != payload.get("tg_id"):
                return JSONResponse(
                    {"status": "error", "message": "Only seller can confirm rub payment"},
                    status_code=403
                )

            if deal.currency != 'rub':
                return JSONResponse(
                    {"status": "error", "message": "This deal is not in rubles"},
                    status_code=400
                )

            if deal.rub_payment_confirmed:
                return JSONResponse(
                    {"status": "error", "message": "Payment already confirmed"},
                    status_code=400
                )

            # Помечаем оплату как подтвержденную
            deal.rub_payment_confirmed = True

            await session.commit()

            buyer_info = await get_user_info_new(deal.buyer_id)

            await send_notification_to_user(
                deal.buyer_id,
                f"✅ Продавец подтвердил получение рублевого платежа!\n\n"
                f"📌 Товар: {deal.product_name}\n"
                f"💰 Сумма: {deal.amount} TON (эквивалент)\n\n"
                f"Теперь вы можете подтвердить получение товара."
            )

            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error confirming rub payment: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.get("/check_deal_status")
async def check_deal_status(request: Request, deal_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    async with async_session_maker() as session:
        deal = await session.execute(select(Deal).where(Deal.id == deal_id))
        deal = deal.scalar_one_or_none()

        if not deal:
            return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

        # Проверяем истекло ли время расширения
        if deal.time_extension_until and deal.time_extension_until < datetime.now(timezone.utc):
            deal.pending_cancel = True
            deal.cancel_reason = "Время на завершение сделки истекло"
            await session.commit()

        return JSONResponse({
            "status": deal.status,
            "pending_cancel": deal.pending_cancel,
            "time_extension_until": deal.time_extension_until.isoformat() if deal.time_extension_until else None,
            "currency": deal.currency,  # Добавляем валюту
            "rub_payment_confirmed": deal.rub_payment_confirmed if deal.currency == 'rub' else None  # Добавляем статус оплаты для рублевых сделок
        })


@wmarket_router.post("/request_cancel_deal")
async def request_cancel_deal(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()

    try:
        deal_id = int(data.get("deal_id"))
    except (TypeError, ValueError):
        return JSONResponse({"status": "error", "message": "Invalid deal ID"}, status_code=400)

    reason = data.get("reason")

    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if deal.status != "active":
                return JSONResponse({"status": "error", "message": "Deal is not active"}, status_code=400)

            if deal.pending_cancel:
                return JSONResponse({"status": "error", "message": "Cancel request already sent"}, status_code=400)

            deal.pending_cancel = True
            deal.cancel_reason = reason
            deal.cancel_request_by = payload.get("tg_id")

            await session.commit()

            other_user_id = deal.buyer_id if payload.get("tg_id") == deal.seller_id else deal.seller_id

            await send_notification_to_user(
                payload.get("tg_id"),
                f"✅ Ваш запрос на отмену сделки по товару '{deal.product_name}' отправлен на модерацию.\n\n"
                f"Причина: {reason}\n\n"
                f"Ожидайте решения администратора."
            )

            await send_notification_to_user(
                other_user_id,
                f"⚠️ Вторая сторона подала запрос на отмену сделки по товару '{deal.product_name}'.\n\n"
                f"Причина: {reason}\n\n"
                f"Сделка приостановлена до решения администратора."
            )

            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error requesting deal cancellation: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.post("/complete_reservation")
async def complete_reservation(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()
    deal_id = int(data.get("deal_id"))

    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if not deal.is_reserved:
                return JSONResponse({"status": "error", "message": "Deal is not reserved"}, status_code=400)

            if deal.buyer_id != payload.get("tg_id"):
                return JSONResponse({"status": "error", "message": "Not your reservation"}, status_code=403)

            buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
            buyer = buyer.scalar_one_or_none()

            remaining_amount = deal.amount - deal.reservation_amount

            if deal.currency == 'ton':
                if buyer.ton_balance < remaining_amount:
                    return JSONResponse(
                        {"status": "error", "message": "Недостаточно средств на TON балансе"},
                        status_code=400
                    )
                buyer.ton_balance -= remaining_amount

                # Создаем транзакцию для оплаты оставшейся суммы
                payment_transaction = TonTransaction(
                    user_id=deal.buyer_id,
                    amount=-remaining_amount,
                    transaction_type="reservation_completion_payment",
                    status="completed"
                )
                session.add(payment_transaction)

                # Создаем транзакцию для перевода суммы бронирования продавцу
                # (бронь уже была оплачена ранее при создании брони)
                reservation_to_seller_transaction = TonTransaction(
                    user_id=deal.seller_id,
                    amount=deal.reservation_amount,
                    transaction_type="reservation_transfer_to_seller",
                    status="completed"
                )
                session.add(reservation_to_seller_transaction)

            deal.is_reserved = False
            deal.reservation_until = None
            deal.status = "active"

            product = await session.execute(select(Product).where(Product.id == deal.product_id))
            product = product.scalar_one_or_none()
            if product:
                product.reserved = False
                product.reserved_until = None
                product.reserved_by = None

            await session.commit()

            await send_notification_to_user(
                deal.seller_id,
                f"💰 Покупатель выкупил забронированный товар!\n\n"
                f"📌 Товар: {deal.product_name}\n"
                f"💰 Полная сумма: {deal.amount} {deal.currency.upper()}\n"
                f"💰 Из них бронь: {deal.reservation_amount} {deal.currency.upper()}\n"
                f"👤 Покупатель: {buyer.first_name or 'без username'}\n\n"
                f"Выдайте товар покупателю, чтобы он мог подтвердить сделку."
            )

            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error completing reservation: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.post("/cancel_reservation")
async def cancel_reservation(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()
    deal_id = int(data.get("deal_id"))
    is_expired = data.get("is_expired", False)

    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if not deal.is_reserved:
                return JSONResponse({"status": "error", "message": "Deal is not reserved"}, status_code=400)

            if not is_expired and deal.buyer_id != payload.get("tg_id"):
                return JSONResponse({"status": "error", "message": "Not your reservation"}, status_code=403)

            buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
            buyer = buyer.scalar_one_or_none()

            refund_amount = deal.reservation_amount * 2 / 3

            if deal.currency == 'ton':
                buyer.ton_balance += refund_amount

                # Создаем транзакцию для возврата средств при отмене брони
                refund_transaction = TonTransaction(
                    user_id=deal.buyer_id,
                    amount=refund_amount,
                    transaction_type="reservation_refund",
                    status="completed"
                )
                session.add(refund_transaction)

            deal.is_reserved = False
            deal.reservation_until = None
            deal.status = "cancelled"

            product = await session.execute(select(Product).where(Product.id == deal.product_id))
            product = product.scalar_one_or_none()
            if product:
                product.reserved = False
                product.reserved_until = None
                product.reserved_by = None

            await session.commit()

            if not is_expired:
                await send_notification_to_user(
                    deal.buyer_id,
                    f"❌ Вы отменили бронь товара\n\n"
                    f"📌 Товар: {deal.product_name}\n"
                    f"💰 Возвращено: {refund_amount} {deal.currency.upper()}\n"
                    f"💸 Удержан штраф: {deal.reservation_amount - refund_amount} {deal.currency.upper()}"
                )

                await send_notification_to_user(
                    deal.seller_id,
                    f"ℹ️ Покупатель отменил бронь товара\n\n"
                    f"📌 Товар: {deal.product_name}\n"
                    f"💰 Сумма брони: {deal.reservation_amount} {deal.currency.upper()}\n"
                    f"👤 Покупатель: {buyer.first_name or 'без username'}"
                )
            else:
                await send_notification_to_user(
                    deal.buyer_id,
                    f"⌛ Время бронирования истекло\n\n"
                    f"📌 Товар: {deal.product_name}\n"
                    f"💰 Возвращено: {refund_amount} {deal.currency.upper()}\n"
                    f"💸 Удержан штраф: {deal.reservation_amount - refund_amount} {deal.currency.upper()}"
                )

                await send_notification_to_user(
                    deal.seller_id,
                    f"⌛ Время бронирования истекло\n\n"
                    f"📌 Товар: {deal.product_name}\n"
                    f"💰 Сумма брони: {deal.reservation_amount} {deal.currency.upper()}\n"
                    f"👤 Покупатель: {buyer.first_name or 'без username'}"
                )

            return JSONResponse({
                "status": "success",
                "refunded_amount": refund_amount,
                "currency": deal.currency
            })

        except Exception as e:
            await session.rollback()
            print(f"Error canceling reservation: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )