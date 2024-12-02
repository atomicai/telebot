from typing import Optional, List
import os
from loguru import logger


from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from telegram.constants import ChatAction
from telegram.error import BadRequest

from rethinkdb import r

from langchain_openai import ChatOpenAI
from langchain_core.callbacks import AsyncCallbackManager
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain.schema import LLMResult


from src.api.utils import default_chat_title
from src.db.repository import (
    upsert_user,
    get_active_thread,
    get_user_threads,
    create_or_update_thread,
    get_thread_by_id,
    delete_thread,
    add_message_to_thread,
    get_all_messages_by_thread_id,
    get_value,
    get_kv_pairs,
)
from src.db.utils import rethinkdb_connection
from src.domain.running.telegram_chatter import TelegramChatter
from src.db.models import MessageTypeEnum, RatingEnum

from src.api.keyboards import get_delete_confirmation_keyboard, get_rating_keyboard, get_main_menu_keyboard, generate_thread_keyboard






def format_messages(messages: List[dict]) -> str:
    """Форматирует сообщения для отображения в чате."""
    formatted_messages = []
    for msg in messages:
        if msg["message_type"] == MessageTypeEnum.human.value:
            formatted_messages.append(f"Пользователь:\n{msg['text']}")
        elif msg["message_type"] == MessageTypeEnum.ai.value:
            formatted_messages.append(f"Бот:\n{msg['text']}")
    return "\n\n".join(formatted_messages)


async def start(update: Update, context):
    """Обработчик команды /start."""
    async with rethinkdb_connection() as connection:
        logger.info("Received /start command")

        user = await upsert_user(connection, {
            "id": update.message.from_user.id,
            "first_name": update.message.from_user.first_name,
            "last_name": update.message.from_user.last_name,
            "username": update.message.from_user.username,
            "language_code": update.message.from_user.language_code,
            "is_premium": update.message.from_user.is_premium,
        })

        active_thread = await get_active_thread(connection, user["id"])
        if not active_thread:
            active_thread = await create_or_update_thread(
                connection,
                user_id=user["id"],
                title=default_chat_title(),
                set_active=True
            )

        await update.message.reply_text(
            "Я большая языковая модель, начни со мной общение просто отправив любое сообщение.\n"
            "Создать новый чат /new_chat\n"
            "Включить/выключить меню /chat",
            reply_markup=get_main_menu_keyboard(context, None, active_thread)
        )


async def enable_chat_command(update: Update, context):
    """Обработчик команды /chat для активации/деактивации меню."""
    async with rethinkdb_connection() as connection:
        user = await upsert_user(connection, {
            "id": update.message.from_user.id,
            "first_name": update.message.from_user.first_name,
            "last_name": update.message.from_user.last_name,
            "username": update.message.from_user.username,
            "language_code": update.message.from_user.language_code,
            "is_premium": update.message.from_user.is_premium,
        })

        user_data = context.user_data

        user_data["menu_active"] = not user_data.get("menu_active", False)

        if user_data["menu_active"]:
            active_thread = await get_active_thread(connection, user["id"])
            await update.message.reply_text(
                "Меню активировано.",
                reply_markup=get_main_menu_keyboard(context, None, active_thread)
            )
        else:
            await update.message.reply_text(
                "Меню скрыто.",
                reply_markup=ReplyKeyboardRemove()
            )

async def new_chat_command(update: Update, context):
    """Обработчик команды /new_chat для создания нового чата."""
    async with rethinkdb_connection() as connection:
        user = await upsert_user(connection, {
            "id": update.message.from_user.id,
            "first_name": update.message.from_user.first_name,
            "last_name": update.message.from_user.last_name,
            "username": update.message.from_user.username,
            "language_code": update.message.from_user.language_code,
            "is_premium": update.message.from_user.is_premium,
        })

        thread = await create_or_update_thread(connection, user["id"], title=default_chat_title(), set_active=True)

        await update.message.reply_text("Вы создали новый чат")
        await update.message.reply_text(
            f"Активный чат: {thread['title']}",
            reply_markup=get_main_menu_keyboard(context, selected_thread=thread, active_thread=thread)
        )


async def chat_command(update: Update, context):
    """Обработчик команды /chat для отображения списка чатов."""
    async with rethinkdb_connection() as connection:
        logger.info("Received /chat command")
        user = await upsert_user(connection, {
            "id": update.message.from_user.id,
            "first_name": update.message.from_user.first_name,
            "last_name": update.message.from_user.last_name,
            "username": update.message.from_user.username,
            "language_code": update.message.from_user.language_code,
            "is_premium": update.message.from_user.is_premium,
        })


        keyboard = await generate_thread_keyboard(
            connection,
            user,
            limit=10,
            offset=user.get("current_thread_offset", 0)
        )


        await update.message.reply_text("Ваши чаты:", reply_markup=keyboard)


async def callback_query_handler(update: Update, context):
    """Обработчик callback-запросов из клавиатуры."""
    async with rethinkdb_connection() as connection:
        logger.info("Received callback query")
        query = update.callback_query
        data = query.data

        user = await upsert_user(connection, {
            "id": update.effective_user.id,
            "first_name": update.effective_user.first_name,
            "last_name": update.effective_user.last_name,
            "username": update.effective_user.username,
            "language_code": update.effective_user.language_code,
            "is_premium": update.effective_user.is_premium,
        })
        user_data = context.user_data

        if data.startswith("thread_"):
            thread_id = data.split("_")[1]
            thread = await get_thread_by_id(connection, thread_id)
            user_data["selected_thread_id"] = thread_id

            active_thread = await get_active_thread(connection, user["id"])

            await query.message.reply_text(
                f"Выбран чат: {thread['title']}",
                reply_markup=get_main_menu_keyboard(context, selected_thread=thread, active_thread=active_thread)
            )
            await query.answer()
            return

        if data == "show_chats":
            keyboard = await generate_thread_keyboard(
                connection, user, limit=10, offset=user.get("current_thread_offset", 0)
            )
            await query.message.reply_text("Чаты:", reply_markup=keyboard)

        elif data.startswith("show_history_"):
            thread_id = data.split("_")[2]
            messages = await get_all_messages_by_thread_id(connection, thread_id)

            formatted_messages = format_messages(messages)

            MAX_MESSAGE_LENGTH = 4096
            message_chunks = []
            current_chunk = ""
            for formatted_message in formatted_messages.split("\n\n"):
                to_add = f"{formatted_message}\n\n"
                if len(current_chunk) + len(to_add) <= MAX_MESSAGE_LENGTH:
                    current_chunk += to_add
                else:
                    message_chunks.append(current_chunk)
                    current_chunk = to_add
            if current_chunk:
                message_chunks.append(current_chunk)

            for chunk in message_chunks:
                await query.message.reply_text(chunk)

        elif data.startswith("rate_"):
            parts = data.split("_")
            message_id = parts[1]
            rating_str = parts[2]

            if rating_str == "like":
                rating = RatingEnum.like.value
            elif rating_str == "dislike":
                rating = RatingEnum.dislike.value
            else:
                await query.answer("Неверная оценка.")
                return

            message = await r.db("llm_bot_db").table("messages").get(message_id).run(connection)
            if message:
                await r.db("llm_bot_db").table("messages").get(message_id).update({"rating": rating}).run(connection)
                await query.answer("Спасибо за вашу оценку!")
                await query.edit_message_reply_markup(reply_markup=None)
            else:
                await query.answer("Сообщение не найдено.")

        elif data.startswith("delete_"):
            thread_id = data.split("_")[1]
            thread = await get_thread_by_id(connection, thread_id)
            user_data["delete_thread_id"] = thread_id

            await query.message.reply_text(
                "Вы уверены, что хотите удалить чат?",
                reply_markup=get_delete_confirmation_keyboard(thread_id))

        elif data.startswith("confirm_delete_"):
            thread_id = data.split("_")[2]
            await delete_thread(connection, thread_id)
            user_data.pop("delete_thread_id", None)
            selected_thread_id = user_data.pop("selected_thread_id", None)

            active_thread = await get_active_thread(connection, user["id"])

            await query.message.reply_text(
                "Чат удален.",
                reply_markup=get_main_menu_keyboard(
                    context, selected_thread=None, active_thread=active_thread
                )
            )

        elif data == "cancel_delete":
            user_data.pop("delete_thread_id", None)
            selected_thread_id = user_data.get("selected_thread_id")
            active_thread = await get_active_thread(connection, user["id"])
            selected_thread = (
                await get_thread_by_id(connection, selected_thread_id) if selected_thread_id else None
            )
            await query.message.reply_text(
                "Удаление отменено.",
                reply_markup=get_main_menu_keyboard(
                    context, selected_thread=selected_thread, active_thread=active_thread
                )
            )

        elif data.startswith("page_"):
            offset = data.split("_")[1]
            keyboard = await generate_thread_keyboard(
                connection, user, limit=10, offset=offset
            )
            await query.message.reply_text("Чаты:", reply_markup=keyboard)

        elif data == "create_new_chat":
            thread = await create_or_update_thread(
                connection, user["id"], title=default_chat_title(), set_active=True
            )

            await query.message.reply_text("Вы создали новый чат")
            await query.message.reply_text(
                f"Активный чат: {thread['title']}",
                reply_markup=get_main_menu_keyboard(
                    context, selected_thread=thread, active_thread=thread
                )
            )
        else:
            await query.answer()


async def user_message(update: Update, context):
    """Обработчик пользовательских сообщений."""
    async with rethinkdb_connection() as connection:
        logger.info("Received user message")


        user = await upsert_user(connection, {
            "id": update.message.from_user.id,
            "first_name": update.message.from_user.first_name,
            "last_name": update.message.from_user.last_name,
            "username": update.message.from_user.username,
            "language_code": update.message.from_user.language_code,
            "is_premium": update.message.from_user.is_premium,
        })

        user_data = context.user_data
        text = update.message.text.strip()


        selected_thread_id = user_data.get("selected_thread_id")
        active_thread = await get_active_thread(connection, user["id"])
        selected_thread = await get_thread_by_id(connection, selected_thread_id) if selected_thread_id else None

        if text.startswith("✅ ") or text.startswith("◻️ "):
            if selected_thread:
                is_active = selected_thread["id"] == (active_thread["id"] if active_thread else None)
                if not is_active:
                    await create_or_update_thread(connection, user["id"], thread_id=selected_thread["id"],
                                                  set_active=True)
                    active_thread = await get_thread_by_id(connection, selected_thread["id"])

                    await update.message.reply_text(
                        f"Чат '{selected_thread['title']}' теперь активен.",
                        reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread)
                    )
                else:
                    await update.message.reply_text(
                        f"Чат '{selected_thread['title']}' уже активен.",
                        reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread)
                    )
            else:
                await update.message.reply_text(
                    "Нет выбранного чата.",
                    reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread)
                )
            return

        elif text == "✏️ Отредактировать":
            if selected_thread:
                user_data["edit_thread_id"] = selected_thread["id"]
                await update.message.reply_text(
                    "Введите новое название чата:",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("⬅️ Отмена")]],
                        resize_keyboard=True,
                        one_time_keyboard=True
                    )
                )
            else:
                await update.message.reply_text("Нет выбранного чата для редактирования.")
            return

        elif text == "🗑️ Удалить":
            if selected_thread:
                user_data["delete_thread_id"] = selected_thread["id"]
                await update.message.reply_text(
                    "Вы уверены, что хотите удалить чат?",
                    reply_markup=get_delete_confirmation_keyboard(selected_thread["id"])
                )
            else:
                await update.message.reply_text("Нет выбранного чата для удаления.")
            return

        elif text == "💬 Сообщения":
            if selected_thread:
                messages = await get_all_messages_by_thread_id(connection, selected_thread["id"])
                formatted_messages = format_messages(messages)
                if formatted_messages:
                    await update.message.reply_text(formatted_messages)
                else:
                    await update.message.reply_text("Нет сообщений в чате.")
            else:
                await update.message.reply_text("Нет выбранного чата для отображения сообщений.")
            return

        elif text == "📜 Чаты":
            keyboard = await generate_thread_keyboard(
                connection, user, limit=10, offset=user.get("current_thread_offset", 0)
            )
            await update.message.reply_text("Чаты:", reply_markup=keyboard)
            return

        elif text == "➕ Создать чат":
            thread = await create_or_update_thread(connection, user["id"], title=default_chat_title(), set_active=True)

            user_data["selected_thread_id"] = thread["id"]

            await update.message.reply_text("Вы создали новый чат")
            await update.message.reply_text(
                f"Активный чат: {thread['title']}",
                reply_markup=get_main_menu_keyboard(context, selected_thread=thread, active_thread=thread)
            )
            return

        elif text == "⬅️ Отмена":
            if "edit_thread_id" in user_data:
                user_data.pop("edit_thread_id")
                await update.message.reply_text(
                    "Редактирование отменено.",
                    reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread)
                )
            else:
                await update.message.reply_text(
                    "Действие отменено.",
                    reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread)
                )
            return

        if "edit_thread_id" in user_data:
            thread_id = user_data.pop("edit_thread_id")
            new_title = text
            await create_or_update_thread(connection, user["id"], thread_id=thread_id, title=new_title)
            thread = await get_thread_by_id(connection, thread_id)
            selected_thread = thread
            await update.message.reply_text(
                "Название чата обновлено.",
                reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread)
            )
            return

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

        if not active_thread:
            active_thread = await create_or_update_thread(connection, user["id"], title=default_chat_title(),
                                                          set_active=True)
            user_data["selected_thread_id"] = active_thread["id"]

        human_message = await add_message_to_thread(
            connection,
            thread_id=active_thread["id"],
            text=update.message.text,
            message_type=MessageTypeEnum.human.value,
        )

        db_messages = await get_all_messages_by_thread_id(connection, active_thread["id"])

        default_prompt = await get_value(connection, "model_promt")


        messages = [SystemMessage(content=default_prompt)]

        for message in db_messages:
            if message["message_type"] == MessageTypeEnum.human.value:
                messages.append(HumanMessage(content=message["text"]))
            elif message["message_type"] == MessageTypeEnum.ai.value:
                messages.append(AIMessage(content=message["text"]))

        kv_dict = await get_kv_pairs(
            connection,
            keys=[
                "model_promt",
                "model_base_url",
                "model_openai_api_key",
                "model_temperature",
                "model_max_tokens",
                "model_openai_default_model",
                "model_edit_interval",
                "model_initial_token_threshold",
                "model_typing_interval",
            ]
        )

        # Настраиваем обработчик Telegram
        handler = TelegramChatter(
            message=update.message,
            bot=context.bot,
            chat_id=update.effective_chat.id,
            edit_interval=int(kv_dict.get("model_edit_interval", 1)),
            initial_token_threshold=int(kv_dict.get("model_initial_token_threshold", 5)),
            typing_interval=int(kv_dict.get("model_typing_interval", 2)),
        )
        print(kv_dict.get("model_base_url"))
        callback_manager = AsyncCallbackManager([handler])

        # Пробуем вызвать LLM через базовый URL
        try:
            llm = ChatOpenAI(
                base_url=kv_dict.get("model_base_url"),
                openai_api_key=kv_dict.get("model_openai_api_key"),
                temperature=float(kv_dict.get("model_temperature", 0.5)),
                max_tokens=int(kv_dict.get("model_max_tokens", 4096)),
                streaming=True,
                callback_manager=callback_manager,
                verbose=True,
            )
            response: LLMResult = await llm.agenerate(messages=[messages])

        except Exception as e:
            logger.error(f"Error using base_url LLM: {e}")

            # Fallback на модель OpenAI по умолчанию
            try:
                llm = ChatOpenAI(
                    model_name=kv_dict.get("model_openai_default_model", "gpt-3.5-turbo"),
                    openai_api_key=kv_dict.get("model_openai_api_key"),
                    temperature=float(kv_dict.get("model_temperature", 0.5)),
                    max_tokens=int(kv_dict.get("model_max_tokens", 4096)),
                    streaming=True,
                    callback_manager=callback_manager,
                    verbose=True,
                )
                response: LLMResult = await llm.agenerate(messages=[messages])
            except Exception as e2:
                logger.error(f"Error using fallback LLM: {e2}")
                await update.message.reply_text("Извините, у меня возникли проблемы с генерацией ответа.")
                return

        # Извлекаем текст ответа от модели
        ai_message = response.generations[0][0].text

        # Сохраняем ответ модели в базе данных
        ai_message_db = await add_message_to_thread(
            connection,
            thread_id=active_thread["id"],
            text=ai_message,
            message_type=MessageTypeEnum.ai.value,
        )

        rating_keyboard = get_rating_keyboard(ai_message_db["id"])

        # Пробуем обновить сообщение с клавиатурой
        try:
            await handler.message.edit_reply_markup(reply_markup=rating_keyboard)
        except BadRequest as e:
            logger.error(f"Error editing message: {e}")
            await update.message.reply_text('🤖 Оцените ответ:', reply_markup=rating_keyboard)



