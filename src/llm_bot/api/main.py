import asyncio

from loguru import logger

from llm_bot.api.application import get_telegram_application, set_commands
from llm_bot.db.database import init_db


def start_application():
    logger.info("Starting bot in polling mode")

    application = get_telegram_application()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_commands(application))
    loop.run_until_complete(init_db())

    application.run_polling()


if __name__ == "__main__":
    start_application()
