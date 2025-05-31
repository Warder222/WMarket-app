from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy import Column, Integer, String, ForeignKey
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

    tg_id = Column(Integer, unique=True, primary_key=True)
    first_name = Column(String)
    last_name = Column(String)
    username = Column(String, unique=True)
    photo_url = Column(String)
    token = Column(String, unique=True)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, autoincrement=True, primary_key=True)
    category_name = Column(String, unique=True)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, autoincrement=True, primary_key=True)
    tg_id = Column(Integer, ForeignKey("users.tg_id"))
    username = Column(String, ForeignKey("users.username"))
    category_name = Column(String, ForeignKey("categories.category_name"))
    product_name = Column(String)
    product_price = Column(Integer)
    product_description = Column(String)
    product_image_url = Column(String, unique=True)