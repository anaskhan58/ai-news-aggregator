"""The daily pipeline, as four independent, re-runnable steps.

1. scrape   - pull feed metadata from every registered scraper into `articles` (fast)
2. content  - fetch full text (transcripts / page markdown) for new articles
3. digest   - LLM summary per article -> `digests`
4. email    - rank unsent digests against the user profile, email the top N, mark them sent

Each step only touches rows the previous step left behind, so a crash mid-run is safe:
just run it again.
"""

import logging
from datetime import date
from pathlib import Path

from app.agent import CuratorAgent, DigestAgent, EmailAgent
from app.config import ROOT_DIR, settings
from app.database import Article, Repository, create_tables, describe_database, get_session
from app.scrapers import build_scrapers
from app.services.email import EmailStory, render_html, render_text, send_email

logger = logging.getLogger("pipeline")


def scrape(hours: int) -> int:
    total = 0
    for name, scraper in build_scrapers().items():
        try:
            items = scraper.get_items(hours=hours)
        except Exception:
            logger.exception("Scraper %s failed", name)
            continue
        with get_session() as session:
            added = Repository(session).add_new_articles(items)
        logger.info("[scrape] %-10s %3d found, %3d new", name, len(items), added)
        total += added
    return total


def fetch_content() -> int:
    scrapers = build_scrapers()
    with get_session() as session:
        repo = Repository(session)
        articles = repo.articles_pending_content()
        for article in articles:
            scraper = scrapers.get(article.source)
            content = scraper.fetch_content(article.url, article.guid) if scraper else None
            repo.set_content(article, content)
            session.commit()  # keep progress if a later item crashes
            logger.info("[content] %s %s", "ok  " if content else "none", article.title[:70])
    return len(articles)


def generate_digests(hours: int) -> int:
    agent = DigestAgent()
    created = 0
    with get_session() as session:
        repo = Repository(session)
        for article in repo.articles_without_digest(hours):
            text = article.content or article.description or article.title
            try:
                result = agent.summarize(article.source, article.title, text)
            except Exception:
                logger.exception("[digest] failed for %s", article.id)
                continue
            repo.add_digest(article, result.title, result.summary)
            session.commit()
            created += 1
            logger.info("[digest] %s", result.title)
    return created


def send_digest(hours: int, top_n: int, dry_run: bool = False) -> Path | None:
    with get_session() as session:
        repo = Repository(session)
        digests = repo.unsent_digests(hours)
        if not digests:
            logger.info("[email] no new digests in the last %dh - nothing to send", hours)
            return None

        ranked = CuratorAgent().rank([(d.source, d.title, d.summary) for d in digests])
        top = [(digests[s.item_number], s) for s in ranked[:top_n]]
        for digest, scored in top:
            digest.relevance_score = scored.relevance_score
            logger.info("[rank] %4.1f %s", scored.relevance_score, digest.title[:70])

        source_names = {
            a.id: a.source_name
            for a in session.query(Article).filter(Article.id.in_([d.article_id for d, _ in top]))
        }
        stories = [
            EmailStory(d.title, d.summary, d.url, d.source, source_names.get(d.article_id, ""))
            for d, _ in top
        ]
        intro = EmailAgent().write_intro([s.title for s in stories])
        html = render_html(intro.greeting, intro.introduction, stories)
        subject = f"Daily AI News Digest - {date.today():%B %d, %Y}"

        if dry_run:
            out = ROOT_DIR / "output" / f"digest-{date.today()}.html"
            out.parent.mkdir(exist_ok=True)
            out.write_text(html, encoding="utf-8")
            logger.info("[email] dry run - wrote %s (digests NOT marked as sent)", out)
            return out

        send_email(subject, html, render_text(intro.greeting, intro.introduction, stories))
        repo.mark_sent([d for d, _ in top])
        logger.info("[email] sent %d stories to %s", len(stories), settings.email_to)
        return None


def run_daily_pipeline(hours: int, top_n: int, dry_run: bool = False, steps=None) -> None:
    steps = steps or ["scrape", "content", "digest", "email"]
    logger.info("Database: %s | LLM: %s/%s", describe_database(), settings.llm_provider, settings.llm_model)
    create_tables()
    if "scrape" in steps:
        scrape(hours)
    if "content" in steps:
        fetch_content()
    if "digest" in steps:
        generate_digests(hours)
    if "email" in steps:
        send_digest(hours, top_n, dry_run)
