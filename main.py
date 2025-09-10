import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi_socketio import SocketManager

from src.bot import start_bot
from src.endpoints import wmarket_router

app = FastAPI()
app.include_router(wmarket_router)
app.mount("/static", StaticFiles(directory="static"))

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Access-Control-Allow-Origin"]
)

socket_manager = SocketManager(app=app)

async def run_app():
    config = uvicorn.Config("main:app", host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    bot_task = asyncio.create_task(start_bot())

    await server.serve()

    bot_task.cancel()

    try:
        await bot_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(run_app())