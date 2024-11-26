from typing import Optional

from sqlalchemy import select, func
from telegram import User as UserSchema

from llm_bot.db.database import AsyncSession
from llm_bot.db.models import User, Message, Thread, MessageTypeEnum, RatingEnum, KV


async def upsert_user(session: AsyncSession, user: UserSchema | User, offset: Optional[int] = None) -> User:
    user_db = await session.execute(
        select(User).filter(User.id == user.id)
    )
    user_db = user_db.scalar_one_or_none()
    if user_db:
        user_db.username = user.username
        user_db.first_name = user.first_name
        user_db.last_name = user.last_name
        user_db.language_code = user.language_code
        user_db.is_premium = user.is_premium
    else:
        user_db = User(
            id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            is_premium=user.is_premium,
            current_thread_offset=0
        )
        session.add(user_db)
    if offset is not None:
        user_db.current_thread_offset = offset

    await session.commit()
    await session.refresh(user_db)
    return user_db


async def get_user_threads(
        session: AsyncSession,
        user_id: int,
        limit: int = 10, offset: int = 0
) -> tuple[list[Thread], int]:
    total_result = await session.execute(
        select(func.count(Thread.id)).filter(Thread.user_id == user_id)
    )
    total = total_result.scalar_one()

    result = await session.execute(
        select(Thread)
        .filter(Thread.user_id == user_id)
        .order_by(Thread.id.asc())
        .limit(limit)
        .offset(offset)
    )
    threads = result.scalars().all()
    return threads, total


async def create_or_update_thread(
        session: AsyncSession,
        user: User,
        thread_id: int = None,
        title: str = None,
        set_active: bool = False,
) -> Thread:
    """
    Create or update a thread. If thread_id is provided, the thread will be updated.
    Otherwise, a new thread will be created.
    """
    if thread_id is not None:
        thread = await session.get(Thread, thread_id)
        if not thread or thread.user_id != user.id:
            raise ValueError("Thread not found or not owned by user.")
        if title is not None:
            thread.title = title
    else:
        thread = Thread(user_id=user.id, title=title)
        session.add(thread)
        await session.flush()

    if set_active:
        user.active_thread_id = thread.id

    await session.commit()
    await session.refresh(thread)
    return thread


async def get_active_thread(session: AsyncSession, user: User) -> Optional[Thread]:
    if user.active_thread_id is None:
        return None

    await session.refresh(user, ['active_thread'])
    return user.active_thread


async def delete_thread(session: AsyncSession, thread_id: int):
    thread = await get_thread_by_id(session, thread_id)
    user = thread.user

    if user.active_thread_id == thread_id:
        user.active_thread_id = None
        await session.flush()

    await session.delete(thread)
    await session.commit()


async def get_thread_by_id(session: AsyncSession, thread_id: int) -> Thread:
    result = await session.execute(
        select(Thread).where(Thread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if thread:
        return thread
    else:
        raise ValueError("Thread not found or not owned by user.")


async def get_all_messages_by_thread_id(
        session: AsyncSession,
        thread_id: int,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .filter(Message.thread_id == thread_id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()
    return messages


async def add_message_to_thread(
        session: AsyncSession,
        thread_id: int,
        text: str,
        message_type: MessageTypeEnum,
        rating: Optional[RatingEnum] = None
) -> Message:
    message = Message(
        thread_id=thread_id,
        text=text,
        message_type=message_type,
        rating=rating
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def update_message(
        session: AsyncSession,
        message_id: int,
        text: Optional[str] = None,
        rating: Optional[RatingEnum] = None
) -> Message:
    message = await session.get(Message, message_id)
    if not message:
        raise ValueError("Message not found.")
    if text is not None:
        message.text = text
    if rating is not None:
        message.rating = rating
    await session.commit()
    await session.refresh(message)
    return message


async def get_value(session: AsyncSession, key: str) -> Optional[str]:
    result = await session.execute(
        select(KV.value).where(KV.key == key)
    )
    value = result.scalar_one_or_none()
    return value


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    kv = await session.get(KV, key)
    if kv:
        kv.value = value
    else:
        kv = KV(key=key, value=value)
        session.add(kv)
    await session.commit()


async def delete_value(session: AsyncSession, key: str) -> None:
    kv = await session.get(KV, key)
    if kv:
        await session.delete(kv)
        await session.commit()


async def get_keys(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(KV.key)
    )
    keys = result.scalars().all()
    return keys


async def get_kv_pairs(
        session: AsyncSession,
        keys: list[str]
) -> dict[str, Optional[str]]:
    result = await session.execute(
        select(KV.key, KV.value).where(KV.key.in_(keys))
    )
    rows = result.all()
    kv_dict = {row.key: row.value for row in rows}

    return {key: kv_dict.get(key) for key in keys}


async def bulk_set_if_not_exists(session: AsyncSession, kv_dict: dict[str, str]) -> None:
    existing_keys = await session.execute(
        select(KV.key).where(KV.key.in_(kv_dict.keys()))
    )
    existing_keys = {row.key for row in existing_keys.all()}

    new_kv_entries = [
        KV(key=key, value=str(value))
        for key, value in kv_dict.items()
        if key not in existing_keys
    ]

    if new_kv_entries:
        session.add_all(new_kv_entries)
        await session.commit()
