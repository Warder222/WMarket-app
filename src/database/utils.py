import json
from datetime import datetime, timezone, timedelta

from starlette.responses import JSONResponse

from .database import async_session_maker, User, Category, Product, Fav, Chat, ChatParticipant, Message, ChatReport, \
    Referral, UserBlock, TonTransaction, Deal, Review
from sqlalchemy.future import select
from sqlalchemy import update, desc, asc, func, and_, delete, or_, insert, bindparam, Integer, exists


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


async def user_exists(tg_id: int) -> bool:
    async with async_session_maker() as session:
        result = await session.execute(select(func.count()).select_from(User).where(User.tg_id == tg_id))
        count = result.scalar()
        return count > 0


async def record_referral(referrer_id: int, referred_id: int) -> bool:
    async with async_session_maker() as session:
        try:
            existing_ref = await session.execute(
                select(func.count()).select_from(Referral).where(
                    (Referral.referrer_id == referrer_id) &
                    (Referral.referred_id == referred_id)
                )
            )

            if existing_ref.scalar() > 0:
                return False

            print(referrer_id, referred_id)
            referral = Referral(
                referrer_id=referrer_id,
                referred_id=referred_id
            )
            session.add(referral)
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            print(f"Error recording referral: {e}")
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
            if not user:
                return None
            # 0-tg_id / 1-username / 2-photo_url / 3-plus_rep / 4-minus_rep / 5-rub_balance / 6-ton_balance
            user_info = [user.tg_id, user.first_name, user.photo_url,
                         user.plus_rep, user.minus_rep, user.rub_balance, user.ton_balance,
                         user.earned_rub, user.earned_ton]
            return user_info
        except Exception as exc:
            print(f"Error: {exc}")
            return None


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


async def get_all_not_digit_categories():
    async with async_session_maker() as db:
        try:
            q = select(Category).filter_by(digital=False)
            result = await db.execute(q)
            categories = result.scalars()
            all_categories = [cat.category_name for cat in categories]
            return all_categories
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_all_digit_categories():
    async with async_session_maker() as db:
        try:
            q = select(Category).filter_by(digital=True)
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
            q = select(Product).filter_by(active=True).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at / 6-tg_id / 7-is_fav
            all_products = [[prod.product_name, prod.product_price,
                             prod.product_description,prod.product_image_url,
                             prod.id, prod.created_at, prod.tg_id] for prod in products]

            for product in all_products:
                image_urls = json.loads(product[3]) if product[3] else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"
                product[3] = first_image

            all_favs = await get_all_user_favs(tg_id)
            [prod.append(True) if prod[4] in all_favs else prod.append(False) for prod in all_products]
            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_all_products_from_category(category_name, tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Product).filter_by(category_name=category_name, active=True).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at / 6-tg_id / 7-is_fav
            all_products = [[prod.product_name, prod.product_price,
                             prod.product_description, prod.product_image_url[0],
                             prod.id, prod.created_at, prod.tg_id] for prod in products]
            all_favs = await get_all_user_favs(tg_id)
            all_products = [prod.append(True) if prod[4] in all_favs else prod.append(False) for prod in all_products]

            for product in all_products:
                image_urls = json.loads(product[3]) if product[3] else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"
                product[3] = first_image

            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_count_fav_add(product_id):
    async with async_session_maker() as db:
        try:
            q = select(Fav).filter_by(product_id=product_id)
            result = await db.execute(q)
            fav_count = result.scalars()
            fav_arr = [fav.tg_id for fav in fav_count]
            return len(fav_arr)
        except Exception as exc:
            print(f"Error: {exc}")
            return 0


# В функции get_product_info убедитесь, что запрос включает все поля:
async def get_product_info(product_id: int, user_tg_id: int | None):
    async with async_session_maker() as session:
        query = select(
            Product.id,
            Product.tg_id,
            Product.product_name,
            Product.product_price,
            Product.product_description,
            Product.product_image_url,
            Product.category_name,
            Product.created_at,
            # Добавляем проверку на избранное
            exists().where(
                and_(
                    Fav.tg_id == user_tg_id,
                    Fav.product_id == Product.id
                )
            ).label("is_fav"),
            Product.reserved,  # product_info[9]
            Product.reserved_by,  # product_info[10]
            Product.reserved_until,  # product_info[11]
            Product.reservation_amount,  # product_info[12]
            Product.reservation_currency  # product_info[13]
        ).where(Product.id == product_id)

        result = await session.execute(query)
        product = result.first()
        product = list(product)

        if not product:
            return None

        image_urls = json.loads(product[5]) if product[5] else []
        first_image = image_urls[0] if image_urls else "static/img/zaglush.png"
        product[5] = first_image

        return product


async def get_product_info_with_all_photos(product_id: int, user_tg_id: int | None):
    async with async_session_maker() as session:
        query = select(
            Product.id,
            Product.tg_id,
            Product.product_name,
            Product.product_price,
            Product.product_description,
            Product.product_image_url,
            Product.category_name,
            Product.created_at,
            # Добавляем проверку на избранное
            exists().where(
                and_(
                    Fav.tg_id == user_tg_id,
                    Fav.product_id == Product.id
                )
            ).label("is_fav"),
            Product.reserved,  # product_info[9]
            Product.reserved_by,  # product_info[10]
            Product.reserved_until,  # product_info[11]
            Product.reservation_amount,  # product_info[12]
            Product.reservation_currency  # product_info[13]
        ).where(Product.id == product_id)

        result = await session.execute(query)
        product = result.first()

        if not product:
            return None

        return product


async def add_new_product(product_data, tg_id):
    async with async_session_maker() as db:
        try:
            product = Product(
                tg_id=tg_id,
                category_name=product_data.get("category_name"),
                product_name=product_data.get("product_name"),
                product_price=product_data.get("product_price"),
                product_description=product_data.get("product_description"),
                product_image_url=product_data.get("product_image_url")  # Сохраняем как JSON строку
            )
            db.add(product)
            await db.commit()
        except Exception as exc:
            print(exc)


async def restore_product_post(product_id: int):
    async with async_session_maker() as db:
        try:
            await db.execute(
                update(Product)
                .where(Product.id == product_id)
                .values(active=True)
            )
            await db.commit()
            return True
        except Exception as e:
            print(e)
            return False

async def delete_product_post(product_id: int):
    async with async_session_maker() as db:
        try:
            await db.execute(delete(Fav).where(Fav.product_id == product_id))
            await db.execute(delete(Product).where(Product.id == product_id))
            await db.commit()
            return True
        except Exception as e:
            print(e)
            return False


async def archive_product_post(product_id: int):
    async with async_session_maker() as db:
        try:
            await db.execute(
                update(Product)
                .where(Product.id == product_id)
                .values(active=None)
            )
            await db.commit()
            return True
        except Exception as e:
            print(e)
            return False

async def update_product_post(product_id: int, update_data):
    async with async_session_maker() as db:
        try:
            print(f"Updating product {product_id} with data:", update_data)  # Логирование
            await db.execute(
                update(Product)
                .where(Product.id == int(product_id))
                .values(**update_data)
            )
            await db.commit()
            return True
        except Exception as e:
            print("Update error:", e)  # Логирование ошибки
            return False

async def get_user_archived_products(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Product).filter_by(tg_id=tg_id, active=None).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()
            all_products = [[prod.product_name, prod.product_price,
                     prod.product_description, prod.product_image_url,
                     prod.id, prod.created_at, prod.id] for prod in products]
            for product in all_products:
                image_urls = json.loads(product[3]) if product[3] else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"
                product[3] = first_image
            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_user_active_products(tg_id: int, current_user_id: int):
    async with async_session_maker() as session:
        try:
            # Получаем продукты с нужными полями
            result = await session.execute(
                select(
                    Product.product_name,
                    Product.product_price,
                    Product.product_description,
                    Product.product_image_url,
                    Product.id,
                    Product.created_at,
                    Product.id,  # Дублируем id для совместимости с шаблоном
                    Product.reserved  # Добавляем информацию о бронировании
                )
                .where(Product.tg_id == tg_id)
                .where(Product.active == True)
                .order_by(desc(Product.created_at)))

            products = result.all()

            # Получаем избранное текущего пользователя
            all_favs = await get_all_user_favs(current_user_id)

            # Формируем результат в том же формате, что и раньше
            all_products = []
            for prod in products:
                product_list = list(prod)
                # Добавляем флаг избранного (индекс 7)
                product_list.append(True if product_list[4] in all_favs else False)
                all_products.append(product_list)

            for product in all_products:
                image_urls = json.loads(product[3]) if product[3] else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"
                product[3] = first_image

            return all_products
        except Exception as exc:
            print(f"Error in get_user_active_products: {exc}")
            return []


async def get_user_moderation_products(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Product).filter_by(tg_id=tg_id, active=False).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at
            # 6-cat_name / 7-tg_id
            all_products = [[prod.product_name, prod.product_price,
                             prod.product_description, prod.product_image_url,
                             prod.id, prod.created_at, prod.category_name, prod.tg_id] for prod in products]
            # all_favs = await get_all_user_favs(tg_id)
            # [prod.append(True) if prod[4] in all_favs else prod.append(False) for prod in all_products]

            for product in all_products:
                image_urls = json.loads(product[3]) if product[3] else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"
                product[3] = first_image

            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_all_moderation_products():
    async with async_session_maker() as db:
        try:
            q = select(Product).filter_by(active=False).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at
            # 6-cat_name / 7-tg_id
            all_products = [[prod.product_name, prod.product_price,
                             prod.product_description, prod.product_image_url,
                             prod.id, prod.created_at, prod.category_name, prod.tg_id] for prod in products]
            # all_favs = await get_all_user_favs(tg_id)
            # [prod.append(True) if prod[4] in all_favs else prod.append(False) for prod in all_products]

            for product in all_products:
                image_urls = json.loads(product[3]) if product[3] else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"
                product[3] = first_image

            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []

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


# chats_________________________________________________________________________________________________________________
async def create_chat(product_id: int, buyer_id: int):
    async with async_session_maker() as db:
        # Получаем информацию о продукте
        product = await db.execute(select(Product).filter_by(id=product_id))
        product = product.scalar_one_or_none()

        if not product:
            return None

        # Проверяем, что пользователь не создает чат сам с собой
        if product.tg_id == buyer_id:
            return None

        # Проверяем существование чата
        existing_chat = await db.execute(
            select(Chat)
            .join(ChatParticipant, Chat.id == ChatParticipant.chat_id)
            .where(Chat.product_id == product_id)
            .where(ChatParticipant.user_id.in_([product.tg_id, buyer_id]))
            .group_by(Chat.id)
            .having(func.count(ChatParticipant.user_id) == 2)
        )
        existing_chat = existing_chat.scalar_one_or_none()

        if existing_chat:
            return existing_chat.id

        # Создаем новый чат
        chat = Chat(product_id=product_id)
        db.add(chat)
        await db.flush()

        # Добавляем участников
        participants = [
            ChatParticipant(chat_id=chat.id, user_id=product.tg_id),
            ChatParticipant(chat_id=chat.id, user_id=buyer_id)
        ]
        db.add_all(participants)
        await db.commit()
        return chat.id

async def check_user_in_chat(chat_id: int, user_id: int) -> bool:
    async with async_session_maker() as session:
        was_participant = await session.execute(
            select(func.count())
            .select_from(ChatParticipant)
            .where(
                (ChatParticipant.chat_id == chat_id) &
                (ChatParticipant.user_id == user_id)
            )
        )
        if not was_participant.scalar():
            return {"status": "error", "message": "Not a participant"}


async def leave_chat_post(chat_id: int, user_id: int) -> bool:
    """Пользователь покидает чат"""
    async with async_session_maker() as session:
        try:
            # Удаляем пользователя из участников чата
            await session.execute(
                delete(ChatParticipant)
                .where(
                    (ChatParticipant.chat_id == chat_id) &
                    (ChatParticipant.user_id == user_id)
                )
            )

            # Проверяем, остались ли другие участники
            remaining = await session.execute(
                select(func.count())
                .select_from(ChatParticipant)
                .where(ChatParticipant.chat_id == chat_id)
            )
            remaining_count = remaining.scalar()

            # Если участников не осталось, удаляем чат полностью
            if remaining_count == 0:
                await session.execute(delete(Message).where(Message.chat_id == chat_id))
                await session.execute(delete(ChatReport).where(ChatReport.chat_id == chat_id))
                await session.execute(delete(Chat).where(Chat.id == chat_id))

            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            print(f"Error leaving chat: {e}")
            return False


async def get_chat_messages(chat_id: int, user_id: int):
    async with async_session_maker() as db:
        # Помечаем сообщения как прочитанные
        await db.execute(
            update(Message)
            .where(Message.chat_id == chat_id, Message.receiver_id == user_id, Message.is_read == False)
            .values(is_read=True)
        )
        await db.commit()

        # Получаем все сообщения
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(asc(Message.created_at)))
        messages = result.scalars().all()

        # Получаем информацию о продукте и участниках
        chat = await db.execute(select(Chat).filter_by(id=chat_id))
        chat = chat.scalar_one_or_none()
        product = await db.execute(select(Product).filter_by(id=chat.product_id))
        product = product.scalar_one_or_none()

        participants = await db.execute(
            select(ChatParticipant.user_id)
            .where(ChatParticipant.chat_id == chat_id))
        participants = participants.scalars().all()

        other_user_id = next((p for p in participants if p != user_id), None)
        other_user = await db.execute(select(User).filter_by(tg_id=other_user_id))
        other_user = other_user.scalar_one_or_none()

        return {
            "messages": messages,
            "product": product,
            "other_user": other_user
        }

async def get_chat_info_post(chat_id):
    async with async_session_maker() as session:
        participants = await session.execute(
            select(ChatParticipant.user_id)
            .where(ChatParticipant.chat_id == chat_id)
        )
        user_ids = [p[0] for p in participants.all()]
        user_one = await get_user_info(user_ids[0])
        user_two = await get_user_info(user_ids[1])
        return {
            "user1_id": user_ids[0] if len(user_ids) > 0 else None,
            "user2_id": user_ids[1] if len(user_ids) > 1 else None,
            "user1_username": user_one[1] if len(user_ids) > 0 else None,
            "user2_username": user_two[1] if len(user_ids) > 1 else None,
        }


async def send_message(chat_id: int, sender_id: int, content: str, mark_unread: bool = True):
    async with async_session_maker() as db:
        # Получаем chat и определяем получателя
        participants = await db.execute(
            select(ChatParticipant.user_id)
            .where(ChatParticipant.chat_id == chat_id))
        participants = participants.scalars().all()
        receiver_id = next((p for p in participants if p != sender_id), None)

        if not receiver_id:
            return None

        message = Message(
            chat_id=chat_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            content=content,
            is_read=not mark_unread  # Устанавливаем статус прочитанности
        )
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message


async def report_message(message_id: int):
    async with async_session_maker() as db:
        await db.execute(
            update(Message)
            .where(Message.id == message_id)
            .values(reported=True))
        await db.commit()
        return True


async def get_user_chats(user_id: int):
    """Получить все активные чаты пользователя, отсортированные по последнему сообщению"""
    async with async_session_maker() as session:
        # Подзапрос для получения времени последнего сообщения в каждом чате
        last_message_subq = (
            select(
                Message.chat_id,
                func.max(Message.created_at).label('last_message_time')
            )
            .group_by(Message.chat_id)
            .subquery()
        )

        # Основной запрос
        result = await session.execute(
            select(
                Chat,
                last_message_subq.c.last_message_time
            )
            .join(ChatParticipant, ChatParticipant.chat_id == Chat.id)
            .join(last_message_subq, Chat.id == last_message_subq.c.chat_id, isouter=True)
            .where(ChatParticipant.user_id == user_id)
            .order_by(
                desc(last_message_subq.c.last_message_time),
                desc(Chat.created_at)
            )
        )

        chats_with_times = result.all()

        # Формируем полную информацию о чатах
        chats_with_info = []
        for chat, last_message_time in chats_with_times:
            # Получаем информацию о продукте
            product = await session.execute(select(Product).where(Product.id == chat.product_id))
            product = product.scalar_one_or_none()

            # Получаем информацию о собеседнике
            other_participants = await session.execute(
                select(ChatParticipant.user_id)
                .where(
                    (ChatParticipant.chat_id == chat.id) &
                    (ChatParticipant.user_id != user_id)
                )
            )
            other_user_id = other_participants.scalar_one_or_none()

            other_user = await session.execute(select(User).where(User.tg_id == other_user_id))
            other_user = other_user.scalar_one_or_none()

            # Получаем последнее сообщение - use first() instead of scalar_one_or_none()
            last_message = await session.execute(
                select(Message)
                .where(Message.chat_id == chat.id)
                .order_by(desc(Message.created_at))
                .limit(1)
            )
            last_message = last_message.first()
            if last_message:
                last_message = last_message[0]  # Extract the Message object from the row


            image_urls = json.loads(product.product_image_url) if product.product_image_url else []
            first_image = image_urls[0] if image_urls else "static/img/zaglush.png"
            product.product_image_url = first_image

            chats_with_info.append({
                "id": chat.id,
                "product_id": chat.product_id,
                "product_title": product.product_name if product else "Неизвестный товар",
                "product_price": product.product_price if product else 0,
                "product_image": product.product_image_url if product else "",
                "product_active": product.active if product else None,
                "seller_username": other_user.first_name if other_user else "Неизвестный",
                "last_message": last_message.content if last_message else "Чат начат",
                "last_message_time": last_message.created_at.strftime("%H:%M") if last_message else "",
                "unread_count": await count_unread_messages(chat.id, user_id)
            })

        return chats_with_info

async def get_chat_participants(chat_id: int, exclude_user_id: int = None):
    """Получить участников чата, исключая указанного пользователя"""
    async with async_session_maker() as session:
        query = select(ChatParticipant).where(ChatParticipant.chat_id == chat_id)
        if exclude_user_id:
            query = query.where(ChatParticipant.user_id != exclude_user_id)
        result = await session.execute(query)
        return result.scalars().all()

async def get_chat_part_info(chat_id: int):
    async with async_session_maker() as session:
        participants = await session.execute(
            select(ChatParticipant.user_id)
            .where(ChatParticipant.chat_id == chat_id)
        )
        participant_ids = [p[0] for p in participants.all()]

        users_info = {}
        for user_id in participant_ids:
            user = await session.execute(select(User).where(User.tg_id == user_id))
            user = user.scalar_one_or_none()
            if user:
                users_info[user_id] = user.first_name or user.username or f"User {user_id}"

        return users_info

async def get_last_chat_message(chat_id: int):
    """Получить последнее сообщение в чате"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

async def count_unread_messages(chat_id: int, user_id: int):
    """Подсчитать непрочитанные сообщения для пользователя в чате"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count(Message.id))
            .where(Message.chat_id == chat_id)
            .where(Message.receiver_id == user_id)  # Убедитесь, что тип соответствует BigInteger
            .where(Message.is_read == False)
        )
        return result.scalar_one() or 0


async def all_count_unread_messages(user_id):
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count(Message.id))
            .where(Message.receiver_id == user_id)
            .where(Message.is_read == False)
        )
        return result.scalar_one() or 0


async def report_chat(chat_id: int, reporter_id: int, reason: str):
    async with async_session_maker() as db:
        try:
            report = ChatReport(
                chat_id=chat_id,
                reporter_id=reporter_id,
                reason=reason
            )
            db.add(report)
            await db.commit()
            return True
        except Exception as exc:
            print(f"Error reporting chat: {exc}")
            return False

async def get_chat_reports(resolved: bool = False):
    async with async_session_maker() as db:
        try:
            q = select(ChatReport).filter_by(resolved=resolved).order_by(desc(ChatReport.created_at))
            result = await db.execute(q)
            return result.scalars().all()
        except Exception as exc:
            print(f"Error getting chat reports: {exc}")
            return []


async def resolve_chat_report(report_id: int, admin_id: int):
    async with async_session_maker() as db:
        try:
            # Явно указываем тип параметра
            q = update(ChatReport) \
                .where(ChatReport.id == int(report_id)) \
                .values(resolved=True, admin_id=admin_id)
            print(f"\n\nТип report_id({report_id}) = {type(report_id)}")
            await db.execute(q, {'report_id': int(report_id)})
            await db.commit()
            return True
        except Exception as exc:
            print(f"Error resolving chat report: {exc}")
            return False


async def get_ref_count(tg_id):
    async with async_session_maker() as db:
        try:
            refs = await db.execute(
                select(func.count()).select_from(Referral).where(
                    (Referral.referrer_id == tg_id)
                )
            )

            return refs.scalar()
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_last_product_id(tg_id: int):
    """
    Получает ID последнего добавленного продукта пользователя
    :param tg_id: ID пользователя в Telegram
    :return: ID продукта или None
    """
    async with async_session_maker() as db:
        try:
            result = await db.execute(
                select(Product.id)
                .where(Product.tg_id == tg_id)
                .order_by(desc(Product.created_at))
                .limit(1)
            )
            return result.scalar_one_or_none()
        except Exception as exc:
            print(f"Error getting last product ID: {exc}")
            return None

async def get_product_owner(product_id: int):
    """
    Получает владельца продукта по ID продукта
    :param product_id: ID продукта
    :return: ID пользователя в Telegram или None
    """
    async with async_session_maker() as db:
        try:
            result = await db.execute(
                select(Product.tg_id)
                .where(Product.id == product_id)
            )
            return result.scalar_one_or_none()
        except Exception as exc:
            print(f"Error getting product owner: {exc}")
            return None

async def check_user_blocked_post(user_id: int):
    async with async_session_maker() as session:
        result = await session.execute(
            select(UserBlock.unblock_at).where(and_(UserBlock.user_id == user_id,or_(UserBlock.unblock_at.is_(None), UserBlock.unblock_at > datetime.utcnow())))
        )
        block = result.fetchone()
        return {"is_blocked": block is not None}


async def check_user_block_post(tg_id):
    async with async_session_maker() as session:
        result = await session.execute(
            select(UserBlock.unblock_at).where((UserBlock.user_id == tg_id) & ((UserBlock.unblock_at.is_(None)) |(UserBlock.unblock_at > datetime.utcnow())))
        )
        block = result.fetchone()
        return block


async def notify_reporter_about_block_post(report_id: int):
    async with async_session_maker() as session:
        report = await session.execute(
            select(ChatReport)
            .where(ChatReport.id == int(report_id))
        )
        report = report.scalar_one_or_none()
        return report


async def block_user_post(user_id, report_id: int, admin_id, reason, unblock_at):
    async with async_session_maker() as session:
        # Преобразуем user_id в число
        user_id = int(user_id) if user_id else None

        # Если все параметры None - это запрос на разблокировку
        if admin_id is None and reason is None and unblock_at is None:
            # Удаляем запись о блокировке
            await session.execute(
                delete(UserBlock)
                .where(UserBlock.user_id == user_id)
            )

            # Восстанавливаем активные объявления пользователя
            await session.execute(
                update(Product)
                .where(Product.tg_id == user_id)
                .values(active=True)
            )
        else:
            # Блокировка пользователя
            result = await check_user_blocked_post(user_id)
            if not result["is_blocked"]:
                # Добавляем запись о блокировке
                await session.execute(
                    insert(UserBlock).values(
                        user_id=user_id,
                        blocked_by=admin_id,
                        reason=reason,
                        unblock_at=unblock_at
                    )
                )
            else:
                # Обновляем существующую блокировку
                await session.execute(
                    update(UserBlock)
                    .where(UserBlock.user_id == user_id)
                    .values(
                        blocked_by=admin_id,
                        reason=reason,
                        unblock_at=unblock_at
                    )
                )

            # Архивируем все объявления пользователя
            await session.execute(
                update(Product)
                .where(Product.tg_id == user_id)
                .values(active=None)
            )

        # Помечаем отчет как решенный, если он был передан
        if report_id:
            await resolve_chat_report(int(report_id), admin_id)

        await session.commit()

async def get_all_users_info():
    async with async_session_maker() as session:
        try:
            users = await session.execute(select(User))
            users = users.scalars().all()

            users_info = []
            for user in users:
                is_blocked = await check_user_blocked_post(user.tg_id)
                users_info.append({
                    "tg_id": user.tg_id,
                    "first_name": user.first_name,
                    "username": user.username,
                    "is_blocked": is_blocked.get("is_blocked", False)
                })

            return users_info
        except Exception as e:
            print(f"Error getting users info: {e}")
            return []


async def get_current_currency(tg_id: int):
    async with async_session_maker() as session:
        result = await session.execute(
            select(User.current_currency).where(User.tg_id == tg_id))
        currency = result.scalar_one_or_none()
        return currency or 'rub'

async def set_current_currency(tg_id: int, currency: str):
    async with async_session_maker() as session:
        await session.execute(
            update(User)
            .where(User.tg_id == tg_id)
            .values(current_currency=currency)
        )
        await session.commit()

async def get_balance_user_info(tg_id: int):
    async with async_session_maker() as session:
        result = await session.execute(
            select(User.rub_balance, User.ton_balance, User.current_currency)
            .where(User.tg_id == tg_id)
        )
        user_data = result.fetchone()
        return user_data

async def add_ton_balance(tg_id, amount):
    async with async_session_maker() as session:
        try:
            user = await session.execute(select(User).where(User.tg_id == tg_id))
            user = user.scalar_one_or_none()
            if user:
                user.ton_balance += amount
                await session.commit()

                return JSONResponse({
                    "status": "success",
                    "new_balance": user.ton_balance
                })
        except Exception as e:
            print(f"Error updating TON balance: {e}")
            return JSONResponse({"status": "error", "message": "Database error"}, status_code=500)


async def create_ton_transaction(user_id: int, amount: float, transaction_type: str):
    async with async_session_maker() as session:
        try:
            transaction = TonTransaction(
                user_id=user_id,
                amount=amount,
                transaction_type=transaction_type,
            )
            session.add(transaction)
            await session.commit()
            return transaction
        except Exception as e:
            await session.rollback()
            print(f"Error creating transaction: {e}")
            return None

async def get_user_ton_transactions(user_id: int, limit: int = 20):
    async with async_session_maker() as session:
        try:
            result = await session.execute(
                select(TonTransaction)
                .where(TonTransaction.user_id == user_id)
                .order_by(desc(TonTransaction.created_at))
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            print(f"Error getting transactions: {e}")
            return []


async def get_user_active_deals(tg_id: int):
    """Получаем активные сделки пользователя"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Deal).where(
                or_(
                    Deal.seller_id == tg_id,
                    Deal.buyer_id == tg_id
                ),
                Deal.status == 'active'
            ).order_by(Deal.created_at.desc()))
        deals = result.scalars().all()

        deals_with_users = []
        for deal in deals:
            seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
            seller = seller.scalar_one_or_none()
            buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
            buyer = buyer.scalar_one_or_none()
            admin_gave_time = False
            try:
                if deal.time_extension_until > datetime.now(timezone.utc):
                    admin_gave_time = True
            except TypeError:
                pass

            deals_with_users.append({
                "id": deal.id,
                "product_name": deal.product_name,
                "seller_id": deal.seller_id,
                "buyer_id": deal.buyer_id,
                "seller_first_name": seller.first_name if seller else None,
                "seller_username": seller.username if seller else None,
                "buyer_first_name": buyer.first_name if buyer else None,
                "buyer_username": buyer.username if buyer else None,
                "amount": deal.amount,
                "currency": deal.currency,
                "status": deal.status,
                "pending_cancel": deal.pending_cancel,
                "cancel_request_by": deal.cancel_request_by,
                "created_at": deal.created_at,
                "admin_gave_time": admin_gave_time
            })

        return deals_with_users


async def get_user_completed_deals(user_id: int, tg_id: int = None):
    """Получаем завершенные сделки пользователя по user_id или tg_id"""
    async with async_session_maker() as session:
        # Определяем ID для поиска (если передан tg_id, находим соответствующий user_id)
        query_user_id = user_id
        if tg_id is not None:
            user = await session.execute(select(User).where(User.tg_id == tg_id))
            user = user.scalar_one_or_none()
            if user:
                query_user_id = user.id

        result = await session.execute(
            select(Deal)
            .where(
                (Deal.seller_id == query_user_id) | (Deal.buyer_id == query_user_id),
                Deal.status.in_(["completed", "completed_by_admin", "cancelled", "cancelled_by_admin"])
            )
            .order_by(desc(Deal.completed_at if Deal.completed_at is not None else Deal.created_at))
        )
        deals = result.scalars().all()

        deal_list = []
        for deal in deals:
            # Для сделок с личной встречей показываем сумму в рублях
            amount = deal.amount
            if deal.currency == 'meet':
                # Получаем информацию о продукте для суммы в рублях
                product = await session.execute(select(Product).where(Product.id == deal.product_id))
                product = product.scalar_one_or_none()
                if product:
                    amount = product.product_price

            # Получаем информацию о пользователях
            seller = await session.execute(select(User).where(User.tg_id == deal.seller_id))
            seller = seller.scalar_one_or_none()
            buyer = await session.execute(select(User).where(User.tg_id == deal.buyer_id))
            buyer = buyer.scalar_one_or_none()

            # Формируем текст статуса
            status_text = ""
            if deal.status == 'completed':
                if deal.admin_decision == 'for_seller':
                    status_text = "Завершена администратором (в пользу продавца)"
                else:
                    status_text = "Завершена"
            else:
                if deal.admin_decision == 'for_buyer':
                    status_text = "Отменена администратором (в пользу покупателя)"
                else:
                    status_text = "Отменена"

            deal_list.append({
                "id": deal.id,
                "product_name": deal.product_name,
                "seller_id": deal.seller_id,
                "buyer_id": deal.buyer_id,
                "seller_username": seller.first_name if seller else "Unknown",
                "buyer_username": buyer.first_name if buyer else "Unknown",
                "currency": deal.currency,
                "amount": amount,
                "status": deal.status,
                "status_text": status_text,
                "created_at": deal.created_at,
                "completed_at": deal.completed_at,
                "is_reserved": deal.is_reserved,
                "reservation_amount": deal.reservation_amount,
                "admin_decision": deal.admin_decision
            })

        return deal_list


async def create_review(deal_id: int, from_user_id: int, to_user_id: int, product_id: int, rating: int, text: str):
    async with async_session_maker() as session:
        try:
            review = Review(
                deal_id=deal_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                product_id=product_id,
                rating=rating,
                text=text
            )
            session.add(review)
            await session.commit()
            return review
        except Exception as e:
            await session.rollback()
            print(f"Error creating review: {e}")
            return None


async def get_pending_deals():
    """
    Получает список сделок, ожидающих отмены (pending_cancel=True),
    исключая завершенные и административно обработанные сделки
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(Deal)
            .where(
                and_(
                    Deal.pending_cancel == True,
                    Deal.completed_at.is_(None),
                    Deal.admin_decision.is_(None)  # Исключаем сделки с решением администратора
                )
            )
            .order_by(Deal.created_at.desc())
        )
        return result.scalars().all()


async def get_deal_time_extension(deal_id: int):
    """
    Получает время расширения для сделки (time_extension_until)

    :param deal_id: ID сделки
    :return: datetime объекта time_extension_until или None, если не установлено
    """
    async with async_session_maker() as session:
        try:
            result = await session.execute(
                select(Deal.time_extension_until)
                .where(Deal.id == deal_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            print(f"Error getting deal time extension: {e}")
            return None


async def get_user_reserved_deals(tg_id: int):
    async with async_session_maker() as session:
        result = await session.execute(
            select(Deal)
            .where(Deal.is_reserved == True)
            .where(
                (Deal.buyer_id == tg_id) |
                (Deal.seller_id == tg_id)
            )
            .order_by(Deal.reservation_until)
        )
        return result.scalars().all()


async def get_user_active_deals_count(tg_id: int):
    async with async_session_maker() as session:
        try:
            active_deals = await get_user_active_deals(tg_id)
            return len(active_deals)
        except Exception as e:
            print(f"Error getting deal time extension: {e}")
            return 0
