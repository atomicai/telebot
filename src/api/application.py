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
    if url is None:
        url = telegram_bot_config.WEBHOOK_URL
    application = get_telegram_application()
    status_ = await application.bot.set_webhook(url=url)
    if not status_:
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


async def setup_kv_defaults(store: RethinkDocStore):
    """Установка значений KV по умолчанию, если они ещё не установлены."""
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
    application = get_telegram_application()
    await application.initialize()  # Инициализируем приложение

    store = RethinkDocStore()
    await store.connect()
    try:
        await set_commands(application)
        await store.init_db()
        await set_webhook()

        logger.info(f"Model settings loaded: {model_settings}")
        await setup_kv_defaults(store)

        # Не вызываем application.start() или stop(), так как мы обрабатываем обновления вручную

        yield
    finally:
        await store.close()


app = FastAPI(lifespan=telegram_application_lifespan)


@app.post("/webhook")
async def webhook_handler(request: Request):
    """Обработчик вебхука для Telegram."""
    data = await request.json()
    application = get_telegram_application()
    await application.process_update(Update.de_json(data=data, bot=application.bot))


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
    store = RethinkDocStore()
    await store.connect()
    try:
        await store.set_value(kv_request.key, kv_request.value)
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
        value = await store.get_value(key)
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
        keys = await store.get_keys()
    finally:
        await store.close()

    return {"keys": keys}

