"""Curator agent: like a news editor, scores every digest against the user profile and ranks them."""

from pydantic import BaseModel, Field

from app.agent.base import BaseAgent
from app.profiles.user_profile import USER_PROFILE


class ScoredItem(BaseModel):
    item_number: int = Field(description="The [number] of the item in the input list")
    relevance_score: float = Field(ge=0, le=10, description="0 = irrelevant, 10 = must read")
    reasoning: str = Field(description="One short sentence on why it scored this way")


class CuratorOutput(BaseModel):
    items: list[ScoredItem]


class CuratorAgent(BaseAgent):
    temperature = 0.2

    def build_instructions(self) -> str:
        p = USER_PROFILE
        return f"""You are the curator of a personalised AI news briefing - the editor who decides
what makes the front page. Score EVERY item for how valuable it is to this reader.

Reader profile:
- Name: {p['name']}
- Background: {p['background']}
- Interests: {', '.join(p['interests'])}
- Less interested in: {', '.join(p['less_interested_in'])}
- Preferences: {p['preferences']}

Scoring rubric (0-10):
- 9-10: major release or research directly in the reader's interests; they would be annoyed to miss it
- 6-8: clearly relevant and useful
- 3-5: tangentially relevant or minor update
- 0-2: off-topic, marketing, or customer stories with no technical substance

Return one entry per input item, using its [number]. Be decisive: spread scores out."""

    def rank(self, items: list[tuple[str, str, str]]) -> list[ScoredItem]:
        """items: (source, title, summary). Returns scored items sorted best-first."""
        listing = "\n\n".join(
            f"[{i}] ({source}) {title}\n{summary}" for i, (source, title, summary) in enumerate(items)
        )
        result = self.run(listing, CuratorOutput, instructions=self.build_instructions())
        valid = {s.item_number: s for s in result.items if 0 <= s.item_number < len(items)}
        return sorted(valid.values(), key=lambda s: s.relevance_score, reverse=True)
