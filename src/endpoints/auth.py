from fastapi import Request, Cookie
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, update

from src.database.database import User, async_session_maker, Referral
from src.database.methods import get_all_users
from src.endpoints._endpoints_config import wmarket_router, templates
from src.utils import parse_init_data, encode_jwt


@wmarket_router.get("/")
async def index(request: Request):
    context = {
        "request": request
    }
    return templates.TemplateResponse("auth.html", context=context)


@wmarket_router.get("/register")
async def register(request: Request):
    context = {
        "request": request
    }
    return templates.TemplateResponse("register.html", context=context)


@wmarket_router.post("/auth/{oper}")
async def auth(oper: str, request: Request, session_token=Cookie(default=None)):
    form_data = await request.form()
    init_data = form_data.get("initData")
    user_data = parse_init_data(init_data)

    if oper == "login":
        users = await get_all_users()
        if user_data.get("tg_id") not in users:
            response = RedirectResponse(url="/register", status_code=303)
            return response

    new_session_token = await encode_jwt({"tg_id": user_data.get("tg_id")})
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
            add_result = True
        except Exception as exc:
            print(exc)
            add_result = False
    if not add_result:
        async with async_session_maker() as db:
            try:
                q = update(User).where(User.token == session_token).values(token=new_session_token)
                await db.execute(q)
                await db.commit()
            except Exception as exc:
                print(exc)

    ref_code = user_data.get("ref_code")
    if ref_code:
        ref_code = int(ref_code)
        current_user_id = user_data.get("tg_id")

        is_new_user = oper == "reg"

        if is_new_user:
            async with async_session_maker() as session:
                existing_ref = await session.execute(
                    select(func.count()).select_from(Referral).where(
                        Referral.referred_id == current_user_id
                    )
                )
                already_referred = existing_ref.scalar() > 0

            if not already_referred and ref_code != current_user_id:
                async with async_session_maker() as session:
                    referrer_exists = await session.execute(
                        select(func.count()).select_from(User).where(User.tg_id == ref_code)
                    )
                    referrer_exists = referrer_exists.scalar() > 0

                if referrer_exists:
                    async with async_session_maker() as session:
                        try:
                            referral = Referral(
                                referrer_id=ref_code,
                                referred_id=current_user_id
                            )
                            session.add(referral)
                            await session.commit()
                            print(f"Реферал создан: {ref_code} -> {current_user_id}")
                        except Exception as e:
                            await session.rollback()
                            print(f"Error recording referral: {e}")
        else:
            print(f"Пользователь {current_user_id} уже зарегистрирован, реферал не начислен")

    response = RedirectResponse(url="/store", status_code=303)
    response.set_cookie(key="session_token", value=new_session_token, httponly=True, secure=True)
    return response