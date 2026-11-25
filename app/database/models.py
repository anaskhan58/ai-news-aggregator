"""SQLAlchemy models.

One `articles` table for every source (the `source` column tells them apart), so adding
a scraper never needs a schema change. `digests` holds one LLM summary per article.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ContentStatus:
    PENDING = "pending"  # not tried yet
    OK = "ok"  # full text stored in `content`
    UNAVAILABLE = "unavailable"  # tried, none available -> digest uses the description


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(512), primary_key=True)  # "<source>:<guid>"
    source: Mapped[str] = mapped_column(String(50), index=True)
    source_name: Mapped[str] = mapped_column(String(255))
    guid: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    content: Mapped[str | None] = mapped_column(Text)
    content_status: Mapped[str] = mapped_column(String(20), default=ContentStatus.PENDING, index=True)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Digest(Base):
    __tablename__ = "digests"

    article_id: Mapped[str] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    source: Mapped[str] = mapped_column(String(50))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    # the article's original publish date, so "last 24h" filters on news age, not run time
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
