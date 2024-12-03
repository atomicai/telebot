import asyncio

from langchain_core.callbacks import AsyncCallbackHandler
from loguru import logger
from telegram.constants import ChatAction
from telegram.error import BadRequest

from src.api.utils import suppress_and_log


class TelegramChatter(AsyncCallbackHandler):
    def __init__(self, message, bot=None, chat_id=None, edit_interval=1, initial_token_threshold=1, typing_interval=5):
        self.bot = bot
        self.chat_id = chat_id
        self.original_message = message

        self.edit_interval = edit_interval
        self.first_token_threshold = initial_token_threshold
        self.typing_interval = typing_interval

        self.message = None
        self.tokens_received = 0
        self.accumulated_text = []
        self.last_accumulated_text = ''
        self.done_event = asyncio.Event()
        self.edit_task = asyncio.create_task(self._edit_message_periodically())
        self.typing_task = asyncio.create_task(self._send_typing_action_periodically())

    @suppress_and_log(Exception)
    async def _send_typing_action(self):
        if self.bot and self.chat_id:
            logger.info("Sending typing action")
            await self.bot.send_chat_action(chat_id=self.chat_id, action=ChatAction.TYPING)

    @suppress_and_log(BadRequest)
    async def _send_or_edit_message(self):
        if not self.accumulated_text:
            return
        accumulated_text = "".join(self.accumulated_text)
        if not accumulated_text.strip():
            return
        if self.message is None:
            logger.info("Sending message")
            self.message = await self.original_message.reply_text(accumulated_text)
            self.last_accumulated_text = accumulated_text
        else:
            if accumulated_text != self.last_accumulated_text:
                logger.info("Editing message")
                await self.message.edit_text(accumulated_text)
                self.last_accumulated_text = accumulated_text

    async def _edit_message_periodically(self):
        logger.info("Starting message editing task")
        while not self.done_event.is_set():
            await self._send_or_edit_message()
            await asyncio.sleep(self.edit_interval)
        await self._send_or_edit_message()

    async def _send_typing_action_periodically(self):
        logger.info("Starting typing action task")
        while not self.done_event.is_set() and self.tokens_received < self.first_token_threshold:
            await self._send_typing_action()
            await asyncio.sleep(self.typing_interval)

    async def on_llm_new_token(self, token: str, **kwargs):
        self.accumulated_text.append(token)
        self.tokens_received += 1

        if self.tokens_received >= self.first_token_threshold and self.message is None:
            await self._send_or_edit_message()

    async def on_llm_end(self, response, **kwargs):
        logger.info(f"LLM has finished generating tokens {response}")
        # Signal that LLM has finished generating tokens
        self.done_event.set()
        # Wait for background tasks to finish final updates
        await self.edit_task
        # if self.typing_task:
        #     await self.typing_task
