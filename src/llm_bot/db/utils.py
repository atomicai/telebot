from contextlib import asynccontextmanager
from rethinkdb import r
from llm_bot.db.database import RDB_HOST, RDB_PORT, RDB_DB



r.set_loop_type('asyncio')


@asynccontextmanager
async def rethinkdb_connection():
    """Асинхронный контекстный менеджер для подключения к RethinkDB."""
    connection = await r.connect(host=RDB_HOST, port=RDB_PORT, db=RDB_DB)
    try:
        yield connection
    finally:
        await connection.close(noreply_wait=False)


async def setup_rethinkdb():
    """Инициализация базы данных и таблиц в RethinkDB."""
    async with await r.connect(host=RDB_HOST, port=RDB_PORT) as connection:
        # Проверяем наличие базы данных
        if RDB_DB not in await r.db_list().run(connection):
            await r.db_create(RDB_DB).run(connection)

        # Проверяем наличие таблиц
        required_tables = ["users", "threads", "messages", "kv"]
        existing_tables = await r.db(RDB_DB).table_list().run(connection)
        for table in required_tables:
            if table not in existing_tables:
                await r.db(RDB_DB).table_create(table).run(connection)