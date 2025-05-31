from .database import async_session_maker, User, Category, Product
from sqlalchemy.future import select
from sqlalchemy import update


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
            q = select(User).filter_by(id=tg_id)
            result = await db.execute(q)
            session_token = result.scalar_one_or_none()
            return session_token
        except Exception as exc:
            print(f"Error: {exc}")