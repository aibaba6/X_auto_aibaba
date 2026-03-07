from __future__ import annotations

from typing import Iterable

import feedparser

from .models import ContentItem, QuoteCandidate


def fetch_rss_items(feeds: Iterable[str], max_items: int = 20) -> list[ContentItem]:
    results: list[ContentItem] = []
    for feed_url in feeds:
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries[:5]:
            title = getattr(entry, "title", "")
            summary = getattr(entry, "summary", "")
            link = getattr(entry, "link", "")
            results.append(
                ContentItem(
                    source=feed_url,
                    title=title.strip(),
                    summary=summary.strip(),
                    url=link.strip(),
                )
            )
            if len(results) >= max_items:
                return results
    return results


def filter_blocked(items: list[ContentItem], blocked_keywords: list[str]) -> list[ContentItem]:
    if not blocked_keywords:
        return items
    lowered = [k.lower() for k in blocked_keywords]

    def keep(item: ContentItem) -> bool:
        text = f"{item.title}\n{item.summary}".lower()
        return not any(b in text for b in lowered)

    return [item for item in items if keep(item)]


def simple_quote_score(text: str) -> int:
    # 長すぎる投稿やノイズの多い投稿は下げる
    score = 0
    if 40 <= len(text) <= 220:
        score += 2
    if "http" not in text:
        score += 1
    if "?" in text or "なぜ" in text or "課題" in text:
        score += 1
    return score


def rank_quote_candidates(candidates: list[QuoteCandidate], limit: int) -> list[QuoteCandidate]:
    ranked = sorted(candidates, key=lambda c: simple_quote_score(c.text), reverse=True)
    return ranked[:limit]
