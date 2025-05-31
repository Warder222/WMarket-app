from fastapi import APIRouter, Request, Cookie, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

from src.database.utils import get_all_users, add_user, update_token
from src.utils import parse_init_data, encode_jwt, decode_jwt

from datetime import datetime, timezone, timedelta

wmarket_router = APIRouter(
    prefix="",
    tags=["wmarket_router"]
)

templates = Jinja2Templates(directory="templates")


# app_____________________________________________


@wmarket_router.get("/")
async def index(request: Request,
                session_token=Cookie(default=None)):
    if session_token:
        users = await get_all_users()
        payload = await decode_jwt(session_token)

        if (payload.get("tg_id") in users
                and datetime.fromtimestamp(payload.get("exp"), timezone.utc) > datetime.now(timezone.utc)):
            response = RedirectResponse(url="/store", status_code=303)
            return response
    context = {
        "request": request
    }
    return templates.TemplateResponse("auth.html", context=context)


@wmarket_router.post("/")
async def auth(request: Request, session_token=Cookie(default=None)):
    form_data = await request.form()
    init_data = form_data.get("initData")
    user_data = parse_init_data(init_data)

    new_session_token = await encode_jwt({"tg_id": user_data.get("tg_id")})
    add_result = await add_user(user_data, new_session_token)
    if not add_result:
        await update_token(session_token, new_session_token)

    response = RedirectResponse(url="/store", status_code=303)
    response.set_cookie(key="session_token", value=new_session_token, httponly=True, secure=True)
    return response


@wmarket_router.get("/store")
async def store(request: Request):
    context = {
        "request": request
    }
    return templates.TemplateResponse("store.html", context=context)