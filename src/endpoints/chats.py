import json
from datetime import datetime, timezone

from fastapi import Request, Cookie, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse

from src.database.methods import (get_all_users, create_chat, get_chat_messages, report_message,
                                  send_message, get_chat_participants,
                                  get_user_chats, all_count_unread_messages, report_chat, get_chat_part_info,
                                  leave_chat_post, check_user_in_chat, check_user_blocked_post, check_user_block_post, get_user_active_deals_count)
from src.endpoints._endpoints_config import wmarket_router, templates
from src.endpoints.notify import notify_new_message
from src.utils import decode_jwt, is_admin_new
from src.websocket_config import manager


@wmarket_router.get("/chats")
async def chats(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            user_chats = await get_user_chats(payload.get("tg_id"))

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
    chat_id = await create_chat(product_id, payload.get("tg_id"))

    if not chat_id:
        return RedirectResponse(url="/store", status_code=303)

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

    all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
    active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

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
        "active_deals_count": active_deals_count
    }
    return templates.TemplateResponse("chat.html", context=context)


@wmarket_router.post("/leave_chat/{chat_id}")
async def leave_chat_route(chat_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    if not payload or "tg_id" not in payload:
        return {"status": "error", "message": "Invalid token"}

    await check_user_in_chat(chat_id, payload["tg_id"])

    success = await leave_chat_post(chat_id, payload["tg_id"])
    if success:
        return {"status": "success"}
    else:
        return {"status": "error", "message": "Failed to leave chat"}


@wmarket_router.get("/chat_participants_info/{chat_id}")
async def get_chat_participants_info(chat_id: int):
    users_info = await get_chat_part_info(chat_id)
    return users_info



@wmarket_router.post("/report_message/{message_id}")
async def report_message_route(message_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    success = await report_message(message_id)
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
    data = await request.json()
    reason = data.get("reason", "")

    success = await report_chat(chat_id, payload.get("tg_id"), reason)
    return {"status": "success" if success else "error"}


@wmarket_router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            if message_data["type"] == "get_history":
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
                                "id": msg.id
                            }
                            for msg in chat_data["messages"]
                        ]
                    }))

            if message_data["type"] == "send_message" and user_id != "0":
                participants = await get_chat_participants(message_data["chat_id"])
                receiver_id = next((p.user_id for p in participants if p.user_id != int(user_id)), None)

                if not receiver_id:
                    continue

                receiver_connected = manager.is_connected(str(receiver_id))

                message = await send_message(
                    message_data["chat_id"],
                    int(user_id),
                    message_data["content"],
                    mark_unread=not receiver_connected
                )

                if message:
                    if not receiver_connected:
                        await notify_new_message(
                            message_data["chat_id"],
                            int(user_id),
                            message_data["content"]
                        )

                    await manager.broadcast(json.dumps({
                        "type": "new_message",
                        "chat_id": message.chat_id,
                        "sender_id": message.sender_id,
                        "receiver_id": message.receiver_id,
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                        "id": message.id
                    }))
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.close(code=1011)