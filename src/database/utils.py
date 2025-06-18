from .database import async_session_maker, User, Category, Product, Fav
from sqlalchemy.future import select
from sqlalchemy import update, desc, asc


# auth&users_utils______________________________________________________________________________________________________
async def add_user(user_data, session_token):
    async with async_session_maker() as db:
        try:
            user = User(tg_id=user_data.get("tg_id"),
                        first_name=user_data.get("first_name"),
                        last_name=user_data.get("last_name"),
                        username=user_data.get("username"),
                        photo_url=user_data.get("photo_url"),
                        token=session_token)
            db.add(user)
            await db.commit()
            return True
        except Exception as exc:
            print(exc)
            return False


async def update_token(session_token, new_session_token):
    async with async_session_maker() as db:
        try:
            q = update(User).where(User.token == session_token).values(token=new_session_token)
            await db.execute(q)
            await db.commit()
        except Exception as exc:
            print(exc)


async def get_all_users():
    async with async_session_maker() as db:
        try:
            q = select(User)
            result = await db.execute(q)
            users = result.scalars()
            all_tg_id = [u.tg_id for u in users]
            return all_tg_id
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_user_jwt(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(User).filter_by(tg_id=tg_id)
            result = await db.execute(q)
            session_token = result.scalar_one_or_none()
            return session_token
        except Exception as exc:
            print(f"Error: {exc}")


async def get_user_info(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(User).filter_by(tg_id=tg_id)
            result = await db.execute(q)
            user = result.scalar_one_or_none()
            # 0-tg_id / 1-username / 2-photo_url
            user_info = [user.tg_id, user.username, user.photo_url]
            return user_info
        except Exception as exc:
            print(f"Error: {exc}")
            return []


# cats&products_utils_______________________________________________________________________________________________
async def get_all_categories():
    async with async_session_maker() as db:
        try:
            q = select(Category)
            result = await db.execute(q)
            categories = result.scalars()
            all_categories = [cat.category_name for cat in categories]
            return all_categories
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_all_products(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Product).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at / 6-is_fav
            all_products = [[prod.product_name, prod.product_price,
                             prod.product_description, prod.product_image_url,
                             prod.id, prod.created_at] for prod in products]
            all_favs = await get_all_user_favs(tg_id)
            [prod.append(True) if prod[4] in all_favs else prod.append(False) for prod in all_products]
            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_all_products_from_category(category_name, tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Product).filter_by(category_name=category_name).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at / 6-is_fav
            all_products = [[prod.product_name, prod.product_price,
                             prod.product_description, prod.product_image_url,
                             prod.id, prod.created_at] for prod in products]
            all_favs = await get_all_user_favs(tg_id)
            [prod.append(True) if prod[4] in all_favs else prod.append(False) for prod in all_products]
            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_product_info(product_id, tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Product).filter_by(id=product_id)
            result = await db.execute(q)
            product = result.scalar_one_or_none()
            # 0-product_id / 1-tg_id / 2-name / 3-price / 4-description / 5-image_url / 6-category_name / 7-created_at
            # 8-is_fav
            product_info = [product.id, product.tg_id, product.product_name, product.product_price,
                            product.product_description, product.product_image_url, product.category_name,
                            product.created_at]
            all_favs = await get_all_user_favs(tg_id)
            if product.id in all_favs:
                product_info.append(True)
            else:
                product_info.append(False)
            return product_info
        except Exception as exc:
            print(exc)


async def add_new_product(product_data, tg_id):
    async with async_session_maker() as db:
        try:
            product = Product(tg_id=tg_id,
                              category_name=product_data.get("category_name"),
                              product_name=product_data.get("product_name"),
                              product_price=product_data.get("product_price"),
                              product_description=product_data.get("product_description"),
                              product_image_url=product_data.get("product_image_url"))
            db.add(product)
            await db.commit()
        except Exception as exc:
            print(exc)


# favs__________________________________________________________________________________________________________________
async def get_all_user_favs(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Fav).filter_by(tg_id=tg_id)
            result = await db.execute(q)
            favs = result.scalars()
            all_favs = [fav.product_id for fav in favs]
            return all_favs
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def add_fav(tg_id, product_id):
    async with async_session_maker() as db:
        try:
            q = await db.execute(select(Fav).filter_by(tg_id=tg_id, product_id=product_id))
            fav = q.scalars().first()
            if not fav:
                fav = Fav(tg_id=tg_id,
                          product_id=product_id)
                db.add(fav)
                await db.commit()
        except Exception as exc:
            print(exc)


async def del_fav(tg_id, product_id):
    async with async_session_maker() as db:
        try:
            q = await db.execute(select(Fav).filter_by(tg_id=tg_id, product_id=product_id))
            fav = q.scalars().first()
            await db.delete(fav)
            await db.commit()
        except Exception as exc:
            print(exc)