import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import APIRouter, Request, Cookie, Form, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update, func, desc
from starlette.responses import JSONResponse

from src.bot import send_notification_to_user
from src.config import settings, manager
from src.database.database import async_session_maker, User, TonTransaction, ChatParticipant, Chat, Deal, Review, \
    Product
from src.database.utils import (get_all_users, add_user, update_token, get_all_categories, get_all_products,
                                get_all_products_from_category, add_fav, get_all_user_favs, del_fav, get_user_info,
                                add_new_product, get_product_info, get_user_active_products,
                                get_user_moderation_products, create_chat, get_chat_messages, report_message,
                                send_message, get_chat_participants,
                                get_user_chats, all_count_unread_messages, get_all_digit_categories,
                                get_all_not_digit_categories, resolve_chat_report, get_chat_reports, report_chat,
                                user_exists, record_referral, get_ref_count, get_chat_part_info,
                                get_user_archived_products, delete_product_post, archive_product_post,
                                restore_product_post, update_product_post, get_all_moderation_products,
                                leave_chat_post, check_user_in_chat, get_chat_info_post, block_user_post,
                                notify_reporter_about_block_post, check_user_blocked_post, check_user_block_post,
                                get_all_users_info, get_current_currency, set_current_currency, get_balance_user_info,
                                add_ton_balance, get_user_ton_transactions, create_ton_transaction,
                                get_user_active_deals, get_user_completed_deals, get_pending_deals,
                                get_user_reserved_deals, get_count_fav_add, get_user_active_deals_count,
                                get_product_info_with_all_photos)
from src.tonapi import TonapiClient, withdraw_ton_request
from src.utils import parse_init_data, encode_jwt, decode_jwt, is_admin, get_ton_to_rub_rate

wmarket_router = APIRouter(
    prefix="",
    tags=["wmarket_router"]
)

def from_json(value):
    return json.loads(value)

templates = Jinja2Templates(directory="templates")
templates.env.filters['from_json'] = from_json


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
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))
            context = {
                "request": request,
                "cats": cats,
                "dig_cats": dig_cats,
                "products": products,
                "now": now,
                "all_undread_count_message": all_undread_count_message,
                "user_tg_id": payload.get("tg_id"),
                "admin": admin_res,
                "active_deals_count": active_deals_count
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
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))
            context = {
                "request": request,
                "cats": cats,
                "dig_cats": dig_cats,
                "products": products,
                "now": now,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "active_deals_count": active_deals_count
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
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))
            context = {
                "request": request,
                "categories": categories,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "active_deals_count": active_deals_count
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
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

            context = {
                "request": request,
                "active_products": active_products,
                "moderation_products": moderation_products,
                "archived_products": archived_products,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "current_tab": tab,  # Добавляем текущую вкладку в контекст
                "active_deals_count": active_deals_count
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
async def add_product_post(
        request: Request,
        session_token=Cookie(default=None),
        category: str = Form(),
        product_name: str = Form(),
        product_price: int = Form(),
        product_description: str = Form(),
        product_images: List[UploadFile] = File(...)  # Теперь принимаем список файлов
):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            try:
                image_urls = []

                # Ограничиваем количество изображений до 10
                if len(product_images) > 10:
                    raise HTTPException(status_code=400, detail="Можно загрузить не более 10 изображений")

                for image in product_images:
                    file_content = await image.read()
                    file_ext = os.path.splitext(image.filename)[1]
                    if file_ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif']:
                        raise HTTPException(status_code=400, detail="Неподдерживаемый формат изображения")

                    filename = f"{uuid.uuid4()}{file_ext}"
                    file_path = os.path.join(settings.UPLOAD_DIR, filename)

                    with open(file_path, "wb") as buffer:
                        buffer.write(file_content)

                    image_urls.append(f"static/uploads/{filename}")

                product_data = {
                    "category_name": category,
                    "product_name": product_name,
                    "product_price": product_price,
                    "product_description": product_description,
                    "product_image_url": json.dumps(image_urls)  # Сохраняем как JSON строку
                }

                await add_new_product(product_data, payload.get("tg_id"))

                # Отправляем уведомление пользователю
                await send_notification_to_user(
                    payload.get("tg_id"),
                    "✅ Ваше объявление отправлено на проверку\n\n"
                    f"📌 Название: {product_name}\n"
                    f"⚙️ Категория: {category}\n"
                    f"💰 Цена: {product_price} ₽\n"
                    f"📸 Фотографий: {len(image_urls)}\n\n"
                    "Обычно проверка занимает до 24 часов."
                )

                return JSONResponse({"status": "success", "redirect": "/ads_review?tab=moderation"})

            except Exception as e:
                print(str(e))
                raise HTTPException(status_code=500, detail="Ошибка при добавлении товара")

    raise HTTPException(status_code=401, detail="Неавторизованный запрос")


@wmarket_router.post("/report_product")
async def report_product(
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
    product_id = data.get("product_id")

    try:
        # Явно преобразуем product_id в int
        product_id_int = int(product_id)
    except (TypeError, ValueError):
        return {"status": "error", "message": "Invalid product ID"}

    # Получаем информацию о продукте
    product = await get_product_info(product_id_int, None)
    if not product:
        return {"status": "error", "message": "Product not found"}

    # Отправляем объявление на повторную проверку
    update_data = {"active": False}  # Отправляем на модерацию
    update_res = await update_product_post(product_id_int, update_data)

    if update_res:
        # Отправляем уведомление владельцу
        await send_notification_to_user(
            product[1],  # tg_id владельца
            f"⚠️ Ваше объявление '{product[2]}' было отправлено на повторную проверку администратором."
        )
        return {"status": "success"}

    return {"status": "error", "message": "Failed to update product"}


@wmarket_router.post("/edit_product")
async def edit_product_post(
        request: Request,
        session_token=Cookie(default=None),
        product_id: int = Form(),
        title: str = Form(),
        price: int = Form(),
        category: str = Form(),
        description: str = Form(),
        current_images: str = Form(),
        new_images: List[UploadFile] = File(None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            product = await get_product_info(product_id, payload.get("tg_id"))
            if not product or product[1] != payload.get("tg_id"):
                return JSONResponse({"status": "error", "message": "Недостаточно прав"}, status_code=403)

            try:
                # Обрабатываем текущие изображения
                existing_images = json.loads(current_images) if current_images else []

                # Обрабатываем новые изображения
                new_image_urls = []
                if new_images:
                    # Ограничиваем количество изображений до 10
                    if len(existing_images) + len(new_images) > 10:
                        raise HTTPException(status_code=400, detail="Можно загрузить не более 10 изображений")

                    for image in new_images:
                        try:
                            # Проверяем тип содержимого файла
                            content_type = image.content_type
                            if content_type not in ['image/jpeg', 'image/png', 'image/gif']:
                                raise HTTPException(status_code=400,
                                                    detail=f"Неподдерживаемый формат изображения: {content_type}")

                            file_content = await image.read()

                            # Проверяем сигнатуры файлов для дополнительной валидации
                            if len(file_content) < 12:  # Минимальный размер для проверки сигнатур
                                raise HTTPException(status_code=400, detail="Файл слишком мал для изображения")

                            # Проверка сигнатур популярных форматов
                            if (file_content.startswith(b'\xFF\xD8\xFF') or  # JPEG
                                    file_content.startswith(b'\x89PNG\r\n\x1a\n') or  # PNG
                                    file_content.startswith(b'GIF87a') or  # GIF
                                    file_content.startswith(b'GIF89a')):
                                pass  # Valid image
                            else:
                                raise HTTPException(status_code=400, detail="Файл не является допустимым изображением")

                            file_ext = os.path.splitext(image.filename)[1].lower()
                            if file_ext not in ['.jpg', '.jpeg', '.png', '.gif']:
                                file_ext = '.jpg'  # Default extension if not provided or invalid

                            filename = f"{uuid.uuid4()}{file_ext}"
                            file_path = os.path.join(settings.UPLOAD_DIR, filename)

                            with open(file_path, "wb") as buffer:
                                buffer.write(file_content)

                            new_image_urls.append(f"static/uploads/{filename}")
                        except Exception as e:
                            print(f"Error processing image {image.filename}: {str(e)}")
                            continue  # Пропускаем проблемные файлы вместо падения всего запроса

                # Объединяем существующие и новые изображения
                all_images = existing_images + new_image_urls

                if not all_images:
                    raise HTTPException(status_code=400, detail="Должна быть хотя бы одна фотография")

                # Обновляем данные
                update_data = {
                    "product_name": title,
                    "product_price": price,
                    "category_name": category,
                    "product_description": description,
                    "product_image_url": json.dumps(all_images),
                    "active": False  # Отправляем на модерацию
                }

                update_res = await update_product_post(product_id, update_data)
                if update_res:
                    # Отправляем уведомление пользователю
                    await send_notification_to_user(
                        payload.get("tg_id"),
                        "✅ Ваше объявление отправлено на проверку\n\n"
                        f"📌 Название: {title}\n"
                        f"⚙️ Категория: {category}\n"
                        f"💰 Цена: {price} ₽\n"
                        f"📸 Фотографий: {len(all_images)}\n\n"
                        "Обычно проверка занимает до 24 часов."
                    )

                    return JSONResponse({
                        "status": "success",
                        "redirect": "/ads_review?tab=moderation"
                    })
                else:
                    return JSONResponse({"status": "error", "message": "Ошибка обновления"}, status_code=500)

            except HTTPException as he:
                raise he
            except Exception as e:
                print(str(e))
                raise HTTPException(status_code=500, detail="Ошибка при обновлении товара")

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
            product_info = await get_product_info_with_all_photos(product_id, payload.get("tg_id"))
            categories = await get_all_not_digit_categories()
            user_info = await get_user_info(product_info[1])
            positive_reviews = user_info[3]
            negative_reviews = user_info[4]
            reputation = positive_reviews - negative_reviews
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
            fav_count = await get_count_fav_add(product_id)
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
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))
            context = {
                "request": request,
                "products": products,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "active_deals_count": active_deals_count
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
            admin_crown = await is_admin(user_info[0])
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))
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
                "referrals_count": referrals_count,
                "admin_crown": admin_crown,
                "active_deals_count": active_deals_count
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
            admin_crown = await is_admin(user_info[0])
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))
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
                "unblock_at": unblock_at,
                "admin_crown": admin_crown,
                "active_deals_count": active_deals_count
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

            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

            context = {
                "request": request,
                "chats": user_chats,  # Use the returned list directly
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

    # Проверяем, заблокирован ли собеседник
    if chat_data["other_user"]:
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
                # Получаем получателя из базы данных
                participants = await get_chat_participants(message_data["chat_id"])
                receiver_id = next((p.user_id for p in participants if p.user_id != int(user_id)), None)

                if not receiver_id:
                    continue

                # Проверяем, подключен ли получатель к чату
                receiver_connected = manager.is_connected(str(receiver_id))

                message = await send_message(
                    message_data["chat_id"],
                    int(user_id),
                    message_data["content"],
                    mark_unread=not receiver_connected
                )

                if message:
                    # Отправляем уведомление только если получатель не в чате
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
        users = await get_all_users_info()

        # Получаем отзывы на модерации
        async with async_session_maker() as session:
            result = await session.execute(
                select(Review)
                .where(Review.moderated == False)
                .order_by(Review.created_at.desc())
            )
            reviews = result.scalars().all()

        # Получаем сделки, ожидающие отмены
        pending_deals = await get_pending_deals()
        active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

        context = {
            "request": request,
            "reports": reports,
            "all_undread_count_message": all_undread_count_message,
            "admin": admin_res,
            "moderation_products": moderation_products,
            "users": users,
            "reviews": reviews,
            "pending_deals": pending_deals,  # Добавляем сделки в контекст
            "active_tab": request.query_params.get("tab", "reports"),
            "active_deals_count": active_deals_count
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
    Отправляет уведомление о новом сообщении в чате только если получатель не в чате
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

        # Проверяем, подключен ли получатель к чату
        if manager.is_connected(str(receiver_id)):
            print(f"User {receiver_id} is in chat, skipping notification")
            return

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
    block = data.get("block", True)  # По умолчанию блокируем
    duration = data.get("duration", None)
    reason = data.get("reason", "")

    # Если это запрос на разблокировку
    if not block:
        await block_user_post(user_id, None, None, None, None)

        message = (
            f"✅ Ваш аккаунт был досрочно разблокирован администратором.\n\n"
            f"⚠️ Пожалуйста, больше не нарушайте правила Маркета."
        )

        await send_notification_to_user(user_id, message)

        return {"status": "success", "message": "User unblocked"}

    # Определяем время разблокировки
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

    # Сохраняем блокировку в базе данных
    await block_user_post(user_id, None, payload.get("tg_id"), reason, unblock_at)

    # Отправляем уведомление пользователю
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


# async def notify_user_blocked(user_id: int, duration: str, reason: str):
#     duration_text = {
#         "1h": "1 час",
#         "1d": "1 день",
#         "7d": "7 дней",
#         "30d": "30 дней",
#         "365d": "1 год",
#         "permanent": "навсегда"
#     }.get(duration, duration)
#
#     message = (
#         f"⛔ Ваш аккаунт был заблокирован администратором.\n\n"
#         f"⌛ Срок блокировки: {duration_text}\n"
#         f"📝 Причина: {reason or 'не указана'}\n\n"
#         f"Если Вы считаете, что это ошибка, свяжитесь с поддержкой - справа снизу "
#         f"@Wmarket_app (сообщение каналу) или @Wmarket_support"
#     )
#
#     await send_notification_to_user(user_id, message)


# async def notify_reporter_about_block(report_id: int, blocked_user_id: int):
#     report = await notify_reporter_about_block_post(int(report_id))
#
#     if report:
#         blocked_user = await get_user_info(blocked_user_id)
#         message = (
#
#             f"⚠️ Ваша жалоба была рассмотрена.\n\n"
#             f"Пользователь {blocked_user[1]} был заблокирован за нарушение правил маркета.\n"
#             f"Спасибо за помощь в поддержании порядка на площадке! ❤️‍🔥"
#         )
#
#         await send_notification_to_user(report.reporter_id, message)


@wmarket_router.get("/check_user_block")
async def check_user_block(request: Request, session_token=Cookie(default=None)):
    if not session_token:
        return {"is_blocked": False}

    payload = await decode_jwt(session_token)
    block = await check_user_block_post(payload.get("tg_id"))

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
        "is_chat_page": True,
        "active_deals_count": 0
    }
    return templates.TemplateResponse("blocked.html", context=context)


@wmarket_router.get("/check_user_blocked/{user_id}")
async def check_user_blocked(user_id: int):
    await check_user_blocked_post(user_id)


@wmarket_router.get("/wallet")
async def wallet_page(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
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


tonapi = TonapiClient(api_key=settings.TONAPI_KEY)


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
            # Создаем запись о транзакции
            transaction = await create_ton_transaction(
                payload.get("tg_id"),
                amount,
                "deposit"
            )

            # Проверяем транзакцию через tonapi
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
            # Обновляем баланс
            await add_ton_balance(payload.get("tg_id"), amount)

            # Обновляем статус транзакции
            await session.execute(
                update(TonTransaction)
                .where(TonTransaction.id == transaction.id)
                .values(status="completed")
            )
            await session.commit()

            # Отправляем уведомление
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
                # Создаем запись о транзакции
                tx = await create_ton_transaction(
                    payload.get("tg_id"),
                    amount,
                    "withdraw"
                )

                # Проверяем баланс пользователя
                user = await session.execute(select(User).where(User.tg_id == payload.get("tg_id")))
                user = user.scalar_one_or_none()

                if not user:
                    return JSONResponse({"status": "error", "message": "User not found"}, status_code=404)

                if user.ton_balance < amount:
                    return JSONResponse(
                        {"status": "error", "message": "Недостаточно средств на балансе"},
                        status_code=400
                    )

                # Выполняем вывод
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

                # Обновляем баланс пользователя
                user.ton_balance -= amount

                # Обновляем статус транзакции
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


@wmarket_router.get("/deals")
async def deals(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            tab = request.query_params.get('tab', 'active')

            # Получаем все типы сделок
            active_deals = await get_user_active_deals(payload.get("tg_id"))
            completed_deals = await get_user_completed_deals(payload.get("tg_id"))
            reserved_deals = await get_user_reserved_deals(payload.get("tg_id"))  # Новая функция

            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = await is_admin(payload.get("tg_id"))
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

            context = {
                "request": request,
                "active_deals": active_deals,
                "completed_deals": completed_deals,
                "reserved_deals": reserved_deals,  # Добавляем в контекст
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "current_tab": tab,
                "user_tg_id": payload.get("tg_id"),
                "active_deals_count": active_deals_count
            }
            return templates.TemplateResponse("deals.html", context=context)

    response = RedirectResponse(url="/", status_code=303)
    return response


@wmarket_router.get("/check_chat_exists/{product_id}")
async def check_chat_exists(product_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"exists": False}

    payload = await decode_jwt(session_token)
    buyer_id = payload.get("tg_id")

    # Get product owner
    product = await get_product_info(product_id, None)
    if not product:
        return {"exists": False}

    seller_id = product[1]

    # Check if chat exists between buyer and seller for this product
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


@wmarket_router.get("/get_ton_to_rub_rate")
async def get_ton_to_rub_rate_endpoint():
    rate = await get_ton_to_rub_rate()
    if rate:
        return JSONResponse({"rate": rate})
    else:
        return JSONResponse({"status": "error", "message": "Не удалось получить курс TON/RUB"}, status_code=500)


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

    # Получаем информацию о продукте
    product = await get_product_info(product_id, None)
    if not product:
        return JSONResponse({"status": "error", "message": "Product not found"}, status_code=404)

    seller_id = product[1]
    buyer_id = payload.get("tg_id")

    if seller_id == buyer_id:
        return JSONResponse({"status": "error", "message": "Cannot buy your own product"}, status_code=400)

    async with async_session_maker() as session:
        try:
            # Для встречи не проверяем баланс
            if currency != 'meet':
                # Проверяем баланс и списываем средства
                user = await session.execute(select(User).where(User.tg_id == buyer_id))
                user = user.scalar_one_or_none()

                if currency == 'rub':
                    if user.rub_balance < amount:
                        return JSONResponse(
                            {"status": "error", "message": "Недостаточно средств на рублёвом балансе"},
                            status_code=400
                        )
                    user.rub_balance -= amount
                else:  # TON
                    if user.ton_balance < amount:
                        return JSONResponse(
                            {"status": "error", "message": "Недостаточно средств на TON балансе"},
                            status_code=400
                        )
                    user.ton_balance -= amount

            # Создаем сделку
            deal = Deal(
                product_id=product_id,
                product_name=product[2],
                seller_id=seller_id,
                buyer_id=buyer_id,
                amount=amount,
                currency=currency,
                status="active",
                created_at=datetime.now(timezone.utc)
            )
            session.add(deal)
            await session.commit()

            # Получаем информацию о покупателе
            buyer_info = await get_user_info(buyer_id)

            # Отправляем уведомление продавцу
            if currency == 'meet':
                await send_notification_to_user(
                    seller_id,
                    f"💰 Покупатель хочет встретиться для оплаты!\n\n"
                    f"📌 Название: {product[2]}\n"
                    f"💰 Сумма: {product[3]} ₽ (оплата при встрече)\n"
                    f"👤 Покупатель: {buyer_info[1] or 'без username'}\n\n"
                    f"Договоритесь о времени и месте встречи в чате."
                )
            else:
                await send_notification_to_user(
                    seller_id,
                    f"💰 Товар оплачен, и ждёт подтверждения!\n\n"
                    f"📌 Название: {product[2]}\n"
                    f"💰 Сумма: {amount} {currency.upper()}\n"
                    f"👤 Покупатель: {buyer_info[1] or 'без username'}\n\n"
                    f"Выдайте товар покупателю, чтобы он мог подтвердить сделку."
                )

            # Отправляем уведомление покупателю
            if currency == 'meet':
                await send_notification_to_user(
                    buyer_id,
                    f"✅ Вы создали сделку с оплатой при встрече!\n\n"
                    f"📌 Товар: {product[2]}\n"
                    f"💰 Сумма: {product[3]} ₽\n"
                    f"👤 Продавец: {product[1]}\n\n"
                    f"Договоритесь о времени и месте встречи в чате."
                )

            return JSONResponse({"status": "success"})

        except Exception as e:
            await session.rollback()
            print(f"Error creating deal: {e}")
            return JSONResponse(
                {"status": "error", "message": "Internal server error"},
                status_code=500
            )


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
            # Получаем сделку
            result = await session.execute(select(Deal).where(Deal.id == int(deal_id)))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            # Проверяем, что это покупатель подтверждает сделку
            if deal.buyer_id != payload.get("tg_id"):
                return JSONResponse(
                    {"status": "error", "message": "Only buyer can confirm deal"},
                    status_code=403
                )

            # Проверяем статус сделки
            if deal.status != "active":
                return JSONResponse(
                    {"status": "error", "message": "Deal is not active"},
                    status_code=400
                )

            # Для сделок с личной встречей отправляем на модерацию
            if deal.currency == 'meet':
                deal.pending_cancel = True
                deal.cancel_reason = "Ожидает подтверждения администратором (личная встреча)"
                deal.cancel_request_by = payload.get("tg_id")

                # Создаем отзыв (но не добавляем в репутацию пока)
                review = Review(
                    deal_id=deal.id,
                    from_user_id=deal.buyer_id,
                    to_user_id=deal.seller_id,
                    product_id=deal.product_id,
                    rating=rating,
                    text=review_text,
                    moderated=False  # Отзыв тоже на модерации
                )
                session.add(review)

                await session.commit()

                # Уведомления
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

            # Для обычных сделок (rub/ton) завершаем автоматически
            # Рассчитываем сумму с учетом комиссии (7%)
            seller_amount = deal.amount * 0.93
            market_fee = deal.amount * 0.07

            # Обновляем статус сделки
            deal.status = "completed"
            deal.completed_at = datetime.now(timezone.utc)

            # Зачисляем средства продавцу
            seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
            seller = seller.scalar_one_or_none()

            # Добавляем баланс продавцу в зависимости от валюты сделки
            if deal.currency == 'rub':
                if seller.earned_rub is None:
                    seller.earned_rub = 0.0
                seller.earned_rub += seller_amount
                seller.rub_balance += seller_amount
            else:  # TON
                if seller.earned_ton is None:
                    seller.earned_ton = 0.0
                seller.earned_ton += seller_amount
                seller.ton_balance += seller_amount

            # Создаем отзыв
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

            # Архивируем товар
            await archive_product_post(deal.product_id)

            # Получаем информацию о пользователях
            buyer_info_arr = await get_user_info(deal.buyer_id)
            seller_info_arr = await get_user_info(deal.seller_id)

            # Отправляем уведомление продавцу
            await send_notification_to_user(
                deal.seller_id,
                f"✅ Сделка завершена!\n\n"
                f"📌 Товар: {deal.product_name}\n"
                f"💰 Сумма: {seller_amount:.2f} {deal.currency.upper()} (комиссия: {market_fee:.2f})\n"
                f"👤 {buyer_info_arr[1]} подтвердил получение товара.\n\n"
                f"Средства зачислены на ваш баланс!"
            )

            # Отправляем уведомление покупателю
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


@wmarket_router.post("/admin/moderate_review/{review_id}")
async def moderate_review(
        review_id: int,
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    approve = data.get("approve", False)
    reason = data.get("reason", "")

    async with async_session_maker() as session:
        try:
            # Получаем отзыв
            result = await session.execute(select(Review).where(Review.id == review_id))
            review = result.scalar_one_or_none()

            if not review:
                return JSONResponse({"status": "error", "message": "Review not found"}, status_code=404)

            if approve:
                # Обновляем репутацию пользователя
                user = await session.execute(select(User).where(User.tg_id == review.to_user_id))
                user = user.scalar_one_or_none()

                if review.rating > 0:
                    user.plus_rep += 1
                else:
                    user.minus_rep += 1

                review.moderated = True

                # Отправляем уведомление пользователю
                from_user_info = await get_user_info(review.from_user_id)
                to_user_info = await get_user_info(review.to_user_id)

                await send_notification_to_user(
                    review.to_user_id,
                    f"📢 Ваш рейтинг обновлён!\n\n"
                    f"Получен {'положительный' if review.rating > 0 else 'отрицательный'} отзыв "
                    f"от пользователя {from_user_info[1] if from_user_info else 'неизвестен'}.\n\n"
                    f"Текст отзыва: {review.text}"
                )

                # Уведомление автору отзыва
                await send_notification_to_user(
                    review.from_user_id,
                    f"✅ Ваш отзыв был одобрен модератором и учтён в репутации пользователя."
                )
            else:
                # Отклоняем отзыв
                await session.delete(review)

                # Уведомление автору отзыва
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
            # Если время истекло, отправляем сделку на модерацию
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
        deal_id = int(data.get("deal_id"))  # Convert to integer
    except (TypeError, ValueError):
        return JSONResponse({"status": "error", "message": "Invalid deal ID"}, status_code=400)

    reason = data.get("reason")

    async with async_session_maker() as session:
        try:
            # Получаем сделку - now using the integer deal_id
            result = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            # Проверяем, что сделка активна
            if deal.status != "active":
                return JSONResponse({"status": "error", "message": "Deal is not active"}, status_code=400)

            # Проверяем, что запрос на отмену еще не отправлен
            if deal.pending_cancel:
                return JSONResponse({"status": "error", "message": "Cancel request already sent"}, status_code=400)

            # Обновляем статус сделки
            deal.pending_cancel = True
            deal.cancel_reason = reason
            deal.cancel_request_by = payload.get("tg_id")

            await session.commit()

            # Отправляем уведомления
            other_user_id = deal.buyer_id if payload.get("tg_id") == deal.seller_id else deal.seller_id

            # Уведомление инициатору
            await send_notification_to_user(
                payload.get("tg_id"),
                f"✅ Ваш запрос на отмену сделки по товару '{deal.product_name}' отправлен на модерацию.\n\n"
                f"Причина: {reason}\n\n"
                f"Ожидайте решения администратора."
            )

            # Уведомление второй стороне
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

@wmarket_router.post("/admin/moderate_cancel_request/{deal_id}")
async def moderate_cancel_request(
        deal_id: int,
        request: Request,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    approve = data.get("approve", False)

    async with async_session_maker() as session:
        try:
            # Получаем сделку
            deal = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = deal.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if not deal.pending_cancel:
                return JSONResponse({"status": "error", "message": "No pending cancellation"}, status_code=400)

            if approve:
                # Возвращаем средства покупателю
                buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
                buyer = buyer.scalar_one_or_none()

                if deal.currency == 'rub':
                    buyer.rub_balance += deal.amount
                else:
                    buyer.ton_balance += deal.amount

                # Обновляем статус сделки
                deal.status = "cancelled"
                deal.completed_at = datetime.now(timezone.utc)
                deal.pending_cancel = False

                # Отправляем уведомления
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
                # Отклоняем запрос на отмену
                deal.pending_cancel = False

                # Отправляем уведомления
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


@wmarket_router.get("/api/user_reviews/{user_id}")
async def get_user_reviews(user_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    async with async_session_maker() as session:
        try:
            # Получаем отзывы о пользователе
            result = await session.execute(
                select(Review, User.first_name)
                .join(User, Review.from_user_id == User.tg_id)
                .where(Review.to_user_id == user_id)
                .where(Review.moderated == True)
                .order_by(desc(Review.created_at)))

            reviews = []
            for review, from_user_name in result.all():
                reviews.append({
                    "id": review.id,
                    "from_user_id": review.from_user_id,
                    "from_user_name": from_user_name,
                    "to_user_id": review.to_user_id,
                    "rating": review.rating,
                    "text": review.text,
                    "created_at": review.created_at.isoformat()
                })

            return reviews

        except Exception as e:
            print(f"Error getting user reviews: {e}")
            return JSONResponse({"status": "error", "message": "Internal server error"}, status_code=500)


# Добавим эти endpoint'ы в wmarket_router

@wmarket_router.get("/admin/get_deal_info/{deal_id}")
async def get_deal_info(
    deal_id: int,
    session_token=Cookie(default=None)
):
    if not session_token:
        return {"status": "error", "message": "Unauthorized"}

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
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

        # Получаем информацию о пользователях
        seller = await get_user_info(deal.seller_id)
        buyer = await get_user_info(deal.buyer_id)

        return {
            "id": deal.id,
            "product_name": deal.product_name,
            "seller_id": deal.seller_id,
            "seller_first_name": seller[1] if seller else "Unknown",
            "buyer_id": deal.buyer_id,
            "buyer_first_name": buyer[1] if buyer else "Unknown",
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
    admin_res = await is_admin(payload.get("tg_id"))
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    action = data.get("action")  # "for_seller" или "for_buyer"
    reason = data.get("reason", "")

    async with async_session_maker() as session:
        try:
            # Получаем сделку
            result = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if deal.status != "active":
                return JSONResponse({"status": "error", "message": "Deal is not active"}, status_code=400)

            # Получаем информацию о пользователях
            buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
            buyer = buyer.scalar_one_or_none()
            seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
            seller = seller.scalar_one_or_none()

            if action == "for_seller":
                # Рассчитываем сумму с учетом комиссии (7%)
                seller_amount = deal.amount * 0.93
                market_fee = deal.amount * 0.07

                # Зачисляем средства продавцу
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
                # Возвращаем средства покупателю
                if deal.currency == 'rub':
                    buyer.rub_balance += deal.amount
                else:
                    buyer.ton_balance += deal.amount

                # Обновляем статус сделки
                deal.status = "completed_by_admin"
                deal.completed_at = datetime.now(timezone.utc)
                deal.admin_decision = "for_buyer"
                deal.admin_reason = reason
                deal.admin_id = payload.get("tg_id")

                # Отправляем уведомления
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
    admin_res = await is_admin(payload.get("tg_id"))
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    hours = int(data.get("hours", 24))
    reason = data.get("reason", "")

    async with async_session_maker() as session:
        try:
            # Получаем сделку
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
            # Get the product
            result = await session.execute(select(Product).where(Product.id == product_id))
            product = result.scalar_one_or_none()

            if not product:
                return JSONResponse({"status": "error", "message": "Product not found"}, status_code=404)

            # Check if product is already reserved
            if product.reserved and product.reserved_until > datetime.now(timezone.utc):
                return JSONResponse(
                    {"status": "error", "message": "Product is already reserved"},
                    status_code=400
                )

            # Get user balance
            user = await session.execute(select(User).where(User.tg_id == payload.get("tg_id")))
            user = user.scalar_one_or_none()

            if not user:
                return JSONResponse({"status": "error", "message": "User not found"}, status_code=404)

            # Deduct balance
            if currency == 'rub':
                if user.rub_balance < amount:
                    return JSONResponse(
                        {"status": "error", "message": "Insufficient RUB balance"},
                        status_code=400
                    )
                user.rub_balance -= amount
            else:  # TON
                if user.ton_balance < amount:
                    return JSONResponse(
                        {"status": "error", "message": "Insufficient TON balance"},
                        status_code=400
                    )
                user.ton_balance -= amount

            # Update product reservation status
            product.reserved = True
            product.reserved_until = datetime.now(timezone.utc) + timedelta(hours=48)
            product.reserved_by = payload.get("tg_id")
            product.reservation_amount = amount
            product.reservation_currency = currency

            product_price = product.product_price
            if currency == "ton":
                ton_rate = await get_ton_to_rub_rate()
                product_price = round(product_price / ton_rate, 4)

            # Create a new deal record for the reservation
            deal = Deal(
                product_id=product.id,
                product_name=product.product_name,
                seller_id=product.tg_id,
                buyer_id=payload.get("tg_id"),
                amount=product_price,  # Full price of the product
                currency=currency,
                status="reserved",
                is_reserved=True,
                reservation_amount=amount,
                reservation_until=datetime.now(timezone.utc) + timedelta(hours=48),
                created_at=datetime.now(timezone.utc)
            )
            session.add(deal)

            await session.commit()

            # Send notification to seller
            await send_notification_to_user(
                product.tg_id,
                f"🔒 Ваш товар '{product.product_name}' был забронирован!\n\n"
                f"👤 Покупатель: {user.first_name or 'без username'}\n"
                f"💰 Сумма брони: {amount} {currency.upper()}\n"
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


@wmarket_router.post("/complete_reservation")
async def complete_reservation(
    request: Request,
    session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    data = await request.json()
    deal_id = int(data.get("deal_id"))  # Преобразуем в int

    async with async_session_maker() as session:
        try:
            # Получаем сделку - теперь используем целочисленный deal_id
            result = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if not deal.is_reserved:
                return JSONResponse({"status": "error", "message": "Deal is not reserved"}, status_code=400)

            if deal.buyer_id != payload.get("tg_id"):
                return JSONResponse({"status": "error", "message": "Not your reservation"}, status_code=403)

            # Проверяем баланс покупателя
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

            # Обновляем статус сделки
            deal.is_reserved = False
            deal.reservation_until = None
            deal.status = "active"

            # Обновляем статус товара
            product = await session.execute(select(Product).where(Product.id == deal.product_id))
            product = product.scalar_one_or_none()
            if product:
                product.reserved = False
                product.reserved_until = None
                product.reserved_by = None

            await session.commit()

            # Отправляем уведомление продавцу
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
    deal_id = int(data.get("deal_id"))  # Преобразуем в int
    is_expired = data.get("is_expired", False)

    async with async_session_maker() as session:
        try:
            # Получаем сделку - теперь используем целочисленный deal_id
            result = await session.execute(select(Deal).where(Deal.id == deal_id))
            deal = result.scalar_one_or_none()

            if not deal:
                return JSONResponse({"status": "error", "message": "Deal not found"}, status_code=404)

            if not deal.is_reserved:
                return JSONResponse({"status": "error", "message": "Deal is not reserved"}, status_code=400)

            # Проверяем права (только покупатель или истекшее время)
            if not is_expired and deal.buyer_id != payload.get("tg_id"):
                return JSONResponse({"status": "error", "message": "Not your reservation"}, status_code=403)

            # Возвращаем 2/3 суммы брони
            buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
            buyer = buyer.scalar_one_or_none()

            refund_amount = deal.reservation_amount * 2 / 3

            if deal.currency == 'rub':
                buyer.rub_balance += refund_amount
            else:
                buyer.ton_balance += refund_amount

            # Обновляем статус сделки и товара
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

            # Отправляем уведомления
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


@wmarket_router.get("/api/deal_info/{deal_id}")
async def get_deal_info(deal_id: int):
    async with async_session_maker() as session:
        result = await session.execute(select(Deal).where(Deal.id == deal_id))
        deal = result.scalar_one_or_none()
        if deal:
            return {
                "id": deal.id,
                "product_name": deal.product_name,
                "currency": deal.currency,
                "amount": deal.amount,
                "status": deal.status
            }
        return {"status": "error", "message": "Deal not found"}


@wmarket_router.post("/admin/complete_meet_deal/{deal_id}")
async def complete_meet_deal(
    deal_id: int,
    request: Request,
    session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    admin_res = await is_admin(payload.get("tg_id"))
    if not admin_res:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=403)

    data = await request.json()
    action = data.get("action")  # "confirm" или "cancel"

    async with async_session_maker() as session:
        try:
            # Получаем сделку
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
                # Подтверждаем сделку - только меняем статус, не трогая отзыв
                deal.status = "completed"
                deal.completed_at = datetime.now(timezone.utc)
                deal.pending_cancel = False

                seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
                seller = seller.scalar_one_or_none()

                # Рассчитываем сумму с учетом комиссии (7%)
                seller_amount = deal.amount * 0.93
                market_fee = deal.amount * 0.07

                seller.rub_balance += seller_amount
                if seller.earned_rub is None:
                    seller.earned_rub = 0.0
                seller.earned_rub += seller_amount

                await archive_product_post(deal.product_id)

                # Отправляем уведомления
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
                # Отменяем сделку и удаляем отзыв
                deal.status = "cancelled"
                deal.completed_at = datetime.now(timezone.utc)
                deal.pending_cancel = False

                # Удаляем отзыв, если он есть
                review = await session.execute(
                    select(Review)
                    .where(Review.deal_id == deal_id)
                    .where(Review.moderated == False)
                )
                review = review.scalar_one_or_none()

                if review:
                    await session.delete(review)

                # Отправляем уведомления
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


@wmarket_router.get("/api/check_review_exists")
async def check_review_exists(deal_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return {"exists": False}

    payload = await decode_jwt(session_token)
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count())
            .select_from(Review)
            .where(Review.deal_id == deal_id)
            .where(Review.from_user_id == payload.get("tg_id"))
        )
        count = result.scalar()
        return {"exists": count > 0}