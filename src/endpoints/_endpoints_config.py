import json
from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

wmarket_router = APIRouter(
    prefix="",
    tags=["wmarket_router"]
)

wmarket_api_router = APIRouter(
    prefix="/api",
    tags=["wmarket_api_router"]
)

def from_json(value):
    return json.loads(value)

templates = Jinja2Templates(directory="templates")
templates.env.filters['from_json'] = from_json