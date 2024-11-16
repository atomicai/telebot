from pydoc import describe

import requests
import json_repair
import json
import os

from requests import session

from utility import check_user_in_db, get_last_user_messages, get_last_bot_messages

from db.database import AsyncSessionLocal
from db.models import Users, Answers

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from openAI_utility import openai_response

CORE_URL = "https://b3r0a7f3dl4l.share.zrok.io" # - это для GPN на порт 1228 llama3.1 70b q4

CHAT_URL = f"{CORE_URL}/v1/chat/completions"

headers = {"Content-Type": "application/json"}

stream: bool = False



context_chat_id = None
MESSAGE, GENDER = range(2)



keyboard = [["\U0001F44D", "\U0001F44E", "\U0001F4A3"]]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:

    await update.message.reply_text(
        "Hi! I can answer any question you have",

    )


async def user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:

    """делает вид типо думает пока ждет ответа"""
    await update.message.reply_text(
        'Let me think...'
    )

    """добавляет id юзера в переменную и потом проверяет, существует ли он"""
    user_id = update.message.from_user.id
    user_check = check_user_in_db(AsyncSessionLocal, user_id)

    """если не сущесвутет, то создает добавляет юзера, так же вопрос и ответ в бд"""
    if not user_check:
        async with AsyncSessionLocal() as session:

            user_id = update.message.from_user.id
            first_message = update.message.text
            user_message = update.message.text

            user = Users(user_id=user_id, topic=user_message, context_counter=2)
            session.add(user)
            session.commit()

            data = {
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": 'You are an expert on universes from books, movies, games and law. Answer in JSON format. Also you need to write answer in "description" key',
                    },
                    {
                        "role": "user",
                        "content": f'{user_message}',
                    }
                ],
                "temperature": 0.0,
                "max_tokens": 4096
            }

            response = requests.post(CHAT_URL, headers=headers, data=json.dumps(data), timeout=120)
            js_response = response.json()

            json_answer = json_repair.loads(js_response['choices'][0]['message']['content'])
            bot_response = json_answer['desciption']

            answers = Answers(first_message=first_message, user_answers=user_message, bot_response=bot_response)

            session.add(answers)
            session.commit()

            await update.message.reply_text(
                bot_response, reply_markup="""добавляет маркап, для оценки ответа(пока не доделал)"""
            )


    elif user_check:
        async with AsyncSessionLocal() as session:

            context_counter = session.query(Users).filter(Users.user_id == user_id)


            if context_counter == 0:
                """если счетчик равен нулю, то просто сохраняется вопрос и ответ в бд и меняется счетчик"""
            elif context_counter < 10:
                user_last_messages = get_last_user_messages(session, user_id, context_counter)
                bot_last_messages = get_last_bot_messages(session, user_id, context_counter)


                data = {
                    "stream": False,
                    "messages": [
                        {
                            "role": "system",
                            "content": 'You are an expert on universes from books, movies, games and law. Answer in JSON format. Also you need to write answer in "description" key',
                        },
                        {
                            "role": "user",
                            "content": f'{update.message.text}',
                        }
                    ],
                    "temperature": 0.0,
                    "max_tokens": 4096
                }

                response = requests.post(CHAT_URL, headers=headers, data=json.dumps(data), timeout=120)
                js_response = response.json()

                json_answer = json_repair.loads(js_response['choices'][0]['message']['content'])
                bot_answer = json_answer['desciption']

                await update.message.reply_text(
                    bot_answer, reply_markup="""добавляет маркап, для оценки ответа(пока не доделал)"""
                )
            else:
                """логика, если окно контекста уже 10"""


async def buttons_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_response = update.message.text
    if user_response == "\U0001F44D":
        await update.message.reply_text("answer status add in database ")
    elif user_response == "\U0001F44E":
        await update.message.reply_text("answer status add in database")
    elif user_response == "\U0001F4A3":
        await update.message.reply_text("This button do nothing!")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """логика завершения диалога и сброса счетчика"""


def main() -> None:
    """Run the bot."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(f"{bot_token}").build()

    # Add conversation handler with the states GENDER, PHOTO, LOCATION and BIO
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons_response))


    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)



if __name__ == "__main__":
    main()