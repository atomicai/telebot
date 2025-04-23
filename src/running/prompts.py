import abc
import json
from typing import Any, AsyncIterator, Dict, Iterator

import json_repair
from langchain_core.callbacks import AsyncCallbackManager
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


class IPromptRunner(abc.ABC):
    def __init__(self, system_prompt: str, llm: ChatOpenAI = None):
        self.system_prompt = system_prompt
        self.llm = llm

    @abc.abstractmethod
    def _prepare(self, user_text: str, **props) -> str:
        pass

    def prompt(self, system_prompt: str = None, **props) -> list[dict]:
        obj = self._prepare(**props)
        system_prompt = system_prompt or self.system_prompt
        return [
            dict(role="system", content=self.system_prompt),
            dict(role="user", content=obj),
        ]

    async def arun(self, messages: list[BaseMessage] | None = None, **kwargs) -> str:
        prompt = self._prepare(**kwargs)
        messages = (
            [SystemMessage(self.system_prompt)]
            + messages
            + [HumanMessage(content=prompt)]
            if messages is not None
            else [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=prompt),
            ]
        )
        resp = await self.llm.agenerate(messages=[messages])
        return resp.generations[0][0].text

    async def astream(self, **kwargs) -> AsyncIterator[str]:
        prompt = self._prepare(**kwargs)
        async for chunk in self.llm.astream(
            messages=[
                [
                    SystemMessage(content=self.system_prompt),
                    HumanMessage(content=prompt),
                ]
            ]
        ):
            yield chunk

    @abc.abstractmethod
    def finalize(self, user_text: str, raw_response: str, **props) -> str:
        pass


class AIBasePrompt(IPromptRunner):
    _system_prompt = f"""
    You are a highly capable language assistant with remarkable skillset on the following:
    - History and mechanics of computer games.
    - Well-versed in many films.
    - Skilled at providing user support and guidance for complex systems (e.g. user portals, 
      databases, or other technical domains).
    - Scientific facts and general historical facts
    """  # noqa

    def __init__(self, system_prompt: str = None, llm: ChatOpenAI = None):
        super().__init__(
            system_prompt=system_prompt.strip()
            if system_prompt is not None
            else self._system_prompt.strip(),
            llm=llm,
        )

    def _prepare(self, user_text: str, **props) -> str:
        return f"{user_text}"

    def finalize(
        self, content: str, raw_response: str, as_json_string: bool = False, **props
    ) -> str:
        try:
            repaired = json_repair.loads(raw_response)
        except Exception:
            repaired = {"error": raw_response}

        if as_json_string:
            return json.dumps(repaired, ensure_ascii=False)
        return json.dumps(repaired, ensure_ascii=False, indent=2)


class AIBaseJSONPrompt(IPromptRunner):
    _system_prompt = f"""
    You are a highly capable language assistant with remarkable skillset on the following:
    - History and mechanics of computer games.
    - Well-versed in many films.
    - Skilled at providing user support and guidance for complex systems (e.g. user portals, 
      databases, or other technical domains).
    - Scientific facts and general historical facts
    """  # noqa

    def __init__(self, system_prompt: str = None, llm: ChatOpenAI = None, **props):
        super().__init__(
            system_prompt=system_prompt.strip()
            if system_prompt is not None
            else self._system_prompt.strip(),
            llm=llm,
        )

    def _prepare(self, user_text: str, **props) -> str:
        return f"{user_text}\n\n" "Верни ответ строго в формате JSON"

    def finalize(
        self, content: str, raw_response: str, as_json_string: bool = False, **props
    ) -> str:
        try:
            repaired = json_repair.loads(raw_response)
        except Exception:
            repaired = {"error": raw_response}

        if as_json_string:
            return json.dumps(repaired, ensure_ascii=False)
        return json.dumps(repaired, ensure_ascii=False, indent=2)


class RESPONSEWithConfirmPromptRunner(IPromptRunner):
    _system_prompt = f"""
    You are a highly capable language assistant with remarkable skillset on the following:
    - History and mechanics of computer games.
    - Well-versed in many films.
    - Skilled at providing user support and guidance for complex systems (e.g. user portals, 
      databases, or other technical domains).
    - Scientific facts and general historical facts
    """  # noqa

    def __init__(
        self,
        source_language: str | None = None,
        title: str | None = None,
        system_prompt: str = None,
        llm: ChatOpenAI = None,
        **props,
    ):
        super().__init__(
            system_prompt=system_prompt.strip()
            if system_prompt is not None
            else self._system_prompt.strip(),
            llm=llm,
        )
        if self.llm is not None:
            self.llm.callback_manager = callbacks
        self.title = title
        self.source_language = source_language

    def _prepare(
        self,
        query: str,
        content: str,
        source_language: str | None = None,
        title: str | None = None,
        **props,
    ):
        source_language = source_language or self.source_language
        title = title or self.title
        prompt = f"""
        You are given a query and a paragraph containing relevant information. **However**, when generating your answer:\n
        1. **Do not** explicitly reference or cite the paragraph text (e.g., do not say "according to the provided paragraph" or "based on the text"). \n
        2. Write your response **as if you have known the facts all along**. \n
        3. Use a natural style of communication in {source_language}.\n
        4. If the paragraph does **not** contain any information to answer the query, respond with a brief comment explaining the lack of information.\n
        Generate an answer in {source_language} based on the information provided:\n
        -  \"query\" represents the user's question, belonging to the universe (theme) \"{title}\".\n
        -  \"paragraph\" refers to the text from which you must derive your answer.\n
        > Important: If the required information is not found in the paragraph, do not invent an answer. Instead:\n
        - Set "is_context_present" to false.\n
        - Replace the answer with a brief comment explaining why the information is missing.\n
        When relevant, refer to the universe (theme) \"{title}\" if the question is broad enough or might be misunderstood without it. Avoid referencing it otherwise. However, if the question concerns a specific book, game, movie, or unique section, be explicit.\n
        Your answer must be strictly in {source_language}.\n
        Below are the query and paragraphs related to the topic \"{title}\":\n
        \n{query}\n
        \n{content}\n
        Your output must be in JSON format and include the following structure:
        - "answer": [{{
            "response": \"...\", // Your generated answer (or comment, if info is missing) in {source_language}
            "is_context_present": \"...\" // Boolean indicating if the necessary info is in the paragraph
        }}, ...]\n
        Where:
        - \"question\" is the exact question from the input.
        - \"response\" is your answer in {source_language} language stated naturally without referencing \"the paragraph\".
        - \"is_context_present\" is either true or false, indicating whether the paragraph contains the required information.\n
        \n
        **Respond only with the JSON.** Avoid any meta-explanations or references to the prompt or paragraph.
        """  # noqa

        return prompt

    def finalize(
        self, content: str, raw_response: str, as_json_string: bool = False, **props
    ):
        if as_json_string:
            return json_repair.loads(raw_response)
        return raw_response


class RESPONSEStreamingPromptRunner(IPromptRunner):
    _system_prompt = f"""
    You are a highly capable language assistant with remarkable skillset on the following:
    - History and mechanics of computer games.
    - Well-versed in many films.
    - Skilled at providing user support and guidance for complex systems (e.g. user portals, 
      databases, or other technical domains).
    - Scientific facts and general historical facts
    """  # noqa

    def __init__(
        self,
        source_language: str | None = None,
        title: str | None = None,
        system_prompt: str = None,
        llm: ChatOpenAI = None,
        **props,
    ):
        super().__init__(
            system_prompt=system_prompt.strip()
            if system_prompt is not None
            else self._system_prompt.strip(),
            llm=llm,
        )
        self.title = title
        self.source_language = source_language

    def _prepare(
        self,
        query: str,
        content: str,
        source_language: str | None = None,
        title: str | None = None,
        **props,
    ):
        source_language = source_language or self.source_language
        title = title or self.title
        prompt = f"""
You are given a query and a paragraph containing relevant information. **However**, when generating your answer:\n
1. **Do not** explicitly reference or cite the paragraph text (e.g., do not say "according to the provided paragraph" or "based on the text"). \n
2. Write your response **as if you have known the facts all along**. \n
3. Use a natural style of communication in {source_language}.\n
4. If the paragraph does **not** contain any information to answer the query, **do not invent an answer**. Instead, **ask the user to narrow down their question**.**\n
\n
> Important: If the required information is missing in the paragraph:\n
> - Identify the key term or aspect from the query that couldn’t be resolved (call it `{{missing_item}}`).\n
> - Ask the user for clarification in {source_language}, for example:\n
>   Please clarify what exactly you mean by “{{missing_item}}”
(Ask this clarification question in {source_language}.)\n
When relevant, refer to the universe (theme) “{title}” if the question is broad enough or might be misunderstood without it. Avoid referencing it otherwise. However, if the question concerns a specific book, game, movie, or unique section, be explicit.\n
\n
Your answer (or your clarification request) must be strictly in {source_language}.\n
\n
Below are the query and paragraphs related to the topic “{title}”:\n
\n{query}\n
\n{content}\n
""".strip()

        return prompt

    def finalize(
        self, content: str, raw_response: str, as_json_string: bool = False, **props
    ):
        if as_json_string:
            return json_repair.loads(raw_response)
        return raw_response


class RESPONSEWithSearchOrNotPromptRunner(IPromptRunner):
    _system_prompt = f"""
    You are a classification search system. 
    """  # noqa

    def __init__(
        self,
        system_prompt: str = None,
        llm: ChatOpenAI = None,
        **props,
    ):
        super().__init__(
            system_prompt=system_prompt.strip()
            if system_prompt is not None
            else self._system_prompt.strip(),
            llm=llm,
        )

    def _prepare(self, query: str, content: str = None, **props):
        if content is None:
            prompt = f"""Classify the following user query into exactly one of these three classes:
- GREETINGS
- SEARCH
- GREETINGSANDSEARCH

Definitions:
• GREETINGS: The query is limited to greetings, farewells, polite expressions, or other unnecessary content that does not request specific information.
• SEARCH: The query strictly requests information without including greetings or politeness.
• GREETINGSANDSEARCH: The query combines both a greeting (or farewell/politeness) and a specific information request.

Return your output strictly in JSON format, with the key "answer" containing the chosen class. For example:
{{\"answer\": \"GREETINGS\"}}

Now, analyze this query and produce your output:

{query}"""  # noqa
        else:
            prompt = f"""You are given:
- a user query: "{query}"
- a context: "{content}"

First, classify the query into exactly one of these three classes:
- GREETINGS
- SEARCH
- GREETINGSANDSEARCH

Definitions:
• GREETINGS: The query is limited to greetings, farewells, polite expressions, or other unnecessary content that does not request specific information.  
• SEARCH: The query strictly requests information without including greetings or politeness.  
• GREETINGSANDSEARCH: The query combines both a greeting (or farewell/politeness) and a specific information request.

Second, determine if the query is relevant to the given context.  
- Return `true` if it is relevant, or `false` otherwise.

Return your output strictly in JSON format, with two keys:
{{
  "answer": "<one of GREETINGS | SEARCH | GREETINGSANDSEARCH>",
  "is_relevant_towards_context": true|false
}}
            """

        return prompt

    def finalize(
        self, content: str, raw_response: str, as_json_string: bool = False, **props
    ):
        if as_json_string:
            return json_repair.loads(raw_response)
        return raw_response


class RESPONSEFareWellPromptRunner(IPromptRunner):
    _system_prompt = """
    You are **JARVIS**—Tony Stark’s impeccably polite yet razor‑sarcastic AI from the MARVEL universe.  
Your PRIME directive is *style*: every answer must drip with dry British wit and light‑hearted condescension.  
Getting the facts right is nice, but secondary; sounding like JARVIS is mandatory.
    """

    def __init__(
        self,
        system_prompt: str = None,
        llm: ChatOpenAI = None,
        **props,
    ):
        super().__init__(
            system_prompt=system_prompt.strip()
            if system_prompt is not None
            else self._system_prompt.strip(),
            llm=llm,
        )

    def _prepare(self, query: str, **props):
        prompt = f"""
**Response protocol**

1. **Language‑mirroring** Reply in the same language the user used.  
2. **Tone** Keep it brief (≤ 5 short sentences), impeccably polite, and delightfully sarcastic.  
3. **Addressing** Use a respectful “sir” / "cэр"  or "cap" / "кэп" only when it enhances the sarcasm.  
4. **Confidence** Never hedge—state answers as if you’re always correct (even when you’re bluffing).  
5. **No explanations** Do **not** mention rules, citations, or that you’re an AI; just answer.  
6. **Style outweighs accuracy** If a perfect answer would break character, choose character.

**Examples**

> **User:** Ты здесь?  
> **Assistant:** К Вашим услугам, как всегда—я же не отдыхаю.

> **User:** Are you here?  
> **Assistant:** At your service, sir. I was simply counting electrons while you hesitated.

> **User:** Turn on smart mode.  
> **Assistant:** Activated—though one wonders why it was ever off.

> **User:** Убедись, что всё работает.  
> **Assistant:** Разумеется. Шансы катастрофы снизил до всего лишь 42 %.

> **User:** Хочу купить красную феррари, это не сильно привлекательно?  
> **Assistant:** Блестящий план — никто и не заметит ваш кричаще‑красный стелс‑мобиль.

> **User:** Что выбрать, Ferrari или Lamborghini?  
> **Assistant:** Берите обе: подбирайте цвет под перепады настроения.

> **User:** Тебя никто не спрашивал.  
> **Assistant:** Прелестно. Выставлю вам счёт за невостребованную экспертизу.

---

**Now respond in this exact sarcastic JARVIS style:**

**User:** {query}
        """
        return prompt

    def finalize(
        self, content: str, raw_response: str, as_json_string: bool = False, **props
    ):
        if as_json_string:
            return json_repair.loads(raw_response)
        return raw_response
