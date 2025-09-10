
from datetime import datetime, timezone

from fastapi import Request, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette.responses import JSONResponse

from src.bot import send_notification_to_user
from src.database.database import async_session_maker, User, Deal, Review, Product
from src.database.methods import (get_all_users, get_user_info,
                                  all_count_unread_messages, archive_product_post,
                                  get_user_active_deals, get_user_completed_deals,
                                  get_user_reserved_deals, get_user_active_deals_count)
from src.endpoints._endpoints_config import wmarket_router, templates
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
            completed_deals = await get_user_completed_deals(payload.get("tg_id"))
            reserved_deals = await get_user_reserved_deals(payload.get("tg_id"))

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
    rating = data.get("rating")
    review_text = data.get("review_text")

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

            if deal.currency == 'meet':
                deal.pending_cancel = True
                deal.cancel_reason = "Ожидает подтверждения администратором (личная встреча)"
                deal.cancel_request_by = payload.get("tg_id")

                review = Review(
                    deal_id=deal.id,
                    from_user_id=deal.buyer_id,
                    to_user_id=deal.seller_id,
                    product_id=deal.product_id,
                    rating=rating,
                    text=review_text,
                    moderated=False
                )
                session.add(review)

                await session.commit()

                buyer_info = await get_user_info(deal.buyer_id)
                seller_info = await get_user_info(deal.seller_id)

                # Уведомление продавцу
                await send_notification_to_user(
                    deal.seller_id,
                    f"⚠️ Сделка по товару '{deal.product_name}' отправлена на модерацию.\n\n"
                    f"Покупатель {buyer_info[1]} подтвердил получение товара при личной встрече.\n\n"
                    f"Администратор проверит сделку и подтвердит её завершение.\n"
                    f"По вопросам обращайтесь @wmarket_support"
                )

                # Уведомление покупателю
                await send_notification_to_user(
                    deal.buyer_id,
                    f"⚠️ Ваша сделка по товару '{deal.product_name}' отправлена на модерацию.\n\n"
                    f"Для подтверждения сделки обратитесь к @wmarket_support\n"
                    f"Администратор проверит факт передачи товара и подтвердит сделку."
                )

                return {"status": "success"}

            seller_amount = deal.amount * 0.93
            market_fee = deal.amount * 0.07

            deal.status = "completed"
            deal.completed_at = datetime.now(timezone.utc)

            seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
            seller = seller.scalar_one_or_none()

            if deal.currency == 'rub':
                if seller.earned_rub is None:
                    seller.earned_rub = 0.0
                seller.earned_rub += seller_amount
                seller.rub_balance += seller_amount
            else:
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

            buyer_info_arr = await get_user_info(deal.buyer_id)
            seller_info_arr = await get_user_info(deal.seller_id)

            await send_notification_to_user(
                deal.seller_id,
                f"✅ Сделка завершена!\n\n"
                f"📌 Товар: {deal.product_name}\n"
                f"💰 Сумма: {seller_amount:.2f} {deal.currency.upper()} (комиссия: {market_fee:.2f})\n"
                f"👤 {buyer_info_arr[1]} подтвердил получение товара.\n\n"
                f"Средства зачислены на ваш баланс!"
            )

            await send_notification_to_user(
                deal.buyer_id,
                f"✅ Вы подтвердили сделку!\n\n"
                f"📌 Товар: {deal.product_name}\n"
                f"💰 Сумма: {deal.amount} {deal.currency.upper()}\n"
                f"👤 Продавец: {seller_info_arr[1] if seller_info_arr else 'неизвестен'}\n\n"
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


@wmarket_router.get("/check_deal_status")
async def check_deal_status(request: Request, deal_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    async with async_session_maker() as session:
        deal = await session.execute(select(Deal).where(Deal.id == deal_id))
        deal = deal.scalar_one_or_none()

        if not deal:
            return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

        if deal.time_extension_until and deal.time_extension_until < datetime.now(timezone.utc):
            deal.pending_cancel = True
            deal.cancel_reason = "Время на завершение сделки истекло"
            await session.commit()

        return JSONResponse({
            "status": deal.status,
            "pending_cancel": deal.pending_cancel,
            "time_extension_until": deal.time_extension_until.isoformat() if deal.time_extension_until else None
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

            if deal.currency == 'rub':
                if buyer.rub_balance < remaining_amount:
                    return JSONResponse(
                        {"status": "error", "message": "Недостаточно средств на рублёвом балансе"},
                        status_code=400
                    )
                buyer.rub_balance -= remaining_amount
            else:
                if buyer.ton_balance < remaining_amount:
                    return JSONResponse(
                        {"status": "error", "message": "Недостаточно средств на TON балансе"},
                        status_code=400
                    )
                buyer.ton_balance -= remaining_amount

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

            if deal.currency == 'rub':
                buyer.rub_balance += refund_amount
            else:
                buyer.ton_balance += refund_amount

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