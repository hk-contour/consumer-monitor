"""Reddit community scraper via PRAW.

Requires env vars (set as GitHub Actions repository secrets):
  REDDIT_CLIENT_ID
  REDDIT_CLIENT_SECRET
  REDDIT_USER_AGENT  e.g. "consumer-monitor by /u/<your-username>"

Briefing flags seller/partner subs as material leading indicators:
  ETSY -> r/EtsySellers
  DASH -> r/doordash_drivers
  CART -> r/InstacartShoppers
  EBAY -> r/Ebay
  SHOP -> r/shopify
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RedditPost:
    subreddit: str
    title: str
    url: str
    score: int
    created_utc: float
    author: str
    body_preview: str


KARMA_THRESHOLD = 25  # Surface posts above this score; tune after first week


def _client():
    """Lazy import so test envs without praw still work."""
    import praw  # noqa: PLC0415
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "consumer-monitor/0.1"),
    )


def subreddit_from_url(url: str) -> str | None:
    """Parse https://www.reddit.com/r/shopify/ -> 'shopify'."""
    if "/r/" not in url:
        return None
    after = url.split("/r/", 1)[1]
    return after.split("/", 1)[0].strip() or None


def recent_posts(subreddit_name: str, limit: int = 25) -> list[RedditPost]:
    reddit = _client()
    sub = reddit.subreddit(subreddit_name)
    out: list[RedditPost] = []
    for submission in sub.new(limit=limit):
        if submission.score < KARMA_THRESHOLD:
            continue
        body = (submission.selftext or "")[:500]
        out.append(RedditPost(
            subreddit=subreddit_name,
            title=submission.title,
            url=f"https://reddit.com{submission.permalink}",
            score=int(submission.score),
            created_utc=float(submission.created_utc),
            author=str(submission.author) if submission.author else "[deleted]",
            body_preview=body,
        ))
    return out
