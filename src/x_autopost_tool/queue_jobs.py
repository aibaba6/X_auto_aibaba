from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from .collectors import fetch_rss_items, filter_blocked
from .llm import build_noon_news_candidates
from .queue_store import load_queue_items, save_queue_items
from .schedule_utils import now_local, parse_scheduled_datetime
from .settings import AppConfig
from .uniqueness import (
    duplicate_check,
    load_history,
    load_memory,
    register_text,
    save_memory,
    semantic_duplicate_check,
    semantic_summaries,
    strict_fingerprint,
)

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
    history = load_history(config.post_history_path)
    recent_noon_posts = [
        str(entry.get("text", "")).strip()
        for entry in reversed(history.entries)
        if str(entry.get("slot", "")).strip() == "noon" and str(entry.get("text", "")).strip()
    ][:8]
    recent_noon_semantics = semantic_summaries(history, slot="noon", limit=8)
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
        drafts = build_noon_news_candidates(
            model=config.model,
            items=subset,
            tone=config.tone,
            audience=config.audience,
            prediction_horizon=config.prediction_horizon,
            weekday_theme=config.weekly_themes.get(now.strftime("%A").lower(), "通常テーマ"),
            recent_self_posts=recent_noon_posts,
            recent_semantic_summaries=recent_noon_semantics,
            max_candidates=4,
        )
        if not drafts:
            print(f"[noon-refresh] draft build failed for {schedule_at}")
            continue

        text = ""
        reason = ""
        for attempt, draft in enumerate(drafts, start=1):
            print(f"[UNIQUE RETRY] attempt={attempt}")
            print(f"[SEMANTIC RETRY] attempt={attempt}")
            result = duplicate_check(draft.text, memory)
            if result.strict_duplicate:
                print("[UNIQUE REJECT] reason=strict_duplicate")
                continue
            if result.loose_duplicate:
                print("[UNIQUE REJECT] reason=loose_duplicate")
                continue
            semantic = semantic_duplicate_check(draft.text, history, slot="noon")
            if semantic.duplicate:
                print(f"[SEMANTIC REJECT] reason={semantic.reason}")
                continue
            text = draft.text
            reason = draft.reason or "noon-news"
            print(f"[UNIQUE PICKED] fingerprint={strict_fingerprint(text)}")
            print(f"[SEMANTIC PICKED] topic={semantic.candidate.topic[:80]}")
            break
        if not text:
            print(f"[UNIQUE HOLD] reason=no_unique_candidate schedule={schedule_at}")
            print(f"[SEMANTIC HOLD] reason=no_semantically_unique_candidate schedule={schedule_at}")
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
            f"reason={reason}"
        )

    if changed and not dry_run:
        save_queue_items(str(path), queue)
        save_memory(memory)
    print(f"[noon-refresh] changed={changed} dry_run={dry_run}")
    return changed
