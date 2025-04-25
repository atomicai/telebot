from typing import List

from telegram import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatAction
from telegram.error import BadRequest

from src.api.keyboards import KeyboardManager
from src.api.utils import default_chat_title
from src.configuring.loggers import logger
from src.configuring.prime import Config
from src.etc.protocol import construct_llm_protocol
from src.etc.schema import MessageTypeEnum, RatingEnum
from src.running.prompts import (
    RESPONSEFareWellPromptRunner,
    RESPONSEStreamingPromptRunner,
    RESPONSEWithSearchOrNotPromptRunner,
)
from src.running.restore import RethinkDocStore  # Импортируем наш новый класс
from src.running.runner import JarvisCallbackHandler, JARVISRunner
from src.running.telegram_chatter import TelegramChatter


def get_keyboard_manager(store: RethinkDocStore):
    return KeyboardManager(
        store
    )  # или KeyboardManager(store.conn), если так реализовано


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
    store = RethinkDocStore()
    await store.connect()
    try:
        keyboard_manager = get_keyboard_manager(store)

        logger.info("Received /start command")
        await store.create_back_log(
            log_data="Received /start command", log_owner="commands.start"
        )

        user = await store.upsert_user(
            {
                "id": update.message.from_user.id,
                "first_name": update.message.from_user.first_name,
                "last_name": update.message.from_user.last_name,
                "username": update.message.from_user.username,
                "language_code": update.message.from_user.language_code,
                "is_premium": update.message.from_user.is_premium,
            }
        )

        active_thread = await store.get_active_thread(user["id"])
        if not active_thread:
            active_thread = await store.create_or_update_thread(
                user_id=user["id"], title=default_chat_title(), set_active=True
            )

        await update.message.reply_text(
            "Я большая языковая модель, начни со мной общение просто отправив любое сообщение.\n"
            "Создать новый чат /new_chat\n"
            "Включить/выключить меню /chat",
            reply_markup=keyboard_manager.get_main_menu_keyboard(
                context=context, selected_thread=None, active_thread=active_thread
            ),
        )
    finally:
        await store.close()


async def enable_chat_command(update: Update, context):
    store = RethinkDocStore()
    await store.connect()
    try:
        keyboard_manager = get_keyboard_manager(store)

        logger.info("Received command to enable/disable menu (/chat)")
        await store.create_back_log(
            log_data="Received command to enable/disable menu (/chat)",
            log_owner="commands.enable_chat_command",
        )

        user = await store.upsert_user(
            {
                "id": update.message.from_user.id,
                "first_name": update.message.from_user.first_name,
                "last_name": update.message.from_user.last_name,
                "username": update.message.from_user.username,
                "language_code": update.message.from_user.language_code,
                "is_premium": update.message.from_user.is_premium,
            }
        )

        user_data = context.user_data
        user_data["menu_active"] = not user_data.get("menu_active", False)

        if user_data["menu_active"]:
            active_thread = await store.get_active_thread(user["id"])
            await update.message.reply_text(
                "Меню активировано.",
                reply_markup=keyboard_manager.get_main_menu_keyboard(
                    context=context, selected_thread=None, active_thread=active_thread
                ),
            )
        else:
            await update.message.reply_text(
                "Меню скрыто.", reply_markup=ReplyKeyboardRemove()
            )
    finally:
        await store.close()


async def new_chat_command(update: Update, context):
    store = RethinkDocStore()
    await store.connect()
    try:
        keyboard_manager = get_keyboard_manager(store)

        logger.info("Received /new_chat command")
        await store.create_back_log(
            log_data="Received /new_chat command", log_owner="commands.new_chat_command"
        )

        user = await store.upsert_user(
            {
                "id": update.message.from_user.id,
                "first_name": update.message.from_user.first_name,
                "last_name": update.message.from_user.last_name,
                "username": update.message.from_user.username,
                "language_code": update.message.from_user.language_code,
                "is_premium": update.message.from_user.is_premium,
            }
        )

        thread = await store.create_or_update_thread(
            user["id"], title=default_chat_title(), set_active=True
        )

        await update.message.reply_text("Вы создали новый чат")
        await update.message.reply_text(
            f"Активный чат: {thread['title']}",
            reply_markup=keyboard_manager.get_main_menu_keyboard(
                context, selected_thread=thread, active_thread=thread
            ),
        )
    finally:
        await store.close()


async def chat_command(update: Update, context):
    store = RethinkDocStore()
    await store.connect()
    try:
        keyboard_manager = get_keyboard_manager(store)

        logger.info("Received /chat command")
        await store.create_back_log(
            log_data="Received /chat command", log_owner="commands.chat_command"
        )

        user = await store.upsert_user(
            {
                "id": update.message.from_user.id,
                "first_name": update.message.from_user.first_name,
                "last_name": update.message.from_user.last_name,
                "username": update.message.from_user.username,
                "language_code": update.message.from_user.language_code,
                "is_premium": update.message.from_user.is_premium,
            }
        )

        keyboard = await keyboard_manager.generate_thread_keyboard(
            user=user, limit=10, offset=user.get("current_thread_offset", 0)
        )
        await update.message.reply_text("Ваши чаты:", reply_markup=keyboard)
    finally:
        await store.close()


async def callback_query_handler(update: Update, context):
    store = RethinkDocStore()
    await store.connect()
    try:
        keyboard_manager = get_keyboard_manager(store)

        logger.info("Received callback query")
        await store.create_back_log(
            log_data="Received callback query",
            log_owner="commands.callback_query_handler",
        )

        query = update.callback_query
        data = query.data

        user = await store.upsert_user(
            {
                "id": update.effective_user.id,
                "first_name": update.effective_user.first_name,
                "last_name": update.effective_user.last_name,
                "username": update.effective_user.username,
                "language_code": update.effective_user.language_code,
                "is_premium": update.effective_user.is_premium,
            }
        )
        user_data = context.user_data

        if data.startswith("thread_"):
            logger.info(f"Chat selection button pressed: {data}")
            await store.create_back_log(
                log_data=f"Chat selection button pressed: {data}",
                log_owner="commands.callback_query_handler",
            )

            thread_id = data.split("_")[1]
            thread = await store.get_thread_by_id(thread_id)
            user_data["selected_thread_id"] = thread_id

            active_thread = await store.get_active_thread(user["id"])

            await query.message.reply_text(
                f"Выбран чат: {thread['title']}",
                reply_markup=keyboard_manager.get_main_menu_keyboard(
                    context, selected_thread=thread, active_thread=active_thread
                ),
            )
            await query.answer()
            return

        if data == "show_chats":
            logger.info("Show chats button pressed")
            await store.create_back_log(
                log_data="Show chats button pressed",
                log_owner="commands.callback_query_handler",
            )
            keyboard = await keyboard_manager.generate_thread_keyboard(
                user=user, limit=10, offset=user.get("current_thread_offset", 0)
            )
            await query.message.reply_text("Чаты:", reply_markup=keyboard)

        elif data.startswith("show_history_"):
            logger.info(f"Show history button pressed for thread: {data}")
            await store.create_back_log(
                log_data=f"Show history button pressed for thread: {data}",
                log_owner="commands.callback_query_handler",
            )
            thread_id = data.split("_")[2]
            messages = await store.get_all_messages_by_thread_id(thread_id)

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
            logger.info(f"Message rating button pressed: {data}")
            await store.create_back_log(
                log_data=f"Message rating button pressed: {data}",
                log_owner="commands.callback_query_handler",
            )

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

            try:
                await store.update_message(message_id, rating=rating)
                await query.answer("Спасибо за вашу оценку!")
                await query.edit_message_reply_markup(reply_markup=None)
            except ValueError:
                logger.error("Attempt to rate a non-existent message")
                await store.create_back_log(
                    log_data="Attempt to rate a non-existent message",
                    log_owner="commands.callback_query_handler",
                )
                await query.answer("Сообщение не найдено.")

        elif data.startswith("delete_"):
            logger.info(f"Delete chat button pressed: {data}")
            await store.create_back_log(
                log_data=f"Delete chat button pressed: {data}",
                log_owner="commands.callback_query_handler",
            )
            thread_id = data.split("_")[1]
            thread = await store.get_thread_by_id(thread_id)
            user_data["delete_thread_id"] = thread_id

            await query.message.reply_text(
                "Вы уверены, что хотите удалить чат?",
                reply_markup=keyboard_manager.get_delete_confirmation_keyboard(
                    thread_id
                ),
            )

        elif data.startswith("confirm_delete_"):
            logger.info(f"Chat deletion confirmed: {data}")
            await store.create_back_log(
                log_data=f"Chat deletion confirmed: {data}",
                log_owner="commands.callback_query_handler",
            )
            thread_id = data.split("_")[2]
            await store.delete_thread(thread_id)
            user_data.pop("delete_thread_id", None)
            selected_thread_id = user_data.pop("selected_thread_id", None)

            active_thread = await store.get_active_thread(user["id"])

            await query.message.reply_text(
                "Чат удален.",
                reply_markup=keyboard_manager.get_main_menu_keyboard(
                    context, selected_thread=None, active_thread=active_thread
                ),
            )

        elif data == "cancel_delete":
            logger.info("Delete cancellation button pressed")
            await store.create_back_log(
                log_data="Delete cancellation button pressed",
                log_owner="commands.callback_query_handler",
            )
            user_data.pop("delete_thread_id", None)
            selected_thread_id = user_data.get("selected_thread_id")
            active_thread = await store.get_active_thread(user["id"])
            selected_thread = (
                await store.get_thread_by_id(selected_thread_id)
                if selected_thread_id
                else None
            )
            await query.message.reply_text(
                "Удаление отменено.",
                reply_markup=keyboard_manager.get_main_menu_keyboard(
                    context,
                    selected_thread=selected_thread,
                    active_thread=active_thread,
                ),
            )

        elif data.startswith("page_"):
            logger.info(f"Chat pagination button pressed: {data}")
            await store.create_back_log(
                log_data=f"Chat pagination button pressed: {data}",
                log_owner="commands.callback_query_handler",
            )
            offset = data.split("_")[1]
            keyboard = await keyboard_manager.generate_thread_keyboard(
                user=user, limit=10, offset=offset
            )
            await query.edit_message_text("Чаты:", reply_markup=keyboard)

        elif data == "create_new_chat":
            logger.info("Create new chat button pressed")
            await store.create_back_log(
                log_data="Create new chat button pressed",
                log_owner="commands.callback_query_handler",
            )
            thread = await store.create_or_update_thread(
                user["id"], title=default_chat_title(), set_active=True
            )

            await query.message.reply_text("Вы создали новый чат")
            await query.message.reply_text(
                f"Активный чат: {thread['title']}",
                reply_markup=keyboard_manager.get_main_menu_keyboard(
                    context, selected_thread=thread, active_thread=thread
                ),
            )
        else:
            logger.info(f"Unknown button/data pressed: {data}")
            await store.create_back_log(
                log_data=f"Unknown button/data pressed: {data}",
                log_owner="commands.callback_query_handler",
            )
            await query.answer()
    finally:
        await store.close()


async def user_message(update: Update, context):
    store = RethinkDocStore()
    await store.connect()
    try:
        keyboard_manager = get_keyboard_manager(store)

        logger.info("Received a message from the user")
        await store.create_back_log(
            log_data="Received a message from the user",
            log_owner="commands.user_message",
        )

        user = await store.upsert_user(
            {
                "id": update.message.from_user.id,
                "first_name": update.message.from_user.first_name,
                "last_name": update.message.from_user.last_name,
                "username": update.message.from_user.username,
                "language_code": update.message.from_user.language_code,
                "is_premium": update.message.from_user.is_premium,
            }
        )

        user_data = context.user_data
        text = update.message.text.strip()

        selected_thread_id = user_data.get("selected_thread_id")
        active_thread = await store.get_active_thread(user["id"])
        selected_thread = (
            await store.get_thread_by_id(selected_thread_id)
            if selected_thread_id
            else None
        )

        if text.startswith("✅ ") or text.startswith("◻️ "):
            logger.info(f"Chat switch button pressed: '{text}'")
            await store.create_back_log(
                log_data=f"Chat switch button pressed: '{text}'",
                log_owner="commands.user_message",
            )
            if selected_thread:
                is_active = (
                    active_thread and selected_thread["id"] == active_thread["id"]
                )
                if not is_active:
                    await store.create_or_update_thread(
                        user["id"], thread_id=selected_thread["id"], set_active=True
                    )
                    active_thread = await store.get_thread_by_id(selected_thread["id"])

                    logger.info(
                        f"Sending user a message about the new active chat: {selected_thread['title']}"
                    )
                    await store.create_back_log(
                        log_data=f"Sending user a message about the new active chat: {selected_thread['title']}",
                        log_owner="commands.user_message",
                    )
                    await update.message.reply_text(
                        f"Чат '{selected_thread['title']}' теперь активен.",
                        reply_markup=keyboard_manager.get_main_menu_keyboard(
                            context, selected_thread, active_thread
                        ),
                    )
                else:
                    logger.info(
                        f"Sending user a message about the already active chat: {selected_thread['title']}"
                    )
                    await store.create_back_log(
                        log_data=f"Sending user a message about the already active chat: {selected_thread['title']}",
                        log_owner="commands.user_message",
                    )
                    await update.message.reply_text(
                        f"Чат '{selected_thread['title']}' уже активен.",
                        reply_markup=keyboard_manager.get_main_menu_keyboard(
                            context, selected_thread, active_thread
                        ),
                    )
            else:
                logger.info("No chat selected while switching.")
                await store.create_back_log(
                    log_data="No chat selected while switching.",
                    log_owner="commands.user_message",
                )
                await update.message.reply_text(
                    "Нет выбранного чата.",
                    reply_markup=keyboard_manager.get_main_menu_keyboard(
                        context, selected_thread, active_thread
                    ),
                )
            return

        elif text == "✏️ Отредактировать":
            logger.info("Edit button pressed")
            await store.create_back_log(
                log_data="Edit button pressed", log_owner="commands.user_message"
            )
            if selected_thread:
                user_data["edit_thread_id"] = selected_thread["id"]
                logger.info(
                    f"Sending user a message prompting them to enter a new chat title: {selected_thread['id']}"
                )
                await store.create_back_log(
                    log_data=f"Sending user a message prompting them to enter a new chat title: {selected_thread['id']}",
                    log_owner="commands.user_message",
                )
                await update.message.reply_text(
                    "Введите новое название чата:",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("⬅️ Отмена")]],
                        resize_keyboard=True,
                        one_time_keyboard=True,
                    ),
                )
            else:
                logger.info("Attempted to edit a chat, but no chat was selected.")
                await store.create_back_log(
                    log_data="Attempted to edit a chat, but no chat was selected.",
                    log_owner="commands.user_message",
                )
                await update.message.reply_text(
                    "Нет выбранного чата для редактирования."
                )
            return

        elif text == "🗑️ Удалить":
            logger.info("Delete button pressed")
            await store.create_back_log(
                log_data="Delete button pressed", log_owner="commands.user_message"
            )
            if selected_thread:
                user_data["delete_thread_id"] = selected_thread["id"]
                logger.info(
                    f"Sending chat deletion confirmation: {selected_thread['id']}"
                )
                await store.create_back_log(
                    log_data=f"Sending chat deletion confirmation: {selected_thread['id']}",
                    log_owner="commands.user_message",
                )
                await update.message.reply_text(
                    "Вы уверены, что хотите удалить чат?",
                    reply_markup=keyboard_manager.get_delete_confirmation_keyboard(
                        selected_thread["id"]
                    ),
                )
            else:
                logger.info("Attempted to delete a chat, but no chat was selected.")
                await store.create_back_log(
                    log_data="Attempted to delete a chat, but no chat was selected.",
                    log_owner="commands.user_message",
                )
                await update.message.reply_text("Нет выбранного чата для удаления.")
            return

        elif text == "💬 Сообщения":
            logger.info("Messages button pressed")
            await store.create_back_log(
                log_data="Messages button pressed", log_owner="commands.user_message"
            )
            if selected_thread:
                messages = await store.get_all_messages_by_thread_id(
                    selected_thread["id"]
                )
                formatted_messages = format_messages(messages)
                if formatted_messages:
                    logger.info(
                        f"Sending chat messages {selected_thread['id']} to the user"
                    )
                    await store.create_back_log(
                        log_data=f"Sending chat messages {selected_thread['id']} to the user",
                        log_owner="commands.user_message",
                    )
                    await update.message.reply_text(formatted_messages)
                else:
                    await update.message.reply_text("Нет сообщений в чате.")
            else:
                await update.message.reply_text(
                    "Нет выбранного чата для отображения сообщений."
                )
            return

        elif text == "📜 Чаты":
            logger.info("Chats button pressed")
            await store.create_back_log(
                log_data="Chats button pressed", log_owner="commands.user_message"
            )
            keyboard = await keyboard_manager.generate_thread_keyboard(
                user=user, limit=10, offset=user.get("current_thread_offset", 0)
            )
            logger.info("Sending chat list to the user")
            await store.create_back_log(
                log_data="Sending chat list to the user",
                log_owner="commands.user_message",
            )
            await update.message.reply_text("Чаты:", reply_markup=keyboard)
            return

        elif text == "➕ Новый чат":
            logger.info("New chat button pressed")
            await store.create_back_log(
                log_data="New chat button pressed", log_owner="commands.user_message"
            )
            thread = await store.create_or_update_thread(
                user["id"], title=default_chat_title(), set_active=True
            )
            user_data["selected_thread_id"] = thread["id"]

            logger.info(f"Message to user about creating a new chat: {thread['id']}")
            await store.create_back_log(
                log_data=f"Message to user about creating a new chat: {thread['id']}",
                log_owner="commands.user_message",
            )
            await update.message.reply_text("Вы создали новый чат")
            await update.message.reply_text(
                f"Активный чат: {thread['title']}",
                reply_markup=keyboard_manager.get_main_menu_keyboard(
                    context, selected_thread=thread, active_thread=thread
                ),
            )
            return

        elif text == "⬅️ Отмена":
            logger.info("Cancel button pressed")
            await store.create_back_log(
                log_data="Cancel button pressed", log_owner="commands.user_message"
            )
            if "edit_thread_id" in user_data:
                user_data.pop("edit_thread_id")
                logger.info("Editing canceled by user")
                await store.create_back_log(
                    log_data="Editing canceled by user",
                    log_owner="commands.user_message",
                )
                await update.message.reply_text(
                    "Редактирование отменено.",
                    reply_markup=keyboard_manager.get_main_menu_keyboard(
                        context, selected_thread, active_thread
                    ),
                )
            else:
                logger.info("Canceling another action by user")
                await store.create_back_log(
                    log_data="Canceling another action by user",
                    log_owner="commands.user_message",
                )
                await update.message.reply_text(
                    "Действие отменено.",
                    reply_markup=keyboard_manager.get_main_menu_keyboard(
                        context, selected_thread, active_thread
                    ),
                )
            return

        if "edit_thread_id" in user_data:
            thread_id = user_data.pop("edit_thread_id")
            new_title = text
            await store.create_or_update_thread(
                user["id"], thread_id=thread_id, title=new_title
            )
            thread = await store.get_thread_by_id(thread_id)
            selected_thread = thread

            logger.info(f"Chat title {thread_id} updated to '{new_title}' by user.")
            await store.create_back_log(
                log_data=f"Chat title {thread_id} updated to '{new_title}' by user.",
                log_owner="commands.user_message",
            )
            await update.message.reply_text(
                "Название чата обновлено.",
                reply_markup=keyboard_manager.get_main_menu_keyboard(
                    context, selected_thread, active_thread
                ),
            )
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )

        if not active_thread:
            active_thread = await store.create_or_update_thread(
                user["id"], title=default_chat_title(), set_active=True
            )
            user_data["selected_thread_id"] = active_thread["id"]

        human_message = await store.add_message_to_thread(
            thread_id=active_thread["id"],
            text=update.message.text,
            message_type=MessageTypeEnum.human.value,
        )
        logger.info(f"human_message=[{human_message}]")
        db_messages = await store.get_all_messages_by_thread_id(active_thread["id"])
        # TODO LLM generating response in progress ...
        edit_interval = int(Config.telegram.get("edit_interval", 3))
        initial_token_threshold = int(Config.telegram.get("initial_token_threshold", 5))
        typing_interval = int(Config.telegram.get("typing_interval", 3))
        logger.info(
            f"user_message | edit_interval=[{edit_interval}] | initial_token_threshold=[{initial_token_threshold}] | typing_interval=[{typing_interval}]"
        )
        telegram_chatter = TelegramChatter(
            message=update.message,
            bot=context.bot,
            chat_id=update.effective_chat.id,
            edit_interval=edit_interval,
            initial_token_threshold=initial_token_threshold,
            typing_interval=typing_interval,
        )
        telegram_callbacks = [telegram_chatter]
        jarvis_callbacks = [JarvisCallbackHandler(typing_interval=typing_interval)]

        logger.info("Beginning LLM request (base_url)")
        await store.create_pipeline_log(
            message_id=str(human_message["id"]),
            log_data="Beginning LLM request (base_url)",
            log_owner="commands.user_message",
            pipeline_version="v1",
        )

        try:
            connection_params = dict(
                host=Config.llm.get("LLM_API_URL", None),
                api_key=Config.llm.get("LLM_API_KEY", "<YOUR_API_KEY>"),
                temperature=float(Config.llm.get("temperature", 0.22)),
                max_tokens=int(Config.llm.get("max_tokens", 4096)),
                streaming=True,
                verbose=True,
            )
            se_runner = RESPONSEWithSearchOrNotPromptRunner(
                llm=construct_llm_protocol(
                    **connection_params, callbacks=jarvis_callbacks
                )
            )
            fa_runner = RESPONSEFareWellPromptRunner(
                llm=construct_llm_protocol(
                    **connection_params, callbacks=telegram_callbacks
                )
            )

            re_runner = RESPONSEStreamingPromptRunner(
                llm=construct_llm_protocol(
                    **connection_params, callbacks=telegram_callbacks
                )
            )
        except Exception as e:
            logger.error(f"Error using base_url LLM: {e}")
            await store.create_back_log(
                log_data=f"Error using base_url LLM: {e}",
                log_owner="commands.user_message",
            )
            await store.create_pipeline_log(
                message_id=str(human_message["id"]),
                log_data=f"Error using base_url LLM: {e}",
                log_owner="commands.user_message",
                pipeline_version="v1",
            )
        else:
            # TODO: Propagate API from config instead of hard-coding
            jarvis_runner = JARVISRunner(
                se_runner=se_runner, fa_runner=fa_runner, re_runner=re_runner
            )

            ai_message, state = await jarvis_runner.arun(
                query=db_messages[-1]["text"],
                db_messages=db_messages[:-1],
                return_state=True,
            )  # noqa
            logger.info("Saving model response to the database...")
            await store.create_back_log(
                log_data="Saving model response to the database...",
                log_owner="commands.user_message",
            )
            ai_message_db = await store.add_message_to_thread(
                thread_id=active_thread["id"],
                text=ai_message,
                message_type=MessageTypeEnum.ai.value,
                parent_id=human_message["id"],
                message_topic=state["message_topic"],
                is_relevant_towards_context=state["is_relevant_towards_context"],
            )

            human_message = await store.update_message(
                message_id=human_message["id"],
                message_topic=state["message_topic"],
                is_relevant_towards_context=state["is_relevant_towards_context"],
            )

            logger.info(
                f"Model response saved to message ID={ai_message_db['id']} (thread_id={active_thread['id']})"
            )
            await store.create_back_log(
                log_data=f"Model response saved to message ID={ai_message_db['id']} (thread_id={active_thread['id']})",
                log_owner="commands.user_message",
            )

            rating_keyboard = keyboard_manager.get_rating_keyboard(ai_message_db["id"])

            try:
                await telegram_chatter.message.edit_reply_markup(
                    reply_markup=rating_keyboard
                )
            except BadRequest as e:
                logger.error(f"Error editing message (BadRequest): {e}")
                await store.create_back_log(
                    log_data=f"Error editing message (BadRequest): {e}",
                    log_owner="commands.user_message",
                )
                await update.message.reply_text(
                    "🤖 Оцените ответ:", reply_markup=rating_keyboard
                )
    finally:
        await store.close()
