import os

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, func, \
    UniqueConstraint, select, insert
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

DATABASE_URL = settings.get_db_url()

engine = create_async_engine(url=DATABASE_URL)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    __abstract__ = True


class User(Base):
    __tablename__ = "users"

    tg_id = Column(BigInteger, unique=True, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    username = Column(String, unique=True)
    photo_url = Column(String)
    token = Column(String, unique=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    plus_rep = Column(Integer, default=0)
    minus_rep = Column(Integer, default=0)
    ton_balance = Column(Float, default=0.0)
    earned_ton = Column(Float, default=0.0)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, autoincrement=True, primary_key=True)
    category_name = Column(String, unique=True)
    digital = Column(Boolean, default=False)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, autoincrement=True, primary_key=True)
    tg_id = Column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"))
    category_name = Column(String, ForeignKey("categories.category_name", ondelete="CASCADE"))
    product_name = Column(String)
    product_price = Column(Float)
    product_description = Column(String)
    product_image_url = Column(String)
    location = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    active = Column(Boolean, default=False)
    reserved = Column(Boolean, default=False)
    reserved_until = Column(DateTime(timezone=True), nullable=True)
    reserved_by = Column(BigInteger, ForeignKey("users.tg_id", ondelete="SET NULL"), nullable=True)
    reservation_amount = Column(Float, nullable=True)
    reservation_currency = Column(String, nullable=True)


class Fav(Base):
    __tablename__ = "favs"

    id = Column(Integer, autoincrement=True, primary_key=True)
    tg_id = Column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"))
    product_id = Column(Integer, ForeignKey("products.id", ondelete='CASCADE'))


class Chat(Base):
    __tablename__ = 'chats'

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id', ondelete='CASCADE'))
    created_at = Column(DateTime(timezone=True), default=func.now())


class ChatParticipant(Base):
    __tablename__ = 'chat_participants'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.id', ondelete='CASCADE'))
    user_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))
    joined_at = Column(DateTime(timezone=True), default=func.now())


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.id', ondelete='CASCADE'))
    sender_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))
    receiver_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))
    content = Column(String)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reported = Column(Boolean, default=False)


class ChatReport(Base):
    __tablename__ = 'chat_reports'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey('chats.id', ondelete='CASCADE'))
    reporter_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved = Column(Boolean, default=False)
    admin_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='SET NULL'), nullable=True)


class Referral(Base):
    __tablename__ = 'referrals'

    id = Column(Integer, primary_key=True)
    referrer_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))
    referred_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'), unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserBlock(Base):
    __tablename__ = 'user_blocks'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))
    blocked_by = Column(BigInteger, ForeignKey('users.tg_id', ondelete='SET NULL'))
    reason = Column(String)
    blocked_at = Column(DateTime(timezone=True), server_default=func.now())
    unblock_at = Column(DateTime(timezone=True), nullable=True)


class TonTransaction(Base):
    __tablename__ = 'ton_transactions'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))
    amount = Column(Float)
    transaction_type = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default='pending')


class Deal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name = Column(String)
    seller_id = Column(BigInteger, ForeignKey('users.tg_id'))
    buyer_id = Column(BigInteger, ForeignKey('users.tg_id'))
    currency = Column(String)
    amount = Column(Float)  # Сумма в основной валюте (TON для RUB сделок - залог)
    rub_amount = Column(Float, nullable=True)  # Добавляем поле для суммы в рублях
    status = Column(String, default="active")
    pending_cancel = Column(Boolean, default=False)
    cancel_reason = Column(String, nullable=True)
    cancel_request_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    admin_decision = Column(String, nullable=True)
    admin_reason = Column(String, nullable=True)
    admin_id = Column(BigInteger, ForeignKey('users.tg_id'), nullable=True)
    time_extension = Column(Integer, nullable=True)
    time_extension_until = Column(DateTime(timezone=True), nullable=True)
    is_reserved = Column(Boolean, default=False)
    reservation_amount = Column(Float, nullable=True)
    reservation_until = Column(DateTime(timezone=True), nullable=True)
    rub_payment_confirmed = Column(Boolean, default=False, nullable=True)
    collateral_amount = Column(Float, nullable=True)  # Сумма залога в TON


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    deal_id = Column(Integer, ForeignKey("deals.id"))
    from_user_id = Column(BigInteger, ForeignKey("users.tg_id"))
    to_user_id = Column(BigInteger, ForeignKey("users.tg_id"))
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    rating = Column(Integer)
    text = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    moderated = Column(Boolean, default=False)


class AdminRole(Base):
    __tablename__ = "admin_roles"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), unique=True)
    role = Column(String)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())


async def init_categories():
    async with async_session_maker() as session:
        try:
            # Читаем категории из not_dig_cats.txt (digital=False)
            not_dig_file = os.path.join(os.path.dirname(__file__), '..', '..', 'not_dig_cats.txt')
            if os.path.exists(not_dig_file):
                with open(not_dig_file, 'r', encoding='utf-8') as f:
                    not_dig_categories = [line.strip() for line in f if line.strip()]
            else:
                print(f"Файл {not_dig_file} не найден")
                not_dig_categories = []

            # Читаем категории из dig_cats.txt (digital=True)
            dig_file = os.path.join(os.path.dirname(__file__), '..', '..', 'dig_cats.txt')
            if os.path.exists(dig_file):
                with open(dig_file, 'r', encoding='utf-8') as f:
                    dig_categories = [line.strip() for line in f if line.strip()]
            else:
                print(f"Файл {dig_file} не найден")
                dig_categories = []

            # Получаем существующие категории из БД
            existing_categories_result = await session.execute(
                select(Category.category_name)
            )
            existing_categories = {cat[0] for cat in existing_categories_result.all()}

            # Добавляем нецифровые категории
            new_not_dig_categories = []
            for category_name in not_dig_categories:
                if category_name not in existing_categories:
                    new_not_dig_categories.append({
                        'category_name': category_name,
                        'digital': False
                    })

            # Добавляем цифровые категории
            new_dig_categories = []
            for category_name in dig_categories:
                if category_name not in existing_categories:
                    new_dig_categories.append({
                        'category_name': category_name,
                        'digital': True
                    })

            # Вставляем новые категории
            if new_not_dig_categories:
                await session.execute(
                    insert(Category),
                    new_not_dig_categories
                )
                print(f"Добавлено {len(new_not_dig_categories)} нецифровых категорий")

            if new_dig_categories:
                await session.execute(
                    insert(Category),
                    new_dig_categories
                )
                print(f"Добавлено {len(new_dig_categories)} цифровых категорий")

            await session.commit()
            print("Инициализация категорий завершена")

        except Exception as e:
            await session.rollback()
            print(f"Ошибка при инициализации категорий: {e}")