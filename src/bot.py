import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from src.config import settings
from src.database.utils import get_user_info, get_product_info
import asyncio
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=settings.TG_BOT_TOKEN)
dp = Dispatcher()


async def send_notification_to_user(user_id: int, message: str, product_id: int = None):
    try:
        # Создаем клавиатуру с кнопкой "Перейти в чат"
        builder = InlineKeyboardBuilder()

        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML",
            reply_markup=builder.as_markup() if product_id else None)
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")


@dp.message(Command("start"))
async def handle_start(message: Message):
    # Обработка deep links для быстрого перехода в чат
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("chat_"):
        product_id = int(args[1].split("_")[1])
        product = await get_product_info(product_id, message.from_user.id)
        if product:
            await message.answer(
                f"Вы можете перейти к чату по объявлению '{product[2]}' в мини-приложении",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                    types.InlineKeyboardButton(
                        text="Открыть мини-приложение",
                        web_app=types.WebAppInfo(url=f"{settings.MINI_APP_URL}/start_chat/{product_id}")
                    )
                ]])
            )
        else:
            await message.answer("Объявление не найдено")
    else:
        await message.answer(
            "Этот бот отправляет уведомления о событиях в мини-приложении. "
            "Для работы с объявлениями перейдите в мини-приложение:",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                types.InlineKeyboardButton(
                    text="Открыть мини-приложение",
                    web_app=types.WebAppInfo(url=settings.MINI_APP_URL)
                )
            ]])
        )


async def start_bot():
    await dp.start_polling(bot)