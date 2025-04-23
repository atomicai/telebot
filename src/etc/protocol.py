from langchain_core.callbacks import AsyncCallbackHandler, AsyncCallbackManager
from langchain_openai import ChatOpenAI


def construct_llm_protocol(
    host: str,
    port: int = None,
    temperature: float = 0.22,
    max_tokens=4096,
    streaming: bool = True,
    verbose: bool = False,
    api_key: str = "<YOUR_API_KEY_HERE>",
    callbacks: list[AsyncCallbackHandler] = None,
):
    base_url = f"{host}" if port is None else f"{host}:{port}"
    if callbacks is not None:
        callback_manager = AsyncCallbackManager(callbacks)
    else:
        callback_manager = None
    return ChatOpenAI(
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
        verbose=verbose,
        api_key=api_key,
        callbacks=callback_manager,
    )


__all__ = ["construct_llm_protocol"]
