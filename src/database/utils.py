from datetime import datetime

from starlette.responses import JSONResponse

from .database import async_session_maker, User, Category, Product, Fav, Chat, ChatParticipant, Message, ChatReport, \
    Referral, UserBlock, TonTransaction, Deal
from sqlalchemy.future import select
from sqlalchemy import update, desc, asc, func, and_, delete, or_, insert, bindparam, Integer


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
                         user.plus_rep, user.minus_rep, user.rub_balance, user.ton_balance]
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


async def get_product_info(product_id: int, tg_id):
    async with async_session_maker() as db:
        try:
            # Явно указываем тип параметра
            q = select(Product).filter_by(id=product_id)
            result = await db.execute(q)
            product = result.scalar_one_or_none()
            if not product:
                return None
            # 0-product_id / 1-tg_id / 2-name / 3-price / 4-description / 5-image_url / 6-category_name / 7-created_at
            # 8-is_fav
            product_info = [product.id, product.tg_id, product.product_name, product.product_price,
                            product.product_description, product.product_image_url, product.category_name,
                            product.created_at]
            all_favs = await get_all_user_favs(tg_id) if tg_id else []
            product_info.append(product.id in all_favs)
            return product_info
        except Exception as exc:
            print(exc)
            return None


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
            return [[prod.product_name, prod.product_price,
                     prod.product_description, prod.product_image_url,
                     prod.id, prod.created_at, prod.id] for prod in products]
        except Exception as exc:
            print(f"Error: {exc}")
            return []


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
            # 0-product_name / 1-product_price / 2-product_description / 3-product_image_url / 4-id / 5-created_at
            # 6-cat_name / 7-tg_id
            all_products = [[prod.product_name, prod.product_price,
                             prod.product_description, prod.product_image_url,
                             prod.id, prod.created_at, prod.category_name, prod.tg_id] for prod in products]
            # all_favs = await get_all_user_favs(tg_id)
            # [prod.append(True) if prod[4] in all_favs else prod.append(False) for prod in all_products]
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
    """Получить все активные чаты пользователя"""
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
            q = select(ChatReport).filter_by(resolved=resolved).order_by(asc(ChatReport.created_at))
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

        # Помечаем отчет как решенный
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
        return result.scalars().all()

async def get_user_completed_deals(tg_id: int):
    """Получаем завершенные сделки пользователя"""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Deal).where(
                or_(
                    Deal.seller_id == tg_id,
                    Deal.buyer_id == tg_id
                ),
                Deal.status.in_(['completed', 'cancelled'])
            ).order_by(Deal.created_at.desc()))
        return result.scalars().all()