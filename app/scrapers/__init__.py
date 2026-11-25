"""Scraper registry: the one place to add or remove sources.

To add a source: subclass RSSScraper (see blogs.py), then add an instance below.
"""

from app.scrapers.base import FeedItem, RSSScraper
from app.scrapers.blogs import AnthropicScraper, OpenAIScraper
from app.scrapers.youtube import YouTubeScraper

# Find a channel id: open the channel page -> View source -> search for "channel_id=" or "externalId".
YOUTUBE_CHANNELS = [
    "UCawZsQWqfGSbCI5yjkdVkTA",  # Matthew Berman
    "UCn8ujwUInbJkBhffxqAPBVQ",  # Dave Ebbelaar
]


def build_scrapers() -> dict[str, RSSScraper]:
    scrapers: list[RSSScraper] = [
        YouTubeScraper(YOUTUBE_CHANNELS),
        OpenAIScraper(),
        AnthropicScraper(),
    ]
    return {s.name: s for s in scrapers}


__all__ = ["FeedItem", "RSSScraper", "build_scrapers", "YOUTUBE_CHANNELS"]
