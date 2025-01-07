from enum import Enum
from datetime import datetime

class MessageTypeEnum(Enum):
    system = "system"
    human = "human"
    ai = "ai"


class RatingEnum(Enum):
    like = "like"
    dislike = "dislike"


class User:
    """Модель пользователя."""
    def __init__(self, id: int, first_name: str, last_name: str = None, username: str = None,
                 is_premium: bool = False, language_code: str = None, active_thread_id: int = None,
                 current_thread_offset: int = 0):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.username = username
        self.is_premium = is_premium
        self.language_code = language_code
        self.active_thread_id = active_thread_id
        self.current_thread_offset = current_thread_offset
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class Thread:
    """Модель потока (чата)."""
    def __init__(self, id: int, user_id: int, title: str):
        self.id = id
        self.user_id = user_id
        self.title = title
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class Message:
    """Модель сообщения."""
    def __init__(self, id: int, thread_id: int, text: str, message_type: MessageTypeEnum, rating: RatingEnum = None):
        self.id = id
        self.thread_id = thread_id
        self.text = text
        self.message_type = message_type
        self.rating = rating
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


class KV:
    """Модель для KV-хранилища."""
    def __init__(self, key: str, value: str = None):
        self.key = key
        self.value = value


class PipelineLog:
    """Модель лога для операций, связанных непосредственно с пайплайном LLM."""
    def __init__(
        self,
        message_id: str | None = None,
        log_id: str | None = None,
        log_data: str | None = None,
        log_owner: str | None = None,
        log_datatime: int | None = None,
        pipeline_version: str | None = None
    ):
        self.message_id = message_id
        self.log_id = log_id
        self.log_data = log_data
        self.log_owner = log_owner
        self.log_datatime = log_datatime
        self.pipeline_version = pipeline_version

class BackLog:
    """Модель лога для всех вспомогательных действий (BD-операции, нажатия кнопок, ошибки и т.д.)."""
    def __init__(
        self,
        log_id: str | None = None,
        log_data: str | None = None,
        log_owner: str | None = None,
        log_datatime: int | None = None
    ):
        self.log_id = log_id
        self.log_data = log_data
        self.log_owner = log_owner
        self.log_datatime = log_datatime