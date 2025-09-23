import asyncio
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.config import settings
from src.database.methods import get_all_users, get_product_info_new
from src.utils import is_admin_new

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=settings.TG_BOT_TOKEN)
dp = Dispatcher()


async def send_notification_to_user(user_id: int, message: str, product_id: int = None):
    try:
        builder = InlineKeyboardBuilder()

        await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML",
            reply_markup=builder.as_markup() if product_id else None)
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")


async def set_main_menu(bot: Bot):
    main_menu_commands = [
        BotCommand(command='/start', description='Запустить бота'),
        BotCommand(command='/broadcast', description='Рассылка (админ)'),
    ]

    await bot.set_my_commands(main_menu_commands)


@dp.message(Command("start"))
async def handle_start(message: Message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("chat_"):
        product_id = int(args[1].split("_")[1])
        product = await get_product_info_new(product_id, message.from_user.id)
        if product:
            await message.answer(
                f"Вы можете перейти к чату по объявлению '{product["product_name"]}' в мини-приложении",
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


class BroadcastState(StatesGroup):
    waiting_for_message = State()


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    admin_res = False
    admin_role = await is_admin_new(message.from_user.id)
    if admin_role:
        admin_res = True
    if not admin_res:
        await message.answer("❌ У вас нет прав для этой команды")
        return

    await message.answer(
        "📢 Введите сообщение для рассылки:",
        reply_markup=types.ForceReply(selective=True)
    )
    await state.set_state(BroadcastState.waiting_for_message)


@dp.message(BroadcastState.waiting_for_message, F.text)
async def process_broadcast_message(message: Message, state: FSMContext):
    broadcast_text = message.text
    users = await get_all_users()

    success = 0
    failed = 0

    for user_id in users:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"{broadcast_text}"
            )
            success += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            failed += 1
            continue

    await message.answer(
        f"✅ Рассылка завершена\n"
        f"▪ Успешно: {success}\n"
        f"▪ Не удалось: {failed}"
    )
    await state.clear()

async def start_bot():
    await set_main_menu(bot)
    await dp.start_polling(bot)