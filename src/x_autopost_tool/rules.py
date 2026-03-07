from __future__ import annotations

import re

from .models import DraftPost, QuoteCandidate
from .settings import AppConfig


HASHTAG_RE = re.compile(r"(?:^|\s)#\w+")
FUTURE_HINT_RE = re.compile(r"(今後|これから|3.?ヶ月|6.?ヶ月|増える|減る|広がる|進む|シフト)")
ACTION_HINT_RE = re.compile(r"(今週|今日|まずは|試す|やってみる|見直す|検証|実験|メモ|外してみる)")
EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001F5FF"
    r"\U0001F600-\U0001F64F"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F700-\U0001F77F"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA70-\U0001FAFF]"
)


def _contains_any(text: str, words: list[str]) -> bool:
    lowered = text.lower()
    return any(w.lower() in lowered for w in words)


def validate_post_draft(
    draft: DraftPost,
    config: AppConfig,
    min_chars: int | None = None,
    max_chars: int | None = None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    text = draft.text.strip()
    text_len = len(text)

    min_limit = min_chars if min_chars is not None else config.min_post_chars
    max_limit = max_chars if max_chars is not None else config.max_post_chars
    if text_len < min_limit or text_len > max_limit:
        reasons.append(f"文字数が範囲外({text_len})")

    has_prediction = _contains_any(text, config.require_prediction_keywords) or bool(FUTURE_HINT_RE.search(text))
    if config.require_prediction_keywords and not has_prediction:
        reasons.append("予測キーワード不足")

    has_action = _contains_any(text, config.require_action_keywords) or bool(ACTION_HINT_RE.search(text))
    if config.require_action_keywords and not has_action:
        reasons.append("アクションキーワード不足")

    if config.forbidden_claim_keywords and _contains_any(text, config.forbidden_claim_keywords):
        reasons.append("断定表現を含む")

    if text.count("\n") < config.min_line_breaks:
        reasons.append("改行不足")

    hashtags = HASHTAG_RE.findall(text)
    if len(hashtags) < config.min_hashtags:
        reasons.append(f"ハッシュタグ不足({len(hashtags)})")
    if len(hashtags) > config.max_hashtags:
        reasons.append(f"ハッシュタグ過多({len(hashtags)})")

    emoji_count = len(EMOJI_RE.findall(text))
    if emoji_count > config.max_emojis:
        reasons.append(f"絵文字過多({emoji_count})")

    return len(reasons) == 0, reasons


def score_quote_candidate(candidate: QuoteCandidate, config: AppConfig) -> int:
    text = candidate.text.strip()
    score = 0
    engagement = (
        candidate.like_count
        + candidate.retweet_count * 3
        + candidate.reply_count * 2
        + candidate.quote_count * 2
    )

    if config.quote_min_chars <= len(text) <= config.quote_max_chars:
        score += 2
    if "http" not in text:
        score += 1
    if _contains_any(text, config.quote_preferred_keywords):
        score += 2
    if "?" in text:
        score += 1
    if engagement >= config.quote_min_engagement_score:
        score += 2
    if config.quote_prefer_video and candidate.has_video:
        score += 3
    elif config.quote_fallback_to_image and candidate.has_image:
        score += 2
    if candidate.has_url:
        score -= 1
    return score


def filter_quote_candidates(candidates: list[QuoteCandidate], config: AppConfig) -> list[QuoteCandidate]:
    out: list[QuoteCandidate] = []
    for c in candidates:
        text = c.text.strip()
        if config.quote_exclude_if_starts_with_mention and text.startswith("@"):
            continue
        if config.quote_exclude_if_contains_url and "http" in text:
            continue
        if not (config.quote_min_chars <= len(text) <= config.quote_max_chars):
            continue
        out.append(c)
    return out
