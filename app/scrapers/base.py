"""Shared scraper building blocks.

Every source is an RSS/Atom feed, so one base class does the fetching, parsing and
time filtering. A concrete scraper only names its feeds and (optionally) knows how
to fetch the full content of one item.
"""

import logging
from abc import ABC
from calendar import timegm
from datetime import datetime, timedelta, timezone

import feedparser
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class FeedItem(BaseModel):
    """One entry from a feed, normalised across sources."""

    source: str  # scraper name, e.g. "youtube"
    source_name: str  # human label, e.g. channel or feed title
    guid: str  # stable id inside the source (video id, article guid)
    title: str
    url: str
    description: str = ""
    published_at: datetime

    @property
    def id(self) -> str:
        return f"{self.source}:{self.guid}"


class RSSScraper(ABC):
    name: str = "rss"

    def __init__(self, feed_urls: list[str]):
        self.feed_urls = feed_urls

    # --- hooks a subclass may override -------------------------------------------
    def include(self, entry) -> bool:
        return True

    def guid_for(self, entry) -> str:
        return entry.get("id") or entry.get("link")

    def fetch_content(self, url: str, guid: str) -> str | None:
        """Full text for one item (markdown, transcript...). None = not available."""
        return None

    # --- shared logic ---------------------------------------------------------------
    def get_items(self, hours: int = 24) -> list[FeedItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        items: list[FeedItem] = []
        for feed_url in self.feed_urls:
            feed = feedparser.parse(feed_url, agent="ai-news-aggregator/1.0")
            if feed.bozo and not feed.entries:
                logger.warning("Could not read feed %s: %s", feed_url, feed.get("bozo_exception"))
                continue
            feed_title = feed.feed.get("title", self.name)
            for entry in feed.entries:
                published = _entry_datetime(entry)
                if not published or published < cutoff or not self.include(entry):
                    continue
                items.append(
                    FeedItem(
                        source=self.name,
                        source_name=entry.get("author") or feed_title,
                        guid=self.guid_for(entry),
                        title=entry.get("title", "").strip(),
                        url=entry.get("link", ""),
                        description=_clean(entry.get("summary", "")),
                        published_at=published,
                    )
                )
        return items


def _entry_datetime(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(timegm(parsed), tz=timezone.utc)


def _clean(html: str) -> str:
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
