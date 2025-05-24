from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

wmarket_router = APIRouter(
    prefix="",
    tags=["wmarket_router"]
)

templates = Jinja2Templates(directory="templates")


# app_____________________________________________


@wmarket_router.get("/")
async def auth(request: Request):
    pass