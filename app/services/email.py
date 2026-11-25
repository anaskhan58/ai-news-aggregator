"""Render the digest as a minimal HTML email and send it through Gmail SMTP."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape

from app.config import settings

SOURCE_LABELS = {"youtube": "YouTube", "openai": "OpenAI", "anthropic": "Anthropic"}


@dataclass
class EmailStory:
    title: str
    summary: str
    url: str
    source: str
    source_name: str = ""


def render_html(greeting: str, introduction: str, stories: list[EmailStory]) -> str:
    blocks = []
    for story in stories:
        label = SOURCE_LABELS.get(story.source, story.source.title())
        if story.source_name and story.source == "youtube":
            label = f"{label} · {story.source_name}"
        blocks.append(
            f"""
      <div style="margin:0 0 22px 0;">
        <h3 style="margin:0 0 4px 0;font-size:16px;">
          <a href="{escape(story.url)}" style="color:#1a1a1a;text-decoration:none;">{escape(story.title)}</a>
        </h3>
        <p style="margin:0 0 4px 0;font-size:12px;color:#777;"><em>{escape(label)}</em></p>
        <p style="margin:0 0 4px 0;font-size:14px;line-height:1.5;">{escape(story.summary)}</p>
        <a href="{escape(story.url)}" style="font-size:13px;color:#2563eb;">Read more &rarr;</a>
      </div>"""
        )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f6f6f6;">
  <div style="max-width:640px;margin:0 auto;padding:24px;background:#ffffff;
              font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1a1a1a;">
    <h2 style="margin:0 0 12px 0;font-size:20px;">{escape(greeting)}</h2>
    <p style="margin:0 0 24px 0;font-size:14px;line-height:1.6;color:#333;">{escape(introduction)}</p>
    <hr style="border:none;border-top:1px solid #eee;margin:0 0 20px 0;">
    {''.join(blocks)}
    <p style="font-size:11px;color:#999;margin-top:28px;">Sent by your AI News Aggregator.</p>
  </div>
</body></html>"""


def render_text(greeting: str, introduction: str, stories: list[EmailStory]) -> str:
    lines = [greeting, "", introduction, ""]
    for s in stories:
        lines += [f"## {s.title}", s.summary, s.url, ""]
    return "\n".join(lines)


def send_email(subject: str, html: str, text: str) -> None:
    if not (settings.email_from and settings.email_app_password and settings.email_to):
        raise RuntimeError("Set MY_EMAIL and APP_PASSWORD (Gmail app password) to send email.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.email_from
    message["To"] = settings.email_to
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(settings.email_from, settings.email_app_password)
        smtp.send_message(message)
