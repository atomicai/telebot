import os
import time
import uuid
from typing import Dict, List, Optional

from rethinkdb import r

from src.configuring.loggers import logger


class RethinkDocStore:
    def __init__(self, host: str = None, port: int = None, db: str = None):
        self.host = host or os.getenv("RETHINKDB_HOST")
        self.port = port or int(os.getenv("RETHINKDB_PORT", "28015"))
        self.db = db or os.getenv("RETHINKDB_DB")

        self.conn = None
        r.set_loop_type("asyncio")

    async def connect(self):
        """Установить соединение с RethinkDB"""
        self.conn = await r.connect(host=self.host, port=self.port, db=self.db)
        logger.info(f"Connected to RethinkDB at {self.host}:{self.port}, DB: {self.db}")

    async def close(self):
        """Закрыть соединение с RethinkDB"""
        if self.conn:
            await self.create_back_log(
                log_data="RethinkDB connection closed.",
                log_owner="RethinkDocStore.close",
            )
            await self.conn.close(noreply_wait=False)
            logger.info("RethinkDB connection closed.")

            self.conn = None

    async def on_startup_prepare_structure(self):
        """
        Инициализация БД и необходимых таблиц:
        - users
        - threads
        - messages
        - kv
        - pipeline
        - backlogs
        """
        async with await r.connect(host=self.host, port=self.port) as conn:
            logger.info("Initializing database and tables in RethinkDB.")

            db_list = await r.db_list().run(conn)
            if self.db not in db_list:
                await r.db_create(self.db).run(conn)

            tables = await r.db(self.db).table_list().run(conn)
            required_tables = [
                "users",
                "threads",
                "messages",
                "kv",
                "pipeline",
                "backlogs",
            ]
            for table in required_tables:
                if table not in tables:
                    await r.db(self.db).table_create(table).run(conn)
                await r.db(self.db).wait().run(conn)

            logger.info("Database and tables are ready.")

    async def create_pipeline_log(
        self,
        message_id: Optional[str] = None,
        log_data: Optional[str] = None,
        log_owner: Optional[str] = None,
        pipeline_version: str = "v1",
    ) -> None:
        """
        Запись лога в таблицу "pipeline" + запись в loguru-файл.
        PipelineLog используется для хранения информации,
        связанной с запросом к LLM или обработкой пайплайна.
        """
        pipeline_table = r.db(self.db).table("pipeline")

        log_id = str(uuid.uuid4())
        log_datatime = int(time.time() * 1000)

        log_record = {
            "log_id": log_id,
            "message_id": message_id,
            "log_data": log_data,
            "log_owner": log_owner,
            "log_datatime": log_datatime,
            "pipeline_version": pipeline_version,
        }

        await pipeline_table.insert(log_record).run(self.conn)
        logger.info(f"[PIPELINE] {log_owner}: {log_data}")

    async def create_back_log(
        self, log_data: Optional[str] = None, log_owner: Optional[str] = None
    ) -> None:
        """
        Запись лога в таблицу "backlogs" + запись в loguru-файл.
        BackLog используется для хранения вспомогательной и отладочной информации.
        """
        backlogs_table = r.db(self.db).table("backlogs")
        logger.info(backlogs_table)
        log_id = str(uuid.uuid4())
        log_datatime = int(time.time() * 1000)

        log_record = {
            "log_id": log_id,
            "log_data": log_data,
            "log_owner": log_owner,
            "log_datatime": log_datatime,
        }

        await backlogs_table.insert(log_record).run(self.conn)
        logger.info(f"[BACKLOG] {log_owner}: {log_data}")

    async def upsert_user(self, user_data: Dict, offset: Optional[int] = None) -> Dict:
        """
        Управление данными пользователя, включая создание или обновление данных пользователя, таких как текущий поток.
        """
        users_table = r.db(self.db).table("users")
        existing_user = await users_table.get(user_data["id"]).run(self.conn)

        if existing_user:
            updated_user = {**existing_user, **user_data}
            if offset is not None:
                updated_user["current_thread_offset"] = offset
            await users_table.get(user_data["id"]).update(updated_user).run(self.conn)

            logger.info(f"User {user_data['id']} data updated.")
            await self.create_back_log(
                log_data=f"User {user_data['id']} data updated.",
                log_owner="RethinkDocStore.upsert_user",
            )
            return updated_user
        else:
            new_user = {
                "id": user_data["id"],
                **user_data,
                "current_thread_offset": offset or 0,
            }
            await users_table.insert(new_user).run(self.conn)

            logger.info(f"User {user_data['id']} created.")
            await self.create_back_log(
                log_data=f"User {user_data['id']} created.",
                log_owner="RethinkDocStore.upsert_user",
            )
            return new_user

    async def get_user_threads(
        self, user_id: int, limit: int = 10, offset: int = 0
    ) -> tuple[List[Dict], int]:
        """
        Поддержка просмотра потоков для пользователя.
        """
        threads_table = r.db(self.db).table("threads")

        offset = int(offset)
        limit = int(limit)

        cursor = (
            await threads_table.filter({"user_id": user_id})
            .order_by(r.desc("created_at"))
            .slice(offset, offset + limit)
            .run(self.conn)
        )
        threads = cursor
        total_count = (
            await threads_table.filter({"user_id": user_id}).count().run(self.conn)
        )

        logger.info(
            f"Fetched {len(threads)} threads for user {user_id}, total threads={total_count}."
        )
        await self.create_back_log(
            log_data=f"Fetched {len(threads)} threads for user {user_id}, total threads={total_count}.",
            log_owner="RethinkDocStore.get_user_threads",
        )
        return threads, total_count

    async def create_or_update_thread(
        self,
        user_id: int,
        thread_id: Optional[int] = None,
        title: Optional[str] = None,
        set_active: bool = False,
    ) -> Dict:
        """
        Управление потоками пользователя, включая создание, обновление и выбор активного потока.
        """
        threads_table = r.db(self.db).table("threads")
        users_table = r.db(self.db).table("users")

        if thread_id:
            thread = await threads_table.get(thread_id).run(self.conn)
            if not thread or thread["user_id"] != user_id:
                logger.info(
                    f"Thread {thread_id} not found or not owned by user {user_id}."
                )
                await self.create_back_log(
                    log_data=f"Thread {thread_id} not found or not owned by user {user_id}.",
                    log_owner="RethinkDocStore.create_or_update_thread",
                )
                raise ValueError("Thread not found or not owned by user.")
            if title:
                thread["title"] = title
            await threads_table.get(thread_id).update(thread).run(self.conn)
        else:
            thread = {"user_id": user_id, "title": title}
            result = await threads_table.insert(thread, return_changes=True).run(
                self.conn
            )
            thread = result["changes"][0]["new_val"]

        if set_active:
            await (
                users_table.get(user_id)
                .update({"active_thread_id": thread["id"]})
                .run(self.conn)
            )

        logger.info(
            f"Thread {thread['id']} created/updated for user {user_id}. set_active={set_active}."
        )
        await self.create_back_log(
            log_data=f"Thread {thread['id']} created/updated for user {user_id}. set_active={set_active}.",
            log_owner="RethinkDocStore.create_or_update_thread",
        )
        return thread

    async def get_active_thread(self, user_id: int) -> Optional[Dict]:
        """
        Позволяет пользователю быстро перейти к своему активному потоку.
        """
        users_table = r.db(self.db).table("users")
        threads_table = r.db(self.db).table("threads")

        user = await users_table.get(user_id).run(self.conn)
        if not user or not user.get("active_thread_id"):
            logger.info(f"No active thread found for user {user_id}.")
            await self.create_back_log(
                log_data=f"No active thread found for user {user_id}.",
                log_owner="RethinkDocStore.get_active_thread",
            )
            return None

        thread = await threads_table.get(user["active_thread_id"]).run(self.conn)

        logger.info(f"Fetched active thread {thread['id']} for user {user_id}.")
        await self.create_back_log(
            log_data=f"Fetched active thread {thread['id']} for user {user_id}.",
            log_owner="RethinkDocStore.get_active_thread",
        )
        return thread

    async def delete_thread(self, thread_id: int):
        """
        Безопасное удаление потоков вместе с их контентом.
        """
        threads_table = r.db(self.db).table("threads")
        messages_table = r.db(self.db).table("messages")
        users_table = r.db(self.db).table("users")

        thread = await threads_table.get(thread_id).run(self.conn)
        if not thread:
            raise ValueError("Thread not found.")

        await (
            users_table.filter({"active_thread_id": thread_id})
            .update({"active_thread_id": None})
            .run(self.conn)
        )

        await messages_table.filter({"thread_id": thread_id}).delete().run(self.conn)

        await threads_table.get(thread_id).delete().run(self.conn)

        logger.info(f"Thread {thread_id} and all related messages have been deleted.")
        await self.create_back_log(
            log_data=f"Thread {thread_id} and all related messages have been deleted.",
            log_owner="RethinkDocStore.delete_thread",
        )

    async def get_thread_by_id(self, thread_id: int) -> Dict:
        """
        Позволяет пользователю или системе получать детальную информацию о потоке.
        """
        threads_table = r.db(self.db).table("threads")
        thread = await threads_table.get(thread_id).run(self.conn)
        if not thread:
            raise ValueError("Thread not found.")

        logger.info(f"Thread {thread_id} retrieved.")
        await self.create_back_log(
            log_data=f"Thread {thread_id} retrieved.",
            log_owner="RethinkDocStore.get_thread_by_id",
        )
        return thread

    async def get_all_messages_by_thread_id(self, thread_id: int) -> List[Dict]:
        """
        Обеспечивает доступ ко всем сообщениям в контексте конкретного потока.
        """
        messages_table = r.db(self.db).table("messages")
        cursor = (
            await messages_table.filter({"thread_id": thread_id})
            .order_by("created_at")
            .run(self.conn)
        )

        messages = []
        if isinstance(cursor, list):
            messages = cursor
        else:
            async for message in cursor:
                messages.append(message)

        logger.info(f"Fetched {len(messages)} messages for thread {thread_id}.")
        await self.create_back_log(
            log_data=f"Fetched {len(messages)} messages for thread {thread_id}.",
            log_owner="RethinkDocStore.get_all_messages_by_thread_id",
        )
        return messages

    async def add_message_to_thread(
        self,
        thread_id: int,
        text: str,
        message_type: str,
        rating: Optional[str] = None,
        message_topic: str = None,
        is_relevant_towards_context: str = None,
        parent_id: str = None,
    ) -> Dict:
        """
        Создание новых сообщений, связанных с потоком, для взаимодействия пользователей.
        """
        messages_table = r.db(self.db).table("messages")
        message = {
            "thread_id": thread_id,
            "text": text,
            "message_type": message_type,
            "rating": rating,
            "created_at": r.now(),
            "message_topic": message_topic,
            "parent_id": parent_id,
            "is_relevant_towards_context": is_relevant_towards_context,
        }
        result = await messages_table.insert(message, return_changes=True).run(
            self.conn
        )
        new_msg = result["changes"][0]["new_val"]

        logger.info(f"Message added to thread {thread_id}, type={message_type}")
        await self.create_back_log(
            log_data=f"Message added to thread {thread_id}, type={message_type}",
            log_owner="RethinkDocStore.add_message_to_thread",
        )
        return new_msg

    async def update_message(
        self,
        message_id: int,
        text: Optional[str] = None,
        rating: Optional[str] = None,
        message_topic: Optional[str] = None,
        is_relevant_towards_context: Optional[str] = None,
    ) -> Dict:
        """
        Позволяет редактировать ранее созданные сообщения.
        """
        messages_table = r.db(self.db).table("messages")
        message = await messages_table.get(message_id).run(self.conn)
        if not message:
            raise ValueError("Message not found.")

        if text is not None:
            message["text"] = text
        if rating is not None:
            message["rating"] = rating
        if message_topic is not None:
            message["message_topic"] = message_topic
        if is_relevant_towards_context is not None:
            message["is_relevant_towards_context"] = is_relevant_towards_context

        await messages_table.get(message_id).update(message).run(self.conn)

        logger.info(
            f"Message {message_id} updated (text={bool(text)}, rating={rating})"
        )
        await self.create_back_log(
            log_data=f"Message {message_id} updated (text={bool(text)}, rating={rating})",
            log_owner="RethinkDocStore.update_message",
        )
        return message

    async def get_value(self, key: str) -> Optional[str]:
        """
        Предоставляет доступ к конфигурационным или системным параметрам по ключу.
        """
        kv_table = r.db(self.db).table("kv")
        kv_cursor = await kv_table.filter({"key": key}).run(self.conn)
        kv = None
        try:
            kv = await kv_cursor.next()
        except StopAsyncIteration:
            pass

        value = kv["value"] if kv else None

        logger.info(f"Retrieved value for key={key}: {value}")
        await self.create_back_log(
            log_data=f"Retrieved value for key={key}: {value}",
            log_owner="RethinkDocStore.get_value",
        )
        return value

    async def set_value(self, key: str, value: str):
        """
        Позволяет задавать конфигурационные параметры или данные для хранения.
        """
        kv_table = r.db(self.db).table("kv")
        existing_kv = await kv_table.get(key).run(self.conn)

        if existing_kv:
            await kv_table.get(key).update({"value": value}).run(self.conn)
        else:
            await kv_table.insert({"key": key, "value": value}).run(self.conn)

        logger.info(f"Set KV value: key={key}, value={value}")
        await self.create_back_log(
            log_data=f"Set KV value: key={key}, value={value}",
            log_owner="RethinkDocStore.set_value",
        )

    async def delete_value(self, key: str):
        """
        Управляет очисткой конфигурационных данных.
        """
        kv_table = r.db(self.db).table("kv")
        await kv_table.get(key).delete().run(self.conn)

        logger.info(f"Deleted KV key: {key}")
        await self.create_back_log(
            log_data=f"Deleted KV key: {key}", log_owner="RethinkDocStore.delete_value"
        )

    async def get_keys(self) -> List[str]:
        """
        Предоставляет список доступных конфигурационных параметров.
        """
        kv_table = r.db(self.db).table("kv")
        cursor = await kv_table.pluck("key").run(self.conn)
        keys_list = await cursor.to_list()
        keys = [item["key"] for item in keys_list]

        logger.info(f"Fetched keys: {keys}")
        await self.create_back_log(
            log_data=f"Fetched keys: {keys}", log_owner="RethinkDocStore.get_keys"
        )
        return keys

    async def get_kv_pairs(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """
        Выборочное извлечение конфигурационных данных.
        """
        kv_table = r.db(self.db).table("kv")
        cursor = await kv_table.filter(
            lambda row: r.expr(keys).contains(row["key"])
        ).run(self.conn)

        kv_list = []
        async for item in cursor:
            kv_list.append(item)

        result = {kv["key"]: kv.get("value") for kv in kv_list}

        logger.info(f"Retrieved KV pairs for keys: {keys}")
        await self.create_back_log(
            log_data=f"Retrieved KV pairs for keys: {keys}",
            log_owner="RethinkDocStore.get_kv_pairs",
        )
        return result

    async def bulk_set_if_not_exists(self, kv_dict: dict[str, str]) -> None:
        """
        Массовое добавление данных без перезаписи существующих значений.
        """
        kv_table = r.db(self.db).table("kv")
        cursor = await kv_table.filter(
            lambda doc: r.expr(list(kv_dict.keys())).contains(doc["key"])
        ).run(self.conn)

        existing_keys = set()
        async for entry in cursor:
            existing_keys.add(entry["key"])

        new_kv_entries = [
            {"id": key, "key": key, "value": str(value)}
            for key, value in kv_dict.items()
            if key not in existing_keys
        ]

        if new_kv_entries:
            await kv_table.insert(new_kv_entries).run(self.conn)
            logger.info(
                f"Default bulk insert of KV without overwrite: {list(kv_dict.keys())}"
            )
            await self.create_back_log(
                log_data=f"Default bulk insert of KV without overwrite: {list(kv_dict.keys())}",
                log_owner="RethinkDocStore.bulk_set_if_not_exists",
            )
