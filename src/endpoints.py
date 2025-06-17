import os
import uuid

from fastapi import APIRouter, Request, Cookie, Depends, Form, UploadFile, File, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from src.config import settings
from src.database.utils import (get_all_users, add_user,
                                update_token, get_all_categories, get_all_products,
                                get_all_products_from_category, add_fav, get_all_user_favs, del_fav, get_user_info,
                                add_new_product)
from src.utils import parse_init_data, encode_jwt, decode_jwt

from datetime import datetime, timezone, timedelta

wmarket_router = APIRouter(
    prefix="",
    tags=["wmarket_router"]
)

templates = Jinja2Templates(directory="templates")


# auth__________________________________________________________________________________________________________________
@wmarket_router.get("/")
async def index(request: Request,
                session_token=Cookie(default=None)):
    # if session_token:
    #     users = await get_all_users()
    #     payload = await decode_jwt(session_token)
    #
    #     if (payload.get("tg_id") in users
    #             and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
    #         response = RedirectResponse(url="/store", status_code=303)
    #         return response
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


@wmarket_router.post("/{oper}")
async def auth(oper: str, request: Request, session_token=Cookie(default=None)):
    form_data = await request.form()
    init_data = form_data.get("initData")
    user_data = parse_init_data(init_data)

    if oper == "auth":
        users = await get_all_users()
        if user_data.get("tg_id") not in users:
            response = RedirectResponse(url="/register", status_code=303)
            return response

    new_session_token = await encode_jwt({"tg_id": user_data.get("tg_id")})
    add_result = await add_user(user_data, new_session_token)
    if not add_result:
        await update_token(session_token, new_session_token)

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

            categories = await get_all_categories()
            products = await get_all_products(payload.get("tg_id"))
            now = datetime.now(timezone.utc)

            context = {
                "request": request,
                "categories": categories,
                "products": products,
                "now": now
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
            categories = await get_all_categories()
            products = await get_all_products_from_category(category_name, payload.get("tg_id"))
            now = datetime.now(timezone.utc)

            context = {
                "request": request,
                "categories": categories,
                "products": products,
                "now": now
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
            context = {
                "request": request,
                "categories": categories
            }
            return templates.TemplateResponse("add_product.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response


@wmarket_router.post("/add_product")
async def add_product(request: Request,
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
                max_size = 3 * 1024 * 1024

                if len(file_content) > max_size:
                    raise HTTPException(status_code=413, detail="Размер файла не должен превышать 5 МБ)")

                if product_price <= 0:
                    raise HTTPException(status_code=400, detail="Цена должна быть положительной")

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

    response = RedirectResponse(url="/store", status_code=303)
    return response


@wmarket_router.get("/test_add")
async def test_add():
    product_data = {"category_name": "Техника и электроника",
                    "product_name": "Samsung Galaxy S25 Ultra",
                    "product_price": 90000,
                    "product_description": "Абсолютно новая модель / Экран 6.9 (3120×1440) Dynamic AMOLED 2X 120 Гц / ПамятьВстроенная 512 ГБ, оперативная 12 ГБ / ФотоОсновная камера200 МП , 4 камеры",
                    "product_image_url": "/static/img/samsung.jpg"}
    test = await add_product(product_data, 1391622942)
    # 1391622942, 1002424749
    # Автомобили, Недвижимость, Мебель


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
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id
            products = [[prod[0], prod[1], prod[2], prod[3], prod[4]] for prod in all_products if prod[4] in all_favs]

            context = {
                "request": request,
                "products": products
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

            positive_reviews = 100
            negative_reviews = 50
            reputation = positive_reviews - negative_reviews

            user_info = await get_user_info(payload.get("tg_id"))

            context = {
                "request": request,
                "reputation": reputation,
                "positive_reviews": positive_reviews,
                "negative_reviews": negative_reviews,
                "user_info": user_info
            }
            return templates.TemplateResponse("profile.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response


# @wmarket_router.get("/profile/{username}")
# async def another_profile(username: str, request: Request, session_token=Cookie(default=None)):
#     if session_token:
#         users = await get_all_users()
#         payload = await decode_jwt(session_token)
#
#         if (payload.get("tg_id") in users
#                 and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
#             user_info = await get_user_info(payload.get("tg_id"))
#
#             if username in user_info:
#                 return RedirectResponse(url="/profile", status_code=303)
#
#             positive_reviews = 100
#             negative_reviews = 50
#             reputation = positive_reviews - negative_reviews
#
#             user_info = await get_user_info(payload.get("tg_id"))
#
#             context = {
#                 "request": request,
#                 "reputation": reputation,
#                 "positive_reviews": positive_reviews,
#                 "negative_reviews": negative_reviews,
#                 "user_info": user_info
#             }
#             return templates.TemplateResponse("profile.html", context=context)
#
#     response = RedirectResponse(url="/", status_code=303)
#     return response