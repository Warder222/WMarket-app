from datetime import datetime, timezone

from fastapi import Request, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func

from src.database.database import async_session_maker, Referral
from src.database.methods import (get_all_users, all_count_unread_messages,
                                  check_user_blocked_post, check_user_block_post, get_user_active_deals_count,
                                  get_user_info_new, get_user_active_products_new)
from src.endpoints._endpoints_config import wmarket_router, templates
from src.utils import decode_jwt, is_admin_new


@wmarket_router.get("/profile")
async def profile(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            user_info = await get_user_info_new(payload.get("tg_id"))
            positive_reviews = user_info["plus_rep"]
            negative_reviews = user_info["minus_rep"]
            reputation = positive_reviews - negative_reviews
            products = await get_user_active_products_new(payload.get("tg_id"), payload.get("tg_id"))
            now = datetime.now(timezone.utc)
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
            referrals_count = []
            async with async_session_maker() as db:
                try:
                    refs = await db.execute(
                        select(func.count()).select_from(Referral).where(
                            (Referral.referrer_id == payload.get("tg_id"))
                        )
                    )

                    referrals_count = refs.scalar()
                except Exception as exc:
                    print(f"Error: {exc}")

            admin_crown = False
            moderator_hat = False
            admin_role = await is_admin_new(user_info["tg_id"])
            if admin_role == "founder":
                admin_crown = True
            elif admin_role and admin_role != "founder":
                moderator_hat = True
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
                "moderator_hat": moderator_hat,
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

            block = await check_user_blocked_post(seller_tg_id)
            is_blocked = block.get("is_blocked", False)
            unblock_at = None

            if is_blocked:
                block_info = await check_user_block_post(seller_tg_id)
                unblock_time = block_info[0].replace(tzinfo=timezone.utc)
                current_time = datetime.now(timezone.utc)
                if block and unblock_time > current_time:
                    unblock_at = block_info[0].strftime("%d.%m.%Y %H:%M")
                else:
                    is_blocked = False

            user_info = await get_user_info_new(seller_tg_id)
            positive_reviews = user_info["plus_rep"]
            negative_reviews = user_info["minus_rep"]
            reputation = positive_reviews - negative_reviews
            products = await get_user_active_products_new(seller_tg_id, payload.get("tg_id"))
            now = datetime.now(timezone.utc)
            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
            admin_crown = False
            moderator_hat = False
            admin_role = await is_admin_new(user_info["tg_id"])
            if admin_role == "founder":
                admin_crown = True
            elif admin_role and admin_role != "founder":
                moderator_hat = True
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
                "moderator_hat": moderator_hat,
                "active_deals_count": active_deals_count
            }
            return templates.TemplateResponse("profile.html", context=context)

    response = RedirectResponse(url="/", status_code=303)
    return response


#block__________________________________________________________________________________________________________________
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
#_______________________________________________________________________________________________________________________