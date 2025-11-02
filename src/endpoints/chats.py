import json
from datetime import datetime, timezone

from fastapi import Cookie, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, desc, func, select, update

from src.bot import send_notification_to_user
from src.database.database import Chat, ChatParticipant, ChatReport, Message, Product, User, async_session_maker
from src.database.methods import (all_count_unread_messages, check_user_block_post, check_user_blocked_post,
                                  get_all_users, get_chat_messages, get_user_active_deals_count, get_user_info_new,
                                  mark_messages_as_read, check_existing_report, create_system_message,
                                  check_any_active_chat_report, get_active_deal_for_chat)
from src.endpoints._endpoints_config import templates, wmarket_router
from src.utils import decode_jwt, is_admin_new
from src.websocket_config import manager


@wmarket_router.get("/chats")
async def chats(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):

            async with async_session_maker() as session:
                last_message_subq = (
                    select(
                        Message.chat_id,
                        func.max(Message.created_at).label('last_message_time')
                    )
                    .group_by(Message.chat_id)
                    .subquery()
                )

                result = await session.execute(
                    select(
                        Chat,
                        last_message_subq.c.last_message_time
                    )
                    .join(ChatParticipant, ChatParticipant.chat_id == Chat.id)
                    .join(last_message_subq, Chat.id == last_message_subq.c.chat_id, isouter=True)
                    .where(ChatParticipant.user_id == payload.get("tg_id"))
                    .order_by(
                        desc(last_message_subq.c.last_message_time),
                        desc(Chat.created_at)
                    )
                )

                chats_with_times = result.all()

                chats_with_info = []
                for chat, last_message_time in chats_with_times:
                    product = await session.execute(select(Product).where(Product.id == chat.product_id))
                    product = product.scalar_one_or_none()

                    other_participants = await session.execute(
                        select(ChatParticipant.user_id)
                        .where(
                            (ChatParticipant.chat_id == chat.id) &
                            (ChatParticipant.user_id != payload.get("tg_id"))
                        )
                    )
                    other_user_id = other_participants.scalar_one_or_none()

                    other_user = await session.execute(select(User).where(User.tg_id == other_user_id))
                    other_user = other_user.scalar_one_or_none()

                    last_message = await session.execute(
                        select(Message)
                        .where(Message.chat_id == chat.id)
                        .order_by(desc(Message.created_at))
                        .limit(1)
                    )
                    last_message = last_message.first()
                    if last_message:
                        last_message = last_message[0]
                    image_urls = json.loads(product.product_image_url) if product.product_image_url else []

                    count_unread_result = await session.execute(
                        select(func.count(Message.id))
                        .where(Message.chat_id == chat.id)
                        .where(Message.receiver_id == payload.get("tg_id"))
                        .where(Message.is_read == False)
                    )
                    count_unread_messages = count_unread_result.scalar() or 0

                    chats_with_info.append({
                        "id": chat.id,
                        "product_id": chat.product_id,
                        "product_title": product.product_name if product else "Неизвестный товар",
                        "product_price": product.product_price if product else 0,
                        "product_image": image_urls[0] if image_urls else "static/img/zaglush.png",
                        "product_active": product.active if product else None,
                        "seller_username": other_user.first_name if other_user else "Неизвестный",
                        "last_message": last_message.content if last_message else "Чат начат",
                        "last_message_time": last_message.created_at.strftime("%H:%M") if last_message else "",
                        "unread_count": count_unread_messages
                    })

            user_chats = chats_with_info

            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

            context = {
                "request": request,
                "chats": user_chats,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "active_deals_count": active_deals_count
            }
            return templates.TemplateResponse("chats.html", context=context)

    response = RedirectResponse(url="/", status_code=303)
    return response


@wmarket_router.get("/start_chat/{product_id}")
async def start_chat(product_id: int, request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return RedirectResponse(url="/", status_code=303)

    payload = await decode_jwt(session_token)

    async with async_session_maker() as db:
        product = await db.execute(select(Product).filter_by(id=product_id))
        product = product.scalar_one_or_none()

        if not product:
            return RedirectResponse(url="/store?error=product_not_found", status_code=303)

        if product.tg_id == payload.get("tg_id"):
            return RedirectResponse(url="/store?error=cannot_chat_with_yourself", status_code=303)

        existing_chat = await db.execute(
            select(Chat)
            .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
            .where(Chat.product_id == product_id)
            .where(ChatParticipant.user_id.in_([product.tg_id, payload.get("tg_id")]))
            .group_by(Chat.id)
            .having(func.count(ChatParticipant.user_id) == 2)
        )
        existing_chat = existing_chat.scalar_one_or_none()

        if existing_chat:
            return RedirectResponse(url=f"/chat/{existing_chat.id}", status_code=303)

        chat = Chat(product_id=product_id)
        db.add(chat)
        await db.flush()

        participants = [
            ChatParticipant(chat_id=chat.id, user_id=product.tg_id),
            ChatParticipant(chat_id=chat.id, user_id=payload.get("tg_id"))
        ]
        db.add_all(participants)
        await db.commit()
        chat_id = chat.id

    return RedirectResponse(url=f"/chat/{chat_id}", status_code=303)


@wmarket_router.get("/chat/{chat_id}")
async def chat_page(chat_id: int, request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return RedirectResponse(url="/", status_code=303)

    payload = await decode_jwt(session_token)
    chat_data = await get_chat_messages(chat_id, payload.get("tg_id"))

    if not chat_data:
        return RedirectResponse(url="/chats", status_code=303)

    is_blocked = False
    unblock_at = None

    if chat_data["other_user"]:
        other_user_id = chat_data["other_user"].tg_id
        block = await check_user_blocked_post(other_user_id)
        is_blocked = block.get("is_blocked", False)
        unblock_at = None

    if is_blocked:
        block_info = await check_user_block_post(other_user_id)
        unblock_time = block_info[0].replace(tzinfo=timezone.utc)
        current_time = datetime.now(timezone.utc)
        if block and unblock_time > current_time:
            unblock_at = block_info[0].strftime("%d.%m.%Y %H:%M")
        else:
            is_blocked = False

    # Получаем информацию об активной сделке
    active_deal = await get_active_deal_for_chat(chat_id, payload.get("tg_id"))

    all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
    active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))
    print(f"Текущий id пользователя чата = {payload.get("tg_id")}")

    context = {
        "request": request,
        "chat_id": chat_id,
        "messages": chat_data["messages"],
        "product": chat_data["product"],
        "other_user": chat_data["other_user"],
        "current_user": {"id": payload.get("tg_id")},
        "is_chat_page": True,
        "all_undread_count_message": all_undread_count_message,
        "is_blocked": is_blocked,
        "unblock_at": unblock_at,
        "active_deals_count": active_deals_count,
        "active_deal": active_deal  # Добавляем информацию о сделке
    }
    return templates.TemplateResponse("chat.html", context=context)


@wmarket_router.post("/leave_chat/{chat_id}")
async def leave_chat_route(chat_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    if not payload or "tg_id" not in payload:
        return {"status": "error", "message": "Invalid token"}

    async with async_session_maker() as session:
        was_participant = await session.execute(
            select(func.count())
            .select_from(ChatParticipant)
            .where(
                (ChatParticipant.chat_id == chat_id) &
                (ChatParticipant.user_id == payload["tg_id"])
            )
        )
        if not was_participant.scalar():
            return {"status": "error", "message": "Not a participant"}


    success = False
    async with async_session_maker() as session:
        try:
            await session.execute(
                delete(ChatParticipant)
                .where(
                    (ChatParticipant.chat_id == chat_id) &
                    (ChatParticipant.user_id == payload["tg_id"])
                )
            )

            remaining = await session.execute(
                select(func.count())
                .select_from(ChatParticipant)
                .where(ChatParticipant.chat_id == chat_id)
            )
            remaining_count = remaining.scalar()

            if remaining_count == 0:
                await session.execute(delete(Message).where(Message.chat_id == chat_id))
                await session.execute(delete(ChatReport).where(ChatReport.chat_id == chat_id))
                await session.execute(delete(Chat).where(Chat.id == chat_id))

            await session.commit()
            success = True
        except Exception as e:
            await session.rollback()
            print(f"Error leaving chat: {e}")

    if success:
        return {"status": "success"}
    else:
        return {"status": "error", "message": "Failed to leave chat"}


@wmarket_router.get("/chat_participants_info/{chat_id}")
async def get_chat_participants_info(chat_id: int):
    users_info = {}
    async with async_session_maker() as session:
        participants = await session.execute(
            select(ChatParticipant.user_id)
            .where(ChatParticipant.chat_id == chat_id)
        )
        participant_ids = [p[0] for p in participants.all()]

        users_info_result = {}
        for user_id in participant_ids:
            user = await session.execute(select(User).where(User.tg_id == user_id))
            user = user.scalar_one_or_none()
            if user:
                users_info_result[user_id] = user.first_name or user.username or f"User {user_id}"

        users_info = users_info_result
    return users_info


@wmarket_router.post("/report_message/{message_id}")
async def report_message_route(message_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    success = False

    async with async_session_maker() as db:
        await db.execute(
            update(Message)
            .where(Message.id == message_id)
            .values(reported=True))
        await db.commit()
        success = True

    return {"status": "success" if success else "error"}


@wmarket_router.post("/report_chat/{chat_id}")
async def report_chat_route(
        chat_id: int,
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    reporter_id = payload.get("tg_id")
    data = await request.json()
    reason = data.get("reason", "")

    existing_chat_report = await check_any_active_chat_report(chat_id)
    if not existing_chat_report:
        return {
            "status": "error",
            "message": "На этот чат уже подана жалоба. Дождитесь решения администратора."
        }

    success = False
    async with async_session_maker() as db:
        try:
            report = ChatReport(
                chat_id=chat_id,
                reporter_id=reporter_id,
                reason=reason
            )
            db.add(report)
            await db.commit()
            success = True

            reporter_info = await get_user_info_new(reporter_id)

            system_message_content = f"⚠️ {reporter_info['first_name']} <br>Отправил жалобу на этот чат"
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

        except Exception as exc:
            print(f"Error reporting chat: {exc}")
            if "unique_chat_report" in str(exc).lower():
                return {
                    "status": "error",
                    "message": "У вас уже есть активная жалоба на этот чат. Дождитесь её решения."
                }

    return {"status": "success" if success else "error"}


@wmarket_router.get("/check_existing_report/{chat_id}")
async def check_existing_report_route(
        chat_id: int,
        session_token=Cookie(default=None)
):
    if not session_token:
        return {"has_existing_report": False}

    payload = await decode_jwt(session_token)
    reporter_id = payload.get("tg_id")

    existing_report = await check_existing_report(chat_id, reporter_id)

    return {"has_existing_report": existing_report}



@wmarket_router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            if message_data["type"] == "get_history":
                await mark_messages_as_read(message_data["chat_id"], int(user_id))

                chat_data = await get_chat_messages(message_data["chat_id"], int(user_id))
                if chat_data:
                    await websocket.send_text(json.dumps({
                        "type": "chat_history",
                        "messages": [
                            {
                                "chat_id": msg.chat_id,
                                "sender_id": msg.sender_id,
                                "receiver_id": msg.receiver_id,
                                "content": msg.content,
                                "created_at": msg.created_at.isoformat(),
                                "id": msg.id,
                                "is_read": msg.is_read
                            }
                            for msg in chat_data["messages"]
                        ]
                    }))

            if message_data["type"] == "send_message" and user_id != "0":
                participants = {}
                async with async_session_maker() as session:
                    query = select(ChatParticipant).where(ChatParticipant.chat_id == message_data["chat_id"])
                    result = await session.execute(query)
                    participants = result.scalars().all()

                receiver_id = next((p.user_id for p in participants if p.user_id != int(user_id)), None)

                if not receiver_id:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Получатель не найден в чате"
                    }))
                    continue

                receiver_connected = manager.is_connected(str(receiver_id))

                message_obj = None
                async with async_session_maker() as db:
                    participants = await db.execute(
                        select(ChatParticipant.user_id)
                        .where(ChatParticipant.chat_id == message_data["chat_id"]))
                    participants = participants.scalars().all()
                    receiver_id = next((p for p in participants if p != int(user_id)), None)

                    if not receiver_id:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Участник чата не найден"
                        }))
                        continue

                    try:
                        message_obj = Message(
                            chat_id=message_data["chat_id"],
                            sender_id=int(user_id),
                            receiver_id=receiver_id,
                            content=message_data["content"],
                            is_read=receiver_connected
                        )
                        db.add(message_obj)
                        await db.commit()
                        await db.refresh(message_obj)
                    except Exception as e:
                        await db.rollback()
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": f"Ошибка сохранения сообщения: {str(e)}"
                        }))
                        continue

                if not receiver_connected:
                    try:
                        chat_data = await get_chat_messages(message_data["chat_id"], int(user_id))
                        if not chat_data:
                            print(f"Chat data not found for chat_id: {message_data['chat_id']}")
                            continue

                        receiver_id = chat_data["other_user"].tg_id
                        user_data = await get_user_info_new(int(user_id))

                        notification_message = (
                            f"💬 Новое сообщение от \n{user_data['first_name']} \n\n📢 Объявление:\n{chat_data['product'].product_name}"
                        )

                        await send_notification_to_user(receiver_id, notification_message, chat_data['product'].id)
                        print(
                            f"Notification sent to user {receiver_id} about new message in chat {message_data['chat_id']}")

                    except Exception as e:
                        print(f"Error in notify_new_message: {e}")

                broadcast_data = {
                    "type": "new_message",
                    "chat_id": message_obj.chat_id,
                    "sender_id": message_obj.sender_id,
                    "receiver_id": message_obj.receiver_id,
                    "content": message_obj.content,
                    "created_at": message_obj.created_at.isoformat(),
                    "id": message_obj.id,
                    "is_read": message_obj.is_read
                }

                await manager.broadcast(json.dumps(broadcast_data))

    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close(code=1011)