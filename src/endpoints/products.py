import json
import os
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import Cookie, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, update
from starlette.responses import JSONResponse

from src.bot import send_notification_to_user
from src.config import settings
from src.database.database import Category, Deal, Product, async_session_maker
from src.database.methods import (all_count_unread_messages, archive_product_post, get_all_users,
                                  get_product_info_new, get_user_active_deals_count, get_user_active_products_new,
                                  get_user_archived_products_new, get_user_moderation_products_new,
                                  update_product_post)
from src.endpoints._endpoints_config import templates, wmarket_router
from src.utils import decode_jwt, is_admin_new


@wmarket_router.get("/product_review")
async def product_review(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            tab = request.query_params.get('tab', 'active')

            active_products = []
            moderation_products = []
            archived_products = []

            if tab == 'active':
                active_products = await get_user_active_products_new(payload.get("tg_id"), payload.get("tg_id"))
            elif tab == 'moderation':
                moderation_products = await get_user_moderation_products_new(payload.get("tg_id"))
            elif tab == 'archived':
                archived_products = await get_user_archived_products_new(payload.get("tg_id"))

            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
            active_deals_count = await get_user_active_deals_count(payload.get("tg_id"))

            context = {
                "request": request,
                "active_products": active_products,
                "moderation_products": moderation_products,
                "archived_products": archived_products,
                "all_undread_count_message": all_undread_count_message,
                "admin": admin_res,
                "current_tab": tab,
                "active_deals_count": active_deals_count
            }
            return templates.TemplateResponse("product_review.html", context=context)

    response = RedirectResponse(url="/store", status_code=303)
    return response


@wmarket_router.get('/add_product')
async def add_product(request: Request, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):

            categories = []
            async with async_session_maker() as db:
                try:
                    q = select(Category)
                    result = await db.execute(q)
                    categories = result.scalars()
                    all_categories = [cat.category_name for cat in categories]
                    categories = all_categories
                except Exception as exc:
                    print(f"Error: {exc}")

            all_undread_count_message = await all_count_unread_messages(payload.get("tg_id"))
            admin_res = False
            admin_role = await is_admin_new(payload.get("tg_id"))
            if admin_role:
                admin_res = True
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


@wmarket_router.post("/add_product")
async def add_product_post(
        request: Request,
        session_token=Cookie(default=None),
        category: str = Form(),
        product_name: str = Form(),
        product_price: float = Form(),
        product_description: str = Form(),
        product_images: List[UploadFile] = File(...)
):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            try:
                image_urls = []

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
                    "product_image_url": json.dumps(image_urls)
                }

                async with async_session_maker() as db:
                    try:
                        product = Product(
                            tg_id=payload.get("tg_id"),
                            category_name=product_data.get("category_name"),
                            product_name=product_data.get("product_name"),
                            product_price=product_data.get("product_price"),
                            product_description=product_data.get("product_description"),
                            product_image_url=product_data.get("product_image_url")
                        )
                        db.add(product)
                        await db.commit()
                    except Exception as exc:
                        print(exc)

                await send_notification_to_user(
                    payload.get("tg_id"),
                    "✅ Ваше объявление отправлено на проверку\n\n"
                    f"📌 Название: {product_name}\n"
                    f"⚙️ Категория: {category}\n"
                    f"💰 Цена: {product_price} ₽\n"
                    f"📸 Фотографий: {len(image_urls)}\n\n"
                    "Обычно проверка занимает до 24 часов."
                )

                return JSONResponse({"status": "success", "redirect": "/product_review?tab=moderation"})

            except Exception as e:
                print(str(e))
                raise HTTPException(status_code=500, detail="Ошибка при добавлении товара")

    raise HTTPException(status_code=401, detail="Неавторизованный запрос")


@wmarket_router.post("/delete_product/{product_id}")
async def delete_product(product_id: int, session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):

            async with async_session_maker() as session:
                try:
                    await session.execute(
                        update(Deal)
                        .where(Deal.product_id == product_id)
                        .values(product_id=None)
                    )

                    # Теперь удаляем сам товар
                    result = await session.execute(
                        delete(Product)
                        .where(Product.id == product_id)
                        .where(Product.tg_id == payload.get("tg_id"))
                    )

                    await session.commit()

                    if result.rowcount > 0:
                        return JSONResponse({"status": "success"})
                    else:
                        return JSONResponse({"status": "error", "message": "Product not found or not owned by user"},
                                            status_code=404)

                except Exception as e:
                    await session.rollback()
                    print(f"Error deleting product: {e}")
                    return JSONResponse({"status": "error", "message": "Database error"}, status_code=500)

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
            rest_product = False
            async with async_session_maker() as db:
                try:
                    await db.execute(
                        update(Product)
                        .where(Product.id == product_id)
                        .values(active=True)
                    )
                    await db.commit()
                    rest_product = True
                except Exception as e:
                    print(e)

            if rest_product:
                return JSONResponse({"status": "success"})
            else:
                return JSONResponse({"status": "error"}, status_code=500)
    response = RedirectResponse(url="/store", status_code=303)
    return response


#ads____________________________________________________________________________________________________________________
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
        product_images: List[UploadFile] = File(None)
):
    if not session_token:
        raise HTTPException(status_code=401, detail="Неавторизованный запрос")

    payload = await decode_jwt(session_token)
    print(f"Editing product {product_id} for user {payload.get('tg_id')}")

    product = await get_product_info_new(product_id, payload.get("tg_id"))
    if not product or product["tg_id"] != payload.get("tg_id"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    try:
        print(f"Raw current_images: {current_images}")

        existing_images = []
        if current_images:
            try:
                temp_images = json.loads(current_images)
                print(f"Parsed current images: {temp_images}")
                existing_images = [img for img in temp_images if
                                   img and isinstance(img, str) and img.startswith('static/uploads/')]
            except json.JSONDecodeError as e:
                print(f"Error parsing current_images: {e}")
                existing_images = []

        print(f"Filtered existing images: {existing_images}")

        new_image_urls = []
        if product_images:
            print(f"Processing {len(product_images)} new images")
            for image in product_images:
                try:
                    print(f"Processing image: {image.filename}")
                    file_content = await image.read()
                    if not file_content:
                        print("Empty file content, skipping")
                        continue

                    file_ext = os.path.splitext(image.filename)[1].lower()
                    if file_ext not in ['.jpg', '.jpeg', '.png', '.gif']:
                        print(f"Invalid file extension: {file_ext}, skipping")
                        continue

                    filename = f"{uuid.uuid4()}{file_ext}"
                    file_path = os.path.join(settings.UPLOAD_DIR, filename)

                    with open(file_path, "wb") as buffer:
                        buffer.write(file_content)

                    new_url = f"static/uploads/{filename}"
                    new_image_urls.append(new_url)
                    print(f"Saved new image: {new_url}")
                except Exception as e:
                    print(f"Error processing image: {str(e)}")
                    continue

        all_images = existing_images + new_image_urls
        print(f"Final image list: {all_images}")

        if not all_images:
            raise HTTPException(status_code=400, detail="Должна быть хотя бы одна фотография")

        update_data = {
            "product_name": title,
            "product_price": price,
            "category_name": category,
            "product_description": description,
            "product_image_url": json.dumps(all_images),
            "active": False
        }

        print(f"Updating product with data: {update_data}")
        update_res = await update_product_post(product_id, update_data)

        if update_res:
            print("Product updated successfully")
            await send_notification_to_user(
                payload.get("tg_id"),
                "✅ Ваше объявление обновлено и отправлено на проверку"
            )

            return JSONResponse({
                "status": "success",
                "redirect": "/product_review?tab=moderation"
            })
        else:
            print("Failed to update product")
            raise HTTPException(status_code=500, detail="Ошибка при обновлении товара")

    except HTTPException as he:
        print(f"HTTPException: {he}")
        raise he
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении товара")
#_______________________________________________________________________________________________________________________