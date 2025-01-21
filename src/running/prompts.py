import abc
import json
import json_repair


class IPromptRunner(abc.ABC):

    @abc.abstractmethod
    def _prepare(self, user_text: str, **props) -> str:
        pass

    @abc.abstractmethod
    def finalize(self, user_text: str, raw_response: str, **props) -> str:
        pass


class AIBasePrompt(IPromptRunner):
    def __init__(self, system_prompt: str = "You are an AI assistant."):
        self.system_prompt = system_prompt.strip()

    def _prepare(self, user_text: str, **props) -> str:
        return f"{user_text}"

    def finalize(self, user_text: str, raw_response: str, **props) -> str:
        return raw_response


class AIBaseJSONPrompt(AIBasePrompt):

    def _prepare(self, user_text: str, **props) -> str:
        return (
            f"{user_text}\n\n"
            "Верни ответ строго в формате JSON"
        )

    def finalize(self, user_text: str, raw_response: str, as_json_string: bool = False, **props) -> str:
        try:
            repaired = json_repair.loads(raw_response)
        except Exception:
            repaired = {"error": raw_response}

        if as_json_string:
            return json.dumps(repaired, ensure_ascii=False)
        return json.dumps(repaired, ensure_ascii=False, indent=2)
