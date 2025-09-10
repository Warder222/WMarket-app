from fastapi import Request, Cookie
from fastapi.responses import RedirectResponse

from src.database.methods import get_all_users, add_user, update_token, user_exists, record_referral
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
    add_result = await add_user(user_data, new_session_token)
    if not add_result:
        await update_token(session_token, new_session_token)

    ref_code = user_data.get("ref_code")
    if ref_code:
        ref_code = int(ref_code)
        if await user_exists(ref_code):
            res = await record_referral(ref_code, user_data.get("tg_id"))

    response = RedirectResponse(url="/store", status_code=303)
    response.set_cookie(key="session_token", value=new_session_token, httponly=True, secure=True)
    return response