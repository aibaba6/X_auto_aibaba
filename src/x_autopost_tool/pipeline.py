from __future__ import annotations

from datetime import datetime
import time
from pathlib import Path

from .collectors import fetch_rss_items, filter_blocked, rank_quote_candidates
from .llm import build_noon_news_post, build_post_drafts, build_quote_post
from .media_tools import generate_image_with_freepik_mystic, generate_image_with_nanobanana
from .models import ContentItem, DraftPost
from .pdf_knowledge import get_pdf_knowledge_snippets
from .queue_store import load_queue_items, queue_sync_enabled, save_queue_items
from .schedule_utils import now_local, parse_scheduled_datetime
from .rules import filter_quote_candidates, score_quote_candidate, validate_post_draft
from .settings import AppConfig
from .uniqueness import append_history, fingerprint, history_fingerprints, is_duplicate, load_history, load_memory, register_text, save_history, save_memory
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


def _fingerprints(texts: list[str]) -> set[str]:
    out: set[str] = set()
    for text in texts:
        value = (text or "").strip()
        if value:
            out.add(fingerprint(value))
    return out


def _is_recent_duplicate(text: str, recent_fingerprints: set[str]) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    return fingerprint(value) in recent_fingerprints


def _is_posted_before(text: str, posted_fingerprints: set[str]) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    return fingerprint(value) in posted_fingerprints


def _fallback_draft(item: ContentItem, slot: str, horizon: str) -> DraftPost:
    title = item.title.replace("\n", " ").strip()
    if len(title) > 48:
        title = title[:48] + "..."

    if slot == "morning":
        text = (
            f"最新: {title}。示唆: 今日の制作では『要素を増やす前に構造を減らす』視点が効きます。"
            f"予測: {horizon}で、見た目より意図説明ができるデザインの評価が上がる。"
            "行動: 今週は1画面だけ再設計して差分を検証。"
        )
    elif slot == "noon":
        text = (
            f"今日の要点: {title}。示唆: まず1機能だけAI化。"
            f"予測: {horizon}で試作速度が標準化。行動: 今週1つだけ小さく実験。"
        )
    else:
        text = (
            f"今日は {title} を見て、焦らなくていいと感じました。示唆: 完璧な正解より、続けられる改善が強い。"
            f"予測: {horizon}で差がつくのは習慣化。行動: 今週は1つだけ振り返りを言語化。"
        )
    return DraftPost(text=text, reason="fallback")


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


def _find_due_queue_item(items: list[dict], slot: str, now: datetime, config: AppConfig) -> tuple[int, dict] | None:
    matches: list[tuple[datetime, int, dict]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if str(item.get("slot", "")).strip() != slot:
            continue
        schedule_at = str(item.get("schedule_at", "")).strip()
        if not schedule_at:
            continue
        due_at = parse_scheduled_datetime(schedule_at, config)
        if not due_at:
            continue
        if due_at <= now:
            matches.append((due_at, idx, item))
    if not matches:
        return None
    matches.sort(key=lambda x: x[0])
    _due_at, idx, item = matches[0]
    return idx, item


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
) -> bool:
    if not queue_path and not queue_sync_enabled():
        print("[QUEUE SKIP] queue_path未設定")
        return False
    queue_label = queue_path or "remote-sync"
    if not queue_sync_enabled():
        from pathlib import Path

        queue_file = Path(queue_path)
        queue_label = str(queue_file)
        if not queue_file.exists():
            print(f"[QUEUE SKIP] queue file not found: {queue_file}")
            return False
    queue = load_queue_items(queue_path)
    if not queue:
        print(f"[QUEUE SKIP] queue file not found: {queue_label}")
        return False
    found = _find_due_queue_item(queue, resolved_slot, now, config)
    if not found:
        print(f"[QUEUE SKIP] due item not found slot={resolved_slot} items={len(queue)}")
        return False

    idx, item = found
    text = str(item.get("text", "")).strip()
    refresh_mode = str(item.get("refresh_mode", "")).strip()
    if not text and refresh_mode == "jit_noon" and resolved_slot == "noon":
        source_items = fetch_rss_items(config.rss_feeds, max_items=config.max_input_items)
        source_items = filter_blocked(source_items, config.blocked_keywords)
        weekday_theme = config.weekly_themes.get(_weekday_key(now), "通常テーマ")
        draft = build_noon_news_post(
            model=config.model,
            items=source_items[: min(5, len(source_items))],
            tone=config.tone,
            audience=config.audience,
            prediction_horizon=config.prediction_horizon,
            weekday_theme=weekday_theme,
            recent_self_posts=recent_self_posts,
        )
        if draft:
            text = draft.text
            item["text"] = text
            item["last_refreshed_at"] = now.replace(microsecond=0).isoformat()
            save_queue_items(queue_path, queue)
            print(f"[QUEUE REFRESH] slot=noon schedule_at={item.get('schedule_at', '')} reason={draft.reason}")
    if not text:
        print(
            "[QUEUE HOLD] "
            f"slot={resolved_slot} schedule_at={item.get('schedule_at', '')} refresh_mode={refresh_mode or 'none'}"
        )
        return True

    media_path = _resolve_media_path(str(item.get("media_path", "")))
    media_paths = [media_path] if media_path else None
    reply_text = str(item.get("reply_text", "")).strip()
    print(
        "[QUEUE POST] "
        f"slot={resolved_slot} "
        f"schedule_at={item.get('schedule_at', '')} "
        f"media={'yes' if media_paths else 'no'} "
        f"reply={'yes' if reply_text else 'no'}"
    )

    if config.dry_run:
        reply_info = f"\n  reply: {reply_text}" if reply_text else ""
        media_info = f"\n  media: {media_paths}" if media_paths else ""
        print(f"[DRY-RUN QUEUE POST] {text}{media_info}{reply_info}")
        return True

    tweet_id = _safe_create_post(x, text, label=f"queue-post-{resolved_slot}", media_paths=media_paths)
    if not tweet_id:
        return False
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
    )
    save_history(history)
    del queue[idx]
    save_queue_items(queue_path, queue)
    print(f"queue posted: {tweet_id}")
    return True


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
    posted_slot_fingerprints = history_fingerprints(history, slot=resolved_slot)
    memory_changed = False
    history_changed = False
    x = XClient()
    recent_self_posts = x.recent_self_posts(limit=12)
    recent_post_fingerprints = _fingerprints(recent_self_posts)
    print(f"[RECENT POSTS] count={len(recent_self_posts)}")

    if _post_due_queue_item(x, config, resolved_slot, now, memory, queue_path, recent_self_posts=recent_self_posts):
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
        print("情報ソースが空のため終了")
        return

    if resolved_slot == "noon" and slot_latest_share_mode:
        print("[2/5] 昼枠: AIニュース要約投稿を生成")
        noon_draft = build_noon_news_post(
            model=config.model,
            items=items[: min(5, len(items))],
            tone=config.tone,
            audience=config.audience,
            prediction_horizon=config.prediction_horizon,
            weekday_theme=weekday_theme,
            recent_self_posts=recent_self_posts,
        )
        if noon_draft and not (
            is_duplicate(noon_draft.text, memory)
            or _is_recent_duplicate(noon_draft.text, recent_post_fingerprints)
            or _is_posted_before(noon_draft.text, posted_slot_fingerprints)
        ):
            if config.dry_run:
                print(f"[DRY-RUN NOON NEWS] {noon_draft.text}")
                return
            else:
                tweet_id = _safe_create_post(x, noon_draft.text, label="main-post-noon-news")
                if tweet_id:
                    register_text(noon_draft.text, memory)
                    save_memory(memory)
                    append_history(
                        noon_draft.text,
                        history,
                        slot="noon",
                        source="noon-news",
                        tweet_id=tweet_id,
                        posted_at=now.isoformat(),
                    )
                    posted_slot_fingerprints.add(fingerprint(noon_draft.text))
                    save_history(history)
                    print(f"noon news posted: {tweet_id}")
                    return
        print("[NOON FALLBACK] 昼枠専用生成を通常投稿生成へフォールバック")

    print("[2/5] 投稿案生成")
    drafts = build_post_drafts(
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
    )
    if not drafts and items:
        print("[FALLBACK] 生成失敗のためテンプレ投稿を作成")
        drafts = [_fallback_draft(items[0], resolved_slot, config.prediction_horizon)]

    passed_drafts = []
    for d in drafts:
        ok, reasons = validate_post_draft(d, config, min_chars=slot_min_chars, max_chars=slot_max_chars)
        if ok:
            if (
                is_duplicate(d.text, memory)
                or _is_recent_duplicate(d.text, recent_post_fingerprints)
                or (resolved_slot in {"morning", "noon"} and _is_posted_before(d.text, posted_slot_fingerprints))
            ):
                print("[DROP DRAFT] 重複投稿")
                continue
            passed_drafts.append(d)
        else:
            print(f"[DROP DRAFT] {','.join(reasons)}")
    if not passed_drafts and drafts and config.force_post_if_no_passed:
        non_duplicate_forced = [
            d
            for d in drafts
            if not is_duplicate(d.text, memory)
            and not _is_recent_duplicate(d.text, recent_post_fingerprints)
            and not (resolved_slot in {"morning", "noon"} and _is_posted_before(d.text, posted_slot_fingerprints))
        ]
        if non_duplicate_forced:
            print("[FORCE POST] 品質ゲート通過案がないため、未使用の先頭案を採用")
            passed_drafts = [non_duplicate_forced[0]]
        else:
            for item in items:
                alt = _fallback_draft(item, resolved_slot, config.prediction_horizon)
                if not is_duplicate(alt.text, memory) and not _is_recent_duplicate(
                    alt.text, recent_post_fingerprints
                ) and not (resolved_slot in {"morning", "noon"} and _is_posted_before(alt.text, posted_slot_fingerprints)):
                    print("[FORCE POST] 生成案が重複のため、RSSベースの代替案を採用")
                    passed_drafts = [alt]
                    break
    if not passed_drafts:
        print("[SKIP POST] 投稿可能な新規案がありません")
        return

    print("[3/5] 通常投稿")
    for i, d in enumerate(passed_drafts, start=1):
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
                else:
                    media_path, _mode, err = generate_image_with_nanobanana(
                        d.text, config.media_morning_image_output_dir
                    )
                if media_path:
                    media_paths = [media_path]
                    break
                if provider != "nanobanana_cmd":
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
        )
        posted_slot_fingerprints.add(fingerprint(d.text))
        history_changed = True
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
        if is_duplicate(quote_text, memory) or _is_recent_duplicate(quote_text, recent_post_fingerprints):
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
        )
        history_changed = True
        posted_quotes += 1
        print(f"quote posted: {quote_id}")

    if memory_changed:
        save_memory(memory)
    if history_changed:
        save_history(history)
