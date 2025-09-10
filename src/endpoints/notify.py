from src.bot import send_notification_to_user
from src.database.methods import get_user_info, get_product_info, get_chat_messages
from src.websocket_config import manager


async def notify_new_message(chat_id: int, sender_id: int, content: str):
    try:
        chat_data = await get_chat_messages(chat_id, sender_id)
        if not chat_data:
            print(f"Chat data not found for chat_id: {chat_id}")
            return

        receiver_id = chat_data["other_user"].tg_id

        if manager.is_connected(str(receiver_id)):
            print(f"User {receiver_id} is in chat, skipping notification")
            return

        product = chat_data["product"]
        username = await get_user_info(sender_id)

        message = (
            f"💬 Новое сообщение от \n{username[1]} \n\n📢 Объявление:\n{product.product_name}"
        )

        await send_notification_to_user(receiver_id, message, product.id)
        print(f"Notification sent to user {receiver_id} about new message in chat {chat_id}")

    except Exception as e:
        print(f"Error in notify_new_message: {e}", exc_info=True)


async def notify_product_approved(product_id: int):
    try:
        product = await get_product_info(product_id, None)
        if not product:
            print(f"Product not found: {product_id}")
            return

        seller_id = product[1]
        user_info = await get_user_info(seller_id)
        if not user_info:
            print(f"User info not found for seller: {seller_id}")
            return

        message = (
            f"✅ Ваше объявление прошло модерацию!\n\n"
            f"📌 Название: {product[2]}\n"
            f"⚙️ Категория: {product[6]}\n"
            f"💰 Цена: {product[3]} ₽"
        )

        await send_notification_to_user(seller_id, message)
        print(f"Product approval notification sent to user {seller_id} for product {product_id}")

    except Exception as e:
        print(f"Error in notify_product_approved: {e}", exc_info=True)


async def notify_product_rejected(product_id: int, reason: str = None):
    try:
        product = await get_product_info(product_id, None)
        if not product:
            print(f"Product not found: {product_id}")
            return

        seller_id = product[1]
        user_info = await get_user_info(seller_id)
        if not user_info:
            print(f"User info not found for seller: {seller_id}")
            return

        message = (
            f"❌ Ваше объявление не прошло модерацию\n\n"
            f"📌 Название: {product[2]}\n"
            f"📝 Причина/пункт: {reason}\n\n"
            f'Вы можете исправить его (<a href="https://telegra.ph/Osnovnye-punkty-i-prichiny-blokirovki-06-26">прочитав причину или пункт</a>)'
            f" и повторно опубликовать."
        )

        await send_notification_to_user(seller_id, message)
        print(f"Product rejection notification sent to user {seller_id} for product {product_id}")

    except Exception as e:
        print(f"Error in notify_product_rejected: {e}", exc_info=True)