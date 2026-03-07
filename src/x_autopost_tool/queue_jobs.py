from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .llm import build_quote_post
from .rules import filter_quote_candidates, score_quote_candidate
from .settings import AppConfig
from .uniqueness import is_duplicate, load_memory, register_text, save_memory
from .x_client import XClient


def _parse_schedule_at(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _engagement_score(c) -> int:
    return c.like_count + c.retweet_count * 3 + c.reply_count * 2 + c.quote_count * 2


def _pick_noon_latest_candidate(candidates, config: AppConfig):
    ranked = sorted(
        candidates,
        key=lambda c: (
            1 if c.has_video else 0,
            1 if c.has_image else 0,
            _engagement_score(c),
            score_quote_candidate(c, config),
        ),
        reverse=True,
    )
    if config.quote_prefer_video:
        videos = [c for c in ranked if c.has_video]
        if videos:
            return videos[0]
        if config.quote_fallback_to_image:
            images = [c for c in ranked if c.has_image]
            if images:
                return images[0]
    return ranked[0] if ranked else None


def _load_queue(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return data if isinstance(data, list) else []


def _save_queue(path: Path, queue: list[dict[str, Any]]) -> None:
    path.write_text(yaml.safe_dump(queue, allow_unicode=True, sort_keys=False), encoding="utf-8")


def refresh_noon_queue(config: AppConfig, queue_path: str, dry_run: bool = False) -> int:
    path = Path(queue_path)
    queue = _load_queue(path)
    if not queue:
        print(f"[noon-refresh] queue not found or empty: {path}")
        return 0

    noon_profile = config.slot_profiles.get("noon", {})
    latest_mode = bool(noon_profile.get("latest_share_mode", False))
    capture_minutes = int(noon_profile.get("latest_capture_minutes_before", 30))
    if not latest_mode:
        print("[noon-refresh] latest_share_mode is false, skip")
        return 0

    now = datetime.now()
    changed = 0
    x = XClient()
    memory = load_memory(config.uniqueness_memory_path)

    for item in queue:
        slot = str(item.get("slot", "")).strip()
        schedule_at = str(item.get("schedule_at", "")).strip()
        if slot != "noon" or not schedule_at:
            continue

        scheduled_dt = _parse_schedule_at(schedule_at)
        if not scheduled_dt:
            continue
        window_start = scheduled_dt - timedelta(minutes=capture_minutes)
        if not (window_start <= now < scheduled_dt):
            continue

        refreshed_at = _parse_schedule_at(str(item.get("last_refreshed_at", "")).strip())
        if refreshed_at and (now - refreshed_at) < timedelta(minutes=10):
            continue

        candidates = x.search_multi(config.x_noon_queries, per_query=config.quote_candidates_limit)
        candidates = filter_quote_candidates(candidates, config)
        candidates = [c for c in candidates if score_quote_candidate(c, config) >= config.quote_min_score]
        if not candidates:
            print(f"[noon-refresh] no candidates for {schedule_at}")
            continue

        best = _pick_noon_latest_candidate(candidates, config)
        if not best:
            continue

        text = build_quote_post(config.model, best, tone=config.tone, audience=config.audience)
        if is_duplicate(text, memory):
            print(f"[noon-refresh] duplicate skipped schedule={schedule_at}")
            continue
        item["text"] = text
        item["source_tweet_id"] = best.tweet_id
        item["source_author"] = best.author
        item["last_refreshed_at"] = now.replace(microsecond=0).isoformat()
        item["refresh_mode"] = "jit_noon"
        changed += 1
        register_text(text, memory)
        print(
            "[noon-refresh] updated "
            f"schedule={schedule_at} "
            f"target={best.tweet_id} video={best.has_video} image={best.has_image}"
        )

    if changed and not dry_run:
        _save_queue(path, queue)
        save_memory(memory)
    print(f"[noon-refresh] changed={changed} dry_run={dry_run}")
    return changed
