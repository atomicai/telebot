import sys
from loguru import logger


def configure_logging():

    logger.remove()


    logger.add(
        sys.stdout,
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        colorize=True
    )


if __name__ == "__main__":
    configure_logging()