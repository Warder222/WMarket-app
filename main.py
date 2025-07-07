import asyncio
import uvicorn

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
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
    allow_methods=["*"],  # Явно укажите методы
    allow_headers=["*"],
    expose_headers=["Access-Control-Allow-Origin"]  # Добавьте это
)

socket_manager = SocketManager(app=app)

async def run_app():
    # Запуск FastAPI
    config = uvicorn.Config("main:app", host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)

    # Запуск бота в фоновом режиме
    bot_task = asyncio.create_task(start_bot())

    await server.serve()

    # Отмена задачи бота при остановке сервера
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(run_app())
#
# if __name__ == "__main__":
#     uvicorn.run("main:app")