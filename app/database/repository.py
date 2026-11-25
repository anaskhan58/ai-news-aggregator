"""All database reads/writes live here, so the rest of the app never writes queries."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Article, ContentStatus, Digest, utcnow
from app.scrapers.base import FeedItem


def _since(hours: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # --- articles -----------------------------------------------------------------
    def add_new_articles(self, items: list[FeedItem]) -> int:
        """Insert items not seen before; existing ones are skipped (not overwritten)."""
        unique = {item.id: item for item in items}
        if not unique:
            return 0
        existing = set(
            self.session.scalars(select(Article.id).where(Article.id.in_(unique.keys())))
        )
        new = [item for key, item in unique.items() if key not in existing]
        self.session.add_all(Article(id=item.id, **item.model_dump()) for item in new)
        return len(new)

    def articles_pending_content(self) -> list[Article]:
        stmt = select(Article).where(Article.content_status == ContentStatus.PENDING)
        return list(self.session.scalars(stmt))

    def set_content(self, article: Article, content: str | None) -> None:
        article.content = content
        article.content_status = ContentStatus.OK if content else ContentStatus.UNAVAILABLE

    def articles_without_digest(self, hours: int) -> list[Article]:
        stmt = (
            select(Article)
            .outerjoin(Digest, Digest.article_id == Article.id)
            .where(Digest.article_id.is_(None))
            .where(Article.content_status != ContentStatus.PENDING)
            .where(Article.published_at >= _since(hours))
            .order_by(Article.published_at.desc())
        )
        return list(self.session.scalars(stmt))

    # --- digests ------------------------------------------------------------------
    def add_digest(self, article: Article, title: str, summary: str) -> Digest:
        digest = Digest(
            article_id=article.id,
            source=article.source,
            url=article.url,
            title=title,
            summary=summary,
            published_at=article.published_at,
        )
        self.session.add(digest)
        return digest

    def unsent_digests(self, hours: int) -> list[Digest]:
        stmt = (
            select(Digest)
            .where(Digest.sent_at.is_(None))
            .where(Digest.published_at >= _since(hours))
            .order_by(Digest.published_at.desc())
        )
        return list(self.session.scalars(stmt))

    def mark_sent(self, digests: list[Digest]) -> None:
        now = utcnow()
        for digest in digests:
            digest.sent_at = now
