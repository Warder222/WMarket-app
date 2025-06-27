import json
import os
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, Cookie, Depends, Form, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from starlette.responses import JSONResponse

from src.bot import send_notification_to_user
from src.config import settings, manager
from src.database.utils import (get_all_users, add_user, update_token, get_all_categories, get_all_products,
                                get_all_products_from_category, add_fav, get_all_user_favs, del_fav, get_user_info,
                                add_new_product, get_product_info, get_user_active_products,
                                get_user_moderation_products, create_chat, get_chat_messages, report_message,
                                send_message, count_unread_messages, get_last_chat_message, get_chat_participants,
                                get_user_chats, all_count_unread_messages, get_all_digit_categories,
                                get_all_not_digit_categories, resolve_chat_report, get_chat_reports, report_chat,
                                user_exists, record_referral, get_ref_count, get_chat_part_info,
                                get_user_archived_products, delete_product_post, archive_product_post,
                                restore_product_post, update_product_post, get_all_moderation_products,
                                leave_chat_post, check_user_in_chat, get_chat_info_post, block_user_post,
                                notify_reporter_about_block_post, check_user_blocked_post, check_user_block_post)
from src.utils import parse_init_data, encode_jwt, decode_jwt, is_admin

wmarket_router = APIRouter(
    prefix="",
    tags=["wmarket_router"]
)

templates = Jinja2Templates(directory="templates")


# auth__________________________________________________________________________________________________________________
@wmarket_router.get("/")
async def index(request: Request):
    context = {
        "request": request
    }
    return templates.TemplateResponse("auth.html", context=context)


@wmarket_router.get("/register")
async def register(request: Request):
    context = {
        "request": request
    }
    return templates.TemplateResponse("register.html", context=context)


@wmarket_router.post("/auth/{oper}")
async def auth(oper: str, request: Request, session_token=Cookie(default=None)):
    form_data = await request.form()
    init_data = form_data.get("initData")
    user_data = parse_init_data(init_data)

    if oper == "login":
        users = await get_all_users()
        if user_data.get("tg_id") not in users:
            response = RedirectResponse(url="/register", status_code=303)
            return response

    new_session_token = await encode_jwt({"tg_id": user_data.get("tg_id")})
    add_result = await add_user(user_data, new_session_token)
    if not add_result:
        await update_token(session_token, new_session_token)

    ref_code = user_data.get("ref_code")
    if ref_code:
        ref_code = int(ref_code)
        if await user_exists(ref_code):
            res = await record_referral(ref_code, user_data.get("tg_id"))

    response = RedirectResponse(url="/store", status_code=303)
    response.set_cookie(key="session_token", value=new_session_token, httponly=True, secure=True)
    return response


# store_________________________________________________________________________________________________________________
@wmarket_router.get("/store")
async def store(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):

            cats = await get_all_not_digit_categories()
            dig_cats = await get_all_digit_categories()
            products = await get_all_products(payload.get("tg_id"))
            now = datetime.now(timezone.utc)
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
            context = {
                "request": request,
                "cats": cats,
                "dig_cats": dig_cats,
                "products": products,
                "now": now,
                "all_undread_count_message": all_undread_count_message,
                "user_tg_id": payload.get("tg_id"),
                "admin": admin_res
            }
            return templates.TemplateResponse("store.html", context=context)

    response = RedirectResponse(url="/", status_code=303)
    return response


@wmarket_router.get("/store/{category_name}")
async def store_get(category_name: str, request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            cats = await get_all_not_digit_categories()
            dig_cats = await get_all_digit_categories()
            products = await get_all_products_from_category(category_name, payload.get("tg_id"))
            now = datetime.now(timezone.utc)
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
            context = {
                "request": request,
                "cats": cats,
                "dig_cats": dig_cats,
                "products": products,
                "now": now,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res
            }
            return templates.TemplateResponse("store.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response


@wmarket_router.get('/add_product')
async def add_product(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            categories = await get_all_categories()
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
            context = {
                "request": request,
                "categories": categories,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res
            }
            return templates.TemplateResponse("add_product.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response


@wmarket_router.get("/ads_review")
async def ads_review(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            # Получаем параметр tab из URL (по умолчанию 'active')
            tab = request.query_params.get('tab', 'active')

            # Инициализируем все переменные как пустые списки
            active_products = []
            moderation_products = []
            archived_products = []

            # Загружаем только нужные данные в зависимости от выбранной вкладки
            if tab == 'active':
                active_products = await get_user_active_products(payload.get("tg_id"), payload.get("tg_id"))
            elif tab == 'moderation':
                moderation_products = await get_user_moderation_products(payload.get("tg_id"))
            elif tab == 'archived':
                archived_products = await get_user_archived_products(payload.get("tg_id"))

            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))

            context = {
                "request": request,
                "active_products": active_products,
                "moderation_products": moderation_products,
                "archived_products": archived_products,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "current_tab": tab  # Добавляем текущую вкладку в контекст
            }
            return templates.TemplateResponse("ads_review.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response


@wmarket_router.post("/delete_product/{product_id}")
async def delete_product(product_id: int, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            rest_product = await delete_product_post(product_id=product_id)
            if rest_product:
                return JSONResponse({"status": "success"})
            else:
                return JSONResponse({"status": "error"}, status_code=500)
    response = RedirectResponse(url="/store", status_code=303)
    return response

@wmarket_router.post("/archive_product/{product_id}")
async def archive_product(product_id: int, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            rest_product = await archive_product_post(product_id=product_id)
            if rest_product:
                return JSONResponse({"status": "success"})
            else:
                return JSONResponse({"status": "error"}, status_code=500)
    response = RedirectResponse(url="/store", status_code=303)
    return response

@wmarket_router.post("/restore_product/{product_id}")
async def restore_product(product_id: int, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            rest_product = await restore_product_post(product_id=product_id)
            if rest_product:
                return JSONResponse({"status": "success"})
            else:
                return JSONResponse({"status": "error"}, status_code=500)
    response = RedirectResponse(url="/store", status_code=303)
    return response

@wmarket_router.post("/add_product")
async def add_product_post(request: Request,
                      session_token=Cookie(default=None),
                      category: str = Form(),
                      product_name: str = Form(),
                      product_price: int = Form(),
                      product_description: str = Form(),
                      product_image: UploadFile = File()):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            try:
                file_content = await product_image.read()
                file_ext = os.path.splitext(product_image.filename)[1]
                if file_ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif']:
                    raise HTTPException(status_code=400, detail="Неподдерживаемый формат изображения")

                filename = f"{uuid.uuid4()}{file_ext}"
                file_path = os.path.join(settings.UPLOAD_DIR, filename)

                with open(file_path, "wb") as buffer:
                    buffer.write(file_content)

                product_data = {"category_name": category,
                                "product_name": product_name,
                                "product_price": product_price,
                                "product_description": product_description,
                                "product_image_url": f"static/uploads/{filename}"}

                await add_new_product(product_data, payload.get("tg_id"))
            except Exception as e:
                print(str(e))

    response = RedirectResponse(url="/ads_review?moderation=true", status_code=303)
    return response


@wmarket_router.post("/edit_product")
async def edit_product_post(
        request: Request,
        session_token=Cookie(default=None),
        product_id: int = Form(),
        title: str = Form(),
        price: int = Form(),
        category: str = Form(),
        description: str = Form(),
        image: UploadFile = File(None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            product = await get_product_info(product_id, payload.get("tg_id"))
            if not product or product[1] != payload.get("tg_id"):
                return JSONResponse({"status": "error", "message": "Недостаточно прав"}, status_code=403)

            # Обновляем данные
            update_data = {
                "product_name": title,
                "product_price": price,
                "category_name": category,
                "product_description": description,
                "active": False  # Отправляем на модерацию
            }

            # Если загружено новое изображение
            if image and image.filename:
                file_content = await image.read()
                file_ext = os.path.splitext(image.filename)[1]
                if file_ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif']:
                    raise HTTPException(status_code=400, detail="Неподдерживаемый формат изображения")

                filename = f"{uuid.uuid4()}{file_ext}"
                file_path = os.path.join(settings.UPLOAD_DIR, filename)

                with open(file_path, "wb") as buffer:
                    buffer.write(file_content)

                update_data["product_image_url"] = f"static/uploads/{filename}"

            update_res = await update_product_post(product_id, update_data)
            if update_res:
                return JSONResponse({"status": "success"})
            else:
                return JSONResponse({"status": "error", "message": "Ошибка обновления"}, status_code=500)
    return JSONResponse({"status": "error", "message": "Неавторизованный запрос"}, status_code=401)


@wmarket_router.get('/ads/{product_id}')
async def ads_view(product_id: int, request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            # 0-product_id / 1-tg_id / 2-name / 3-price / 4-description / 5-image_url / 6-category_name / 7-created_at
            # 8-is_fav
            product_info = await get_product_info(product_id, payload.get("tg_id"))
            categories = await get_all_not_digit_categories()
            user_info = await get_user_info(product_info[1])
            positive_reviews = user_info[3]
            negative_reviews = user_info[4]
            reputation = positive_reviews - negative_reviews
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
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
                "admin": admin_res
            }
            return templates.TemplateResponse("ads.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response


# fav___________________________________________________________________________________________________________________
@wmarket_router.get("/favorite")
async def favs(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            all_favs = await get_all_user_favs(payload.get("tg_id"))
            all_products = await get_all_products(payload.get("tg_id"))
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at / 6-is_fav
            products = [[prod[0], prod[1], prod[2], prod[3], prod[4], prod[5], prod[6]] for prod in all_products if prod[4] in all_favs]
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
            context = {
                "request": request,
                "products": products,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res
            }
            return templates.TemplateResponse("favs.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response


@wmarket_router.post("/add_fav")
async def fav_add_post(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):

            form_data = await request.form()
            product_id = form_data.get("fav_id")
            await add_fav(payload.get("tg_id"), int(product_id))

            referer = request.headers.get("referer", "/store")
            return RedirectResponse(url=referer, status_code=303)

    response = RedirectResponse(url="/store", status_code=303)
    return response


@wmarket_router.post("/del_fav")
async def fav_dell_post(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):

            form_data = await request.form()
            product_id = form_data.get("fav_id")
            await del_fav(payload.get("tg_id"), int(product_id))

            referer = request.headers.get("referer", "/store")
            return RedirectResponse(url=referer, status_code=303)

    response = RedirectResponse(url="/store", status_code=303)
    return response


# profile_______________________________________________________________________________________________________________
@wmarket_router.get("/profile")
async def profile(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            user_info = await get_user_info(payload.get("tg_id"))
            positive_reviews = user_info[3]
            negative_reviews = user_info[4]
            reputation = positive_reviews - negative_reviews
            products = await get_user_active_products(payload.get("tg_id"), payload.get("tg_id"))
            now = datetime.now(timezone.utc)
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
            referrals_count = await get_ref_count(payload.get("tg_id"))

            context = {
                "request": request,
                "reputation": reputation,
                "positive_reviews": positive_reviews,
                "negative_reviews": negative_reviews,
                "user_info": user_info,
                "user_tg_id": payload.get("tg_id"),
                "user_products": products,
                "now": now,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "referrals_count": referrals_count
            }
            return templates.TemplateResponse("profile.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response


@wmarket_router.get("/profile/{seller_tg_id}")
async def another_profile(seller_tg_id: int, request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            if seller_tg_id == payload.get("tg_id"):
                response = RedirectResponse(url="/profile", status_code=303)
                return response

            # Проверяем блокировку пользователя
            block = await check_user_blocked_post(seller_tg_id)
            is_blocked = block.get("is_blocked", False)
            unblock_at = None

            if is_blocked:
                block_info = await check_user_block_post(seller_tg_id)
                unblock_time = block_info[0].replace(tzinfo=timezone.utc)  # если нет информации о часовом поясе
                current_time = datetime.now(timezone.utc)
                if block and unblock_time > current_time:
                    unblock_at = block_info[0].strftime("%d.%m.%Y %H:%M")
                else:
                    is_blocked = False

            user_info = await get_user_info(seller_tg_id)
            positive_reviews = user_info[3]
            negative_reviews = user_info[4]
            reputation = positive_reviews - negative_reviews
            products = await get_user_active_products(seller_tg_id, payload.get("tg_id"))
            now = datetime.now(timezone.utc)
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
            context = {
                "request": request,
                "reputation": reputation,
                "positive_reviews": positive_reviews,
                "negative_reviews": negative_reviews,
                "user_info": user_info,
                "user_tg_id": payload.get("tg_id"),
                "user_products": products,
                "now": now,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "is_blocked": is_blocked,
                "unblock_at": unblock_at
            }
            return templates.TemplateResponse("profile.html", context=context)

    response = RedirectResponse(url="/", status_code=303)
    return response


# chat__________________________________________________________________________________________________________________
@wmarket_router.get("/chats")
async def chats(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            # Получаем все чаты пользователя
            user_chats = await get_user_chats(payload.get("tg_id"))

            # Формируем список чатов для отображения
            chats_list = []
            for chat in user_chats:
                # Получаем информацию о продукте
                product = await get_product_info(chat.product_id, payload.get("tg_id"))

                # Получаем информацию о собеседнике
                other_participants = await get_chat_participants(chat.id, exclude_user_id=payload.get("tg_id"))
                other_user_id = other_participants[0].user_id if other_participants else None

                # Получаем данные пользователя
                other_user_info = await get_user_info(other_user_id) if other_user_id else None

                # Получаем последнее сообщение в чате
                last_message = await get_last_chat_message(chat.id)

                admin_res = await is_admin(payload.get("tg_id"))

                chats_list.append({
                    "id": chat.id,
                    "product_id": chat.product_id,
                    "product_title": product[2] if product else "Неизвестный товар",
                    "product_price": product[3] if product else 0,
                    "product_image": product[5] if product else "",
                    "seller_username": other_user_info[1] if other_user_info else "Неизвестный",
                    "last_message": last_message.content if last_message else "Чат начат",
                    "last_message_time": last_message.created_at.strftime("%H:%M") if last_message else "",
                    "unread_count": await count_unread_messages(chat.id, payload.get("tg_id")),
                    "admin": admin_res
                })

            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))

            context = {
                "request": request,
                "chats": chats_list,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res
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

    # Проверяем, заблокирован ли собеседник
    other_user_id = chat_data["other_user"].tg_id
    block = await check_user_blocked_post(other_user_id)
    is_blocked = block.get("is_blocked", False)
    unblock_at = None

    if is_blocked:
        block_info = await check_user_block_post(other_user_id)
        unblock_time = block_info[0].replace(tzinfo=timezone.utc)  # если нет информации о часовом поясе
        current_time = datetime.now(timezone.utc)
        if block and unblock_time > current_time:
            unblock_at = block_info[0].strftime("%d.%m.%Y %H:%M")
        else:
            is_blocked = False

    all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))

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
        "unblock_at": unblock_at
    }
    return templates.TemplateResponse("chat.html", context=context)


@wmarket_router.post("/leave_chat/{chat_id}")
async def leave_chat_route(chat_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    if not payload or "tg_id" not in payload:
        return {"status": "error", "message": "Invalid token"}

    # Проверяем, что пользователь действительно был участником чата
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


@wmarket_router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            if message_data["type"] == "get_history":
                # Отправляем историю сообщений при подключении
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
                message = await send_message(
                    message_data["chat_id"],
                    int(user_id),
                    message_data["content"]
                )
                if message:
                    # Отправляем уведомление о новом сообщении
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
        print(f"WebSocket error: {str(e)}")
        await websocket.close(code=1011)


@wmarket_router.get("/user_info/{user_id}")
async def get_user_info_endpoint(user_id: int):
    user_info = await get_user_info(user_id)
    if user_info:
        return {
            "first_name": user_info[1],
            "photo_url": user_info[2]
        }
    return {}


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


@wmarket_router.get("/admin/chat_reports")
async def admin_chat_reports(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return RedirectResponse(url="/", status_code=303)

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
    if admin_res:
        reports = await get_chat_reports(resolved=False)
        all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
        moderation_products = await get_all_moderation_products()
        context = {
            "request": request,
            "reports": reports,
            "all_undread_count_message": all_undread_count_message,
            "admin": admin_res,
            "moderation_products": moderation_products
        }
        return templates.TemplateResponse("admin_chat_reports.html", context=context)


@wmarket_router.get("/admin/chat/{chat_id}")
async def admin_chat_view(
        chat_id: int,
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return RedirectResponse(url="/", status_code=303)

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
    if admin_res:
        chat_data = await get_chat_messages(chat_id, None)
        if not chat_data:
            return RedirectResponse(url="/admin/chat_reports", status_code=303)

        all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))

        context = {
            "request": request,
            "chat_id": chat_id,
            "messages": chat_data["messages"],
            "product": chat_data["product"],
            "other_user": chat_data["other_user"],
            "current_user": {"id": 0, "is_admin": True},
            "all_undread_count_message": all_undread_count_message,
            "is_chat_page": True
        }
        return templates.TemplateResponse("chat.html", context=context)


@wmarket_router.post("/admin/resolve_report/{report_id}")
async def resolve_report_route(
        report_id: int,  # FastAPI автоматически преобразует параметр в int
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
    if admin_res:
        success = await resolve_chat_report(report_id, payload.get("tg_id"))
        return {"status": "success" if success else "error"}
    return {"status": "error", "message": "Unauthorized"}


# bot___________________________________________________________________________________________________________________
async def notify_new_message(chat_id: int, sender_id: int, content: str):
    """
    Отправляет уведомление о новом сообщении в чате
    :param chat_id: ID чата
    :param sender_id: ID отправителя сообщения
    :param content: Текст сообщения
    """
    try:
        # Получаем информацию о чате и участниках
        chat_data = await get_chat_messages(chat_id, sender_id)
        if not chat_data:
            print(f"Chat data not found for chat_id: {chat_id}")
            return

        receiver_id = chat_data["other_user"].tg_id
        product = chat_data["product"]
        username = await get_user_info(sender_id)

        # Формируем текст уведомления
        message = (
            f"💬 Новое сообщение от \n{username[1]} \n\n📢 Объявление:\n{product.product_name}"
        )

        # Отправляем уведомление получателю
        await send_notification_to_user(receiver_id, message, product.id)
        print(f"Notification sent to user {receiver_id} about new message in chat {chat_id}")

    except Exception as e:
        print(f"Error in notify_new_message: {e}", exc_info=True)


async def notify_product_approved(product_id: int):
    """
    Отправляет уведомление о том, что объявление прошло модерацию
    :param product_id: ID объявления
    """
    try:
        # Получаем информацию о продукте
        product = await get_product_info(product_id, None)
        if not product:
            print(f"Product not found: {product_id}")
            return

        seller_id = product[1]
        user_info = await get_user_info(seller_id)
        if not user_info:
            print(f"User info not found for seller: {seller_id}")
            return

        # Формируем текст уведомления
        message = (
            f"✅ Ваше объявление прошло модерацию!\n\n"
            f"📌 Название: {product[2]}\n"
            f"⚙️ Категория: {product[6]}\n"
            f"💰 Цена: {product[3]} ₽"
        )

        # Отправляем уведомление продавцу
        await send_notification_to_user(seller_id, message)
        print(f"Product approval notification sent to user {seller_id} for product {product_id}")

    except Exception as e:
        print(f"Error in notify_product_approved: {e}", exc_info=True)


async def notify_product_rejected(product_id: int, reason: str = None):
    """
    Отправляет уведомление о том, что объявление не прошло модерацию
    :param product_id: ID объявления
    :param reason: Причина отказа (опционально)
    """
    try:
        # Получаем информацию о продукте
        product = await get_product_info(product_id, None)
        if not product:
            print(f"Product not found: {product_id}")
            return

        seller_id = product[1]
        user_info = await get_user_info(seller_id)
        if not user_info:
            print(f"User info not found for seller: {seller_id}")
            return

        # Формируем текст уведомления
        message = (
            f"❌ Ваше объявление не прошло модерацию\n\n"
            f"📌 Название: {product[2]}\n"
            f"📝 Причина/пункт: {reason}\n\n"
            f'Вы можете исправить его (<a href="https://telegra.ph/Osnovnye-punkty-i-prichiny-blokirovki-06-26">прочитав причину или пункт</a>)'
            f" и повторно опубликовать."
        )

        # Отправляем уведомление продавцу
        await send_notification_to_user(seller_id, message)
        print(f"Product rejection notification sent to user {seller_id} for product {product_id}")

    except Exception as e:
        print(f"Error in notify_product_rejected: {e}", exc_info=True)


@wmarket_router.post("/admin/approve_product/{product_id}")
async def approve_product(product_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
    if admin_res:
        # Обновляем статус продукта
        update_data = {"active": True}
        update_res = await update_product_post(product_id, update_data)

        if update_res:
            # Отправляем уведомление продавцу
            await notify_product_approved(product_id)
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
    admin_res = await is_admin(payload.get("tg_id"))
    if admin_res:
        data = await request.json()
        reason = data.get("reason", "")

        # Обновляем статус продукта
        update_data = {"active": False}
        update_res = await update_product_post(product_id, update_data)

        if update_res:
            # Отправляем уведомление продавцу с причиной
            await notify_product_rejected(product_id, reason)
            await delete_product_post(product_id)
            return {"status": "success"}

    return {"status": "error", "message": "Неавторизованный запрос"}


# ban___________________________________________________________________________________________________________________
@wmarket_router.get("/admin/get_chat_info/{chat_id}")
async def get_chat_info(chat_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
    if admin_res:
        chat_info = await get_chat_info_post(chat_id)
        return chat_info
    return {"status": "error", "message": "Unauthorized"}


@wmarket_router.post("/admin/block_user")
async def block_user(
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
    if not admin_res:
        return {"status": "error", "message": "Unauthorized"}

    data = await request.json()
    user_id = data.get("user_id")
    duration = data.get("duration")
    reason = data.get("reason", "")
    chat_id = data.get("chat_id")
    report_id = int(data.get("report_id"))

    # Вычисляем срок блокировки
    if duration == "1h":
        unblock_at = datetime.now(timezone.utc) + timedelta(hours=1)
    elif duration == "1d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=1)
    elif duration == "7d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=7)
    elif duration == "30d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=30)
    elif duration == "365d":
        unblock_at = datetime.now(timezone.utc) + timedelta(days=365)
    else:  # permanent
        unblock_at = None

    # Сохраняем блокировку в базе данных
    await block_user_post(user_id, int(report_id), payload.get("tg_id"), reason, unblock_at)

    # Отправляем уведомления
    await notify_user_blocked(user_id, duration, reason)
    await notify_reporter_about_block(int(report_id), user_id)

    return {"status": "success"}


async def notify_user_blocked(user_id: int, duration: str, reason: str):
    duration_text = {
        "1h": "1 час",
        "1d": "1 день",
        "7d": "7 дней",
        "30d": "30 дней",
        "365d": "1 год",
        "permanent": "навсегда"
    }.get(duration, duration)

    message = (
        f"⛔ Ваш аккаунт был заблокирован администратором.\n\n"
        f"⌛ Срок блокировки: {duration_text}\n"
        f"📝 Причина: {reason or 'не указана'}\n\n"
        f"Если Вы считаете, что это ошибка, свяжитесь с поддержкой - справа снизу "
        f"@Wmarket_app (сообщение каналу) или @Wmarket_support"
    )

    await send_notification_to_user(user_id, message)


async def notify_reporter_about_block(report_id: int, blocked_user_id: int):
    report = await notify_reporter_about_block_post(int(report_id))

    if report:
        blocked_user = await get_user_info(blocked_user_id)
        message = (

            f"⚠️ Ваша жалоба была рассмотрена.\n\n"
            f"Пользователь {blocked_user[1]} был заблокирован за нарушение правил маркета.\n"
            f"Спасибо за помощь в поддержании порядка на площадке! ❤️‍🔥"
        )

        await send_notification_to_user(report.reporter_id, message)


@wmarket_router.get("/check_user_block")
async def check_user_block(request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return {"is_blocked": False}

    payload = await decode_jwt(session_token)
    block = await check_user_block_post(payload.get("tg_id"))

    print(block)
    if block:
        unblock_time = block[0].replace(tzinfo=timezone.utc)  # если нет информации о часовом поясе
        current_time = datetime.now(timezone.utc)
        if block and unblock_time > current_time:
            return {
                "is_blocked": True,
                "unblock_at": block[0].isoformat() if block[0] else None
            }
    return {"is_blocked": False}


@wmarket_router.get("/blocked")
async def blocked_page(request: Request, session_token=Cookie(default=None)):
    context = {
        "request": request,
        "all_undread_count_message": 0,
        "is_chat_page": True
    }
    return templates.TemplateResponse("blocked.html", context=context)


@wmarket_router.get("/check_user_blocked/{user_id}")
async def check_user_blocked(user_id: int):
    await check_user_blocked_post(user_id)