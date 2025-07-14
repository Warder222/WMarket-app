from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func, BigInteger, Boolean, Float
from sqlalchemy.orm import DeclarativeBase
from src.config import settings

DATABASE_URL = settings.get_db_url()

engine = create_async_engine(url=DATABASE_URL)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    __abstract__ = True

# models________________________________________________________________________________________________________________


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
    rub_balance = Column(Float, default=0.0)  # Добавляем
    ton_balance = Column(Float, default=0.0)  # Добавляем
    current_currency = Column(String, default='rub')  # Добавляем для хранения выбранной валюты


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
    product_price = Column(Integer)
    product_description = Column(String)
    product_image_url = Column(String, unique=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    active = Column(Boolean, default=False)


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
    sender_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE')) # Было Integer → стало BigInteger
    receiver_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))  # Аналогично
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
    user_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))  # BigInteger
    blocked_by = Column(BigInteger, ForeignKey('users.tg_id', ondelete='SET NULL'))  # BigInteger
    reason = Column(String)
    blocked_at = Column(DateTime(timezone=True), server_default=func.now())
    unblock_at = Column(DateTime(timezone=True), nullable=True)


class TonTransaction(Base):
    __tablename__ = 'ton_transactions'

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.tg_id', ondelete='CASCADE'))
    amount = Column(Float)
    transaction_type = Column(String)  # 'deposit' или 'withdraw'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default='pending')  # 'pending', 'completed', 'failed'


class Deal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    product_name = Column(String)
    seller_id = Column(BigInteger, ForeignKey('users.tg_id'))
    buyer_id = Column(BigInteger, ForeignKey('users.tg_id'))
    currency = Column(String)
    amount = Column(Float)
    status = Column(String, default="active")  # active, completed, cancelled
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)