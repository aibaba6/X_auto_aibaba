from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from .collectors import fetch_rss_items, filter_blocked
from .llm import build_noon_news_post
from .queue_store import load_queue_items, save_queue_items
from .schedule_utils import now_local, parse_scheduled_datetime
from .settings import AppConfig
from .uniqueness import is_duplicate, load_memory, register_text, save_memory

def refresh_noon_queue(config: AppConfig, queue_path: str, dry_run: bool = False) -> int:
    path = Path(queue_path)
    queue = load_queue_items(str(path))
    if not queue:
        print(f"[noon-refresh] queue not found or empty: {path}")
        return 0

    noon_profile = config.slot_profiles.get("noon", {})
    latest_mode = bool(noon_profile.get("latest_share_mode", False))
    capture_minutes = int(noon_profile.get("latest_capture_minutes_before", 30))
    if not latest_mode:
        print("[noon-refresh] latest_share_mode is false, skip")
        return 0

    now = now_local(config)
    changed = 0
    memory = load_memory(config.uniqueness_memory_path)
    source_items = fetch_rss_items(config.rss_feeds, max_items=config.max_input_items)
    source_items = filter_blocked(source_items, config.blocked_keywords)
    if not source_items:
        print("[noon-refresh] rss source is empty")
        return 0

    for item in queue:
        slot = str(item.get("slot", "")).strip()
        schedule_at = str(item.get("schedule_at", "")).strip()
        if slot != "noon" or not schedule_at:
            continue

        scheduled_dt = parse_scheduled_datetime(schedule_at, config)
        if not scheduled_dt:
            continue
        window_start = scheduled_dt - timedelta(minutes=capture_minutes)
        if not (window_start <= now < scheduled_dt):
            continue

        refreshed_at = parse_scheduled_datetime(str(item.get("last_refreshed_at", "")).strip(), config)
        if refreshed_at and (now - refreshed_at) < timedelta(minutes=10):
            continue

        subset = source_items[: min(5, len(source_items))]
        draft = build_noon_news_post(
            model=config.model,
            items=subset,
            tone=config.tone,
            audience=config.audience,
            prediction_horizon=config.prediction_horizon,
            weekday_theme=config.weekly_themes.get(now.strftime("%A").lower(), "通常テーマ"),
        )
        if not draft:
            print(f"[noon-refresh] draft build failed for {schedule_at}")
            continue

        text = draft.text
        if is_duplicate(text, memory):
            print(f"[noon-refresh] duplicate skipped schedule={schedule_at}")
            continue
        item["text"] = text
        item["source_tweet_id"] = ""
        item["source_author"] = "rss-summary"
        item["last_refreshed_at"] = now.replace(microsecond=0).isoformat()
        item["refresh_mode"] = "jit_noon"
        changed += 1
        register_text(text, memory)
        print(
            "[noon-refresh] updated "
            f"schedule={schedule_at} "
            f"reason={draft.reason or 'noon-news'}"
        )

    if changed and not dry_run:
        save_queue_items(str(path), queue)
        save_memory(memory)
    print(f"[noon-refresh] changed={changed} dry_run={dry_run}")
    return changed
