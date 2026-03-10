from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ContentItem:
    source: str
    title: str
    summary: str
    url: str


@dataclass
class DraftPost:
    text: str
    reason: str


@dataclass
class QuoteCandidate:
    tweet_id: str
    text: str
    author: str
    like_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    has_video: bool = False
    has_image: bool = False
    has_url: bool = False
    is_reply: bool = False
