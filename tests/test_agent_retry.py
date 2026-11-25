"""BaseAgent retries rate-limit / server errors and stops on configuration errors."""

import pytest
from openai import NotFoundError, RateLimitError
from pydantic import BaseModel

from app.agent import base
from app.agent.base import BaseAgent, LLMConfigError


class Out(BaseModel):
    x: int


def _error(cls):
    return cls.__new__(cls)  # skip the SDK constructor (needs a real HTTP response)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(base.time, "sleep", sleeps.append)
    return sleeps


def test_retries_rate_limit_then_succeeds(monkeypatch, no_sleep):
    calls = iter([_error(RateLimitError), _error(RateLimitError), Out(x=1)])

    def fake_run(self, *args):
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(BaseAgent, "_run", fake_run)
    assert BaseAgent(model="m").run("hi", Out) == Out(x=1)
    assert no_sleep[:2] == [15, 30]


def test_gives_up_after_all_retries(monkeypatch, no_sleep):
    def always_limited(self, *args):
        raise _error(RateLimitError)

    monkeypatch.setattr(BaseAgent, "_run", always_limited)
    with pytest.raises(RateLimitError):
        BaseAgent(model="m").run("hi", Out)
    assert no_sleep == list(base.RETRY_DELAYS)


def test_unknown_model_is_a_config_error_without_retry(monkeypatch, no_sleep):
    def not_found(self, *args):
        raise _error(NotFoundError)

    monkeypatch.setattr(BaseAgent, "_run", not_found)
    with pytest.raises(LLMConfigError, match="not found"):
        BaseAgent(model="old-model").run("hi", Out)
    assert no_sleep == []
