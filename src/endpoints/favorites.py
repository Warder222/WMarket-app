from datetime import datetime, timezone

from fastapi import Request, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from starlette.responses import JSONResponse

from src.database.database import async_session_maker, Fav
from src.database.methods import (get_all_users, get_all_products_new, get_all_user_favs,
                                  all_count_unread_messages, get_user_active_deals_count)
from src.endpoints._endpoints_config import templates, wmarket_router
from src.utils import decode_jwt, is_admin_new


@wmarket_router.get("/favorite")
async def favs(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            all_favs = await get_all_user_favs(payload.get("tg_id"))
            all_products = await get_all_products_new(payload.get("tg_id"))

            products = [{'product_id': prod["product_id"],
                         'product_name': prod["product_name"],
                         'product_price': prod["product_price"],
                         'product_description': prod["product_description"],
                         'product_image_url': prod["product_image_url"],
                         'created_at': prod["created_at"],
                         'tg_id': prod["tg_id"],
                         'is_fav': prod["is_fav"]} for prod in all_products if prod["product_id"] in all_favs]

            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
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
        payload = await decode_jwt(session_token)
        form_data = await request.form()
        product_id = form_data.get("fav_id")
        async with async_session_maker() as db:
            try:
                q = await db.execute(select(Fav).filter_by(tg_id=payload.get("tg_id"), product_id=int(product_id)))
                fav = q.scalars().first()
                if not fav:
                    fav = Fav(tg_id=payload.get("tg_id"),
                              product_id=int(product_id))
                    db.add(fav)
                    await db.commit()
            except Exception as exc:
                print(exc)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JSONResponse({"status": "success"})

        return RedirectResponse(url=request.headers.get("referer", "/store"), status_code=303)
    return RedirectResponse(url="/", status_code=303)


@wmarket_router.post("/del_fav")
async def fav_dell_post(request: Request, session_token=Cookie(default=None)):
    if session_token:
        payload = await decode_jwt(session_token)
        form_data = await request.form()
        product_id = form_data.get("fav_id")
        async with async_session_maker() as db:
            try:
                q = await db.execute(select(Fav).filter_by(tg_id=payload.get("tg_id"), product_id=int(product_id)))
                fav = q.scalars().first()
                await db.delete(fav)
                await db.commit()
            except Exception as exc:
                print(exc)

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JSONResponse({"status": "success"})

        return RedirectResponse(url=request.headers.get("referer", "/store"), status_code=303)
    return RedirectResponse(url="/", status_code=303)
