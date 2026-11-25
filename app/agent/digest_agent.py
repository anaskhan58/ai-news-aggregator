"""Digest agent: turns one article / video transcript into a short title + 2-3 sentence summary."""

from pydantic import BaseModel, Field

from app.agent.base import BaseAgent

MAX_CHARS = 12_000  # keep prompts cheap; the opening of an article carries the news


class DigestOutput(BaseModel):
    title: str = Field(description="Short, specific headline (max ~12 words)")
    summary: str = Field(description="2-3 sentence summary of the key news and why it matters")


class DigestAgent(BaseAgent):
    temperature = 0.3
    instructions = """You are an expert AI news analyst writing for a busy AI engineer.
Summarise the given article or video transcript.

Rules:
- Title: a short, specific headline that states the actual news, not clickbait.
- Summary: 2-3 sentences. Lead with what happened, then why it matters technically or practically.
- Use concrete facts (model names, numbers, release details). No hype, no filler phrases.
- If the content is only a short description, summarise what is known without inventing details."""

    def summarize(self, source: str, title: str, content: str) -> DigestOutput:
        user_input = f"Source: {source}\nOriginal title: {title}\n\nContent:\n{content[:MAX_CHARS]}"
        return self.run(user_input, DigestOutput)
