"""YouTube: latest videos via the channel RSS feed, transcripts via youtube-transcript-api."""

import logging

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

from app.config import settings
from app.scrapers.base import RSSScraper

logger = logging.getLogger(__name__)

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


class YouTubeScraper(RSSScraper):
    name = "youtube"

    def __init__(self, channel_ids: list[str]):
        super().__init__([FEED_URL.format(channel_id=c) for c in channel_ids])
        proxy = None
        if settings.webshare_username and settings.webshare_password:
            proxy = WebshareProxyConfig(
                proxy_username=settings.webshare_username,
                proxy_password=settings.webshare_password,
            )
        self.transcripts = YouTubeTranscriptApi(proxy_config=proxy)

    def include(self, entry) -> bool:
        # Shorts are usually clips of long-form videos and rarely have transcripts.
        return "/shorts/" not in entry.get("link", "")

    def guid_for(self, entry) -> str:
        return entry.get("yt_videoid") or entry.get("id", "").removeprefix("yt:video:")

    def fetch_content(self, url: str, guid: str) -> str | None:
        try:
            transcript = self.transcripts.fetch(guid, languages=["en", "en-US", "en-GB"])
        except Exception as exc:  # disabled captions, IP block, private video...
            logger.info("No transcript for %s: %s", guid, type(exc).__name__)
            return None
        return " ".join(snippet.text for snippet in transcript)
