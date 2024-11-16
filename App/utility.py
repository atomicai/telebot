from sqlalchemy.orm import Session
from sqlalchemy import exists, desc

from App.db.models import Users, Answers


async def check_user_in_db(db: Session, user_id: int):
    """
    Проверяет, существует ли пользователь
    """
    return db.query(exists().where(Users.user_id == user_id)).scalar()


def get_last_user_messages(db: Session, user_id: int, limit: int):
    """
    получаем послендие сообщения пользователя
    """
    user_messages = (
        db.query(Answers)
        .join(Users, Answers.chat_id == Users.user_id)
        .filter(Users.user_id == user_id)
        .filter(Answers.user_answers.isnot(None))
        .order_by(desc(Answers.timestamp))
        .limit(limit/2)
        .all()
    )

    return user_messages

def get_last_bot_messages(db: Session, user_id: int, limit: int):
    """
        получаем послендие сообщения бота
    """
    bot_responses = (
        db.query(Answers)
        .join(Users, Answers.chat_id == Users.user_id)
        .filter(Users.user_id == user_id)
        .filter(Answers.chat_response.isnot(None))
        .order_by(desc(Answers.timestamp))
        .limit(limit / 2)
        .all()
    )

    return bot_responses