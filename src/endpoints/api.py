
from datetime import datetime, timezone

from fastapi import Request, Cookie, APIRouter
from sqlalchemy import select, func, desc
from starlette.responses import JSONResponse

from src.database.database import async_session_maker, User, Deal, Review
from src.database.methods import (get_all_products,
                                  get_all_products_from_category, get_all_user_favs, get_user_active_products,
                                  get_user_moderation_products,
                                  get_user_archived_products, check_user_blocked_post)
from src.endpoints._endpoints_config import wmarket_api_router
from src.utils import decode_jwt, is_admin_new, can_manage_admins


@wmarket_api_router.get("/products")
async def get_products(
        request: Request,
        page: int = 1,
        category: str = None,
        search: str = None,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    per_page = 20

    try:
        if category:
            products = await get_all_products_from_category(category, payload.get("tg_id"))
        else:
            products = await get_all_products(payload.get("tg_id"))

        if search:
            search_lower = search.lower()
            products = [p for p in products if search_lower in p[0].lower()]

        total = len(products)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_products = products[start:end]

        now = datetime.now(timezone.utc)
        formatted_products = []
        for product in paginated_products:
            created_at_str = product[5].strftime('%Y-%m-%d %H:%M:%S') if isinstance(product[5], datetime) else product[
                5]
            is_new = (now - product[5]).total_seconds() < 86400 if isinstance(product[5], datetime) else False

            formatted_product = list(product)
            formatted_product[5] = created_at_str
            formatted_product.append(is_new)
            formatted_products.append(formatted_product)

        return JSONResponse({
            "status": "success",
            "products": formatted_products,
            "total": total
        })
    except Exception as e:
        print(f"Error in get_products: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@wmarket_api_router.get("/favorites")
async def get_favorites(
        request: Request,
        page: int = 1,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    per_page = 20

    try:
        all_favs = await get_all_user_favs(payload.get("tg_id"))
        all_products = await get_all_products(payload.get("tg_id"))

        products = [prod for prod in all_products if prod[4] in all_favs]

        total = len(products)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_products = products[start:end]

        formatted_products = []
        for product in paginated_products:
            formatted_product = list(product)
            formatted_product[5] = product[5].strftime('%Y-%m-%d %H:%M:%S') if isinstance(product[5], datetime) else \
            product[5]
            formatted_products.append(formatted_product)

        return JSONResponse({
            "status": "success",
            "products": formatted_products,
            "total": total
        })
    except Exception as e:
        print(f"Error in get_favorites: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)



@wmarket_api_router.get("/user_review_products")
async def get_user_review_products(
        request: Request,
        page: int = 1,
        tab: str = 'active',
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    per_page = 20  # Количество товаров на странице

    try:
        if tab == 'active':
            products = await get_user_active_products(payload.get("tg_id"), payload.get("tg_id"))
        elif tab == 'moderation':
            products = await get_user_moderation_products(payload.get("tg_id"))
        elif tab == 'archived':
            products = await get_user_archived_products(payload.get("tg_id"))
        else:
            return JSONResponse({"status": "error", "message": "Invalid tab"}, status_code=400)

        # Пагинация
        total = len(products)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_products = products[start:end]

        # Форматирование дат
        formatted_products = []
        for product in paginated_products:
            formatted_product = list(product)
            formatted_product[5] = product[5].strftime('%Y-%m-%d %H:%M:%S') if isinstance(product[5], datetime) else product[5]
            formatted_products.append(formatted_product)

        return JSONResponse({
            "status": "success",
            "products": formatted_products,
            "total": total
        })
    except Exception as e:
        print(f"Error in get_user_products: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@wmarket_api_router.get("/user_products")
async def get_user_products(
        request: Request,
        user_id: int,
        page: int = 1,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    per_page = 20

    try:
        products = await get_user_active_products(user_id, payload.get("tg_id"))

        total = len(products)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_products = products[start:end]

        formatted_products = []
        for product in paginated_products:
            formatted_product = list(product)
            formatted_product[5] = product[5].strftime('%Y-%m-%d %H:%M:%S') if isinstance(product[5], datetime) else \
            product[5]
            formatted_product.append(
                (datetime.now(timezone.utc) - product[5]).total_seconds() < 86400 if isinstance(product[5],
                                                                                                datetime) else False)
            formatted_products.append(formatted_product)

        return JSONResponse({
            "status": "success",
            "products": formatted_products,
            "total": total
        })
    except Exception as e:
        print(f"Error in get_user_products: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@wmarket_api_router.get("/check_user_blocked/{user_id}")
async def check_user_blocked(user_id: int):
    await check_user_blocked_post(user_id)


@wmarket_api_router.get("/user_reviews/{user_id}")
async def get_user_reviews(user_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    async with async_session_maker() as session:
        try:
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


@wmarket_api_router.get("/deal_info/{deal_id}")
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


@wmarket_api_router.get("/check_review_exists")
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


@wmarket_api_router.get("/search_users")
async def search_users(request: Request, q: str, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    admin_role = await is_admin_new(payload.get("tg_id"))
    if not can_manage_admins(admin_role):
        return JSONResponse({"status": "error", "message": "Access denied"}, status_code=403)

    async with async_session_maker() as session:
        result = await session.execute(
            select(User)
            .where(User.username.ilike(f"{q}%"))
            .limit(10)
        )
        users = result.scalars().all()

        return [{
            "tg_id": user.tg_id,
            "first_name": user.username
        } for user in users]


# @wmarket_router.get("/user_info/{user_id}")
# async def get_user_info_endpoint(user_id: int):
#     user_info = await get_user_info(user_id)
#     if user_info:
#         return {
#             "first_name": user_info[1],
#             "photo_url": user_info[2]
#         }
#     return {}