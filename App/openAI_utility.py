import asyncio
from os.path import exists

import openai
import os

from requests import Session

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY





async def openai_response(topic: str):
    response = await openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        message=[
            {"role": "system", "content": "You are an expert on universes from books, movies, games and law. Answer in JSON format."},
            {"role": "user", "content": f"{topic}"}
        ]
    )
    generated_text = response.choices[0].message["content"].strip()

    return generated_text


