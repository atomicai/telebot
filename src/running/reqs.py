import asyncio as asio

import aiohttp
import simplejson as json
from loguru import logger
from more_itertools import chunked
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm

from src.etc.schema import Document
from src.tooling.coro import _limit_concurrency


class APIRunner:
    def __init__(self, connect: int = 3, backoff_factor: float = 0.5):
        self.connect = connect
        self.backoff_factor = backoff_factor
        self.session: aiohttp.ClientSession | None = None
        self._own_session = False

    def _prepare_for_request(self, host, port, route):
        return f"{host}:{str(port)}/{route}" if port is not None else f"{host}/{route}"

    @retry(
        stop=stop_after_attempt(3),  # пример: не более 3 попыток
        wait=wait_exponential(
            multiplier=0.5
        ),  # экспоненциальная задержка (0.5, 1, 2, ...)
        retry=retry_if_exception_type(
            aiohttp.ClientError
        ),  # повторяем при сетевых ошибках
        reraise=True,
    )
    async def _post_with_retry(
        self, url: str, json_data: dict | None = None, headers: dict | None = None
    ) -> dict:
        """
        Общий метод POST с ретраями.
        Возвращает JSON, если запрос завершился без ошибок.
        """
        if not self.session:
            raise RuntimeError(
                "Session is not initialized. Use 'async with APIRunner()' context."
            )

        async with self.session.post(
            url, data=json.dumps(json_data), headers=headers
        ) as response:
            # Если статус != 2xx, выбрасываем исключение для retrу
            response.raise_for_status()
            return await response.json(content_type=None)

    async def __aenter__(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            self._own_session = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._own_session and self.session and not self.session.closed:
            await self.session.close()
            self.session = None
            self._own_session = False

    async def INDEX(
        self,
        js_docs,
        host: str,
        port: int = None,
        route: str = "indexing",
        headers: dict = None,
        batch_size: int = 16,
        **props,
    ):
        headers = {"content-type": "application/json"} if headers is None else headers
        logger.info(props)
        api = self._prepare_for_request(host=host, port=port, route=route)
        count_done_docs: int = 0
        answers = []
        for batch_idx, js_batch_docs in enumerate(
            tqdm(chunked(js_docs, n=batch_size), desc="INDEX")
        ):
            _js_docs = [
                Document.from_dict(js_doc).to_dict(uuid_to_str=True)
                for js_doc in js_batch_docs
            ]
            props["dataset_name_or_docs"] = _js_docs
            data = await self._post_with_retry(api, json_data=props, headers=None)
            answers.append(data)

            count_done_docs += len(js_batch_docs)

            logger.info(f"/{route.upper()} | {count_done_docs} - {len(js_docs)}")
        return answers

    async def SEARCH(
        self,
        queries: str | list[str],
        host: str,
        port: int = None,
        route: str = "searching",
        headers: dict = None,
        batch_size: int = 16,
        as_knowledge_base: bool = False,
        **props,
    ):
        headers = {"content-type": "application/json"} if headers is None else headers
        api = self._prepare_for_request(host=host, port=port, route=route)
        count_queries_done: int = 0
        js_queries = [queries] if isinstance(queries, str) else queries
        answers = []
        for batch_idx, js_batch_queries in enumerate(
            tqdm(chunked(js_queries, n=batch_size))
        ):
            for js_raw_text in js_batch_queries:
                props["text"] = js_raw_text
                data = await self._post_with_retry(api, json_data=props, headers=None)
                answers.append(data)

            count_queries_done += len(js_batch_queries)

            logger.info(
                f"/{route.upper()} | `count_queries_done`=[{count_queries_done}] | `count_queries`=[{len(js_queries)}]"
            )
        if as_knowledge_base:
            answers = "\n".join(
                f"PARAGRAPH {i + 1}: {doc['content']}"
                for answer in answers
                for i, doc in enumerate(answer["docs"])
            )

        return answers

    async def SEARCH_WITH_BATCH(
        self,
        queries: str | list[str],
        host: str,
        port: int = None,
        route: str = "searching",
        headers: dict = None,
        batch_size: int = 16,
        max_coros_size: int = 5,
        **props,
    ):
        headers = {"content-type": "application/json"} if headers is None else headers
        api = self._prepare_for_request(host=host, port=port, route=route)
        count_queries_done: int = 0
        js_queries = [queries] if isinstance(queries, str) else queries
        answers = []
        for batch_idx, js_batch_queries in enumerate(
            tqdm(chunked(js_queries, n=batch_size))
        ):
            runners = [
                asio.create_task(
                    self._post_with_retry(
                        api, json_data=props.update({"text": js_raw_text}), headers=None
                    )
                )
                for js_raw_text in js_batch_queries
            ]
            cur_result = await asio.gather(
                *_limit_concurrency(runners, concurrency=max_coros_size)
            )

            answers.extend(cur_result)

            count_queries_done += len(js_batch_queries)

            logger.info(
                f"/{route.upper()} | `count_queries_done`=[{count_queries_done}] | `count_queries`=[{len(js_queries)}]"
            )
        return answers

    async def DELETE(self, host: str, port: int = None, route: str = "delete", **props):
        api = self._prepare_for_request(host=host, port=port, route=route)
        body = dict(json=props)
        response = self.session.post(api, **body)

        return response

    async def FIND(self, host: str, port: int = None, route: str = "find", **props):
        api = self._prepare_for_request(host=host, port=port, route=route)
        response = await self._post_with_retry(api, json_data=props)

        return response

    async def FINDBYIDS(
        self, host: str, port: int = None, route: str = "findbyids", **props
    ):
        api = self._prepare_for_request(host=host, port=port, route=route)
        response = await self._post_with_retry(api, json_data=props)

        return response
