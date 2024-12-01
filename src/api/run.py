from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Optional

from fastapi import Depends, FastAPI
from loguru import logger
from pydantic import BaseModel
from starlette import status
from starlette.exceptions import HTTPException
from starlette.requests import Request
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.llm_bot.api.commands import (
    callback_query_handler,
    enable_chat_command,
    new_chat_command,
    start,
    user_message,
)
from src.llm_bot.api.config.kv_config import kv_settings
from src.llm_bot.api.config.model_config import model_settings
from src.llm_bot.api.config.telegram_bot_config import telegram_bot_config
from src.llm_bot.api.security.security import get_admin_username
from src.llm_bot.db.database import AsyncSession, init_db
from src.llm_bot.db.repository import (
    bulk_set_if_not_exists,
    get_keys,
    get_value,
    set_value,
)
from src.llm_bot.db.utils import get_session


@lru_cache
def get_telegram_application() -> Application:
    application = Application.builder().token(telegram_bot_config.TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new_chat", new_chat_command))
    # application.add_handler(CommandHandler("chats", chat_command))
    application.add_handler(CommandHandler("chat", enable_chat_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, user_message)
    )
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    return application


async def set_webhook(url: Optional[str] = None):
    if url is None:
        url = telegram_bot_config.WEBHOOK_URL
    application = get_telegram_application()
    status = await application.bot.set_webhook(url=url)
    if not status:
        logger.error(f"Failed to set webhook with URL: {url}")
        return False
    logger.info(f"Webhook set successfully with URL: {url}")
    return True


async def set_commands(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Start the bot"),
            BotCommand("new_chat", "Create a new chat"),
            BotCommand("chat", "Enable or disable a chat menu"),
            # BotCommand('chats', 'Manage your chats'),
        ],
    )
    logger.info("Commands set successfully")


@asynccontextmanager
async def telegram_application_lifespan(app):
    application = get_telegram_application()
    async with application:
        await set_commands(application)
        await init_db()

        await application.start()

        await set_webhook()

        async with AsyncSession() as session:
            await bulk_set_if_not_exists(
                session,
                {
                    kv_settings.ai_model_promt_key: model_settings.promt,
                    kv_settings.ai_model_base_url_key: model_settings.base_url,
                    kv_settings.ai_model_openai_api_key_key: model_settings.openai_api_key,
                    kv_settings.ai_model_temperature_key: model_settings.temperature,
                    kv_settings.ai_model_max_tokens_key: model_settings.max_tokens,
                    kv_settings.ai_model_openai_default_model_key: model_settings.openai_default_model,
                    kv_settings.ai_model_edit_interval_key: model_settings.edit_interval,
                    kv_settings.ai_model_initial_token_threshold_key: model_settings.initial_token_threshold,
                    kv_settings.ai_model_typing_interval_key: model_settings.typing_interval,
                },
            )

        yield
        await application.stop()
        # await database.teardown()


app = FastAPI(lifespan=telegram_application_lifespan)


@app.post(
    "/webhook",
)
async def webhook_handler(
    request: Request,
    application: Application = Depends(get_telegram_application),
):
    data = await request.json()

    await application.process_update(Update.de_json(data=data, bot=application.bot))


class WebhookRequest(BaseModel):
    url: str


class KVRequest(BaseModel):
    key: str
    value: str


@app.post("/set-webhook")
async def set_webhook_endpoint(
    webhook_request: WebhookRequest,
    username: str = Depends(get_admin_username),
):
    success = await set_webhook(webhook_request.url)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set webhook",
        )
    return {"message": "Webhook set successfully", "url": webhook_request.url}


@app.post("/set-value")
async def set_value_endpoint(
    kv_request: KVRequest,
    username: str = Depends(get_admin_username),
    session=Depends(get_session),
):
    await set_value(session, key=kv_request.key, value=kv_request.value)
    return {
        "message": "Value set successfully",
        "key": kv_request.key,
        "value": kv_request.value,
    }


@app.get("/get-value")
async def get_value_endpoint(
    key: str,
    username: str = Depends(get_admin_username),
    session=Depends(get_session),
):
    value = await get_value(session, key)
    return {"key": key, "value": value}


@app.get("/get-keys")
async def get_keys_endpoint(
    username: str = Depends(get_admin_username),
    session=Depends(get_session),
):
    keys = await get_keys(session)
    return {"keys": keys}
