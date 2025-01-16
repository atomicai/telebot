from loguru import logger

from src.configuring.prime import Config

logger.add(
    Config.loguru.LOG_FILE_NAME,
    rotation=Config.loguru.LOG_ROTATION,
    retention=Config.loguru.LOG_RETENTION,
)
