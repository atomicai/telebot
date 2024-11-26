from typing import Optional, List

from langchain_core.callbacks import AsyncCallbackManager
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI
from loguru import logger
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton, ReplyKeyboardRemove,
)
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from llm_bot.api.config.kv_config import kv_settings
from llm_bot.api.utils import default_chat_title
from llm_bot.db.database import AsyncSession
from llm_bot.db.models import MessageTypeEnum, RatingEnum, Message, Thread
from llm_bot.db.repository import (
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
from llm_bot.db.utils import with_async_session
from llm_bot.domain.telegram_streaming_handler import TelegramStreamingHandler


def get_main_menu_keyboard(context, selected_thread: Optional[Thread] = None, active_thread: Optional[Thread] = None) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    condition = context.user_data.get('menu_active', False)
    if not context.user_data.get('menu_active', False):
        return ReplyKeyboardRemove()
    if selected_thread:
        is_active = selected_thread.id == (active_thread.id if active_thread else None)
        first_button_text = f"✅ {selected_thread.title}" if is_active else f"◻️ {selected_thread.title}"
        buttons = [
            [
                KeyboardButton(first_button_text),
                KeyboardButton("💬 Сообщения")
            ],
            [
                KeyboardButton("✏️ Отредактировать"),
                KeyboardButton("🗑️ Удалить"),
            ],
            [
                KeyboardButton("📜 Чаты"),
                KeyboardButton("➕ Создать чат")
            ]
        ]
    else:
        buttons = [
            [
                KeyboardButton("📜 Чаты"),
                KeyboardButton("➕ Создать чат")
            ]
        ]

    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)


def format_messages(messages: List[Message]) -> str:
    formatted_messages = []
    for msg in messages:
        if msg.message_type == MessageTypeEnum.human:
            formatted_messages.append(f"Пользователь:\n{msg.text}")
        elif msg.message_type == MessageTypeEnum.ai:
            formatted_messages.append(f"Бот:\n{msg.text}")
    return "\n\n".join(formatted_messages)


async def generate_thread_keyboard(user, session, limit=10, offset=0) -> InlineKeyboardMarkup:
    threads, total = await get_user_threads(session, user.id, limit=limit, offset=offset)
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"{t.title}{' ✅' if t.id == user.active_thread_id else ' ◻️'}",
                callback_data=f"thread_{t.id}",
            )
        ]
        for t in threads
    ]

    pagination_buttons = []

    if offset > 0:
        pagination_buttons.append(
            InlineKeyboardButton("⬅️", callback_data=f"page_{max(0, offset - limit)}")
        )

    pagination_buttons.append(InlineKeyboardButton("➕", callback_data="create_new_chat"))

    if offset + limit < total:
        pagination_buttons.append(
            InlineKeyboardButton("➡️", callback_data=f"page_{offset + limit}")
        )

    keyboard.append(pagination_buttons)
    return InlineKeyboardMarkup(keyboard)


@with_async_session
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, session: AsyncSession):
    logger.info("Received /start command")
    user = await upsert_user(session, update.message.from_user)

    threads, _ = await get_user_threads(session, user.id)
    # if not threads:
    #     await create_or_update_thread(session, user, title=default_chat_title(), set_active=True)

    active_thread = await get_active_thread(session, user)
    selected_thread = None

    await update.message.reply_text(
        "Я большая языковая модель, начни со мной общение просто отправив любое сообщение.\n"
        # "Управление чатами /chats\n"
        "Создать новый чат /new_chat\n"
        "Включить/выключить меню /chat",
        reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread)
    )


@with_async_session
async def enable_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: AsyncSession):
    user = await upsert_user(session, update.message.from_user)
    user_data = context.user_data

    if 'menu_active' not in user_data:
        user_data['menu_active'] = False

    if user_data['menu_active']:
        user_data['menu_active'] = False
        await update.message.reply_text(
            "Меню скрыто.",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        user_data['menu_active'] = True
        active_thread = await get_active_thread(session, user)
        selected_thread = None

        await update.message.reply_text(
            "Меню активировано.",
            reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread)
        )


@with_async_session
async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: AsyncSession):
    user = await upsert_user(session, update.message.from_user)
    keyboard = await generate_thread_keyboard(user, session, limit=10, offset=user.current_thread_offset)

    await update.message.reply_text("Чаты:", reply_markup=keyboard)


@with_async_session
async def new_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE, session: AsyncSession):
    user = await upsert_user(session, update.message.from_user)
    thread = await create_or_update_thread(session, user, title=default_chat_title(), set_active=True)

    await update.message.reply_text("Вы создали новый чат")
    await update.message.reply_text(
        f"Активный чат: {thread.title}",
        reply_markup=get_main_menu_keyboard(context, selected_thread=thread, active_thread=thread)
    )


@with_async_session
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: AsyncSession):
    logger.info("Received callback query")
    query = update.callback_query
    data = query.data
    user = await upsert_user(session, update.effective_user)
    user_data = context.user_data

    if data.startswith("thread_"):
        thread_id = int(data.split("_")[1])
        thread = await get_thread_by_id(session, thread_id)
        user_data["selected_thread_id"] = thread_id

        active_thread = await get_active_thread(session, user)

        await query.message.reply_text(f"Выбран чат: {thread.title}", reply_markup=get_main_menu_keyboard(context, selected_thread=thread, active_thread=active_thread))
        await query.answer()
        return

    await query.answer()

    if data == "show_chats":
        keyboard = await generate_thread_keyboard(user, session, limit=10, offset=user.current_thread_offset)
        await query.message.reply_text("Чаты:", reply_markup=keyboard)
    elif data.startswith("show_history_"):
        thread_id = int(data.split("_")[2])
        messages = await get_all_messages_by_thread_id(session, thread_id)

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
    elif data.startswith('rate_'):
        parts = data.split('_')
        message_db_id = int(parts[1])
        rating_str = parts[2]
        if rating_str == 'like':
            rating = RatingEnum.like
        elif rating_str == 'dislike':
            rating = RatingEnum.dislike
        else:
            await query.answer("Неверная оценка.")
            return

        message_db = await session.get(Message, message_db_id)
        if message_db:
            message_db.rating = rating
            await session.commit()
            await query.answer("Спасибо за вашу оценку!")
            await query.edit_message_reply_markup(reply_markup=None)
        else:
            await query.answer("Сообщение не найдено.")
    elif data.startswith("delete_"):
        thread_id = int(data.split("_")[1])
        thread = await get_thread_by_id(session, thread_id)
        user_data["delete_thread_id"] = thread_id
        await query.message.reply_text(
            "Вы уверены, что хотите удалить чат?",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Да", callback_data=f"confirm_delete_{thread_id}"),
                        InlineKeyboardButton("❌ Нет", callback_data="cancel_delete"),
                    ]
                ]
            ),
        )
    elif data.startswith("confirm_delete_"):
        thread_id = int(data.split("_")[2])
        thread = await get_thread_by_id(session, thread_id)
        await delete_thread(session, thread_id)
        user_data.pop("delete_thread_id", None)
        selected_thread_id = user_data.pop("selected_thread_id", None)

        active_thread = await get_active_thread(session, user)

        await query.message.reply_text("Чат удален.", reply_markup=get_main_menu_keyboard(context, selected_thread=None, active_thread=active_thread))

    elif data == "cancel_delete":
        user_data.pop("delete_thread_id", None)
        selected_thread_id = user_data.get("selected_thread_id")
        active_thread = await get_active_thread(session, user)
        selected_thread = await get_thread_by_id(session, selected_thread_id) if selected_thread_id else None
        await query.message.reply_text("Удаление отменено.", reply_markup=get_main_menu_keyboard(selected_thread, active_thread))
    elif data.startswith("page_"):
        offset = int(data.split("_")[1])
        keyboard = await generate_thread_keyboard(user, session, limit=10, offset=offset)
        await query.message.reply_text("Чаты:", reply_markup=keyboard)
    elif data == "create_new_chat":
        thread = await create_or_update_thread(session, user, title=default_chat_title(), set_active=True)

        await query.message.reply_text("Вы создали новый чат")
        await query.message.reply_text(f"Активный чат: {thread.title}", reply_markup=get_main_menu_keyboard(context, selected_thread=thread, active_thread=thread))
    else:
        await query.answer()


@with_async_session
async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE, session: AsyncSession):
    logger.info("Received user message")
    user = await upsert_user(session, update.message.from_user)
    user_data = context.user_data
    text = update.message.text.strip()

    selected_thread_id = user_data.get("selected_thread_id")
    active_thread = await get_active_thread(session, user)
    selected_thread = await get_thread_by_id(session, selected_thread_id) if selected_thread_id else None

    if text.startswith("✅ ") or text.startswith("◻️ "):
        if selected_thread:
            is_active = selected_thread.id == (active_thread.id if active_thread else None)
            if not is_active:
                await create_or_update_thread(session, user, thread_id=selected_thread.id, set_active=True)
                active_thread = await get_thread_by_id(session, selected_thread.id)

                await update.message.reply_text(
                    f"Чат '{selected_thread.title}' теперь активен.",
                    reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread)
                )
            else:
                await update.message.reply_text(
                    f"Чат '{selected_thread.title}' уже активен.",
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
            user_data["edit_thread_id"] = selected_thread.id
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
            user_data["delete_thread_id"] = selected_thread.id
            await update.message.reply_text(
                "Вы уверены, что хотите удалить чат?",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("✅ Да", callback_data=f"confirm_delete_{selected_thread.id}"),
                            InlineKeyboardButton("❌ Нет", callback_data="cancel_delete"),
                        ]
                    ]
                ),
            )
        else:
            await update.message.reply_text("Нет выбранного чата для удаления.")
        return

    elif text == "💬 Сообщения":
        if selected_thread:
            messages = await get_all_messages_by_thread_id(session, selected_thread.id)
            formatted_messages = format_messages(messages)
            if formatted_messages:
                await update.message.reply_text(formatted_messages)
            else:
                await update.message.reply_text("Нет сообщений в чате.")
        else:
            await update.message.reply_text("Нет выбранного чата для отображения сообщений.")
        return

    elif text == "📜 Чаты":
        keyboard = await generate_thread_keyboard(user, session, limit=10, offset=user.current_thread_offset)
        await update.message.reply_text("Чаты:", reply_markup=keyboard)
        return

    elif text == "➕ Создать чат":
        thread = await create_or_update_thread(session, user, title=default_chat_title(), set_active=True)

        user_data["selected_thread_id"] = thread.id

        await update.message.reply_text("Вы создали новый чат")
        await update.message.reply_text(
            f"Активный чат: {thread.title}",
            reply_markup=get_main_menu_keyboard(context, selected_thread=thread, active_thread=thread)
        )
        return

    elif text == "⬅️ Отмена":
        if "edit_thread_id" in user_data:
            user_data.pop("edit_thread_id")
            await update.message.reply_text("Редактирование отменено.", reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread))
        else:
            await update.message.reply_text("Действие отменено.", reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread))
        return

    if "edit_thread_id" in user_data:
        thread_id = user_data.pop("edit_thread_id")
        new_title = text
        await create_or_update_thread(session, user, thread_id=thread_id, title=new_title)
        thread = await get_thread_by_id(session, thread_id)
        selected_thread = thread
        await update.message.reply_text("Название чата обновлено.", reply_markup=get_main_menu_keyboard(context, selected_thread, active_thread))
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    if not active_thread:
        active_thread = await create_or_update_thread(session, user, title=default_chat_title(), set_active=True)
        user_data["selected_thread_id"] = active_thread.id

    human_message = await add_message_to_thread(
        session,
        thread_id=active_thread.id,
        text=update.message.text,
        message_type=MessageTypeEnum.human,
    )

    db_messages = await get_all_messages_by_thread_id(session, active_thread.id)

    default_prompt = await get_value(session, key=kv_settings.ai_model_promt_key)
    messages = [SystemMessage(content=default_prompt)]
    for message in db_messages:
        if message.message_type == MessageTypeEnum.human:
            messages.append(HumanMessage(content=message.text))
        else:
            messages.append(AIMessage(content=message.text))

    kv_dict = await get_kv_pairs(
        session,
        keys=[
            kv_settings.ai_model_promt_key,
            kv_settings.ai_model_base_url_key,
            kv_settings.ai_model_openai_api_key_key,
            kv_settings.ai_model_temperature_key,
            kv_settings.ai_model_max_tokens_key,
            kv_settings.ai_model_openai_default_model_key,
            kv_settings.ai_model_edit_interval_key,
            kv_settings.ai_model_initial_token_threshold_key,
            kv_settings.ai_model_typing_interval_key,
        ]
    )

    handler = TelegramStreamingHandler(
        message=update.message,
        bot=context.bot,
        chat_id=update.effective_chat.id,
        edit_interval=int(kv_dict.get(kv_settings.ai_model_edit_interval_key)),
        initial_token_threshold=int(kv_dict.get(kv_settings.ai_model_initial_token_threshold_key)),
        typing_interval=int(kv_dict.get(kv_settings.ai_model_typing_interval_key)),
    )
    callback_manager = AsyncCallbackManager([handler])

    try:
        llm = ChatOpenAI(
            base_url=kv_dict.get(kv_settings.ai_model_base_url_key),
            openai_api_key=kv_dict.get(kv_settings.ai_model_openai_api_key_key),
            temperature=float(kv_dict.get(kv_settings.ai_model_temperature_key)),
            max_tokens=int(kv_dict.get(kv_settings.ai_model_max_tokens_key)),
            streaming=True,
            callback_manager=callback_manager,
            verbose=True,
        )
        response: LLMResult = await llm.agenerate(messages=[messages])
    except Exception as e:
        logger.error(f"Error using base_url LLM: {e}")
        try:
            llm = ChatOpenAI(
                model_name=kv_dict.get(kv_settings.ai_model_openai_default_model_key),
                openai_api_key=kv_dict.get(kv_settings.ai_model_openai_api_key_key),
                temperature=float(kv_dict.get(kv_settings.ai_model_temperature_key)),
                max_tokens=int(kv_dict.get(kv_settings.ai_model_max_tokens_key)),
                streaming=True,
                callback_manager=callback_manager,
                verbose=True,
            )
            response: LLMResult = await llm.agenerate(messages=[messages])
        except Exception as e2:
            logger.error(f"Error using fallback LLM: {e2}")
            await update.message.reply_text("Извините, у меня возникли проблемы с генерацией ответа.")
            return

    ai_message = response.generations[0][0].text

    ai_message_db = await add_message_to_thread(
        session,
        thread_id=active_thread.id,
        text=ai_message,
        message_type=MessageTypeEnum.ai,
    )

    rating_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👍", callback_data=f"rate_{ai_message_db.id}_like"),
            InlineKeyboardButton("👎", callback_data=f"rate_{ai_message_db.id}_dislike")
        ]
    ])

    try:
        await handler.message.edit_reply_markup(reply_markup=rating_keyboard)
    except BadRequest as e:
        logger.error(f"Error editing message: {e}")
        await update.message.reply_text('🤖 Оцените ответ:', reply_markup=rating_keyboard)
