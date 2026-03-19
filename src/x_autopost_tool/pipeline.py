from __future__ import annotations

from datetime import datetime
import time
from pathlib import Path

from .collectors import fetch_rss_items, filter_blocked, rank_quote_candidates
from .analytics_store import analytics_store_path, load_analytics, save_analytics, upsert_post_record
from .content_types import build_evening_type_drafts, build_morning_type_drafts, build_quote_fallback_drafts
from .llm import build_noon_news_candidates, build_post_drafts, build_quote_post, normalize_x_post_text
from .media_tools import generate_image_with_freepik_mystic, generate_image_with_nanobanana, generate_image_with_nanobanana_pro_api
from .models import ContentItem, DraftPost
from .pdf_knowledge import get_pdf_knowledge_snippets
from .quote_format import validate_quote_post
from .queue_store import load_queue_items, queue_sync_enabled, save_queue_items
from .schedule_utils import now_local, parse_scheduled_datetime
from .rules import filter_quote_candidates, score_quote_candidate, validate_post_draft
from .settings import AppConfig
from .uniqueness import (
    append_history,
    duplicate_check,
    evening_duplicate_check,
    history_content_types,
    history_fingerprints,
    history_pattern_types,
    history_idea_keys,
    history_topics,
    load_history,
    load_memory,
    loose_fingerprint,
    register_text,
    semantic_duplicate_check,
    semantic_stage_check,
    semantic_summaries,
    save_history,
    save_memory,
    strict_fingerprint,
)
from .x_client import XClient


def _weekday_key(now: datetime) -> str:
    keys = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    return keys[now.weekday()]


def _resolve_slot(now: datetime, forced_slot: str | None) -> str:
    if forced_slot:
        return forced_slot
    hour = now.hour
    if hour < 10:
        return "morning"
    if hour < 15:
        return "noon"
    return "evening"


def _fingerprints(texts: list[str], mode: str = "strict") -> set[str]:
    out: set[str] = set()
    for text in texts:
        value = (text or "").strip()
        if value:
            out.add(loose_fingerprint(value) if mode == "loose" else strict_fingerprint(value))
    return out


def _is_duplicate_candidate(
    text: str,
    memory,
    *,
    history=None,
    slot: str = "",
    generation_level: str = "strict",
    candidate_count: int = 0,
    recent_strict: set[str],
    recent_loose: set[str],
    posted_strict: set[str] | None = None,
    posted_loose: set[str] | None = None,
    check_posted_history: bool = True,
) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    result = duplicate_check(value, memory)
    print(
        "[HISTORY CHECK] "
        f"strict_dup={'yes' if result.strict_duplicate else 'no'} "
        f"loose_dup={'yes' if result.loose_duplicate else 'no'}"
    )
    if result.strict_duplicate:
        print("[UNIQUE REJECT] reason=strict_duplicate")
        return True
    if result.loose_duplicate:
        print("[UNIQUE REJECT] reason=loose_duplicate")
        return True
    if result.strict_fingerprint in recent_strict or result.loose_fingerprint in recent_loose:
        print("[UNIQUE REJECT] reason=recent_duplicate")
        return True
    if check_posted_history and posted_strict is not None and result.strict_fingerprint in posted_strict:
        print("[UNIQUE REJECT] reason=posted_strict_duplicate")
        return True
    if check_posted_history and posted_loose is not None and result.loose_fingerprint in posted_loose:
        print("[UNIQUE REJECT] reason=posted_loose_duplicate")
        return True
    if history is not None:
        effective_level = _candidate_gen_level(generation_level, candidate_count)
        print(f"[GEN LEVEL] {effective_level}")
        if slot == "evening" and effective_level == "strict":
            evening = evening_duplicate_check(value, history)
            if evening.duplicate:
                print(f"[EVENING REJECT] reason={evening.reason}")
                return True
        stage = semantic_stage_check(value, history, slot=slot or None)
        if stage.duplicate:
            print(f"[SEMANTIC REJECT] reason={stage.reason}")
            return True
        if stage.warning:
            print(f"[SEMANTIC CHECK] warning=yes reason={stage.reason}")
            if effective_level == "strict":
                return True
    return False


def _content_type_allowed(pattern_type: str, recent_types: list[str], *, slot: str) -> bool:
    normalized = (pattern_type or "").strip().lower()
    if not normalized:
        return True
    recent = [value.strip().lower() for value in recent_types if value]
    if not recent:
        return True
    window = 2 if slot == "evening" else 1
    blocked = recent[-window:]
    allowed = normalized not in blocked
    print(f"[CONTENT TYPE] type={normalized} recent={','.join(blocked) or '-'} allowed={'yes' if allowed else 'no'}")
    return allowed


def _candidate_gen_level(level: str, candidate_count: int) -> str:
    if level == "strict" and candidate_count >= 3:
        return "strict"
    if candidate_count < 3:
        return "relaxed"
    return level


def _fallback_draft(item: ContentItem, slot: str, horizon: str) -> DraftPost:
    title = item.title.replace("\n", " ").strip()
    if len(title) > 48:
        title = title[:48] + "..."

    if slot == "morning":
        text = (
            f"{title}は、要素を足す前に構造を減らす視点で見直すと整理しやすい。"
            f"{horizon}では、見た目の派手さより意図を説明できる設計が評価されやすい。"
            "1画面だけ再設計して差分を比べる。"
        )
    elif slot == "noon":
        text = (
            f"{title}は、機能数より運用設計の差が出やすい流れ。"
            f"{horizon}では試作速度より判断の任せ方が差になりやすい。1工程だけAI化して検証する。"
        )
    else:
        text = (
            f"{title}の場面ほど、完璧な正解より続けられる改善を先に決めたほうが崩れにくい。"
            f"{horizon}で差になりやすいのは一度に抱え込まない設計。次に迷わない一言だけ残す。"
        )
    content_type = "news" if slot == "noon" else ("basic" if slot == "morning" else "daily")
    return DraftPost(
        text=normalize_x_post_text(text, slot_name=slot),
        reason="fallback",
        content_type=content_type,
        pattern_type=content_type,
        topic=title,
        structure="一言断言型",
    )


def _short_fallback_draft(slot: str) -> DraftPost:
    if slot == "morning":
        text = "迷いを減らす設計ほど、見た目より先に効きます。\n役割が重なる要素を1つ外して比較する。\n\n#デザイン基礎 #UIデザイン #実務"
        return DraftPost(text=normalize_x_post_text(text, slot_name=slot), reason="short-fallback", content_type="design", pattern_type="practical", topic="判断を減らす設計", structure="一言断言型")
    if slot == "evening":
        text = "進める量より、迷いを減らせた日のほうが次につながります。\n明日の自分が迷わない一言だけ残す。\n\n#デザイン実務 #制作フロー #継続改善"
        return DraftPost(text=normalize_x_post_text(text, slot_name=slot), reason="short-fallback", content_type="design", pattern_type="insight", topic="迷いを減らす終わり方", structure="一言断言型")
    text = "機能を増やす前に、どの判断を軽くするかを見る。\n小さく試して差分を確認する。\n\n#AI #AIニュース #デザイン"
    return DraftPost(text=normalize_x_post_text(text, slot_name=slot), reason="short-fallback", content_type="news", pattern_type="news", topic="判断を軽くするAI活用", structure="一言断言型")


def _guaranteed_slot_draft(slot: str, d: date) -> DraftPost:
    if slot == "morning":
        text = (
            "情報を足す前に、役割の重なりを減らすほうが整います。\n"
            "主役と脇役の差だけ見直す。\n\n"
            "#デザイン基礎\n#UIデザイン\n#情報設計"
        )
        return DraftPost(
            text=normalize_x_post_text(text, slot_name="morning"),
            reason="guaranteed-fallback",
            content_type="design",
            pattern_type="timeless",
            topic="役割の重なりを減らす",
            structure="一言断言型",
        )
    if slot == "evening":
        text = (
            "進んだ量より、迷いを減らせた日のほうが次につながります。\n"
            "次に迷わない一言だけ残して終える。\n\n"
            "#デザイン実務\n#制作フロー\n#継続改善"
        )
        return DraftPost(
            text=normalize_x_post_text(text, slot_name="evening"),
            reason="guaranteed-fallback",
            content_type="design",
            pattern_type="practical",
            topic="迷いを減らす終わり方",
            structure="一言断言型",
        )
    return _short_fallback_draft(slot)


def _build_retry_batches(
    *,
    slot: str,
    items: list[ContentItem],
    seed: int,
    history_count: int,
    horizon: str,
) -> list[tuple[str, list[DraftPost]]]:
    if slot == "morning":
        return [
            ("strict", build_morning_type_drafts(seed=seed + history_count, max_candidates=12, preferred_types=["latest", "trend", "practical", "insight", "timeless", "quote"], items=items)),
            ("relaxed", build_morning_type_drafts(seed=seed + history_count + 19, max_candidates=12, preferred_types=["trend", "latest", "practical", "insight", "timeless", "quote"], items=items)),
            ("forced", build_quote_fallback_drafts(seed=seed + history_count + 37, max_candidates=4) + [_short_fallback_draft("morning")]),
        ]
    if slot == "evening":
        base_item = items[0] if items else ContentItem(source="", title="制作の終わり方", summary="", url="")
        return [
            ("strict", build_evening_type_drafts(items, seed=seed + history_count, max_candidates=14, preferred_types=["latest", "trend", "practical", "insight", "timeless", "quote"])),
            ("relaxed", build_evening_type_drafts(items, seed=seed + history_count + 17, max_candidates=14, preferred_types=["trend", "latest", "practical", "insight", "timeless", "quote"])),
            ("forced", build_evening_type_drafts(items, seed=seed + history_count + 31, max_candidates=10, preferred_types=["latest", "trend", "practical", "insight", "quote"]) + build_quote_fallback_drafts(seed=seed + history_count + 43, max_candidates=2) + [_fallback_draft(base_item, "evening", horizon), _short_fallback_draft("evening")]),
        ]
    base_item = items[0] if items else ContentItem(source="", title="AI運用の設計", summary="", url="")
    return [("forced", [_fallback_draft(base_item, slot, horizon), _short_fallback_draft(slot)])]


def _validate_quote_candidate(draft: DraftPost) -> bool:
    if draft.content_type != "quote":
        return True
    ok, checks = validate_quote_post(draft.text)
    print(
        "[QUOTE VALIDATE] "
        f"english={'yes' if checks['english'] else 'no'} "
        f"translation={'yes' if checks['translation'] else 'no'} "
        f"author={'yes' if checks['author'] else 'no'} "
        f"spacing_ok={'yes' if checks['spacing_ok'] else 'no'}"
    )
    print(f"[QUOTE FORMAT] ok={'yes' if ok else 'no'}")
    if not ok:
        print("[QUOTE REPAIR] action=reject_candidate")
    return ok


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


def _rank_noon_latest_candidates(candidates, config: AppConfig):
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
        images = [c for c in ranked if c.has_image]
        others = [c for c in ranked if c not in videos and c not in images]
        if videos:
            return videos + (images if config.quote_fallback_to_image else []) + others
    return ranked


def _is_transient_media_error(err: str) -> bool:
    e = (err or "").lower()
    return any(k in e for k in ["503", "unavailable", "high demand", "try again later"])


def _safe_search_multi(x: XClient, queries: list[str], per_query: int, label: str):
    try:
        return x.search_multi(queries, per_query=per_query)
    except Exception as e:
        print(f"[X SEARCH ERROR] {label}: {e}")
        return []


def _safe_create_post(
    x: XClient,
    text: str,
    label: str,
    quote_tweet_id: str | None = None,
    media_paths: list[str] | None = None,
) -> str | None:
    try:
        return x.create_post(text, quote_tweet_id=quote_tweet_id, media_paths=media_paths)
    except Exception as e:
        print(f"[X POST ERROR] {label}: {e}")
        return None


def _try_create_post(
    x: XClient,
    text: str,
    quote_tweet_id: str | None = None,
    media_paths: list[str] | None = None,
) -> tuple[str | None, str | None]:
    try:
        post_id = x.create_post(text, quote_tweet_id=quote_tweet_id, media_paths=media_paths)
        return post_id, None
    except Exception as e:
        return None, str(e)


def _is_quote_forbidden_error(err: str | None) -> bool:
    if not err:
        return False
    lowered = err.lower()
    return "403" in lowered and "quoting this post is not allowed" in lowered


def _safe_create_reply(x: XClient, text: str, in_reply_to_tweet_id: str, label: str) -> str | None:
    try:
        return x.create_reply(text, in_reply_to_tweet_id=in_reply_to_tweet_id)
    except Exception as e:
        print(f"[X REPLY ERROR] {label}: {e}")
        return None


def _record_post_analytics(
    config: AppConfig,
    *,
    tweet_id: str,
    posted_at: str,
    text: str,
    slot: str,
    source: str,
    has_media: bool,
    content_type: str = "",
    pattern_type: str = "",
    topic: str = "",
    claim: str = "",
    structure: str = "",
) -> None:
    analytics = load_analytics(analytics_store_path(config.post_history_path))
    upsert_post_record(
        analytics,
        tweet_id=tweet_id,
        posted_at=posted_at,
        text=text,
        slot=slot,
        source=source,
        has_media=has_media,
        content_type=content_type,
        pattern_type=pattern_type,
        topic=topic,
        claim=claim,
        structure=structure,
    )
    save_analytics(analytics)


def _queue_item_id(item: dict) -> str:
    return str(item.get("id", "")).strip() or "-"


def _find_due_queue_item(
    items: list[dict], slot: str, now: datetime, config: AppConfig
) -> tuple[str, tuple[int, dict] | None, str | None]:
    matches: list[tuple[datetime, int, dict]] = []
    slot_items = 0
    malformed_reasons: list[str] = []
    print(f"[QUEUE DUE CHECK] now={now.replace(microsecond=0).isoformat()} slot={slot}")
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_slot = str(item.get("slot", "")).strip()
        if item_slot != slot:
            continue
        slot_items += 1
        item_id = _queue_item_id(item)
        schedule_at = str(item.get("schedule_at", "")).strip()
        status = str(item.get("status", "scheduled")).strip() or "scheduled"
        posted = bool(item.get("posted", False))
        print(f"[QUEUE SYNC ITEM] id={item_id} slot={item_slot} schedule_at={schedule_at or '-'}")
        if posted or status == "posted":
            print(f"[QUEUE DUE CHECK] id={item_id} scheduled=- due=no reason=already_posted")
            continue
        if not schedule_at:
            print(f"[QUEUE HOLD] reason=missing_schedule_at id={item_id}")
            malformed_reasons.append(f"missing_schedule_at:id={item_id}")
            continue
        due_at = parse_scheduled_datetime(schedule_at, config)
        if not due_at:
            print(f"[QUEUE HOLD] reason=parse_failed id={item_id} schedule_at={schedule_at}")
            malformed_reasons.append(f"parse_failed:id={item_id}")
            continue
        is_due = due_at <= now
        print(
            "[QUEUE DUE CHECK] "
            f"id={item_id} "
            f"scheduled={due_at.replace(microsecond=0).isoformat()} "
            f"due={'yes' if is_due else 'no'}"
        )
        if is_due:
            matches.append((due_at, idx, item))
    if matches:
        matches.sort(key=lambda x: x[0])
        _due_at, idx, item = matches[0]
        print(f"[QUEUE PICKED] id={_queue_item_id(item)} slot={slot}")
        return "picked", (idx, item), None
    if malformed_reasons:
        return "hold", None, ",".join(malformed_reasons)
    if slot_items:
        return "no_due", None, "no_due_items"
    return "empty", None, "no_slot_items"


def _resolve_media_path(raw_path: str) -> str | None:
    value = (raw_path or "").strip()
    if not value:
        return None
    path = Path(value).resolve()
    if not path.exists():
        print(f"[QUEUE SKIP] 添付画像が見つかりません: {value}")
        return None
    return str(path)


def _post_due_queue_item(
    x: XClient,
    config: AppConfig,
    resolved_slot: str,
    now: datetime,
    memory,
    queue_path: str | None,
    recent_self_posts: list[str] | None = None,
) -> str:
    if not queue_path and not queue_sync_enabled():
        print("[QUEUE SKIP] queue_path未設定")
        return "no_due"
    queue_label = queue_path or "remote-sync"
    if not queue_sync_enabled():
        from pathlib import Path

        queue_file = Path(queue_path)
        queue_label = str(queue_file)
        if not queue_file.exists():
            print(f"[QUEUE SKIP] queue file not found: {queue_file}")
            return "no_due"
    queue = load_queue_items(queue_path)
    if not queue:
        print(f"[QUEUE SKIP] queue file not found: {queue_label}")
        return "no_due"
    state, found, reason = _find_due_queue_item(queue, resolved_slot, now, config)
    if state == "empty":
        print(f"[QUEUE FALLBACK] reason=no_due_items_only slot={resolved_slot} items={len(queue)}")
        return "no_due"
    if state == "no_due":
        print(f"[QUEUE FALLBACK] reason=no_due_items_only slot={resolved_slot} items={len(queue)}")
        return "no_due"
    if state == "hold" or not found:
        print(f"[QUEUE HOLD] reason={reason or 'queue_item_invalid'} slot={resolved_slot}")
        return "hold"

    idx, item = found
    item_id = _queue_item_id(item)
    text = str(item.get("text", "")).strip()
    refresh_mode = str(item.get("refresh_mode", "")).strip()
    if not text and refresh_mode == "jit_noon" and resolved_slot == "noon":
        history = load_history(config.post_history_path)
        posted_slot_fingerprints = history_fingerprints(history, slot=resolved_slot, mode="strict")
        posted_slot_loose_fingerprints = history_fingerprints(history, slot=resolved_slot, mode="loose")
        recent_semantic = semantic_summaries(history, slot=resolved_slot, limit=8)
        recent_strict = _fingerprints(recent_self_posts or [], mode="strict")
        recent_loose = _fingerprints(recent_self_posts or [], mode="loose")
        source_items = fetch_rss_items(config.rss_feeds, max_items=config.max_input_items)
        source_items = filter_blocked(source_items, config.blocked_keywords)
        weekday_theme = config.weekly_themes.get(_weekday_key(now), "通常テーマ")
        drafts = build_noon_news_candidates(
            model=config.model,
            items=source_items[: min(5, len(source_items))],
            tone=config.tone,
            audience=config.audience,
            prediction_horizon=config.prediction_horizon,
            weekday_theme=weekday_theme,
            recent_self_posts=recent_self_posts,
            recent_semantic_summaries=recent_semantic,
            max_candidates=4,
        )
        picked = None
        for attempt, draft in enumerate(drafts, start=1):
            print(f"[UNIQUE RETRY] attempt={attempt}")
            print(f"[SEMANTIC RETRY] attempt={attempt}")
            if _is_duplicate_candidate(
                draft.text,
                memory,
                history=history,
                slot=resolved_slot,
                recent_strict=recent_strict,
                recent_loose=recent_loose,
                posted_strict=posted_slot_fingerprints,
                posted_loose=posted_slot_loose_fingerprints,
            ):
                continue
            picked = draft
            print(f"[UNIQUE PICKED] fingerprint={strict_fingerprint(draft.text)}")
            semantic = semantic_duplicate_check(draft.text, history, slot=resolved_slot)
            print(f"[SEMANTIC PICKED] topic={semantic.candidate.topic[:80]}")
            break
        if picked:
            text = picked.text
            item["text"] = text
            item["last_refreshed_at"] = now.replace(microsecond=0).isoformat()
            save_queue_items(queue_path, queue)
            print(
                f"[QUEUE REFRESH] id={item_id} slot=noon schedule_at={item.get('schedule_at', '')} reason={picked.reason}"
            )
        else:
            print(f"[UNIQUE HOLD] reason=no_unique_candidate slot=noon id={item_id}")
            print(f"[SEMANTIC HOLD] reason=no_semantically_unique_candidate slot=noon id={item_id}")
    if not text:
        print(
            "[QUEUE HOLD] "
            f"id={item_id} slot={resolved_slot} schedule_at={item.get('schedule_at', '')} refresh_mode={refresh_mode or 'none'}"
        )
        return "hold"

    media_path = _resolve_media_path(str(item.get("media_path", "")))
    if str(item.get("media_path", "")).strip() and not media_path:
        print(f"[QUEUE HOLD] reason=media_resolve_failed id={item_id} path={item.get('media_path', '')}")
        return "hold"
    media_paths = [media_path] if media_path else None
    reply_text = str(item.get("reply_text", "")).strip()
    print(
        "[QUEUE POST] "
        f"id={item_id} "
        f"slot={resolved_slot} "
        f"schedule_at={item.get('schedule_at', '')} "
        f"media={'yes' if media_paths else 'no'} "
        f"media_path={media_path or '-'} "
        f"reply={'yes' if reply_text else 'no'}"
    )

    if config.dry_run:
        reply_info = f"\n  reply: {reply_text}" if reply_text else ""
        media_info = f"\n  media: {media_paths}" if media_paths else ""
        print(f"[DRY-RUN QUEUE POST] {text}{media_info}{reply_info}")
        return "posted"

    tweet_id = _safe_create_post(x, text, label=f"queue-post-{resolved_slot}", media_paths=media_paths)
    if not tweet_id:
        print(f"[QUEUE HOLD] reason=post_failed id={item_id}")
        return "hold"
    if reply_text:
        _safe_create_reply(x, reply_text, in_reply_to_tweet_id=tweet_id, label=f"queue-reply-{resolved_slot}")
    register_text(text, memory)
    save_memory(memory)
    history = load_history(config.post_history_path)
    append_history(
        text,
        history,
        slot=resolved_slot,
        source="queue-post",
        tweet_id=tweet_id,
        posted_at=now.isoformat(),
        content_type=str(item.get("content_type", "")).strip(),
        pattern_type=str(item.get("pattern_type", item.get("content_type", ""))).strip(),
        topic=str(item.get("topic", "")).strip(),
        angle=str(item.get("angle", "")).strip(),
        pattern_id=str(item.get("pattern_id", "")).strip(),
    )
    save_history(history)
    _record_post_analytics(
        config,
        tweet_id=tweet_id,
        posted_at=now.isoformat(),
        text=text,
        slot=resolved_slot,
        source="queue-post",
        has_media=bool(media_paths),
        content_type=str(item.get("content_type", "")).strip(),
        pattern_type=str(item.get("pattern_type", item.get("content_type", ""))).strip(),
        topic=str(item.get("topic", "")).strip(),
        claim=str(item.get("claim", "")).strip(),
        structure=str(item.get("pattern_id", "")).strip() or str(item.get("structure", "")).strip(),
    )
    item["posted"] = True
    item["status"] = "posted"
    item["posted_at"] = now.replace(microsecond=0).isoformat()
    print(f"[QUEUE MARK POSTED] id={item_id} tweet_id={tweet_id}")
    del queue[idx]
    save_queue_items(queue_path, queue)
    print(f"queue posted: {tweet_id}")
    return "posted"


def run_once(config: AppConfig, slot: str | None = None, queue_path: str | None = None) -> None:
    now = now_local(config)
    today_key = _weekday_key(now)
    weekday_theme = config.weekly_themes.get(today_key, "速報と実務示唆を重視した通常投稿")
    resolved_slot = _resolve_slot(now, slot)
    slot_profile = config.slot_profiles.get(resolved_slot, {})
    slot_style = str(slot_profile.get("style", "通常枠"))
    slot_min_chars = int(slot_profile.get("min_chars", config.min_post_chars))
    slot_max_chars = int(slot_profile.get("max_chars", config.max_post_chars))
    slot_posts_per_run = int(slot_profile.get("posts_per_run", config.max_posts_per_run))
    slot_enable_quote = bool(slot_profile.get("enable_quote_posts", config.enable_quote_posts))
    slot_latest_share_mode = bool(slot_profile.get("latest_share_mode", True if resolved_slot == "noon" else False))
    print(f"[theme] {today_key}: {weekday_theme}")
    print(f"[slot] {resolved_slot}: {slot_style}")
    memory = load_memory(config.uniqueness_memory_path)
    history = load_history(config.post_history_path)
    print(f"[HISTORY LOAD] count={len(history.entries)}")
    posted_slot_fingerprints = history_fingerprints(history, slot=resolved_slot, mode="strict")
    posted_slot_loose_fingerprints = history_fingerprints(history, slot=resolved_slot, mode="loose")
    recent_semantic = semantic_summaries(history, slot=resolved_slot, limit=10)
    recent_content_types = history_pattern_types(history, slot=resolved_slot, limit=6)
    recent_idea_keys = history_idea_keys(history, slot=resolved_slot, limit=40)
    posted_topics = history_topics(history, slot=resolved_slot)
    memory_changed = False
    history_changed = False
    x = XClient()
    recent_self_posts = x.recent_self_posts(limit=12)
    recent_post_fingerprints = _fingerprints(recent_self_posts, mode="strict")
    recent_post_loose_fingerprints = _fingerprints(recent_self_posts, mode="loose")
    print(f"[RECENT POSTS] count={len(recent_self_posts)}")

    queue_result = _post_due_queue_item(x, config, resolved_slot, now, memory, queue_path, recent_self_posts=recent_self_posts)
    if queue_result == "posted":
        return
    if queue_result == "hold":
        return

    print("[1/5] RSS収集")
    items = fetch_rss_items(config.rss_feeds, max_items=config.max_input_items)
    items = filter_blocked(items, config.blocked_keywords)
    print(f"- items: {len(items)}")
    pdf_knowledge = get_pdf_knowledge_snippets(
        max_docs=3,
        max_chars_per_doc=700,
        slot_name=resolved_slot,
    )
    if pdf_knowledge:
        print(f"- pdf_knowledge: {len(pdf_knowledge)} docs")

    if not items:
        if resolved_slot in {"morning", "evening"}:
            print(f"[GEN SOURCE] slot={resolved_slot} rss_empty=yes static_only=yes")
        else:
            print(f"[GEN SOURCE] slot={resolved_slot} rss_empty=yes fallback_only=yes")

    if resolved_slot == "noon" and slot_latest_share_mode:
        if not items:
            fallback_noon = _short_fallback_draft("noon")
            print("[FALLBACK USED] type=news-short-empty-source")
            if config.dry_run:
                print(f"[DRY-RUN NOON FALLBACK] {fallback_noon.text}")
                return
            tweet_id = _safe_create_post(x, fallback_noon.text, label="main-post-noon-empty-source")
            if tweet_id:
                register_text(fallback_noon.text, memory)
                save_memory(memory)
                append_history(
                    fallback_noon.text,
                    history,
                    slot="noon",
                    source="noon-empty-source-fallback",
                    tweet_id=tweet_id,
                    posted_at=now.isoformat(),
                    content_type=fallback_noon.content_type,
                    pattern_type=fallback_noon.pattern_type,
                    topic=fallback_noon.topic,
                    angle=fallback_noon.angle,
                    pattern_id=fallback_noon.structure,
                )
                save_history(history)
                _record_post_analytics(
                    config,
                    tweet_id=tweet_id,
                    posted_at=now.isoformat(),
                    text=fallback_noon.text,
                    slot="noon",
                    source="noon-empty-source-fallback",
                    has_media=False,
                    content_type=fallback_noon.content_type,
                    pattern_type=fallback_noon.pattern_type,
                    topic=fallback_noon.topic,
                    claim=fallback_noon.claim,
                    structure=fallback_noon.structure,
                )
                print(f"noon fallback posted: {tweet_id}")
                return
            print("[NO POST GENERATED] reason=noon_empty_source_post_failed")
            print("[UNIQUE HOLD] reason=no_unique_candidate slot=noon")
            print("[SEMANTIC HOLD] reason=no_semantically_unique_candidate slot=noon")
            return
        print("[2/5] 昼枠: AIニュース要約投稿を生成")
        noon_candidates = build_noon_news_candidates(
            model=config.model,
            items=items[: min(5, len(items))],
            tone=config.tone,
            audience=config.audience,
            prediction_horizon=config.prediction_horizon,
            weekday_theme=weekday_theme,
            recent_self_posts=recent_self_posts,
            recent_semantic_summaries=recent_semantic,
            max_candidates=max(4, slot_posts_per_run * 3),
        )
        picked_noon = None
        for attempt, noon_draft in enumerate(noon_candidates, start=1):
            print(f"[UNIQUE RETRY] attempt={attempt}")
            print(f"[SEMANTIC RETRY] attempt={attempt}")
            if _is_duplicate_candidate(
                noon_draft.text,
                memory,
                history=history,
                slot=resolved_slot,
                recent_strict=recent_post_fingerprints,
                recent_loose=recent_post_loose_fingerprints,
                posted_strict=posted_slot_fingerprints,
                posted_loose=posted_slot_loose_fingerprints,
            ):
                continue
            picked_noon = noon_draft
            print(f"[UNIQUE PICKED] fingerprint={strict_fingerprint(noon_draft.text)}")
            semantic = semantic_duplicate_check(noon_draft.text, history, slot=resolved_slot)
            print(f"[SEMANTIC PICKED] topic={semantic.candidate.topic[:80]}")
            break
        if picked_noon:
            if config.dry_run:
                print(f"[DRY-RUN NOON NEWS] {picked_noon.text}")
                return
            else:
                tweet_id = _safe_create_post(x, picked_noon.text, label="main-post-noon-news")
                if tweet_id:
                    register_text(picked_noon.text, memory)
                    save_memory(memory)
                    append_history(
                        picked_noon.text,
                        history,
                        slot="noon",
                        source="noon-news",
                        tweet_id=tweet_id,
                        posted_at=now.isoformat(),
                        content_type="news",
                        pattern_type=getattr(picked_noon, "pattern_type", "news"),
                        topic=getattr(picked_noon, "topic", ""),
                        angle=getattr(picked_noon, "angle", ""),
                        pattern_id=getattr(picked_noon, "structure", ""),
                    )
                    posted_slot_fingerprints.add(strict_fingerprint(picked_noon.text))
                    posted_slot_loose_fingerprints.add(loose_fingerprint(picked_noon.text))
                    save_history(history)
                    _record_post_analytics(
                        config,
                        tweet_id=tweet_id,
                        posted_at=now.isoformat(),
                        text=picked_noon.text,
                        slot="noon",
                        source="noon-news",
                        has_media=False,
                        content_type="news",
                        pattern_type=getattr(picked_noon, "pattern_type", "news"),
                        topic=getattr(picked_noon, "topic", ""),
                        claim=getattr(picked_noon, "claim", ""),
                        structure=getattr(picked_noon, "structure", ""),
                    )
                    print(f"noon news posted: {tweet_id}")
                    return
        fallback_noon = _short_fallback_draft("noon")
        print("[FALLBACK USED] type=news-short")
        if config.dry_run:
            print(f"[DRY-RUN NOON FALLBACK] {fallback_noon.text}")
            return
        tweet_id = _safe_create_post(x, fallback_noon.text, label="main-post-noon-fallback")
        if tweet_id:
            register_text(fallback_noon.text, memory)
            save_memory(memory)
            append_history(
                fallback_noon.text,
                history,
                slot="noon",
                source="noon-fallback",
                tweet_id=tweet_id,
                posted_at=now.isoformat(),
                content_type=fallback_noon.content_type,
                pattern_type=fallback_noon.pattern_type,
                topic=fallback_noon.topic,
                angle=fallback_noon.angle,
                pattern_id=fallback_noon.structure,
            )
            save_history(history)
            _record_post_analytics(
                config,
                tweet_id=tweet_id,
                posted_at=now.isoformat(),
                text=fallback_noon.text,
                slot="noon",
                source="noon-fallback",
                has_media=False,
                content_type=fallback_noon.content_type,
                pattern_type=fallback_noon.pattern_type,
                topic=fallback_noon.topic,
                claim=fallback_noon.claim,
                structure=fallback_noon.structure,
            )
            print(f"noon fallback posted: {tweet_id}")
            return
        print("[UNIQUE HOLD] reason=no_unique_candidate slot=noon")
        print("[SEMANTIC HOLD] reason=no_semantically_unique_candidate slot=noon")
        return

    print("[2/5] 投稿案生成")
    print(f"[GEN START] slot={resolved_slot} type=auto")
    passed_drafts = []
    if resolved_slot in {"morning", "evening"}:
        retry_batches = _build_retry_batches(
            slot=resolved_slot,
            items=items,
            seed=now.toordinal() * (13 if resolved_slot == "evening" else 7),
            history_count=len(history.entries),
            horizon=config.prediction_horizon,
        )
    else:
        retry_batches = [
            (
                "strict",
                build_post_drafts(
                    model=config.model,
                    items=items,
                    tone=config.tone,
                    audience=config.audience,
                    prediction_horizon=config.prediction_horizon,
                    post_style_template=config.post_style_template,
                    voice_guide=config.voice_guide,
                    style_reference_posts=config.style_reference_posts,
                    weekday_theme=weekday_theme,
                    slot_name=resolved_slot,
                    slot_style=slot_style,
                    slot_min_chars=slot_min_chars,
                    slot_max_chars=slot_max_chars,
                    max_posts=slot_posts_per_run,
                    knowledge_snippets=pdf_knowledge,
                    recent_self_posts=recent_self_posts,
                    recent_semantic_summaries=recent_semantic,
                ),
            ),
            ("forced", [_fallback_draft(items[0], resolved_slot, config.prediction_horizon), _short_fallback_draft(resolved_slot)]),
        ]

    for step, (level, drafts) in enumerate(retry_batches, start=1):
        print(f"[RETRY LEVEL] step={step}")
        print(f"[GEN CANDIDATES] count={len(drafts)}")
        if not drafts and items:
            drafts = [_fallback_draft(items[0], resolved_slot, config.prediction_horizon)]
        for attempt, d in enumerate(drafts, start=1):
            print(f"[UNIQUE RETRY] attempt={attempt}")
            print(f"[SEMANTIC RETRY] attempt={attempt}")
            pattern_key = (d.pattern_type or d.content_type or "").strip().lower()
            if level != "forced" and pattern_key and not _content_type_allowed(pattern_key, recent_content_types, slot=resolved_slot):
                print(f"[UNIQUE REJECT] reason=content_type_repeat type={pattern_key}")
                continue
            ok, reasons = validate_post_draft(d, config, min_chars=slot_min_chars, max_chars=slot_max_chars)
            if not ok:
                print(f"[GEN REJECT] reason={','.join(reasons)}")
                print(f"[DROP DRAFT] {','.join(reasons)}")
                continue
            if not _validate_quote_candidate(d):
                print("[GEN REJECT] reason=quote_format_invalid")
                continue
            idea_key = ((d.topic or "").strip().lower(), (d.claim or "").strip().lower(), (d.angle or "").strip().lower())
            print(f"[IDEA] topic={d.topic[:80] if d.topic else '-'} claim={d.claim[:80] if d.claim else '-'} angle={d.angle[:80] if d.angle else '-'}")
            print(f"[PATTERN] {d.pattern_type or d.content_type or '-'}")
            print(f"[STRUCTURE] {d.structure or '-'}")
            topic_key = (d.topic or "").strip().lower()
            if topic_key and topic_key in posted_topics:
                print("[DUPLICATE REJECT] reason=topic_duplicate")
                print("[HISTORY REJECT] reason=topic_duplicate")
                continue
            if any(idea_key) and idea_key in recent_idea_keys:
                print("[DUPLICATE REJECT] reason=idea_duplicate")
                print("[HISTORY REJECT] reason=idea_duplicate")
                continue
            if _is_duplicate_candidate(
                d.text,
                memory,
                history=history,
                slot=resolved_slot,
                generation_level=level,
                candidate_count=len(drafts),
                recent_strict=recent_post_fingerprints,
                recent_loose=recent_post_loose_fingerprints,
                posted_strict=posted_slot_fingerprints,
                posted_loose=posted_slot_loose_fingerprints,
                check_posted_history=True,
            ):
                print("[HISTORY REJECT] reason=duplicate_candidate")
                continue
            if d.pattern_type or d.content_type:
                print(f"[PATTERN PICK] slot={resolved_slot} pattern={d.pattern_type or d.content_type}")
            if d.content_type:
                print(f"[PICKED TYPE] type={d.content_type}")
            if d.topic:
                print(f"[TOPIC] {d.topic[:120]}")
            if d.claim:
                print(f"[CLAIM] {d.claim[:120]}")
            if d.structure:
                print(f"[STRUCTURE] {d.structure}")
            if d.pattern_type == "trend" and d.topic:
                print(f"[TREND SOURCE] {d.topic[:120]}")
            if level == "forced" and d.content_type == "quote":
                print("[FALLBACK USED] type=quote")
            print(f"[FINAL PICK] slot={resolved_slot} pattern={d.pattern_type or d.content_type} topic={d.topic[:80] if d.topic else '-'}")
            print(f"[UNIQUE PICKED] fingerprint={strict_fingerprint(d.text)}")
            semantic = semantic_duplicate_check(d.text, history, slot=resolved_slot)
            print(f"[SEMANTIC PICKED] topic={semantic.candidate.topic[:80]}")
            if resolved_slot == "evening":
                print(
                    f"[EVENING PICKED] hook={semantic.candidate.hook[:60]} "
                    f"structure={semantic.candidate.structure} "
                    f"claim={semantic.candidate.claim[:60]}"
                )
            passed_drafts.append(d)
            if d.content_type:
                recent_content_types.append(d.pattern_type or d.content_type)
            if topic_key:
                posted_topics.add(topic_key)
            if any(idea_key):
                recent_idea_keys.add(idea_key)
            break
        if passed_drafts:
            break
    if not passed_drafts:
        if resolved_slot in {"morning", "evening"}:
            forced = _guaranteed_slot_draft(resolved_slot, now.date())
            print(f"[FALLBACK USED] type={forced.content_type or resolved_slot}-guaranteed")
            print(f"[FINAL PICK] type={forced.content_type or resolved_slot}")
            passed_drafts.append(forced)
        else:
            print(f"[NO POST GENERATED] reason=all_candidates_rejected slot={resolved_slot}")
            print(f"[UNIQUE HOLD] reason=no_unique_candidate slot={resolved_slot}")
            print(f"[SEMANTIC HOLD] reason=no_semantically_unique_candidate slot={resolved_slot}")
            if resolved_slot == "evening":
                print("[EVENING HOLD] reason=no_unique_evening_candidate")
            return

    print("[3/5] 通常投稿")
    for i, d in enumerate(passed_drafts, start=1):
        if not _validate_quote_candidate(d):
            print("[GEN REJECT] reason=quote_format_invalid_before_post")
            continue
        media_paths: list[str] | None = None
        if config.media_enabled and resolved_slot == "morning" and config.media_morning_generate_image:
            provider = config.media_morning_image_provider
            attempts = max(1, config.media_morning_retry_max_attempts)
            delay_sec = max(1, config.media_morning_retry_delay_minutes) * 60
            for a in range(1, attempts + 1):
                if provider == "freepik_mystic":
                    media_path, _mode, err = generate_image_with_freepik_mystic(
                        d.text, config.media_morning_image_output_dir
                    )
                    print("[MEDIA GEN] provider=freepik_mystic model=freepik_mystic")
                elif provider == "nanobanana_pro":
                    media_path, _mode, err, meta = generate_image_with_nanobanana_pro_api(
                        d.text, config.media_morning_image_output_dir
                    )
                    print(
                        "[MEDIA GEN] "
                        f"requested={meta.get('provider_requested')} "
                        f"used={meta.get('provider_used')} "
                        f"model={meta.get('model_used')} "
                        f"fallback={'yes' if meta.get('fallback_used') else 'no'}"
                    )
                else:
                    media_path, _mode, err = generate_image_with_nanobanana(
                        d.text, config.media_morning_image_output_dir
                    )
                    print("[MEDIA GEN] provider=nanobanana_cmd model=nanobanana_cmd")
                if media_path:
                    media_paths = [media_path]
                    break
                if provider not in {"nanobanana_cmd", "nanobanana_pro"}:
                    break
                if not config.media_morning_retry_on_503:
                    break
                if _is_transient_media_error(err) and a < attempts:
                    print(f"[MEDIA RETRY] 503系エラーのため {config.media_morning_retry_delay_minutes}分後に再試行 ({a}/{attempts})")
                    if config.dry_run:
                        continue
                    time.sleep(delay_sec)
                    continue
                break

        if config.dry_run:
            media_info = f"\n  media: {media_paths}" if media_paths else ""
            print(f"[DRY-RUN POST {i}] {d.text}\n  reason: {d.reason}{media_info}")
            continue
        tweet_id = _safe_create_post(x, d.text, label=f"main-post-{resolved_slot}-{i}", media_paths=media_paths)
        if not tweet_id:
            continue
        register_text(d.text, memory)
        memory_changed = True
        append_history(
            d.text,
            history,
            slot=resolved_slot,
            source="main-post",
            tweet_id=tweet_id,
            posted_at=now.isoformat(),
            content_type=d.content_type,
            pattern_type=d.pattern_type,
            topic=d.topic,
            angle=d.angle,
            pattern_id=d.structure,
        )
        _record_post_analytics(
            config,
            tweet_id=tweet_id,
            posted_at=now.isoformat(),
            text=d.text,
            slot=resolved_slot,
            source="main-post",
            has_media=bool(media_paths),
            content_type=d.content_type,
            pattern_type=d.pattern_type,
            topic=d.topic,
            claim=d.claim,
            structure=d.structure,
        )
        posted_slot_fingerprints.add(strict_fingerprint(d.text))
        posted_slot_loose_fingerprints.add(loose_fingerprint(d.text))
        history_changed = True
        print(f"[FINAL PICK] slot={resolved_slot} pattern={d.pattern_type or d.content_type or resolved_slot} type={d.content_type or resolved_slot}")
        print(f"posted: {tweet_id}")

    # Noon latest-share mode should either quote a fresh AI post or fall back to
    # a single normal post. Do not also run the generic quote pipeline.
    if resolved_slot == "noon" and slot_latest_share_mode:
        if memory_changed:
            save_memory(memory)
        if history_changed:
            save_history(history)
        return

    if not slot_enable_quote:
        return

    print("[4/5] 引用候補検索")
    candidates = _safe_search_multi(
        x, config.x_search_queries, per_query=config.quote_candidates_limit, label="quote-candidates"
    )
    candidates = filter_quote_candidates(candidates, config)
    candidates = rank_quote_candidates(candidates, limit=config.quote_candidates_limit)
    candidates = [c for c in candidates if score_quote_candidate(c, config) >= config.quote_min_score]
    if not candidates:
        print("候補なし")
        return

    print(f"[5/5] 引用投稿生成 count={config.max_quote_posts_per_run}")
    posted_quotes = 0
    for c in candidates:
        if posted_quotes >= config.max_quote_posts_per_run:
            break
        quote_text = build_quote_post(config.model, c, tone=config.tone, audience=config.audience)
        if _is_duplicate_candidate(
            quote_text,
            memory,
            history=history,
            slot=resolved_slot,
            recent_strict=recent_post_fingerprints,
            recent_loose=recent_post_loose_fingerprints,
            check_posted_history=False,
        ):
            print(f"[SKIP QUOTE] 重複投稿 target={c.tweet_id}")
            continue
        if config.dry_run:
            print(f"[DRY-RUN QUOTE] {quote_text}\n  quote_tweet_id={c.tweet_id}")
            posted_quotes += 1
            continue
        quote_id = _safe_create_post(x, quote_text, label=f"quote-post-{c.tweet_id}", quote_tweet_id=c.tweet_id)
        if not quote_id:
            continue
        register_text(quote_text, memory)
        memory_changed = True
        append_history(
            quote_text,
            history,
            slot=resolved_slot,
            source="quote-post",
            tweet_id=quote_id,
            posted_at=now.isoformat(),
            content_type="quote",
            pattern_type="quote",
            angle="外部投稿を自分の視点で補足する",
        )
        _record_post_analytics(
            config,
            tweet_id=quote_id,
            posted_at=now.isoformat(),
            text=quote_text,
            slot=resolved_slot,
            source="quote-post",
            has_media=False,
            content_type="quote",
            pattern_type="quote",
            topic=c.author,
            claim="外部投稿を自分の視点で補足する",
            structure="引用解釈型",
        )
        history_changed = True
        posted_quotes += 1
        print(f"quote posted: {quote_id}")

    if memory_changed:
        save_memory(memory)
    if history_changed:
        save_history(history)
