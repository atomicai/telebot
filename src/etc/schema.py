from datetime import datetime
from enum import Enum
from typing import Any

import mmh3
import numpy as np
import polars as pl
import simplejson

from src.etc.format import maybe_cast_to_str


class MessageTopicEnum(Enum):
    greetings = "GREETINGS"
    search = "SEARCH"
    lechat = "LECHAT"


class MessageRelevanceEnum(Enum):
    is_relevant_towards_context = "is_relevant_towards_context"


class MessageTypeEnum(Enum):
    system = "system"
    human = "human"
    ai = "ai"


class RatingEnum(Enum):
    like = "like"
    dislike = "dislike"


class User:
    """Модель пользователя."""

    def __init__(
        self,
        id: int,
        first_name: str,
        last_name: str = None,
        username: str = None,
        is_premium: bool = False,
        language_code: str = None,
        active_thread_id: int = None,
        current_thread_offset: int = 0,
    ):
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

    def __init__(
        self,
        id: int,
        thread_id: int,
        text: str,
        message_type: MessageTypeEnum,
        rating: RatingEnum = None,
    ):
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
        pipeline_version: str | None = None,
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
        log_datatime: int | None = None,
    ):
        self.log_id = log_id
        self.log_data = log_data
        self.log_owner = log_owner
        self.log_datatime = log_datatime


class Document:
    id: str
    content: str | pl.DataFrame
    content_type: str = ("text",)
    dataframe: str | None = None
    keywords: list[str] | None = None
    meta: dict[str, Any] = (None,)
    score: float | None = None
    embedding: np.ndarray | None = None
    id_hash_keys: list[str] | None = None

    # We use a custom init here as we want some custom logic. The annotations above are however still needed in order
    # to use some dataclass magic like "asdict()". See https://www.python.org/dev/peps/pep-0557/#custom-init-method
    # They also help in annotating which object attributes will always be present (e.g. "id") even though they
    # don't need to passed by the user in init and are rather initialized automatically in the init
    def __init__(
        self,
        content: str | pl.DataFrame,
        content_type: str = "text",
        dataframe: str | None = None,
        keywords: list[str] | None = None,
        id: str | None = None,
        score: float | None = None,
        meta: dict[str, Any] | None = None,
        embedding: np.ndarray | None = None,
        id_hash_keys: list[str] | None = None,
    ):
        """
        One of the core data classes in Haystack. It's used to represent documents / passages in a standardized way within Haystack.
        Documents are stored in DocumentStores, are returned by Retrievers, are the input for Readers and are used in
        many other places that manipulate or interact with document-level data.
        Note: There can be multiple Documents originating from one file (e.g. PDF), if you split the text
        into smaller passages. We'll have one Document per passage in this case.
        Each document has a unique ID. This can be supplied by the user or generated automatically.
        It's particularly helpful for handling of duplicates and referencing documents in other objects (e.g. Labels)
        There's an easy option to convert from/to dicts via `from_dict()` and `to_dict`.
        :param content: Content of the document. For most cases, this will be text, but it can be a table or image.
        :param content_type: One of "text", "table", "image" or "audio". Haystack components can use this to adjust their
                             handling of Documents and check compatibility.
        :param id: Unique ID for the document. If not supplied by the user, we'll generate one automatically by
                   creating a hash from the supplied text. This behaviour can be further adjusted by `id_hash_keys`.
        :param score: The relevance score of the Document determined by a model (e.g. Retriever or Re-Ranker).
                      If model's `scale_score` was set to True (default) score is in the unit interval (range of [0,1]), where 1 means extremely relevant.
        :param meta: Meta fields for a document like name, url, or author in the form of a custom dict (any keys and values allowed).
        :param embedding: Vector encoding of the text
        :param id_hash_keys: Generate the document id from a custom list of strings that refere to the documents attributes.
                             If you want ensure you don't have duplicate documents in your DocumentStore but texts are
                             not unique, you can modify the metadata and pass e.g. "meta" to this field (e.g. ["content", "meta"]).
                             In this case the id will be generated by using the content and the defined metadata.
        """  # noqa: E501

        if content is None:
            raise ValueError(
                "Can't create 'Document': Mandatory 'content' field is None"
            )

        self.content = content
        self.content_type = content_type
        self.dataframe = dataframe
        self.keywords = keywords
        self.score = score
        self.meta = meta or {}

        allowed_hash_key_attributes = [
            "content",
            "content_type",
            "dataframe",
            "keywords",
            "score",
            "meta",
            "embedding",
        ]

        if id_hash_keys is not None:  # noqa: SIM102
            if not set(id_hash_keys) <= set(allowed_hash_key_attributes):  # type: ignore
                raise ValueError(
                    f"You passed custom strings {id_hash_keys} to id_hash_keys which is deprecated. Supply instead a list"
                    f" of Document's attribute names that the id should be based on (e.g. {allowed_hash_key_attributes})."
                    " See https://github.com/deepset-ai/haystack/pull/1910 for details)"
                )

        # if embedding is not None:
        #     embedding = np.asarray(embedding)
        self.embedding = embedding

        # Create a unique ID (either new one, or one from user input)
        if id is not None:
            self.id: str = str(id)
        else:
            self.id: str = self._get_id(id_hash_keys=id_hash_keys)

    def _get_id(self, id_hash_keys: list[str] | None = None):
        """
        Generate the id of a document by creating the hash of strings. By default the content of a document is
        used to generate the hash. There are two ways of modifying the generated id of a document. Either static keys
        or a selection of the content.
        :param id_hash_keys: Optional list of fields that should be dynamically used to generate the hash.
        """

        if id_hash_keys is None:
            return f"{mmh3.hash128(str(self.content), signed=False):02x}"

        final_hash_key = ""
        for attr in id_hash_keys:
            final_hash_key += ":" + str(getattr(self, attr))

        if final_hash_key == "":
            raise ValueError(
                "Cant't create 'Document': 'id_hash_keys' must contain at least one of ['content', 'meta']"
            )

        return f"{mmh3.hash128(final_hash_key, signed=False):02x}"

    def to_dict(self, field_map={}, uuid_to_str: bool = False) -> dict:  # noqa: B006
        """
        Convert Document to dict. An optional field_map can be supplied to change the names of the keys in the
        resulting dict. This way you can work with standardized Document objects in Haystack, but adjust the format that
        they are serialized / stored in other places (e.g. elasticsearch)
        Example:
        | doc = Document(content="some text", content_type="text")
        | doc.to_dict(field_map={"custom_content_field": "content"})
        | >>> {"custom_content_field": "some text", content_type": "text"}
        :param field_map: Dict with keys being the custom target keys and values being the standard Document attributes
        :return: dict with content of the Document
        """
        inv_field_map = {v: k for k, v in field_map.items()}
        _doc: dict[str, str] = {}
        for k, v in self.__dict__.items():
            # Exclude internal fields (Pydantic, ...) fields from the conversion process
            if k.startswith("__"):
                continue
            if k == "content":  # noqa: SIM102
                # Convert pd.DataFrame to list of rows for serialization
                if self.content_type == "table" and isinstance(
                    self.content, pl.DataFrame
                ):
                    v = [self.content.columns.tolist()] + self.content.values.tolist()
            k = k if k not in inv_field_map else inv_field_map[k]  # noqa: SIM401
            _doc[k] = v
        if uuid_to_str:
            return maybe_cast_to_str(_doc, uuid_to_str=True)
        return _doc

    @classmethod
    def from_dict(
        cls,
        dict: dict[str, Any],
        field_map: dict[str, Any] = {},  # noqa: B006
        id_hash_keys: list[str] | None = None,
    ):
        """
        Create Document from dict. An optional field_map can be supplied to adjust for custom names of the keys in the
        input dict. This way you can work with standardized Document objects in Haystack, but adjust the format that
        they are serialized / stored in other places (e.g. elasticsearch)
        Example:
        | my_dict = {"custom_content_field": "some text", content_type": "text"}
        | Document.from_dict(my_dict, field_map={"custom_content_field": "content"})
        :param field_map: Dict with keys being the custom target keys and values being the standard Document attributes
        :return: dict with content of the Document
        """

        _doc = dict.copy()
        init_args = [
            "content",
            "content_type",
            "dataframe",
            "keywords",
            "id",
            "score",
            "question",
            "meta",
            "embedding",
        ]
        if "meta" not in _doc.keys():  # noqa: SIM118
            _doc["meta"] = {}
        # copy additional fields into "meta"
        for k, v in _doc.items():
            # Exclude internal fields (Pydantic, ...) fields from the conversion process
            if k.startswith("__"):
                continue
            if k not in init_args and k not in field_map:
                _doc["meta"][k] = v
        # remove additional fields from top level
        _new_doc = {}
        for k, v in _doc.items():
            if k in init_args:
                _new_doc[k] = v
            elif k in field_map:
                k = field_map[k]
                _new_doc[k] = v

        if _doc.get("id") is None:
            _new_doc["id_hash_keys"] = id_hash_keys

        # Convert list of rows to pd.DataFrame
        if _new_doc.get("content_type") == "table" and isinstance(
            _new_doc["content"], list
        ):
            _new_doc["content"] = pl.DataFrame(
                columns=_new_doc["content"][0], data=_new_doc["content"][1:]
            )

        return cls(**_new_doc)

    def to_json(self, field_map={}) -> str:  # noqa: B006
        d = self.to_dict(field_map=field_map)
        j = simplejson.dumps(d, cls=np.NumpyEncoder)
        return j

    @classmethod
    def from_json(cls, data: str, field_map={}):  # noqa: B006
        d = simplejson.loads(data)
        return cls.from_dict(d, field_map=field_map)

    def __eq__(self, other):
        return (
            isinstance(other, self.__class__)
            and getattr(other, "content", None) == self.content
            and getattr(other, "content_type", None) == self.content_type
            and getattr(other, "dataframe", None) == self.dataframe
            and getattr(other, "keywords", None) == self.keywords
            and getattr(other, "id", None) == self.id
            and getattr(other, "score", None) == self.score
            and getattr(other, "meta", None) == self.meta
            and np.array_equal(getattr(other, "embedding", None), self.embedding)
        )

    def __repr__(self):
        doc_dict = self.to_dict()
        embedding = doc_dict.get("embedding", None)
        if embedding is not None:
            doc_dict["embedding"] = (
                f"<embedding of shape {getattr(embedding, 'shape', '[no shape]')}>"
            )
        return f"<Document: {str(doc_dict)}>"

    def __str__(self):
        # In some cases, self.content is None (therefore not subscriptable)
        if self.content is None:
            return f"<Document: id={self.id}, content=None>"
        return f"<Document: id={self.id}, content='{self.content[:100]}{'...' if len(self.content) > 100 else ''}'>"

    def __lt__(self, other):
        """Enable sorting of Documents by score"""
        return self.score < other.score
