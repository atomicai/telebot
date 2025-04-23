"""
Just A Rather Very Intelligent System
"""

import json_repair
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger

from src.etc.schema import MessageTypeEnum
from src.running.prompts import (
    RESPONSEFareWellPromptRunner,
    RESPONSEStreamingPromptRunner,
    RESPONSEWithSearchOrNotPromptRunner,
)
from src.running.reqs import APIRunner


class JarvisCallbackHandler(AsyncCallbackHandler):
    def __init__(self, typing_interval: int = 5):
        self.response = None
        self.state = {}
        self.accumulated_text = []
        self.tokens_received = 0
        self.typing_interval = typing_interval

    async def on_llm_new_token(self, token: str, run_id, **kwargs) -> None:
        self.accumulated_text.append(token)
        self.tokens_received += 1
        if self.tokens_received >= self.typing_interval:
            chunk = self.accumulated_text[-self.tokens_received :]
            logger.info(
                f"{self.__class__.__name__} | on_llm_new_token | run_id=[{run_id}] | chunk=[{chunk}]"
            )
            self.tokens_received = 0

    async def on_llm_end(self, response, run_id, **kwargs):
        self.response = response.generations[0][0].text
        logger.info(
            f"{self.__class__.__name__} | on_llm_end | run_id=[{run_id}] | response=[{self.response}]"
        )


class JARVISRunner:
    def __init__(
        self,
        se_runner: RESPONSEWithSearchOrNotPromptRunner,
        fa_runner: RESPONSEFareWellPromptRunner,
        re_runner: RESPONSEStreamingPromptRunner,
        top_k_messages: int = 5,
        collection_name: str = "ZAKUPKI",
        top_k: int = 3,
        search_by: str = "hybrid",
        alpha: float = 0.8,
        SEARCH_URL: str = "https://4ylja2qff6qv.share.zrok.io",
    ):
        self.state = {}
        self.se_runner = se_runner  # step1
        self.fa_runner = fa_runner  # step2 (a)
        self.re_runner = re_runner  # step2 (b)

        self.top_k_messages = top_k_messages
        self.collection_name = collection_name
        self.top_k = top_k
        self.search_by = search_by
        self.alpha = alpha
        self.SEARCH_URL = SEARCH_URL
        self.api = APIRunner(connect=3, backoff_factor=0.5)

    async def arun(self, query: str, db_messages: list | None = None):
        """
        :param: query - user's query
        :param: messages - The list of previous user's queries
        """
        '{\n  "answer": "GREETINGS",\n  "is_relevant_towards_context": false\n}'
        messages = []
        for message in db_messages:
            if message["message_type"] == MessageTypeEnum.human.value:
                messages.append(HumanMessage(content=message["text"]))
            elif message["message_type"] == MessageTypeEnum.ai.value:
                messages.append(AIMessage(content=message["text"]))
        async with self.api as api:
            search_results = await api.SEARCH(
                queries=[query],
                host=self.SEARCH_URL,
                collection_name=self.collection_name,
                top_k=self.top_k,
                alpha=self.alpha,
                search_by=self.search_by,
                as_knowledge_base=True,
            )

        js_se_response = dict(answer="GREETINGS", is_relevant_towards_context=False)
        se_response = await self.se_runner.arun(query=query, content=search_results)
        try:
            parsed_se_response = json_repair.loads(se_response)
        except:
            logger.error(
                f"{self.se_runner.__class__.__name__} | error parsing for the query=[{query}]"
            )
        else:
            js_se_response.update(parsed_se_response)

        if js_se_response["is_relevant_towards_context"]:
            response = await self.re_runner.arun(
                query=query, content=search_results, messages=messages
            )
        else:
            response = await self.fa_runner.arun(query=query)
        return response
