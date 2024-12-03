import asyncio
from rethinkdb import r
from loguru import logger
import os


RDB_HOST = os.getenv("RETHINKDB_HOST")
RDB_PORT = os.getenv("RETHINKDB_PORT")
RDB_DB = os.getenv("RETHINKDB_DB")

async def init_db():
    async with await r.connect(host=os.getenv(RDB_HOST), port=RDB_PORT) as conn:
        logger.info("Setting up database and tables in RethinkDB.")
        # Create database if not exists
        db_list = await r.db_list().run(conn)
        if RDB_DB not in db_list:
            await r.db_create(RDB_DB).run(conn)

        # Create tables
        tables = await r.db(RDB_DB).table_list().run(conn)
        required_tables = ["users", "threads", "messages", "kv"]
        for table in required_tables:
            if table not in tables:
                await r.db(RDB_DB).table_create(table).run(conn)

        logger.info("Database and tables are set up.")