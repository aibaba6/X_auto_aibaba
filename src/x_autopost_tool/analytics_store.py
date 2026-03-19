from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .text_normalize import cleanup_post_text
from .uniqueness import extract_tags, loose_fingerprint, semantic_signature, strict_fingerprint


@dataclass
class AnalyticsStore:
    path: Path
    entries: list[dict[str, Any]]


def analytics_store_path(post_history_path: str | Path) -> Path:
    history_path = Path(post_history_path)
    if history_path.name:
        return history_path.with_name("post_analytics.yaml")
    return history_path / "post_analytics.yaml"


def load_analytics(path: str | Path) -> AnalyticsStore:
    resolved = Path(path)
    if not resolved.exists():
        return AnalyticsStore(path=resolved, entries=[])
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or []
    return AnalyticsStore(path=resolved, entries=data if isinstance(data, list) else [])


def save_analytics(store: AnalyticsStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(yaml.safe_dump(store.entries, allow_unicode=True, sort_keys=False), encoding="utf-8")


def normalize_source(source: str) -> str:
    value = (source or "").strip().lower()
    if "queue" in value:
        return "queue"
    if "manual" in value or "test" in value:
        return "manual"
    return "auto"


def _engagement_rate(impressions: int, likes: int, reposts: int, replies: int, bookmarks: int) -> float:
    if impressions <= 0:
        return 0.0
    return round(((likes + reposts + replies + bookmarks) / impressions) * 100, 3)


def upsert_post_record(
    store: AnalyticsStore,
    *,
    tweet_id: str,
    posted_at: str,
    text: str,
    slot: str,
    content_type: str = "",
    pattern_type: str = "",
    topic: str = "",
    claim: str = "",
    structure: str = "",
    source: str = "",
    has_media: bool = False,
) -> dict[str, Any]:
    cleaned_text = cleanup_post_text(text or "")
    semantic = semantic_signature(cleaned_text)
    tags = extract_tags(cleaned_text)
    normalized_source = normalize_source(source)
    existing = next((entry for entry in store.entries if str(entry.get("tweet_id", "")).strip() == tweet_id), None)
    base = existing or {}
    record = {
        "tweet_id": tweet_id,
        "posted_at": posted_at,
        "text": cleaned_text,
        "cleaned_text": cleaned_text,
        "slot": slot,
        "content_type": content_type,
        "pattern_type": pattern_type or content_type,
        "topic": topic or semantic.topic,
        "claim": claim or semantic.claim,
        "structure": structure or semantic.structure,
        "hashtags": tags,
        "has_media": bool(has_media),
        "source": normalized_source,
        "strict_fingerprint": strict_fingerprint(cleaned_text),
        "loose_fingerprint": loose_fingerprint(cleaned_text),
        "semantic_signature": {
            "hook": semantic.hook,
            "topic": semantic.topic,
            "claim": semantic.claim,
            "structure": semantic.structure,
            "takeaway": semantic.takeaway,
        },
        "impressions": int(base.get("impressions", 0) or 0),
        "likes": int(base.get("likes", 0) or 0),
        "reposts": int(base.get("reposts", 0) or 0),
        "replies": int(base.get("replies", 0) or 0),
        "bookmarks": int(base.get("bookmarks", 0) or 0),
        "engagement_rate": float(base.get("engagement_rate", 0.0) or 0.0),
        "metrics_updated_at": str(base.get("metrics_updated_at", "")),
    }
    if existing is not None:
        existing.clear()
        existing.update(record)
        return existing
    store.entries.append(record)
    return record


def merge_metric_snapshots(store: AnalyticsStore, snapshots: list[dict[str, Any]]) -> int:
    updated = 0
    index = {str(entry.get("tweet_id", "")).strip(): entry for entry in store.entries}
    for snap in snapshots:
        tweet_id = str(snap.get("tweet_id", "")).strip()
        if not tweet_id or tweet_id not in index:
            continue
        entry = index[tweet_id]
        impressions = int(snap.get("impressions", 0) or 0)
        likes = int(snap.get("likes", 0) or 0)
        reposts = int(snap.get("reposts", 0) or 0)
        replies = int(snap.get("replies", 0) or 0)
        bookmarks = int(snap.get("bookmarks", 0) or 0)
        entry.update(
            {
                "text": cleanup_post_text(str(snap.get("text", "")).strip()) or entry.get("text", ""),
                "cleaned_text": cleanup_post_text(str(snap.get("text", "")).strip()) or entry.get("cleaned_text", ""),
                "posted_at": str(snap.get("posted_at", "")).strip() or entry.get("posted_at", ""),
                "has_media": bool(snap.get("has_media", entry.get("has_media", False))),
                "impressions": impressions,
                "likes": likes,
                "reposts": reposts,
                "replies": replies,
                "bookmarks": bookmarks,
                "engagement_rate": _engagement_rate(impressions, likes, reposts, replies, bookmarks),
                "metrics_updated_at": str(snap.get("metrics_updated_at", "")).strip(),
            }
        )
        updated += 1
    return updated


def backfill_from_history(store: AnalyticsStore, history_entries: list[dict[str, Any]]) -> int:
    added = 0
    for entry in history_entries:
        tweet_id = str(entry.get("tweet_id", "")).strip()
        text = str(entry.get("text", "")).strip()
        if not tweet_id or not text:
            continue
        existing = next((row for row in store.entries if str(row.get("tweet_id", "")).strip() == tweet_id), None)
        before = len(store.entries)
        upsert_post_record(
            store,
            tweet_id=tweet_id,
            posted_at=str(entry.get("posted_at", entry.get("created_at", ""))).strip(),
            text=text,
            slot=str(entry.get("slot", "")).strip(),
            source=str(entry.get("source", "")).strip(),
            has_media=bool(entry.get("has_media", False)),
            content_type=str(entry.get("content_type", "")).strip(),
            pattern_type=str(entry.get("pattern_type", entry.get("content_type", ""))).strip(),
            topic=str(entry.get("topic", entry.get("semantic_topic", ""))).strip(),
            claim=str(entry.get("core_claim", entry.get("semantic_claim", ""))).strip(),
            structure=str(entry.get("pattern_id", entry.get("semantic_structure", ""))).strip(),
        )
        if existing is None and len(store.entries) > before:
            added += 1
    return added


def length_bucket(text: str) -> str:
    n = len((text or "").strip())
    if n < 90:
        return "short"
    if n < 160:
        return "medium"
    if n < 230:
        return "long"
    return "xlong"


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _parse_posted_at(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def summarize_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now().astimezone()
    recent_cutoff = now - timedelta(days=30)
    last30 = [entry for entry in entries if (dt := _parse_posted_at(str(entry.get("posted_at", "")))) and dt >= recent_cutoff]
    avg_impressions = _avg([float(entry.get("impressions", 0) or 0) for entry in last30])
    avg_engagement = _avg([float(entry.get("engagement_rate", 0.0) or 0.0) for entry in last30])
    best = max(entries, key=lambda e: (float(e.get("engagement_rate", 0.0) or 0.0), float(e.get("impressions", 0) or 0)), default=None)
    worst = min(entries, key=lambda e: (float(e.get("engagement_rate", 0.0) or 0.0), float(e.get("impressions", 0) or 0)), default=None)
    return {
        "last30_posts": len(last30),
        "avg_impressions": avg_impressions,
        "avg_engagement_rate": avg_engagement,
        "best_post": best,
        "worst_post": worst,
    }


def compare_group(entries: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if key == "length_bucket":
            group_key = length_bucket(str(entry.get("cleaned_text", entry.get("text", ""))))
        elif key == "has_media":
            group_key = "media" if bool(entry.get("has_media", False)) else "no_media"
        else:
            group_key = str(entry.get(key, "")).strip() or "-"
        groups.setdefault(group_key, []).append(entry)
    rows: list[dict[str, Any]] = []
    for group_key, items in groups.items():
        rows.append(
            {
                "key": group_key,
                "count": len(items),
                "avg_impressions": _avg([float(item.get("impressions", 0) or 0) for item in items]),
                "avg_engagement_rate": _avg([float(item.get("engagement_rate", 0.0) or 0.0) for item in items]),
                "avg_likes": _avg([float(item.get("likes", 0) or 0) for item in items]),
            }
        )
    rows.sort(key=lambda row: (-row["avg_engagement_rate"], -row["avg_impressions"], row["key"]))
    return rows
