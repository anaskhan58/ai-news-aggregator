"""Base agent: one method that sends instructions + input and returns a Pydantic object.

Every provider below speaks the OpenAI API, so one SDK covers all of them:
- openai     -> OpenAI Responses API with structured output (`text_format`)
- gemini, groq, openrouter, ollama, custom -> OpenAI-compatible Chat Completions endpoint
"""

import json
import logging
from dataclasses import dataclass
from typing import TypeVar

from openai import BadRequestError, OpenAI, UnprocessableEntityError
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Provider:
    base_url: str | None
    default_model: str
    key_url: str = ""
    needs_key: bool = True


PROVIDERS = {
    "openai": Provider(None, "gpt-4.1-mini", "https://platform.openai.com/api-keys"),
    "gemini": Provider(
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.5-flash",
        "https://aistudio.google.com/apikey",
    ),
    "groq": Provider("https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "https://console.groq.com/keys"),
    "openrouter": Provider(
        "https://openrouter.ai/api/v1", "openai/gpt-4.1-mini", "https://openrouter.ai/settings/keys"
    ),
    "ollama": Provider("http://localhost:11434/v1", "llama3.2", needs_key=False),
    "custom": Provider(None, ""),  # any OpenAI-compatible server: set LLM_BASE_URL + LLM_MODEL
}


def get_provider() -> Provider:
    if settings.llm_provider not in PROVIDERS:
        raise RuntimeError(f"Unknown LLM_PROVIDER={settings.llm_provider!r}; use one of {list(PROVIDERS)}")
    return PROVIDERS[settings.llm_provider]


def model_name() -> str:
    return settings.llm_model or get_provider().default_model


_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        provider = get_provider()
        api_key = settings.llm_api_key
        if not api_key and provider.needs_key:
            hint = f" Get one at {provider.key_url}" if provider.key_url else ""
            raise RuntimeError(f"LLM_API_KEY is not set for provider '{settings.llm_provider}'.{hint}")
        base_url = settings.llm_base_url or provider.base_url
        if settings.llm_provider == "custom" and not base_url:
            raise RuntimeError("LLM_PROVIDER=custom needs LLM_BASE_URL.")
        _client = OpenAI(api_key=api_key or "not-needed", base_url=base_url)
    return _client


class BaseAgent:
    instructions: str = ""
    temperature: float = 0.3

    def __init__(self, model: str | None = None):
        self.model = model or model_name()

    def run(self, user_input: str, output_type: type[T], instructions: str | None = None) -> T:
        instructions = instructions or self.instructions
        if settings.llm_provider == "openai":
            return self._responses_api(instructions, user_input, output_type)
        try:
            return self._chat_structured(instructions, user_input, output_type)
        except (BadRequestError, UnprocessableEntityError, ValidationError, ValueError) as exc:
            # Some providers/models don't support JSON-schema output; plain JSON mode works almost everywhere.
            logger.info("Structured output failed (%s); retrying in JSON mode", type(exc).__name__)
            return self._chat_json(instructions, user_input, output_type)

    def _responses_api(self, instructions: str, user_input: str, output_type: type[T]) -> T:
        response = get_client().responses.parse(
            model=self.model,
            instructions=instructions,
            input=user_input,
            text_format=output_type,
            temperature=self.temperature,
        )
        return self._require(response.output_parsed)

    def _chat_structured(self, instructions: str, user_input: str, output_type: type[T]) -> T:
        completion = get_client().chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_input},
            ],
            response_format=output_type,
            temperature=self.temperature,
        )
        return self._require(completion.choices[0].message.parsed)

    def _chat_json(self, instructions: str, user_input: str, output_type: type[T]) -> T:
        schema = json.dumps(output_type.model_json_schema())
        completion = get_client().chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": f"{instructions}\n\nReply with ONLY a JSON object matching this JSON schema:\n{schema}",
                },
                {"role": "user", "content": user_input},
            ],
            response_format={"type": "json_object"},
            temperature=self.temperature,
        )
        text = completion.choices[0].message.content or ""
        try:
            return output_type.model_validate_json(text)
        except ValidationError as exc:
            raise ValueError(f"{type(self).__name__}: model output did not match schema: {text[:300]}") from exc

    def _require(self, parsed: T | None) -> T:
        if parsed is None:
            raise ValueError(f"{type(self).__name__}: model returned no parsable output")
        return parsed
