"""Blog scrapers: OpenAI and Anthropic news feeds."""

import logging

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify

from app.scrapers.base import RSSScraper

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; ai-news-aggregator/1.0)"


def url_to_markdown(url: str) -> str | None:
    """Download a page and convert its main content to markdown (lightweight, no ML models)."""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.info("Could not fetch %s: %s", url, exc)
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript", "svg", "form"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body
    if main is None:
        return None
    markdown = markdownify(str(main), heading_style="ATX").strip()
    # collapse the blank-line runs that markdownify leaves behind
    lines = [line.rstrip() for line in markdown.splitlines()]
    text = "\n".join(line for i, line in enumerate(lines) if line or (i and lines[i - 1]))
    return text or None


class OpenAIScraper(RSSScraper):
    """openai.com sits behind Cloudflare, so we keep the RSS title + description only."""

    name = "openai"

    def __init__(self):
        super().__init__(["https://openai.com/news/rss.xml"])


class AnthropicScraper(RSSScraper):
    """Anthropic has no official feed; these community feeds mirror news/engineering/research."""

    name = "anthropic"
    BASE = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds"

    def __init__(self):
        super().__init__(
            [
                f"{self.BASE}/feed_anthropic_news.xml",
                f"{self.BASE}/feed_anthropic_engineering.xml",
                f"{self.BASE}/feed_anthropic_research.xml",
            ]
        )

    def guid_for(self, entry) -> str:
        return entry.get("link") or entry.get("id")

    def fetch_content(self, url: str, guid: str) -> str | None:
        return url_to_markdown(url)
