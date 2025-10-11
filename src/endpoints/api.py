import json
from datetime import datetime, timezone
from fastapi import Cookie, Request
from sqlalchemy import and_, desc, func, select, or_
from starlette.responses import JSONResponse

from src.config import settings
from src.database.database import Product, Review, User, async_session_maker, Deal
from src.database.methods import (
    check_user_blocked_post,
    get_all_products_from_category_new,
    get_all_products_new,
    get_all_user_favs,
    get_user_active_products_new,
    get_user_archived_products_new,
    get_user_moderation_products_new,
)
from src.endpoints._endpoints_config import wmarket_api_router
from src.utils import can_manage_admins, decode_jwt, is_admin_new


@wmarket_api_router.get("/products")
async def get_products(
        request: Request,
        page: int = 1,
        category: str = None,
        search: str = None,
        cities: str = None,
        price_min: float = None,
        price_max: float = None,
        session_token=Cookie(default=None)
):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    per_page = 20

    try:
        async with async_session_maker() as session:
            # Базовый запрос
            query = select(Product).where(Product.active == True)

            # Применяем фильтры
            if category:
                query = query.where(Product.category_name == category)

            if search:
                search_filter = or_(
                    Product.product_name.ilike(f"%{search}%"),
                    Product.product_description.ilike(f"%{search}%")
                )
                query = query.where(search_filter)

            if cities:
                city_list = [city.strip() for city in cities.split(',')]
                query = query.where(Product.location.in_(city_list))

            if price_min is not None:
                query = query.where(Product.product_price >= price_min)

            if price_max is not None:
                query = query.where(Product.product_price <= price_max)

            # Сортировка и пагинация
            query = query.order_by(desc(Product.created_at))
            query = query.offset((page - 1) * per_page).limit(per_page)

            result = await session.execute(query)
            products = result.scalars().all()

            # Получаем избранные товары пользователя
            all_favs = await get_all_user_favs(payload.get("tg_id"))

            formatted_products = []
            for product in products:
                image_urls = json.loads(product.product_image_url) if product.product_image_url else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"

                is_new = (datetime.now(timezone.utc) - product.created_at).total_seconds() < 86400

                formatted_products.append({
                    'product_id': product.id,
                    'product_name': product.product_name,
                    'product_price': product.product_price,
                    'product_description': product.product_description,
                    'product_image_url': first_image,
                    'created_at': product.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'tg_id': product.tg_id,
                    'is_fav': product.id in all_favs,
                    'location': product.location,
                    'is_new': is_new
                })

            return JSONResponse({
                "status": "success",
                "products": formatted_products,
                "total": len(formatted_products)
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
        all_products = await get_all_products_new(payload.get("tg_id"))

        products = [prod for prod in all_products if prod["product_id"] in all_favs]

        total = len(products)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_products = products[start:end]

        formatted_products = []
        for product in paginated_products:
            product["created_at"] = product["created_at"].strftime('%Y-%m-%d %H:%M:%S') if isinstance(
                product["created_at"], datetime) else product["created_at"]
            formatted_products.append(product)

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
    per_page = 20

    try:
        if tab == 'active':
            products = await get_user_active_products_new(payload.get("tg_id"), payload.get("tg_id"))
        elif tab == 'moderation':
            products = await get_user_moderation_products_new(payload.get("tg_id"))
        elif tab == 'archived':
            products = await get_user_archived_products_new(payload.get("tg_id"))
        else:
            return JSONResponse({"status": "error", "message": "Invalid tab"}, status_code=400)

        total = len(products)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_products = products[start:end]

        formatted_products = []
        for product in paginated_products:
            product["created_at"] = product["created_at"].strftime('%Y-%m-%d %H:%M:%S') if isinstance(
                product["created_at"], datetime) else product["created_at"]
            formatted_products.append(product)

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
        products = await get_user_active_products_new(user_id, payload.get("tg_id"))

        total = len(products)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_products = products[start:end]

        formatted_products = []
        for product in paginated_products:
            product["created_at"] = product["created_at"].strftime('%Y-%m-%d %H:%M:%S') if isinstance(
                product["created_at"], datetime) else product["created_at"]
            product["is_new"] = (
                (datetime.now(timezone.utc) - product["created_at"]).total_seconds() < 86400 if isinstance(
                    product["created_at"],
                    datetime) else False)
            formatted_products.append(product)

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


@wmarket_api_router.get("/check_review_exists")
async def api_check_review_exists(deal_id: int, session_token=Cookie(default=None)):
    if not session_token:
        return JSONResponse({"status": "error", "message": "Unauthorized"}, status_code=401)

    payload = await decode_jwt(session_token)
    exists = await check_review_exists(deal_id, payload.get("tg_id"))

    return JSONResponse({"exists": exists})


@wmarket_api_router.get("/get_cities")
async def get_cities():
    return JSONResponse({"cities": settings.RUSSIAN_CITIES})