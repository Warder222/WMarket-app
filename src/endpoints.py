from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse


wmarket_router = APIRouter(
    prefix="",
    tags=["wmarket_router"]
)

templates = Jinja2Templates(directory="templates")


# app_____________________________________________


@wmarket_router.get("/")
async def index(request: Request):
    context = {
        "request": request
    }
    return templates.TemplateResponse("auth.html", context=context)


@wmarket_router.post("/")
async def auth(request: Request):
    form_data = await request.form()
    init_data = form_data.get("initData")

    if not init_data:
        return RedirectResponse("/", status_code=303)

    context = {
        "request": request
    }
    return templates.TemplateResponse("store.html", context=context)
