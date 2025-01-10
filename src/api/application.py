import asyncio
from functools import lru_cache
from typing import Optional

from fastapi import Depends, FastAPI
from loguru import logger
from pydantic import BaseModel
from starlette import status
from starlette.exceptions import HTTPException
from starlette.requests import Request
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from src.api.commands import start, user_message, callback_query_handler, new_chat_command, enable_chat_command
from src.api.config.kv_config import kv_settings
from src.api.config.model_config import model_settings
from src.api.config.telegram_bot_config import telegram_bot_config
from src.api.security.security import get_admin_username
from src.running.restore import RethinkDocStore


class WebhookRequest(BaseModel):
    url: str


class KVRequest(BaseModel):
    key: str
    value: str


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
    store = RethinkDocStore()
    await store.init_db()
    await store.connect()
    try:
        if url is None:
            url = telegram_bot_config.WEBHOOK_URL


        logger.info(f"Trying to set webhook at: {url}")
        await store.create_back_log(
            log_data=f"Trying to set webhook at: {url}",
            log_owner="application.set_webhook"
        )

        application = get_telegram_application()
        status_ = await application.bot.set_webhook(url=url)

        if not status_:

            logger.error(f"Failed to set webhook: {url}")
            await store.create_back_log(
                log_data=f"Failed to set webhook: {url}",
                log_owner="application.set_webhook"
            )
            return False


        logger.info(f"Webhook set successfully: {url}")
        await store.create_back_log(
            log_data=f"Webhook set successfully: {url}",
            log_owner="application.set_webhook"
        )
        return True
    finally:
        await store.close()


async def set_commands(application: Application):
    """Установка команд для Telegram-бота."""
    store = RethinkDocStore()
    await store.init_db()
    await store.connect()
    try:
        logger.info("Setting bot commands...")
        await store.create_back_log(
            log_data="Setting bot commands...",
            log_owner="application.set_commands"
        )

        await application.bot.set_my_commands(
            [
                BotCommand('start', 'Начать работу с ботом'),
                BotCommand('new_chat', 'Создать новый чат'),
                BotCommand('chat', 'Включить или выключить меню чата'),
            ],
        )

        logger.info("Bot commands have been set successfully")
        await store.create_back_log(
            log_data="Bot commands have been set successfully",
            log_owner="application.set_commands"
        )
    finally:
        await store.close()


async def setup_kv_defaults(store: RethinkDocStore):
    """Установка значений KV по умолчанию, если они ещё не установлены."""
    logger.info("Checking and setting default KV values...")
    await store.create_back_log(
        log_data="Checking and setting default KV values...",
        log_owner="application.setup_kv_defaults"
    )
    await store.bulk_set_if_not_exists(
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


async def telegram_application_lifespan(app):
    """Lifespan-контекст для управления жизненным циклом Telegram-приложения."""
    application = get_telegram_application()
    await application.initialize()

    store = RethinkDocStore()
    await store.init_db()
    await store.connect()
    try:

        logger.info("Starting Telegram application (lifespan)")
        await store.create_back_log(
            log_data="Starting Telegram application (lifespan)",
            log_owner="application.telegram_application_lifespan"
        )

        await set_commands(application)
        await store.init_db()
        await set_webhook()


        logger.info(f"Model settings loaded: {model_settings}")
        await store.create_back_log(
            log_data=f"Model settings loaded: {model_settings}",
            log_owner="application.telegram_application_lifespan"
        )

        await setup_kv_defaults(store)

        yield

    finally:
        logger.info("Stopping Telegram application (lifespan) and closing connection.")
        await store.create_back_log(
            log_data="Stopping Telegram application (lifespan) and closing connection.",
            log_owner="application.telegram_application_lifespan"
        )
        await store.close()


app = FastAPI(lifespan=telegram_application_lifespan)


@app.post("/webhook")
async def webhook_handler(request: Request):
    """Обработчик вебхука для Telegram."""
    store = RethinkDocStore()
    await store.connect()
    try:

        logger.info("Received request at /webhook")
        await store.create_back_log(
            log_data="Received request at /webhook",
            log_owner="application.webhook_handler"
        )
    finally:
        await store.close()

    data = await request.json()
    application = get_telegram_application()
    await application.process_update(Update.de_json(data=data, bot=application.bot))


@app.post("/set-webhook")
async def set_webhook_endpoint(
    webhook_request: WebhookRequest,
    username: str = Depends(get_admin_username),
):
    """Установить вебхук."""
    store = RethinkDocStore()
    await store.connect()
    try:

        logger.info(f"Admin {username} requested to set webhook: {webhook_request.url}")
        await store.create_back_log(
            log_data=f"Admin {username} requested to set webhook: {webhook_request.url}",
            log_owner="application.set_webhook_endpoint"
        )
    finally:
        await store.close()

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
    store = RethinkDocStore()
    await store.connect()
    try:

        logger.info(f"Admin {username} sets KV: {kv_request.key} = {kv_request.value}")
        await store.create_back_log(
            log_data=f"Admin {username} sets KV: {kv_request.key} = {kv_request.value}",
            log_owner="application.set_value_endpoint"
        )

        await store.set_value(kv_request.key, kv_request.value)


        logger.info(f"KV has been set successfully: {kv_request.key} = {kv_request.value}")
        await store.create_back_log(
            log_data=f"KV has been set successfully: {kv_request.key} = {kv_request.value}",
            log_owner="application.set_value_endpoint"
        )
    finally:
        await store.close()

    return {"message": "Value set successfully", "key": kv_request.key, "value": kv_request.value}


@app.get("/get-value")
async def get_value_endpoint(
    key: str,
    username: str = Depends(get_admin_username),
):
    """Получить значение из KV-хранилища."""
    store = RethinkDocStore()
    await store.connect()
    try:

        logger.info(f"Admin {username} requests KV value for key: {key}")
        await store.create_back_log(
            log_data=f"Admin {username} requests KV value for key: {key}",
            log_owner="application.get_value_endpoint"
        )

        value = await store.get_value(key)


        logger.info(f"KV value for key {key} = {value}")
        await store.create_back_log(
            log_data=f"KV value for key {key} = {value}",
            log_owner="application.get_value_endpoint"
        )
    finally:
        await store.close()

    return {"key": key, "value": value}


@app.get("/get-keys")
async def get_keys_endpoint(
    username: str = Depends(get_admin_username),
):
    """Получить все ключи из KV-хранилища."""
    store = RethinkDocStore()
    await store.connect()
    try:

        logger.info(f"Admin {username} requests all keys from KV.")
        await store.create_back_log(
            log_data=f"Admin {username} requests all keys from KV.",
            log_owner="application.get_keys_endpoint"
        )

        keys = await store.get_keys()


        logger.info(f"Keys retrieved: {keys}")
        await store.create_back_log(
            log_data=f"Keys retrieved: {keys}",
            log_owner="application.get_keys_endpoint"
        )
    finally:
        await store.close()

    return {"keys": keys}
