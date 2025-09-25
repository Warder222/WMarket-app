import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, desc, select
from starlette.responses import JSONResponse

from src.bot import send_notification_to_user
from src.config import settings
from src.database.database import (AdminRole, ChatParticipant, ChatReport, Deal, Fav, Product, Review, User,
                                   async_session_maker)
from src.database.methods import (all_count_unread_messages, archive_product_post, block_user_post,
                                  check_user_blocked_post, get_chat_messages, get_pending_deals, get_product_info_new,
                                  get_user_active_deals_count, get_user_info_new, resolve_chat_report,
                                  update_product_post, create_system_message)
from src.endpoints._endpoints_config import templates, wmarket_router
from src.utils import (can_manage_admins, can_moderate_chats, can_moderate_deals, can_moderate_products,
                       can_moderate_reviews, decode_jwt, is_admin_new)
from src.websocket_config import manager


@wmarket_router.get("/admin/chat_reports")
async def admin_chat_reports(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return RedirectResponse(url="/", status_code=303)

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if admin_role:
        admin_res = True
    if admin_res:

        reports = []
        async with async_session_maker() as db:
            try:
                q = select(ChatReport).filter_by(resolved=False).order_by(desc(ChatReport.created_at))
                result = await db.execute(q)
                reports = [{"id": report.id,
                            "chat_id": report.chat_id,
                            "reporter_id": report.reporter_id,
                            "reporter_first_name": None,
                            "reason": report.reason,
                            "created_at": report.created_at,
                            "resolved": report.resolved,
                            "admin_id": report.admin_id} for report in result.scalars().all()]
                for rep in reports:
                    reporter_info = await get_user_info_new(rep["reporter_id"])
                    rep["reporter_first_name"] = reporter_info["first_name"]

            except Exception as exc:
                print(f"Error getting chat reports: {exc}")

        all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))

        moderation_products = []
        async with async_session_maker() as db:
            try:
                result = await db.execute(
                    select(Product)
                    .filter_by(active=False)
                    .order_by(desc(Product.created_at))
                )

                for prod in result.scalars():
                    seller_info = await get_user_info_new(prod.tg_id)
                    moderation_products.append({'product_id': prod.id,
                                                'product_name': prod.product_name,
                                                'product_price': prod.product_price,
                                                'product_description': prod.product_description,
                                                'product_image_url': prod.product_image_url,
                                                'created_at': prod.created_at,
                                                'category_name': prod.category_name,
                                                'tg_id': prod.tg_id,
                                                'first_name': seller_info["first_name"]})
            except Exception as exc:
                print(f"Error: {exc}")
        print()

        users = []
        async with async_session_maker() as session:
            try:
                users = await session.execute(select(User))
                users = users.scalars().all()

                users_info = []
                for user in users:
                    is_blocked = await check_user_blocked_post(user.tg_id)
                    users_info.append({
                        "tg_id": user.tg_id,
                        "first_name": user.first_name,
                        "username": user.username,
                        "is_blocked": is_blocked.get("is_blocked", False)
                    })

                users = users_info
            except Exception as e:
                print(f"Error getting users info: {e}")

        async with async_session_maker() as session:
            result = await session.execute(
                select(Review)
                .where(Review.moderated == False)
                .order_by(Review.created_at.desc())
            )
            reviews_arr = result.scalars().all()
        reviews = []
        for review in reviews_arr:
            from_user_review_info = await get_user_info_new(review.from_user_id)
            to_user_review_info = await get_user_info_new(review.to_user_id)
            reviews.append({
                "id": review.id,
                "deal_id": review.deal_id,
                "from_user_id": review.from_user_id,
                "from_user_first_name": from_user_review_info["first_name"],
                "to_user_id": review.to_user_id,
                "to_user_first_name": to_user_review_info["first_name"],
                "product_id": review.product_id,
                "rating": review.rating,
                "text": review.text,
                "created_at": review.created_at,
                "moderated": review.moderated
            })

        pending_deals = await get_pending_deals()
        active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

        admins = []
        async with async_session_maker() as session:
            admins_result = await session.execute(select(AdminRole))
            for admin in admins_result.scalars().all():
                admins.append({"tg_id": admin.user_id,
                               "first_name": (await session.execute(
                                    select(User.first_name).where(User.tg_id == admin.user_id))).scalar() or "Неизвестно",
                               "username": (await session.execute(
                                    select(User.username).where(User.tg_id == admin.user_id))).scalar() or "Нет",
                               "role": admin.role,
                               "assigned_at": admin.assigned_at.strftime("%d.%m.%Y %H:%M")})

        context = {
            "request": request,
            "reports": reports,
            "all_undread_count_message": all_undread_count_message,
            "admin": admin_res,
            "admin_role": admin_role,
            "admins": admins,
            "moderation_products": moderation_products,
            "users": users,
            "reviews": reviews,
            "pending_deals": pending_deals,
            "active_tab": request.query_params.get("tab", "reports"),
            "active_deals_count": active_deals_count
        }
        return templates.TemplateResponse("admin_chat_reports.html", context=context)


@wmarket_router.post("/admin/block_user")
async def block_user(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_chats(admin_role):
        admin_res = True
    if not admin_res:
        return {"status": "error", "message": "Unauthorized"}

    data = await request.json()
    user_id = data.get("user_id")
    block = data.get("block", True)
    duration = data.get("duration", None)
    reason = data.get("reason", "")

    if not block:
        await block_user_post(user_id, None, None, None, None)

        message = (
            f"✅ Ваш аккаунт был досрочно разблокирован администратором.\n\n"
            f"⚠️ Пожалуйста, больше не нарушайте правила Маркета."
        )

        await send_notification_to_user(user_id, message)

        return {"status": "success", "message": "User unblocked"}

    if duration == "1h":
        unblock_at = datetime.now(timezone.utc) + timedelta(hours=1)
    elif duration == "1d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=1)
    elif duration == "3d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=3)
    elif duration == "7d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=7)
    elif duration == "30d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=30)
    elif duration == "90d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=90)
    elif duration == "365d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=365)
    elif duration == "permanent":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=365000)
    else:
        return {"status": "error", "message": "Invalid duration"}

    await block_user_post(user_id, None, payload.get("tg_id"), reason, unblock_at)

    duration_text = {
        "1h": "1 час",
        "1d": "1 день",
        "3d": "3 дня",
        "7d": "7 дней",
        "30d": "1 месяц",
        "90d": "3 месяца",
        "365d": "1 год",
        "permanent": "навсегда"
    }.get(duration, duration)

    message = (
        f"⛔ Ваш аккаунт был заблокирован администратором.\n\n"
        f"⌛ Срок блокировки: {duration_text}\n"
        f"📝 Причина: {reason or 'не указана'}\n\n"
        f"Если Вы считаете, что это ошибка, свяжитесь с поддержкой."
    )

    await send_notification_to_user(user_id, message)

    return {"status": "success"}



@wmarket_router.post("/admin/moderate_review/{review_id}")
async def moderate_review(
        review_id: int,
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_reviews(admin_role):
        admin_res = True
    print(f"Роль {admin_role}, res {admin_res}")
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    approve = data.get("approve", False)
    reason = data.get("reason", "")

    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Review).where(Review.id == review_id))
            review = result.scalar_one_or_none()

            if not review:
                return JSONResponse({"status": "error", "message": "Review not found"}, status_code=404)

            if approve:
                user = await session.execute(select(User).where(User.tg_id == review.to_user_id))
                user = user.scalar_one_or_none()

                if review.rating > 0:
                    user.plus_rep += 1
                else:
                    user.minus_rep += 1

                review.moderated = True

                from_user_info = await get_user_info_new(review.from_user_id)
                to_user_info = await get_user_info_new(review.to_user_id)

                await send_notification_to_user(
                    review.to_user_id,
                    f"📢 Ваш рейтинг обновлён!\n\n"
                    f"Получен {'положительный' if review.rating > 0 else 'отрицательный'} отзыв "
                    f"от пользователя {from_user_info["first_name"] if from_user_info else 'неизвестен'}.\n\n"
                    f"Текст отзыва: {review.text}"
                )

                await send_notification_to_user(
                    review.from_user_id,
                    f"✅ Ваш отзыв был одобрен модератором и учтён в репутации пользователя."
                )
            else:
                await session.delete(review)

                await send_notification_to_user(
                    review.from_user_id,
                    f"❌ Ваш отзыв был отклонён модератором.\n\n"
                    f"Причина: {reason or 'не указана'}\n\n"
                    f"Вы можете оставить новый отзыв, соблюдая правила платформы."
                )

            await session.commit()
            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error moderating review: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.post("/admin/cleanup_unused_images")
async def cleanup_unused_images(session_token=Cookie(default=None)):
    if not session_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_products(admin_role):
        admin_res = True
    if not admin_res:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        async with async_session_maker() as session:
            result = await session.execute(select(Product.product_image_url))
            products = result.scalars().all()

        used_images = set()
        for product in products:
            if product:
                try:
                    images = json.loads(product)
                    for img in images:
                        if img.startswith('static/uploads/'):
                            used_images.add(img.split('/')[-1])
                except json.JSONDecodeError:
                    continue

        all_files = set()
        for root, dirs, files in os.walk(settings.UPLOAD_DIR):
            for file in files:
                all_files.add(file)

        unused_files = all_files - used_images

        deleted_count = 0
        freed_space = 0

        for file in unused_files:
            file_path = os.path.join(settings.UPLOAD_DIR, file)
            try:
                file_size = os.path.getsize(file_path)
                os.remove(file_path)
                deleted_count += 1
                freed_space += file_size
            except Exception as e:
                print(f"Error deleting file {file}: {e}")

        freed_space_mb = freed_space / (1024 * 1024)

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "freed_space_mb": freed_space_mb
        }

    except Exception as e:
        print(f"Error in cleanup_unused_images: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


#ads____________________________________________________________________________________________________________________
@wmarket_router.post("/report_product")
async def report_product(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_role = await is_admin_new(payload.get("tg_id"))
    if not can_moderate_products(admin_role):
        return {"status": "error", "message": "Access denied"}

    data = await request.json()
    product_id = data.get("product_id")

    try:
        product_id_int = int(product_id)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Invalid product ID"}

    product = await get_product_info_new(product_id_int, None)
    if not product:
        return {"status": "error", "message": "Product not found"}

    update_data = {"active": False}
    update_res = await update_product_post(product_id_int, update_data)

    if update_res:
        await send_notification_to_user(
            product["tg_id"],
            f"⚠️ Ваше объявление '{product["product_name"]}' было отправлено на повторную проверку администратором."
        )
        return {"status": "success"}

    return {"status": "error", "message": "Failed to update product"}
#_______________________________________________________________________________________________________________________


#chats__________________________________________________________________________________________________________________
@wmarket_router.get("/admin/get_chat_info/{chat_id}")
async def get_chat_info(chat_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_chats(admin_role):
        admin_res = True
    if admin_res:
        chat_info = {}

        async with async_session_maker() as session:
            participants = await session.execute(
                select(ChatParticipant.user_id)
                .where(ChatParticipant.chat_id == chat_id)
            )
            user_ids = [p[0] for p in participants.all()]
            user_one = await get_user_info_new(user_ids[0])
            user_two = await get_user_info_new(user_ids[1])
            chat_info = {
                "user1_id": user_ids[0] if len(user_ids) > 0 else None,
                "user2_id": user_ids[1] if len(user_ids) > 1 else None,
                "user1_username": user_one["first_name"] if len(user_ids) > 0 else None,
                "user2_username": user_two["first_name"] if len(user_ids) > 1 else None,
            }

        return chat_info
    return {"status": "error", "message": "Unauthorized"}


@wmarket_router.get("/admin/chat/{chat_id}")
async def admin_chat_view(
        chat_id: int,
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return RedirectResponse(url="/", status_code=303)

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_chats(admin_role):
        admin_res = True
    if admin_res:
        chat_data = await get_chat_messages(chat_id, None)
        if not chat_data:
            return RedirectResponse(url="/admin/chat_reports", status_code=303)

        admin_info = await get_user_info_new(payload.get("tg_id"))
        admin_name = admin_info.get("first_name", "Администратор") if admin_info else "Администратор"

        system_message_content = f"⚡ Администратор {admin_name} <br>Зашёл в чат для проверки<br>Решение будет принято в ближайшее время"
        system_message = await create_system_message(chat_id, system_message_content)

        if system_message:
            broadcast_data = {
                "type": "new_message",
                "chat_id": system_message.chat_id,
                "sender_id": system_message.sender_id,
                "receiver_id": system_message.receiver_id,
                "content": system_message.content,
                "created_at": system_message.created_at.isoformat(),
                "id": system_message.id,
                "is_read": system_message.is_read
            }
            await manager.broadcast(json.dumps(broadcast_data))

        all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
        active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

        context = {
            "request": request,
            "chat_id": chat_id,
            "messages": chat_data["messages"],
            "product": chat_data["product"],
            "other_user": chat_data["other_user"],
            "current_user": {"id": 0, "is_admin": True},
            "all_undread_count_message": all_undread_count_message,
            "is_chat_page": True,
            "active_deals_count": active_deals_count
        }
        return templates.TemplateResponse("chat.html", context=context)


@wmarket_router.post("/admin/resolve_report/{report_id}")
async def resolve_report_route(
        report_id: int,
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_chats(admin_role):
        admin_res = True
    if admin_res:
        success = await resolve_chat_report(report_id, payload.get("tg_id"))
        return {"status": "success" if success else "error"}
    return {"status": "error", "message": "Unauthorized"}
#_______________________________________________________________________________________________________________________


#products_______________________________________________________________________________________________________________
@wmarket_router.post("/admin/approve_product/{product_id}")
async def approve_product(product_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_products(admin_role):
        admin_res = True
    if admin_res:
        update_data = {"active": True}
        update_res = await update_product_post(product_id, update_data)

        if update_res:
            try:
                product = await get_product_info_new(product_id, None)
                if not product:
                    print(f"Product not found: {product_id}")

                seller_id = product["tg_id"]
                user_info = await get_user_info_new(seller_id)
                if not user_info:
                    print(f"User info not found for seller: {seller_id}")

                message = (
                    f"✅ Ваше объявление прошло модерацию!\n\n"
                    f"📌 Название: {product["product_name"]}\n"
                    f"⚙️ Категория: {product["category_name"]}\n"
                    f"💰 Цена: {product["product_price"]} ₽"
                )

                await send_notification_to_user(seller_id, message)
                print(f"Product approval notification sent to user {seller_id} for product {product_id}")

            except Exception as e:
                print(f"Error in notify_product_approved: {e}", exc_info=True)

            return {"status": "success"}

    return {"status": "error", "message": "Неавторизованный запрос"}


@wmarket_router.post("/admin/reject_product/{product_id}")
async def reject_product(
        product_id: int,
        request: Request,
        session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_chats(admin_role):
        admin_res = True
    if admin_res:
        data = await request.json()
        reason = data.get("reason", "")

        update_data = {"active": False}
        update_res = await update_product_post(product_id, update_data)

        if update_res:
            try:
                product = await get_product_info_new(product_id, None)
                if not product:
                    print(f"Product not found: {product_id}")

                seller_id = product["tg_id"]
                user_info = await get_user_info_new(seller_id)
                if not user_info:
                    print(f"User info not found for seller: {seller_id}")

                message = (
                    f"❌ Ваше объявление не прошло модерацию\n\n"
                    f"📌 Название: {product["product_name"]}\n"
                    f"📝 Причина/пункт: {reason}\n\n"
                    f'Вы можете исправить его (<a href="https://telegra.ph/Osnovnye-punkty-i-prichiny-blokirovki-06-26">прочитав причину или пункт</a>)'
                    f" и повторно опубликовать."
                )

                await send_notification_to_user(seller_id, message)
                print(f"Product rejection notification sent to user {seller_id} for product {product_id}")

            except Exception as e:
                print(f"Error in notify_product_rejected: {e}", exc_info=True)

            async with async_session_maker() as db:
                try:
                    await db.execute(delete(Fav).where(Fav.product_id == product_id))
                    await db.execute(delete(Product).where(Product.id == product_id))
                    await db.commit()
                except Exception as e:
                    print(e)

            return {"status": "success"}

    return {"status": "error", "message": "Неавторизованный запрос"}
#_______________________________________________________________________________________________________________________


#deals__________________________________________________________________________________________________________________
@wmarket_router.post("/admin/moderate_cancel_request/{deal_id}")
async def moderate_cancel_request(
        deal_id: int,
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_deals(admin_role):
        admin_res = True
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    approve = data.get("approve", False)

    async with async_session_maker() as session:
        try:
            deal = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = deal.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if not deal.pending_cancel:
                return JSONResponse({"status": "error", "message": "No pending cancellation"}, status_code=400)

            if approve:
                buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
                buyer = buyer.scalar_one_or_none()

                if deal.currency == 'rub':
                    buyer.rub_balance += deal.amount
                else:
                    buyer.ton_balance += deal.amount

                deal.status = "cancelled"
                deal.completed_at = datetime.now(timezone.utc)
                deal.pending_cancel = False

                await send_notification_to_user(
                    deal.buyer_id,
                    f"✅ Администратор одобрил отмену сделки по товару '{deal.product_name}'.\n\n"
                    f"Сумма {deal.amount} {deal.currency.upper()} возвращена на ваш баланс."
                )

                await send_notification_to_user(
                    deal.seller_id,
                    f"ℹ️ Администратор одобрил отмену сделки по товару '{deal.product_name}'.\n\n"
                    f"Средства возвращены покупателю."
                )
            else:
                deal.pending_cancel = False

                await send_notification_to_user(
                    deal.cancel_request_by,
                    f"❌ Администратор отклонил ваш запрос на отмену сделки по товару '{deal.product_name}'.\n\n"
                    f"Сделка возобновлена."
                )

                other_user_id = deal.buyer_id if deal.cancel_request_by == deal.seller_id else deal.seller_id
                await send_notification_to_user(
                    other_user_id,
                    f"ℹ️ Администратор отклонил запрос на отмену сделки по товару '{deal.product_name}'.\n\n"
                    f"Сделка возобновлена."
                )

            await session.commit()
            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error moderating cancel request: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.get("/admin/get_deal_info/{deal_id}")
async def get_deal_info(
    deal_id: int,
    session_token=Cookie(default=None)
):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_deals(admin_role):
        admin_res = True
    if not admin_res:
        return {"status": "error", "message": "Unauthorized"}

    async with async_session_maker() as session:
        result = await session.execute(
            select(Deal)
            .where(Deal.id == deal_id)
        )
        deal = result.scalar_one_or_none()

        if not deal:
            return {"status": "error", "message": "Deal not found"}

        seller = await get_user_info_new(deal.seller_id)
        buyer = await get_user_info_new(deal.buyer_id)

        return {
            "id": deal.id,
            "product_name": deal.product_name,
            "seller_id": deal.seller_id,
            "seller_first_name": seller["first_name"] if seller else "Unknown",
            "buyer_id": deal.buyer_id,
            "buyer_first_name": buyer["first_name"] if buyer else "Unknown",
            "amount": deal.amount,
            "currency": deal.currency,
            "status": deal.status,
            "pending_cancel": deal.pending_cancel,
            "cancel_reason": deal.cancel_reason,
            "cancel_request_by": deal.cancel_request_by,
            "created_at": deal.created_at.isoformat()
        }


@wmarket_router.post("/admin/complete_deal/{deal_id}")
async def complete_deal(
    deal_id: int,
    request: Request,
    session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_deals(admin_role):
        admin_res = True
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    action = data.get("action")
    reason = data.get("reason", "")

    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if deal.status != "active":
                return JSONResponse({"status": "error", "message": "Deal is not active"}, status_code=400)

            buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
            buyer = buyer.scalar_one_or_none()
            seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
            seller = seller.scalar_one_or_none()

            if action == "for_seller":
                seller_amount = deal.amount * 0.93
                market_fee = deal.amount * 0.07

                if deal.currency == 'rub':
                    seller.rub_balance += seller_amount
                    if seller.earned_rub is None:
                        seller.earned_rub = 0.0
                    seller.earned_rub += seller_amount
                else:
                    seller.ton_balance += seller_amount
                    if seller.earned_ton is None:
                        seller.earned_ton = 0.0
                    seller.earned_ton += seller_amount

                # Обновляем статус сделки
                deal.status = "completed_by_admin"
                deal.completed_at = datetime.now(timezone.utc)
                deal.admin_decision = "for_seller"
                deal.admin_reason = reason
                deal.admin_id = payload.get("tg_id")

                # Отправляем уведомления
                await send_notification_to_user(
                    deal.seller_id,
                    f"✅ Администратор завершил сделку в вашу пользу!\n\n"
                    f"Товар: {deal.product_name}\n"
                    f"Сумма: {seller_amount:.2f} {deal.currency.upper()} (комиссия 7%)\n"
                    f"Причина решения: {reason}"
                )

                await send_notification_to_user(
                    deal.buyer_id,
                    f"ℹ️ Администратор завершил сделку в пользу продавца.\n\n"
                    f"Товар: {deal.product_name}\n"
                    f"Сумма: {deal.amount} {deal.currency.upper()}\n"
                    f"Причина решения: {reason}"
                )

            elif action == "for_buyer":
                if deal.currency == 'rub':
                    buyer.rub_balance += deal.amount
                else:
                    buyer.ton_balance += deal.amount

                deal.status = "completed_by_admin"
                deal.completed_at = datetime.now(timezone.utc)
                deal.admin_decision = "for_buyer"
                deal.admin_reason = reason
                deal.admin_id = payload.get("tg_id")

                await send_notification_to_user(
                    deal.buyer_id,
                    f"✅ Администратор вернул вам средства по сделке!\n\n"
                    f"Товар: {deal.product_name}\n"
                    f"Сумма: {deal.amount} {deal.currency.upper()}\n"
                    f"Причина решения: {reason}"
                )

                await send_notification_to_user(
                    deal.seller_id,
                    f"ℹ️ Администратор вернул средства покупателю.\n\n"
                    f"Товар: {deal.product_name}\n"
                    f"Сумма: {deal.amount} {deal.currency.upper()}\n"
                    f"Причина решения: {reason}"
                )

                await archive_product_post(deal.product_id)

            await session.commit()
            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error completing deal: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.post("/admin/give_more_time/{deal_id}")
async def give_more_time(
    deal_id: int,
    request: Request,
    session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_deals(admin_role):
        admin_res = True
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    hours = int(data.get("hours", 24))
    reason = data.get("reason", "")

    async with async_session_maker() as session:
        try:
            result = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if deal.status != "active":
                return JSONResponse({"status": "error", "message": "Deal is not active"}, status_code=400)

            # Устанавливаем время для самостоятельного решения
            deal.pending_cancel = False
            deal.cancel_reason = None
            deal.cancel_request_by = None
            deal.admin_decision = "more_time"
            deal.admin_reason = reason
            deal.admin_id = payload.get("tg_id")
            deal.time_extension = hours
            deal.time_extension_until = datetime.now(timezone.utc) + timedelta(hours=hours)

            # Отправляем уведомления
            await send_notification_to_user(
                deal.seller_id,
                f"⏳ Администратор дал вам дополнительное время для завершения сделки!\n\n"
                f"Товар: {deal.product_name}\n"
                f"Сумма: {deal.amount} {deal.currency.upper()}\n"
                f"Время на решение: {hours} часов\n"
                f"Комментарий администратора: {reason or 'нет'}"
            )

            await send_notification_to_user(
                deal.buyer_id,
                f"⏳ Администратор дал вам дополнительное время для завершения сделки!\n\n"
                f"Товар: {deal.product_name}\n"
                f"Сумма: {deal.amount} {deal.currency.upper()}\n"
                f"Время на решение: {hours} часов\n"
                f"Комментарий администратора: {reason or 'нет'}"
            )

            await session.commit()
            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error giving more time for deal: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


@wmarket_router.post("/admin/complete_meet_deal/{deal_id}")
async def complete_meet_deal(
    deal_id: int,
    request: Request,
    session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    admin_res = False
    admin_role = await is_admin_new(payload.get("tg_id"))
    if can_moderate_deals(admin_role):
        admin_res = True
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    action = data.get("action")

    async with async_session_maker() as session:
        try:
            result = await session.execute(
                select(Deal)
                .where(Deal.id == deal_id)
                .where(Deal.currency == 'meet')
                .where(Deal.pending_cancel == True)
            )
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse(
                    {"status": "error", "message": "Сделка не найдена или не требует подтверждения"},
                    status_code=404
                )

            if action == "confirm":
                deal.status = "completed"
                deal.completed_at = datetime.now(timezone.utc)
                deal.pending_cancel = False

                seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
                seller = seller.scalar_one_or_none()

                seller_amount = deal.amount * 0.93
                market_fee = deal.amount * 0.07

                if seller.earned_rub is None:
                    seller.earned_rub = 0.0
                seller.earned_rub += seller_amount

                await archive_product_post(deal.product_id)

                await send_notification_to_user(
                    deal.seller_id,
                    f"✅ Администратор подтвердил сделку с оплатой при встрече!\n\n"
                    f"Товар: {deal.product_name}\n"
                    f"Сумма: {deal.amount} ₽\n"
                    f"Покупатель: ID {deal.buyer_id}\n\n"
                    f"Отзыв по сделке остаётся на модерации."
                )

                await send_notification_to_user(
                    deal.buyer_id,
                    f"✅ Администратор подтвердил сделку с оплатой при встрече!\n\n"
                    f"Товар: {deal.product_name}\n"
                    f"Сумма: {deal.amount} ₽\n"
                    f"Продавец: ID {deal.seller_id}\n\n"
                    f"Отзыв по сделке остаётся на модерации."
                )

            elif action == "cancel":
                deal.status = "cancelled"
                deal.completed_at = datetime.now(timezone.utc)
                deal.pending_cancel = False

                review = await session.execute(
                    select(Review)
                    .where(Review.deal_id == deal_id)
                    .where(Review.moderated == False)
                )
                review = review.scalar_one_or_none()

                if review:
                    await session.delete(review)

                await send_notification_to_user(
                    deal.seller_id,
                    f"❌ Администратор отменил сделку с оплатой при встрече.\n\n"
                    f"Товар: {deal.product_name}\n"
                    f"Сумма: {deal.amount} ₽\n"
                    f"Покупатель: ID {deal.buyer_id}\n\n"
                    f"Отзыв по сделке был удалён."
                )

                await send_notification_to_user(
                    deal.buyer_id,
                    f"❌ Администратор отменил сделку с оплатой при встрече.\n\n"
                    f"Товар: {deal.product_name}\n"
                    f"Сумма: {deal.amount} ₽\n"
                    f"Продавец: ID {deal.seller_id}\n\n"
                    f"Отзыв по сделке был удалён."
                )

            await session.commit()
            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error completing meet deal: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )
#_______________________________________________________________________________________________________________________


#admin__________________________________________________________________________________________________________________
@wmarket_router.post("/admin/add_admin")
async def add_admin_route(request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}
    payload = await decode_jwt(session_token)
    admin_role = await is_admin_new(payload.get("tg_id"))
    if not can_manage_admins(admin_role):
        return {"status": "error", "message": "Access denied"}

    data = await request.json()
    user_id = data.get("user_id")
    role = data.get("role")

    if not user_id or not role:
        return {"status": "error", "message": "Missing data"}

    success = False
    user_id = int(user_id)
    async with async_session_maker() as session:
        if str(user_id) in [admin.strip() for admin in settings.ADMINS.split(",")]:
            success = False

        await session.execute(delete(AdminRole).where(AdminRole.user_id == user_id))

        session.add(AdminRole(user_id=user_id, role=role))
        await session.commit()
        success = True

    return {"status": "success" if success else "error"}


@wmarket_router.post("/admin/remove_admin")
async def remove_admin_route(request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}
    payload = await decode_jwt(session_token)
    admin_role = await is_admin_new(payload.get("tg_id"))
    if not can_manage_admins(admin_role):
        return {"status": "error", "message": "Access denied"}

    data = await request.json()
    user_id = data.get("user_id")

    success = False
    user_id = int(user_id)
    if str(user_id) in [admin.strip() for admin in settings.ADMINS.split(",")]:
        success = False

    async with async_session_maker() as session:
        await session.execute(delete(AdminRole).where(AdminRole.user_id == user_id))
        await session.commit()
        success = True

    return {"status": "success" if success else "error"}
#_______________________________________________________________________________________________________________________