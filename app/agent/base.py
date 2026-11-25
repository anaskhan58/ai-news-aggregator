"""Base agent: one method that sends instructions + input and returns a Pydantic object.

- LLM_PROVIDER=openai -> OpenAI Responses API with structured output (`text_format`)
- LLM_PROVIDER=ollama -> local Ollama through its OpenAI-compatible chat endpoint
"""

from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from app.config import settings

T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if settings.llm_provider == "ollama":
            _client = OpenAI(base_url=settings.ollama_base_url, api_key="ollama")
        else:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is not set (or use LLM_PROVIDER=ollama).")
            _client = OpenAI(api_key=settings.openai_api_key)
    return _client


class BaseAgent:
    instructions: str = ""
    temperature: float = 0.3

    def __init__(self, model: str | None = None):
        self.model = model or settings.llm_model

    def run(self, user_input: str, output_type: type[T], instructions: str | None = None) -> T:
        client = get_client()
        instructions = instructions or self.instructions
        if settings.llm_provider == "ollama":
            completion = client.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user_input},
                ],
                response_format=output_type,
                temperature=self.temperature,
            )
            parsed = completion.choices[0].message.parsed
        else:
            response = client.responses.parse(
                model=self.model,
                instructions=instructions,
                input=user_input,
                text_format=output_type,
                temperature=self.temperature,
            )
            parsed = response.output_parsed
        if parsed is None:
            raise ValueError(f"{type(self).__name__}: model returned no parsable output")
        return parsed
