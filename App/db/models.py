from sqlalchemy import Column, ForeignKey
from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import Text, Boolean, DateTime
from sqlalchemy.orm import relationship

from datetime import datetime

from database import Base


class Users(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    topic = Column(Text)
    context_counter = Column(Integer, default=0)

    answers = relationship('Answers', back_populates='users', cascade="all, delete-orphan")



class Answers(Base):
    __tablename__ = "answers"


    chat_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    first_message = Column(Text, nullable=False)
    user_answers = Column(Text)
    bot_response = Column(Text)
    response_status = Column(Boolean)
    timestamp = Column(DateTime, default=datetime.utcnow)


    users = relationship('Users', back_populates='answers')