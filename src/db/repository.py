from typing import Optional, List, Dict
from loguru import logger
import os

from src.db.database import RDB_DB
from rethinkdb import r

DB_NAME = os.getenv("RETHINKDB_DB")

async def upsert_user(connection, user_data: Dict, offset: Optional[int] = None) -> Dict:
    users_table = r.db(DB_NAME).table("users")
    existing_user = await users_table.get(user_data["id"]).run(connection)

    if existing_user:
        updated_user = {**existing_user, **user_data}
        if offset is not None:
            updated_user["current_thread_offset"] = offset
        await users_table.get(user_data["id"]).update(updated_user).run(connection)
        return updated_user
    else:
        new_user = {
            "id": user_data["id"],
            **user_data,
            "current_thread_offset": offset or 0,
        }
        await users_table.insert(new_user).run(connection)
        return new_user


async def get_user_threads(connection, user_id: int, limit: int = 10, offset: int = 0) -> tuple[List[Dict], int]:
    threads_table = r.db(DB_NAME).table("threads")

    offset = int(offset)
    limit = int(limit)

    cursor = (
        await threads_table
        .filter({"user_id": user_id})
        .order_by(r.desc("created_at"))  # Сортировка по убыванию даты
        .slice(offset, offset + limit)
        .run(connection)
    )
    threads = cursor
    total_count = await threads_table.filter({"user_id": user_id}).count().run(connection)
    return threads, total_count



async def create_or_update_thread(
    connection, user_id: int, thread_id: Optional[int] = None, title: Optional[str] = None, set_active: bool = False
) -> Dict:
    threads_table = r.db(DB_NAME).table("threads")
    users_table = r.db(DB_NAME).table("users")

    if thread_id:
        thread = await threads_table.get(thread_id).run(connection)
        if not thread or thread["user_id"] != user_id:
            raise ValueError("Thread not found or not owned by user.")
        if title:
            thread["title"] = title
        await threads_table.get(thread_id).update(thread).run(connection)
    else:
        thread = {"user_id": user_id, "title": title}
        result = await threads_table.insert(thread, return_changes=True).run(connection)
        thread = result["changes"][0]["new_val"]

    if set_active:
        await users_table.get(user_id).update({"active_thread_id": thread["id"]}).run(connection)

    return thread


async def get_active_thread(connection, user_id: int) -> Optional[Dict]:
    users_table = r.db(DB_NAME).table("users")
    threads_table = r.db(DB_NAME).table("threads")

    user = await users_table.get(user_id).run(connection)
    if not user or not user.get("active_thread_id"):
        return None

    return await threads_table.get(user["active_thread_id"]).run(connection)


async def delete_thread(connection, thread_id: int):
    threads_table = r.db(DB_NAME).table("threads")
    messages_table = r.db(DB_NAME).table("messages")
    users_table = r.db(DB_NAME).table("users")

    thread = await threads_table.get(thread_id).run(connection)
    if not thread:
        raise ValueError("Thread not found.")

    await users_table.filter({"active_thread_id": thread_id}).update({"active_thread_id": None}).run(connection)
    await messages_table.filter({"thread_id": thread_id}).delete().run(connection)
    await threads_table.get(thread_id).delete().run(connection)


async def get_thread_by_id(connection, thread_id: int) -> Dict:
    threads_table = r.db(DB_NAME).table("threads")
    thread = await threads_table.get(thread_id).run(connection)
    if not thread:
        raise ValueError("Thread not found.")
    return thread


async def get_all_messages_by_thread_id(connection, thread_id: int) -> List[Dict]:
    messages_table = r.db(DB_NAME).table("messages")
    cursor = await messages_table.filter({"thread_id": thread_id}).order_by("created_at").run(connection)


    if isinstance(cursor, list):
        return cursor
    else:
        messages = []
        async for message in cursor:
            messages.append(message)
        return messages


async def add_message_to_thread(
    connection,
    thread_id: int,
    text: str,
    message_type: str,
    rating: Optional[str] = None,
) -> Dict:
    messages_table = r.db(DB_NAME).table("messages")
    message = {
        "thread_id": thread_id,
        "text": text,
        "message_type": message_type,
        "rating": rating,
        "created_at": r.now(),
    }
    result = await messages_table.insert(message, return_changes=True).run(connection)
    return result["changes"][0]["new_val"]


async def update_message(
    connection,
    message_id: int,
    text: Optional[str] = None,
    rating: Optional[str] = None,
) -> Dict:
    messages_table = r.db(DB_NAME).table("messages")
    message = await messages_table.get(message_id).run(connection)
    if not message:
        raise ValueError("Message not found.")

    if text is not None:
        message["text"] = text
    if rating is not None:
        message["rating"] = rating

    await messages_table.get(message_id).update(message).run(connection)
    return message


async def get_value(connection, key: str) -> Optional[str]:
    kv_table = r.db(DB_NAME).table("kv")
    kv_cursor = await kv_table.filter({"key": key}).run(connection)
    kv = await kv_cursor.next() if kv_cursor else None
    return kv["value"] if kv else None

async def set_value(connection, key: str, value: str):
    kv_table = r.db(DB_NAME).table("kv")
    existing_kv = await kv_table.get(key).run(connection)

    if existing_kv:
        await kv_table.get(key).update({"value": value}).run(connection)
    else:
        await kv_table.insert({"key": key, "value": value}).run(connection)


async def delete_value(connection, key: str):
    kv_table = r.db(DB_NAME).table("kv")
    await kv_table.get(key).delete().run(connection)


async def get_keys(connection) -> List[str]:
    kv_table = r.db(DB_NAME).table("kv")
    cursor = await kv_table.pluck("key").run(connection)
    keys = await cursor.to_list()
    return [item["key"] for item in keys]


async def get_kv_pairs(connection, keys: List[str]) -> Dict[str, Optional[str]]:
    kv_table = r.db(DB_NAME).table("kv")
    cursor = await kv_table.filter(lambda row: r.expr(keys).contains(row["key"])).run(connection)

    kv_list = []
    async for item in cursor:
        kv_list.append(item)

    result = {kv["key"]: kv.get("value") for kv in kv_list}

    return result


async def bulk_set_if_not_exists(connection, kv_dict: dict[str, str]) -> None:
    cursor = await r.db(RDB_DB).table("kv").filter(
        lambda doc: r.expr(list(kv_dict.keys())).contains(doc["key"])
    ).run(connection)


    existing_keys = set()
    async for entry in cursor:
        existing_keys.add(entry["key"])


    new_kv_entries = [
        {"id": key, "key": key, "value": str(value)}
        for key, value in kv_dict.items()
        if key not in existing_keys
    ]


    if new_kv_entries:
        await r.db(RDB_DB).table("kv").insert(new_kv_entries).run(connection)


