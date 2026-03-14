from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import os
import yaml
from dotenv import load_dotenv


@dataclass
class AppConfig:
    raw: dict[str, Any]

    @property
    def language(self) -> str:
        return self.raw.get("profile", {}).get("language", "ja")

    @property
    def tone(self) -> str:
        return self.raw.get("profile", {}).get("tone", "洞察的")

    @property
    def audience(self) -> str:
        return self.raw.get("profile", {}).get("audience", "テック関心層")

    @property
    def account_handle(self) -> str:
        return self.raw.get("profile", {}).get("account_handle", "@your_account")

    @property
    def rss_feeds(self) -> list[str]:
        return self.raw.get("sources", {}).get("rss_feeds", [])

    @property
    def x_search_queries(self) -> list[str]:
        return self.raw.get("sources", {}).get("x_search_queries", [])

    @property
    def x_noon_queries(self) -> list[str]:
        return self.raw.get("sources", {}).get("x_noon_queries", self.x_search_queries)

    @property
    def blocked_keywords(self) -> list[str]:
        return self.raw.get("filters", {}).get("blocked_keywords", [])

    @property
    def max_posts_per_run(self) -> int:
        return int(self.raw.get("posting", {}).get("max_posts_per_run", 1))

    @property
    def enable_quote_posts(self) -> bool:
        return bool(self.raw.get("posting", {}).get("enable_quote_posts", True))

    @property
    def quote_candidates_limit(self) -> int:
        return int(self.raw.get("posting", {}).get("quote_candidates_limit", 10))

    @property
    def max_quote_posts_per_run(self) -> int:
        return int(self.raw.get("posting", {}).get("max_quote_posts_per_run", 1))

    @property
    def dry_run(self) -> bool:
        return bool(self.raw.get("posting", {}).get("dry_run", True))

    @property
    def force_post_if_no_passed(self) -> bool:
        return bool(self.raw.get("posting", {}).get("force_post_if_no_passed", True))

    @property
    def uniqueness_memory_path(self) -> str:
        return str(self.raw.get("posting", {}).get("uniqueness_memory_path", "post_memory.yaml"))

    @property
    def post_history_path(self) -> str:
        return str(self.raw.get("posting", {}).get("post_history_path", "post_history.yaml"))

    @property
    def model(self) -> str:
        return self.raw.get("generation", {}).get("model", "gpt-4.1-mini")

    @property
    def max_input_items(self) -> int:
        return int(self.raw.get("generation", {}).get("max_input_items", 20))

    @property
    def prediction_horizon(self) -> str:
        return self.raw.get("generation", {}).get("prediction_horizon", "3-6ヶ月")

    @property
    def post_style_template(self) -> list[str]:
        return self.raw.get("generation", {}).get("post_style_template", [])

    @property
    def voice_guide(self) -> list[str]:
        return self.raw.get("generation", {}).get("voice_guide", [])

    @property
    def style_reference_posts(self) -> list[str]:
        refs = self.raw.get("generation", {}).get("style_reference_posts", [])
        return refs if isinstance(refs, list) else []

    @property
    def min_post_chars(self) -> int:
        return int(self.raw.get("quality_gate", {}).get("min_post_chars", 120))

    @property
    def max_post_chars(self) -> int:
        return int(self.raw.get("quality_gate", {}).get("max_post_chars", 280))

    @property
    def min_line_breaks(self) -> int:
        return int(self.raw.get("quality_gate", {}).get("min_line_breaks", 1))

    @property
    def min_hashtags(self) -> int:
        return int(self.raw.get("quality_gate", {}).get("min_hashtags", 2))

    @property
    def max_emojis(self) -> int:
        return int(self.raw.get("quality_gate", {}).get("max_emojis", 2))

    @property
    def require_prediction_keywords(self) -> list[str]:
        return self.raw.get("quality_gate", {}).get("require_prediction_keywords", [])

    @property
    def require_action_keywords(self) -> list[str]:
        return self.raw.get("quality_gate", {}).get("require_action_keywords", [])

    @property
    def forbidden_claim_keywords(self) -> list[str]:
        return self.raw.get("quality_gate", {}).get("forbidden_claim_keywords", [])

    @property
    def max_hashtags(self) -> int:
        return int(self.raw.get("quality_gate", {}).get("max_hashtags", 3))

    @property
    def quote_min_chars(self) -> int:
        return int(self.raw.get("quote_rules", {}).get("min_chars", 40))

    @property
    def quote_max_chars(self) -> int:
        return int(self.raw.get("quote_rules", {}).get("max_chars", 240))

    @property
    def quote_exclude_if_starts_with_mention(self) -> bool:
        return bool(self.raw.get("quote_rules", {}).get("exclude_if_starts_with_mention", True))

    @property
    def quote_exclude_if_contains_url(self) -> bool:
        return bool(self.raw.get("quote_rules", {}).get("exclude_if_contains_url", False))

    @property
    def quote_min_score(self) -> int:
        return int(self.raw.get("quote_rules", {}).get("min_score", 3))

    @property
    def quote_min_engagement_score(self) -> int:
        return int(self.raw.get("quote_rules", {}).get("min_engagement_score", 30))

    @property
    def quote_prefer_video(self) -> bool:
        return bool(self.raw.get("quote_rules", {}).get("prefer_video", True))

    @property
    def quote_fallback_to_image(self) -> bool:
        return bool(self.raw.get("quote_rules", {}).get("fallback_to_image", True))

    @property
    def quote_avoid_links_in_comment(self) -> bool:
        return bool(self.raw.get("quote_rules", {}).get("avoid_links_in_comment", True))

    @property
    def quote_preferred_keywords(self) -> list[str]:
        return self.raw.get("quote_rules", {}).get("preferred_keywords", [])

    @property
    def media_enabled(self) -> bool:
        return bool(self.raw.get("media", {}).get("enabled", False))

    @property
    def media_morning_generate_image(self) -> bool:
        return bool(self.raw.get("media", {}).get("morning_generate_image", False))

    @property
    def media_morning_image_provider(self) -> str:
        return str(self.raw.get("media", {}).get("morning_image_provider", "nanobanana_cmd"))

    @property
    def media_morning_image_output_dir(self) -> str:
        return str(self.raw.get("media", {}).get("morning_image_output_dir", "generated_media"))

    @property
    def media_noon_reply_source_link(self) -> bool:
        return bool(self.raw.get("media", {}).get("noon_reply_source_link", True))

    @property
    def media_morning_retry_on_503(self) -> bool:
        return bool(self.raw.get("media", {}).get("morning_retry_on_503", True))

    @property
    def media_morning_retry_delay_minutes(self) -> int:
        return int(self.raw.get("media", {}).get("morning_retry_delay_minutes", 10))

    @property
    def media_morning_retry_max_attempts(self) -> int:
        return int(self.raw.get("media", {}).get("morning_retry_max_attempts", 3))

    @property
    def weekly_themes(self) -> dict[str, str]:
        return self.raw.get("schedule", {}).get("weekly_themes", {})

    @property
    def required_daily_slots(self) -> list[str]:
        return self.raw.get("schedule", {}).get("required_daily_slots", ["morning", "noon", "evening"])

    @property
    def slot_profiles(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("schedule", {}).get("slot_profiles", {})


def load_config(path: str) -> AppConfig:
    load_dotenv()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return AppConfig(raw=data)


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value
