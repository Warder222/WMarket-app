import json
from datetime import datetime, timezone

from sqlalchemy import and_, asc, delete, desc, exists, func, insert, or_, update
from sqlalchemy.future import select

from .database import (Category, Chat, ChatParticipant, ChatReport, Deal, Fav, Message, Product, TonTransaction,
                       User, UserBlock, async_session_maker, Review, Referral)


#auth&users_____________________________________________________________________________________________________________
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


async def get_user_info_new(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(User).filter_by(tg_id=tg_id)
            result = await db.execute(q)
            user = result.scalar_one_or_none()
            if not user:
                return None
            user_info = {
                "tg_id": user.tg_id,
                "first_name": user.first_name,
                "photo_url": user.photo_url,
                "plus_rep": user.plus_rep,
                "minus_rep": user.minus_rep,
                "ton_balance": user.ton_balance,
                "earned_ton": user.earned_ton
            }
            return user_info
        except Exception as exc:
            print(f"Error: {exc}")
            return None


async def check_user_already_referred(referred_id: int):
    async with async_session_maker() as session:
        try:
            result = await session.execute(
                select(func.count()).select_from(Referral).where(
                    Referral.referred_id == referred_id
                )
            )
            return result.scalar() > 0
        except Exception as exc:
            print(f"Error checking user referral status: {exc}")
            return False
#_______________________________________________________________________________________________________________________


#store&ads&favorites____________________________________________________________________________________________________
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
#_______________________________________________________________________________________________________________________


#products_______________________________________________________________________________________________________________
async def get_all_products_new(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(Product).filter_by(active=True).order_by(desc(Product.created_at))
            result = await db.execute(q)
            products = result.scalars()

            all_products = []

            for prod in products:
                image_urls = json.loads(prod.product_image_url) if prod.product_image_url else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"

                all_products.append({
                    'product_id': prod.id,
                    'product_name': prod.product_name,
                    'product_price': prod.product_price,
                    'product_description': prod.product_description,
                    'product_image_url': first_image,
                    'created_at': prod.created_at,
                    'tg_id': prod.tg_id,
                    'is_fav': False,
                    'location': prod.location
                })

            all_favs = await get_all_user_favs(tg_id)

            for prod in all_products:
                if prod["product_id"] in all_favs:
                    prod['is_fav'] = True

            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_all_products_from_category_new(category_name: str, tg_id: int, limit: int = None, offset: int = None):
    async with async_session_maker() as db:
        try:
            query = select(Product) \
                .filter_by(category_name=category_name, active=True) \
                .order_by(desc(Product.created_at))

            if limit is not None:
                query = query.limit(limit)
            if offset is not None:
                query = query.offset(offset)

            result = await db.execute(query)
            products = result.scalars().all()

            if not products:
                return []

            all_favs = await get_all_user_favs(tg_id)
            all_products = []

            for prod in products:
                image_urls = json.loads(prod.product_image_url) if prod.product_image_url else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"

                is_fav = prod.id in all_favs if prod.tg_id != tg_id else False

                all_products.append({
                    'product_id': prod.id,
                    'product_name': prod.product_name,
                    'product_price': prod.product_price,
                    'product_description': prod.product_description,
                    'product_image_url': first_image,
                    'id': prod.id,
                    'created_at': prod.created_at,
                    'tg_id': prod.tg_id,
                    'is_fav': is_fav
                })

            return all_products
        except Exception as exc:
            print(f"Error in get_all_products_from_category: {exc}")
            return []


async def get_product_info_new(product_id: int, user_tg_id: int | None):
    async with async_session_maker() as session:
        query = select(
            Product.id.label("product_id"),
            Product.tg_id,
            Product.product_name,
            Product.product_price,
            Product.product_description,
            Product.product_image_url,
            Product.category_name,
            Product.created_at,
            Product.location,  # Добавляем location
            exists().where(
                and_(
                    Fav.tg_id == user_tg_id,
                    Fav.product_id == Product.id
                )
            ).label("is_fav"),
            Product.reserved,
            Product.reserved_by,
            Product.reserved_until,
            Product.reservation_amount,
            Product.reservation_currency
        ).where(Product.id == product_id)

        result = await session.execute(query)
        product = result.first()

        if not product:
            return None

        product_dict = dict(product._mapping)

        image_urls = json.loads(product_dict['product_image_url']) if product_dict['product_image_url'] else []
        first_image = image_urls[0] if image_urls else "static/img/zaglush.png"
        product_dict['product_image_url'] = first_image

        return product_dict


async def update_product_post(product_id: int, update_data):
    async with async_session_maker() as db:
        try:
            await db.execute(
                update(Product)
                .where(Product.id == int(product_id))
                .values(**update_data)
            )
            await db.commit()
            return True
        except Exception as e:
            print(f"Update error: {e}")
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


async def get_user_archived_products_new(tg_id):
    async with async_session_maker() as session:
        try:
            result = await session.execute(
                select(
                    Product.product_name,
                    Product.product_price,
                    Product.product_description,
                    Product.product_image_url,
                    Product.id,
                    Product.created_at,
                    Product.reserved,
                    Product.location
                )
                .where(Product.tg_id == tg_id, Product.active == None)
                .order_by(desc(Product.created_at))
            )

            all_products = []
            for prod in result.all():
                image_urls = json.loads(prod.product_image_url) if prod.product_image_url else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"

                all_products.append({
                    'product_id': prod.id,
                    'product_name': prod.product_name,
                    'product_price': prod.product_price,
                    'product_description': prod.product_description,
                    'product_image_url': first_image,
                    'created_at': prod.created_at,
                    'location': prod.location
                })

            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []


async def get_user_active_products_new(tg_id: int, current_user_id: int):
    async with async_session_maker() as session:
        try:
            result = await session.execute(
                select(
                    Product.product_name,
                    Product.product_price,
                    Product.product_description,
                    Product.product_image_url,
                    Product.id,
                    Product.created_at,
                    Product.reserved,
                    Product.location
                )
                .where(Product.tg_id == tg_id, Product.active == True)
                .order_by(desc(Product.created_at))
            )

            all_favs = await get_all_user_favs(current_user_id)
            all_products = []

            for prod in result.all():
                image_urls = json.loads(prod.product_image_url) if prod.product_image_url else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"

                all_products.append({
                    'product_id': prod.id,
                    'product_name': prod.product_name,
                    'product_price': prod.product_price,
                    'product_description': prod.product_description,
                    'product_image_url': first_image,
                    'created_at': prod.created_at,
                    'reserved': prod.reserved,
                    'is_fav': prod.id in all_favs,
                    'location': prod.location
                })

            return all_products
        except Exception as exc:
            print(f"Error in get_user_active_products: {exc}")
            return []


async def get_user_moderation_products_new(tg_id):
    async with async_session_maker() as session:
        try:
            result = await session.execute(
                select(
                    Product.product_name,
                    Product.product_price,
                    Product.product_description,
                    Product.product_image_url,
                    Product.id,
                    Product.created_at,
                    Product.category_name,
                    Product.reserved,
                    Product.tg_id,
                    Product.location
                )
                .where(Product.tg_id == tg_id, Product.active == False)
                .order_by(desc(Product.created_at))
            )

            all_products = []
            for prod in result.all():
                image_urls = json.loads(prod.product_image_url) if prod.product_image_url else []
                first_image = image_urls[0] if image_urls else "static/img/zaglush.png"

                all_products.append({
                    'product_id': prod.id,
                    'product_name': prod.product_name,
                    'product_price': prod.product_price,
                    'product_description': prod.product_description,
                    'product_image_url': first_image,
                    'created_at': prod.created_at,
                    'category_name': prod.category_name,
                    'tg_id': prod.tg_id,
                    'location': prod.location
                })

            return all_products
        except Exception as exc:
            print(f"Error: {exc}")
            return []
#_______________________________________________________________________________________________________________________


#chats__________________________________________________________________________________________________________________
async def get_chat_messages(chat_id: int, user_id: int):
    async with async_session_maker() as db:
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(asc(Message.created_at)))
        messages = result.scalars().all()

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


async def mark_messages_as_read(chat_id: int, user_id: int):
    async with async_session_maker() as db:
        await db.execute(
            update(Message)
            .where(Message.chat_id == chat_id, Message.receiver_id == user_id, Message.is_read == False)
            .values(is_read=True)
        )
        await db.commit()


async def all_count_unread_messages(user_id):
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count(Message.id))
            .where(Message.receiver_id == user_id)
            .where(Message.is_read == False)
        )
        return result.scalar_one() or 0


async def resolve_chat_report(report_id: int, admin_id: int):
    async with async_session_maker() as db:
        try:
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


async def get_resolved_reports_count(chat_id: int, reporter_id: int):
    """Получить количество решенных жалоб пользователя на чат"""
    async with async_session_maker() as db:
        try:
            q = select(func.count(ChatReport.id)).filter_by(
                chat_id=chat_id,
                reporter_id=reporter_id,
                resolved=True
            )
            result = await db.execute(q)
            return result.scalar() or 0
        except Exception as exc:
            print(f"Error getting resolved reports count: {exc}")
            return 0


async def check_existing_report(chat_id: int, reporter_id: int):
    async with async_session_maker() as db:
        try:
            q = select(ChatReport).filter_by(
                chat_id=chat_id,
                reporter_id=reporter_id,
                resolved=False
            )
            result = await db.execute(q)
            return result.scalar_one_or_none() is not None
        except Exception as exc:
            print(f"Error checking existing report: {exc}")
            return False


async def check_any_active_chat_report(chat_id: int):
    async with async_session_maker() as db:
        try:
            q = select(ChatReport).filter_by(
                chat_id=chat_id,
                resolved=False
            )
            result = await db.execute(q)
            result = result.scalar_one_or_none()
            if not result:
                return True
        except Exception as exc:
            print(f"Error checking active chat reports: {exc}")
            return False


async def create_system_message(chat_id: int, content: str):
    async with async_session_maker() as db:
        try:
            system_message = Message(
                chat_id=chat_id,
                sender_id=0,
                receiver_id=0,
                content=content,
                is_read=False,
                created_at=datetime.now(timezone.utc)
            )
            db.add(system_message)
            await db.commit()
            await db.refresh(system_message)
            return system_message
        except Exception as exc:
            print(f"Error creating system message: {exc}")
            return None
#_______________________________________________________________________________________________________________________


#block__________________________________________________________________________________________________________________
async def block_user_post(user_id, report_id: int, admin_id, reason, unblock_at):
    async with async_session_maker() as session:
        user_id = int(user_id) if user_id else None

        if admin_id is None and reason is None and unblock_at is None:
            await session.execute(
                delete(UserBlock)
                .where(UserBlock.user_id == user_id)
            )

            await session.execute(
                update(Product)
                .where(Product.tg_id == user_id)
                .values(active=True)
            )
        else:
            result = await check_user_blocked_post(user_id)
            if not result["is_blocked"]:
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

            await session.execute(
                update(Product)
                .where(Product.tg_id == user_id)
                .values(active=None)
            )

        if report_id:
            await resolve_chat_report(int(report_id), admin_id)

        await session.commit()


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
#_______________________________________________________________________________________________________________________


#deals__________________________________________________________________________________________________________________
async def get_user_active_deals(tg_id: int):
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

            deals_with_users.append({
                "id": deal.id,
                "product_name": deal.product_name,
                "seller_id": deal.seller_id,
                "buyer_id": deal.buyer_id,
                "seller_username": seller.first_name if seller else "Unknown",
                "buyer_username": buyer.first_name if buyer else "Unknown",
                "currency": deal.currency,
                "amount": deal.rub_amount if deal.currency == 'rub' and deal.rub_amount else deal.amount,
                "status": deal.status,
                "status_text": status_text,
                "created_at": deal.created_at,
                "completed_at": deal.completed_at,
                "is_reserved": deal.is_reserved,
                "reservation_amount": deal.reservation_amount,
                "admin_decision": deal.admin_decision,
                "original_amount": deal.amount,
                "rub_payment_confirmed": deal.rub_payment_confirmed,
                "pending_cancel": deal.pending_cancel
            })

        return deals_with_users


async def get_user_active_deals_count(tg_id: int):
    async with async_session_maker() as session:
        try:
            active_deals = await get_user_active_deals(tg_id)
            return len(active_deals)
        except Exception as e:
            print(f"Error getting deal time extension: {e}")
            return 0


async def get_pending_deals():
    async with async_session_maker() as session:
        result = await session.execute(
            select(Deal)
            .where(
                and_(
                    Deal.pending_cancel == True,
                    Deal.completed_at.is_(None),
                    Deal.admin_decision.is_(None)
                )
            )
            .order_by(Deal.created_at.desc())
        )
        deals = result.scalars().all()
        pending_deals = []
        for deal in deals:
            buyer_info = await get_user_info_new(deal.buyer_id)
            seller_info = await get_user_info_new(deal.seller_id)
            pending_deals.append({
                "id": deal.id,
                "product_id": deal.product_id,
                "product_name": deal.product_name,
                "seller_id": deal.seller_id,
                "seller_first_name": seller_info["first_name"],
                "buyer_id": deal.buyer_id,
                "buyer_first_name": buyer_info["first_name"],
                "currency": deal.currency,
                "amount": deal.amount,
                "rub_amount": deal.rub_amount,
                "status": deal.status,
                "pending_cancel": deal.pending_cancel,
                "cancel_reason": deal.cancel_reason,
                "cancel_request_by": deal.cancel_request_by,
                "created_at": deal.created_at,
                "completed_at": deal.completed_at,
                "admin_decision": deal.admin_decision,
                "admin_reason": deal.admin_reason,
                "admin_id": deal.admin_id,
                "time_extension": deal.time_extension,
                "time_extension_until": deal.time_extension_until,
                "is_reserved": deal.is_reserved,
                "reservation_amount": deal.reservation_amount,
                "reservation_until": deal.reservation_until,
            })
        return pending_deals
#_______________________________________________________________________________________________________________________


#payment$ton____________________________________________________________________________________________________________
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
#_______________________________________________________________________________________________________________________


#???____________________________________________________________________________________________________________________
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


async def check_review_exists(deal_id: int, from_user_id: int):
    async with async_session_maker() as session:
        try:
            result = await session.execute(
                select(Review).where(
                    Review.deal_id == deal_id,
                    Review.from_user_id == from_user_id
                )
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            print(f"Error checking review existence: {e}")
            return False


async def get_deal_time_extension(deal_id: int):
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


async def notify_reporter_about_block_post(report_id: int):
    async with async_session_maker() as session:
        report = await session.execute(
            select(ChatReport)
            .where(ChatReport.id == int(report_id))
        )
        report = report.scalar_one_or_none()
        return report


async def get_last_product_id(tg_id: int):
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
#
#
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
#
#
async def get_user_jwt(tg_id):
    async with async_session_maker() as db:
        try:
            q = select(User).filter_by(tg_id=tg_id)
            result = await db.execute(q)
            session_token = result.scalar_one_or_none()
            return session_token
        except Exception as exc:
            print(f"Error: {exc}")
#_______________________________________________________________________________________________________________________