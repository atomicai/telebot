import asyncio
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Optional
from llb_bot.db.database import RDB_HOST, RDB_PORT, RDB_DB

from fastapi import Depends, FastAPI
from loguru import logger
from pydantic import BaseModel
from starlette import status
from starlette.exceptions import HTTPException
from starlette.requests import Request
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram.ext import (
    MessageHandler,
    filters,
)

from llm_bot.api.commands import start, user_message, callback_query_handler, new_chat_command, enable_chat_command
from llm_bot.api.config.kv_config import kv_settings
from llm_bot.api.config.model_config import model_settings
from llm_bot.api.config.telegram_bot_config import telegram_bot_config
from llm_bot.api.security.security import get_admin_username
from llm_bot.db.repository import set_value, get_value, get_keys, bulk_set_if_not_exists
from rethinkdb import r



async def setup_rethinkdb():
    """Инициализация базы данных и таблиц."""
    async with await r.connect(host=RDB_HOST, port=RDB_PORT) as conn:
        logger.info("Setting up RethinkDB database and tables.")
        # Create database if it doesn't exist
        if RDB_DB not in await r.db_list().run(conn):
            await r.db_create(RDB_DB).run(conn)


        required_tables = ["users", "threads", "messages", "kv"]
        for table in required_tables:
            if table not in await r.db(RDB_DB).table_list().run(conn):
                await r.db(RDB_DB).table_create(table).run(conn)
        logger.info("RethinkDB setup complete.")


@lru_cache
def get_telegram_application() -> Application:
    """Создание Telegram-приложения с обработчиками."""
    application = Application.builder().token(telegram_bot_config.TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new_chat", new_chat_command))
    application.add_handler(CommandHandler("chat", enable_chat_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_message))
    application.add_handler(CallbackQueryHandler(callback_query_handler))

    return application


async def set_webhook(url: Optional[str] = None):
    """Установка вебхука для Telegram-бота."""
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
    """Установка команд для Telegram-бота."""
    await application.bot.set_my_commands(
        [
            BotCommand('start', 'Start the bot'),
            BotCommand('new_chat', 'Create a new chat'),
            BotCommand('chat', 'Enable or disable a chat menu'),
        ],
    )
    logger.info("Commands set successfully")


@asynccontextmanager
async def rethinkdb_connection():
    """Контекстный менеджер для подключения к RethinkDB."""
    connection = await r.connect(host=RDB_HOST, port=RDB_PORT, db=RDB_DB)
    try:
        yield connection
    finally:
        await connection.close()


@asynccontextmanager
async def telegram_application_lifespan(app):
    """Жизненный цикл приложения с Telegram-ботом."""
    application = get_telegram_application()
    await setup_rethinkdb()  # Инициализация базы данных

    async with application:
        await set_commands(application)
        await application.start()
        await set_webhook()

        async with rethinkdb_connection() as connection:
            logger.info(f"Model settings loaded: {model_settings}")


            await bulk_set_if_not_exists(
                connection,
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
                }
            )

        yield
        await application.stop()


app = FastAPI(lifespan=telegram_application_lifespan)


@app.post("/webhook")
async def webhook_handler(request: Request):
    """Обработчик вебхука для Telegram."""
    data = await request.json()
    application = get_telegram_application()
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
    """Установить вебхук."""
    success = await set_webhook(webhook_request.url)
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to set webhook")
    return {"message": "Webhook set successfully", "url": webhook_request.url}


@app.post("/set-value")
async def set_value_endpoint(
    kv_request: KVRequest,
    username: str = Depends(get_admin_username),
):
    """Установить значение в KV-хранилище."""
    async with rethinkdb_connection() as connection:
        await set_value(connection, key=kv_request.key, value=kv_request.value)
    return {"message": "Value set successfully", "key": kv_request.key, "value": kv_request.value}


@app.get("/get-value")
async def get_value_endpoint(
    key: str,
    username: str = Depends(get_admin_username),
):
    """Получить значение из KV-хранилища."""
    async with rethinkdb_connection() as connection:
        value = await get_value(connection, key)
    return {"key": key, "value": value}


@app.get("/get-keys")
async def get_keys_endpoint(
    username: str = Depends(get_admin_username),
):
    """Получить все ключи из KV-хранилища."""
    async with rethinkdb_connection() as connection:
        keys = await get_keys(connection)
    return {"keys": keys}
