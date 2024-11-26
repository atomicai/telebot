from functools import wraps

from llm_bot.db.database import AsyncSession


def with_async_session(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with AsyncSession() as session:
            return await func(*args, session=session, **kwargs)

    return wrapper


async def get_session() -> AsyncSession:
    async with AsyncSession() as session:
        yield session
