from datetime import datetime, timezone

from fastapi import Request, Cookie
from fastapi.responses import RedirectResponse

from src.database.methods import (get_all_users, get_all_products,
                                  get_all_products_from_category,all_count_unread_messages, get_all_digit_categories,
                                  get_all_not_digit_categories, get_user_active_deals_count)
from src.endpoints._endpoints_config import wmarket_router, templates
from src.utils import decode_jwt, is_admin_new


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
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
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
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))
            context = {
                "request": request,
                "cats": cats,
                "dig_cats": dig_cats,
                "products": products,
                "now": now,
                "user_tg_id": payload.get("tg_id"),
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "active_deals_count": active_deals_count
            }
            return templates.TemplateResponse("store.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response