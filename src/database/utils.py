from typing import Optional

from .database import async_session_maker, User, Category, Product, Fav, Chat, ChatParticipant, Message, ChatReport, \
    Referral
from sqlalchemy.future import select
from sqlalchemy import update, desc, asc, func, and_


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
            # 0-tg_id / 1-username / 2-photo_url / 3-plus_rep / 4-minus_rep
            user_info = [user.tg_id, user.first_name, user.photo_url, user.plus_rep, user.minus_rep]
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
                             prod.product_description, prod.product_image_url,
                             prod.id, prod.created_at, prod.tg_id] for prod in products]
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
                             prod.product_description, prod.product_image_url,
                             prod.id, prod.created_at, prod.tg_id] for prod in products]
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


async def get_user_active_products(seller_id, tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Product).filter_by(tg_id=seller_id, active=True).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at / 6-id
            # 7-is_fav
            all_products = [[prod.product_name, prod.product_price,
                             prod.product_description, prod.product_image_url,
                             prod.id, prod.created_at, prod.id] for prod in products]
            all_favs = await get_all_user_favs(tg_id)
            [prod.append(True) if prod[4] in all_favs else prod.append(False) for prod in all_products]
            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_user_moderation_products(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Product).filter_by(tg_id=tg_id, active=False).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at / 6-id
            all_products = [[prod.product_name, prod.product_price,
                             prod.product_description, prod.product_image_url,
                             prod.id, prod.created_at, prod.id] for prod in products]
            # all_favs = await get_all_user_favs(tg_id)
            # [prod.append(True) if prod[4] in all_favs else prod.append(False) for prod in all_products]
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


async def send_message(chat_id: int, sender_id: int, content: str):
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
            content=content
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
    """Получить все чаты пользователя"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Chat)
            .join(ChatParticipant, ChatParticipant.chat_id == Chat.id)
            .where(ChatParticipant.user_id == user_id)
            .order_by(Chat.created_at.desc())
        )
        return result.scalars().all()

async def get_chat_participants(chat_id: int, exclude_user_id: int = None):
    """Получить участников чата, исключая указанного пользователя"""
    async with async_session_maker() as session:
        query = select(ChatParticipant).where(ChatParticipant.chat_id == chat_id)
        if exclude_user_id:
            query = query.where(ChatParticipant.user_id != exclude_user_id)
        result = await session.execute(query)
        return result.scalars().all()

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
            q = select(ChatReport).filter_by(resolved=resolved).order_by(asc(ChatReport.created_at))
            result = await db.execute(q)
            return result.scalars().all()
        except Exception as exc:
            print(f"Error getting chat reports: {exc}")
            return []

async def resolve_chat_report(report_id: int, admin_id: int):
    async with async_session_maker() as db:
        try:
            q = update(ChatReport).where(ChatReport.id == report_id).values(
                resolved=True,
                admin_id=admin_id
            )
            await db.execute(q)
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

            return refs.scalars()
        except Exception as exc:
            print(f"Error: {exc}")
            return []