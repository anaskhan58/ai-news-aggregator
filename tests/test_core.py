"""Offline tests: feed parsing, Shorts filtering, de-duplication, sent-tracking, email rendering."""

import os
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite://"  # in-memory DB, set before app imports

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.models import Base
from app.database.repository import Repository
from app.scrapers.base import FeedItem
from app.scrapers.youtube import YouTubeScraper
from app.services.email import EmailStory, render_html

NOW = datetime.now(timezone.utc)


def _youtube_feed(tmp_path):
    def entry(vid, link, published):
        return f"""<entry><id>yt:video:{vid}</id><yt:videoId>{vid}</yt:videoId>
<title>Video {vid}</title><link rel="alternate" href="{link}"/>
<author><name>Test Channel</name></author><published>{published.isoformat()}</published></entry>"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
<title>Test Channel</title>
{entry("_abc123", "https://www.youtube.com/watch?v=_abc123", NOW - timedelta(hours=2))}
{entry("short1", "https://www.youtube.com/shorts/short1", NOW - timedelta(hours=3))}
{entry("old1", "https://www.youtube.com/watch?v=old1", NOW - timedelta(days=5))}
</feed>"""
    path = tmp_path / "feed.xml"
    path.write_text(xml, encoding="utf-8")
    return path


def test_youtube_feed_filters_time_and_shorts(tmp_path):
    scraper = YouTubeScraper([])
    scraper.feed_urls = [str(_youtube_feed(tmp_path))]
    items = scraper.get_items(hours=24)
    assert [i.guid for i in items] == ["_abc123"]  # id with leading underscore kept intact
    assert items[0].id == "youtube:_abc123"
    assert items[0].source_name == "Test Channel"


@pytest.fixture
def repo():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield Repository(session)


def _item(guid, hours_ago=1):
    return FeedItem(source="openai", source_name="OpenAI News", guid=guid, title=f"T {guid}",
                    url=f"https://x/{guid}", description="desc", published_at=NOW - timedelta(hours=hours_ago))


def test_duplicates_are_skipped(repo):
    assert repo.add_new_articles([_item("a"), _item("b"), _item("a")]) == 2
    repo.session.flush()
    assert repo.add_new_articles([_item("a"), _item("c")]) == 1


def test_content_digest_and_sent_tracking(repo):
    repo.add_new_articles([_item("a"), _item("old", hours_ago=72)])
    repo.session.flush()
    for article in repo.articles_pending_content():
        repo.set_content(article, None)
    assert repo.articles_pending_content() == []

    pending = repo.articles_without_digest(hours=24)
    assert [a.guid for a in pending] == ["a"]
    repo.add_digest(pending[0], "Title", "Summary")
    repo.session.flush()
    assert repo.articles_without_digest(hours=24) == []

    unsent = repo.unsent_digests(hours=24)
    assert len(unsent) == 1
    repo.mark_sent(unsent)
    repo.session.flush()
    assert repo.unsent_digests(hours=24) == []


def test_email_html_escapes_content():
    html = render_html("Hey <b>", "Intro", [EmailStory("A & B", "x < y", "https://e.com/?a=1&b=2", "youtube", "Chan")])
    assert "A &amp; B" in html and "x &lt; y" in html and "Hey &lt;b&gt;" in html
    assert "YouTube · Chan" in html
