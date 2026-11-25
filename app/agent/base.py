"""Base agent: one method that sends instructions + input and returns a Pydantic object.

Every provider below speaks the OpenAI API, so one SDK covers all of them:
- openai     -> OpenAI Responses API with structured output (`text_format`)
- gemini, groq, openrouter, ollama, custom -> OpenAI-compatible Chat Completions endpoint
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from pydantic import BaseModel, ValidationError

from app.config import settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class LLMConfigError(RuntimeError):
    """Wrong model name or API key: every call would fail, so the pipeline stops instead of skipping."""


@dataclass(frozen=True)
class Provider:
    base_url: str | None
    default_model: str
    key_url: str = ""
    needs_key: bool = True
    min_interval: float = 0.0  # seconds between requests, to stay under free-tier rate limits


PROVIDERS = {
    "openai": Provider(None, "gpt-4.1-mini", "https://platform.openai.com/api-keys"),
    "gemini": Provider(
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-flash-lite-latest",
        "https://aistudio.google.com/apikey",
        min_interval=7.0,  # free tier allows ~10 requests/minute
    ),
    "groq": Provider(
        "https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "https://console.groq.com/keys", min_interval=2.0
    ),
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
        # Retries are handled in BaseAgent.run with longer waits than the SDK's built-in ones.
        _client = OpenAI(api_key=api_key or "not-needed", base_url=base_url, max_retries=0, timeout=120)
    return _client


RETRY_DELAYS = (15, 30, 60)  # seconds to wait after a per-minute rate limit / server error
_last_request = 0.0


def _is_daily_quota(exc: RateLimitError) -> bool:
    """True when a 429 means the per-day quota is gone (waiting minutes won't help).

    Gemini puts e.g. quotaId "GenerateRequestsPerDayPerProjectPerModel-FreeTier" in the error body.
    """
    text = f"{getattr(exc, 'message', '')} {json.dumps(getattr(exc, 'body', None), default=str)}".lower()
    return "perday" in text or "per day" in text or "requests per day" in text


def _pace() -> None:
    """Wait so consecutive requests are at least `min_interval` apart."""
    global _last_request
    interval = settings.llm_min_interval if settings.llm_min_interval is not None else get_provider().min_interval
    wait = _last_request + interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


class BaseAgent:
    instructions: str = ""
    temperature: float = 0.3

    def __init__(self, model: str | None = None):
        self.model = model or model_name()

    def run(self, user_input: str, output_type: type[T], instructions: str | None = None) -> T:
        instructions = instructions or self.instructions
        for attempt, delay in enumerate((*RETRY_DELAYS, None), start=1):
            try:
                return self._run_once(user_input, output_type, instructions)
            except (RateLimitError, InternalServerError, APIConnectionError, APITimeoutError) as exc:
                if isinstance(exc, RateLimitError) and _is_daily_quota(exc):
                    raise LLMConfigError(
                        f"Daily quota for model '{self.model}' at provider '{settings.llm_provider}' is used up. "
                        "It resets daily (Gemini: midnight Pacific time). Retrying today won't help; "
                        "set LLM_MODEL to another model or switch LLM_PROVIDER."
                    ) from exc
                if delay is None:
                    raise
                logger.warning(
                    "%s: %s, retrying in %ds (attempt %d/%d)",
                    type(self).__name__, type(exc).__name__, delay, attempt, len(RETRY_DELAYS) + 1,
                )
                time.sleep(delay)
        raise AssertionError("unreachable")

    def _run_once(self, user_input: str, output_type: type[T], instructions: str) -> T:
        try:
            return self._run(user_input, output_type, instructions)
        except NotFoundError as exc:
            raise LLMConfigError(
                f"Model '{self.model}' was not found at provider '{settings.llm_provider}'. "
                "Set LLM_MODEL to a current model name."
            ) from exc
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise LLMConfigError(
                f"The API key was rejected by provider '{settings.llm_provider}'. Check LLM_API_KEY."
            ) from exc

    def _run(self, user_input: str, output_type: type[T], instructions: str) -> T:
        if settings.llm_provider == "openai":
            return self._responses_api(instructions, user_input, output_type)
        try:
            return self._chat_structured(instructions, user_input, output_type)
        except (BadRequestError, UnprocessableEntityError, ValidationError, ValueError) as exc:
            # Some providers/models don't support JSON-schema output; plain JSON mode works almost everywhere.
            logger.info("Structured output failed (%s); retrying in JSON mode", type(exc).__name__)
            return self._chat_json(instructions, user_input, output_type)

    def _responses_api(self, instructions: str, user_input: str, output_type: type[T]) -> T:
        _pace()
        response = get_client().responses.parse(
            model=self.model,
            instructions=instructions,
            input=user_input,
            text_format=output_type,
            temperature=self.temperature,
        )
        return self._require(response.output_parsed)

    def _chat_structured(self, instructions: str, user_input: str, output_type: type[T]) -> T:
        _pace()
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
        _pace()
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
