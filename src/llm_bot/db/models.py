from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
    Enum,
    func, CheckConstraint
)
from sqlalchemy.orm import relationship

from llm_bot.db.database import Base


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    is_premium = Column(Boolean, default=False, nullable=True)
    language_code = Column(String, nullable=True)
    active_thread_id = Column(Integer, ForeignKey('threads.id'), nullable=True)
    current_thread_offset = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    threads = relationship(
        'Thread',
        back_populates='user',
        cascade='all, delete-orphan',
        foreign_keys='Thread.user_id'
    )
    active_thread = relationship(
        'Thread',
        foreign_keys=[active_thread_id],
        uselist=False
    )


class Thread(Base):
    __tablename__ = 'threads'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    title = Column(String, nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship(
        'User',
        back_populates='threads',
        foreign_keys=[user_id]
    )
    messages = relationship(
        'Message',
        back_populates='thread',
        cascade='all, delete-orphan'
    )


class MessageTypeEnum(str, PyEnum):
    system = 'system'
    human = 'human'
    ai = 'ai'


class RatingEnum(str, PyEnum):
    like = 'like'
    dislike = 'dislike'


class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    thread_id = Column(Integer, ForeignKey('threads.id'))
    text = Column(Text)
    message_type = Column(Enum(MessageTypeEnum), nullable=False)
    rating = Column(Enum(RatingEnum), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    thread = relationship('Thread', back_populates='messages')

    __table_args__ = (
        CheckConstraint(
            "(message_type != 'ai' AND rating IS NULL) OR message_type = 'ai'",
            name="check_ai_rating_constraint"
        ),
    )


class KV(Base):
    __tablename__ = 'kv'

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
