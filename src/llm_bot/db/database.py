import os

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession as AsyncSession_
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=True)
Base = declarative_base()

AsyncSession = sessionmaker(
    bind=engine, class_=AsyncSession_, expire_on_commit=False, autoflush=False
)


async def init_db():
    logger.info("Creating tables")
    import llm_bot.db.models  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
