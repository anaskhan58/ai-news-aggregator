"""Email agent: writes the greeting + short introduction for the daily digest email."""

from datetime import date

from pydantic import BaseModel, Field

from app.agent.base import BaseAgent
from app.profiles.user_profile import USER_PROFILE


class EmailIntro(BaseModel):
    greeting: str = Field(description="e.g. 'Hey Dave, here is your AI news digest for November 25, 2026'")
    introduction: str = Field(description="2-3 sentences previewing the main themes of today's stories")


class EmailAgent(BaseAgent):
    temperature = 0.6
    instructions = """You write the opening of a personal daily AI news email.
Greet the reader by name with today's date, then write a 2-3 sentence introduction that
previews the most important themes in today's top stories. Friendly, direct, no hype,
no emojis, and do not list every story."""

    def write_intro(self, titles: list[str], today: date | None = None) -> EmailIntro:
        today = today or date.today()
        user_input = (
            f"Reader name: {USER_PROFILE['name']}\n"
            f"Date: {today:%B %d, %Y}\n\nToday's top stories:\n"
            + "\n".join(f"- {t}" for t in titles)
        )
        return self.run(user_input, EmailIntro)
