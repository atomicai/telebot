from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger


def suppress_and_log(*exceptions):
    def decorator(func):
        def wrapper(*args, **kwargs):
            with suppress(*exceptions):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    logger.error(f"An error occurred in {func.__name__}: {e}", exc_info=True)

        return wrapper

    return decorator


def default_chat_title() -> str:
    moscow_time = datetime.now(ZoneInfo('Europe/Moscow'))
    return moscow_time.strftime('Чат %d.%m.%Y %H:%M:%S')

