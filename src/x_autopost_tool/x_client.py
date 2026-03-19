from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable

import tweepy

from .models import QuoteCandidate
from .text_normalize import cleanup_post_text


def _mask_secret(value: str | None) -> str:
    if not value:
        return "missing"
    trimmed = value.strip()
    if not trimmed:
        return "blank"
    if len(trimmed) <= 8:
        return f"len={len(trimmed)}:{'*' * len(trimmed)}"
    return f"len={len(trimmed)}:{trimmed[:4]}...{trimmed[-4:]}"


class XClient:
    def __init__(self) -> None:
        self.consumer_key = os.getenv("X_API_KEY")
        self.consumer_secret = os.getenv("X_API_SECRET")
        self.access_token = os.getenv("X_ACCESS_TOKEN")
        self.access_secret = os.getenv("X_ACCESS_SECRET")
        self.bearer_token = os.getenv("X_BEARER_TOKEN")
        print(
            "[X AUTH DEBUG] "
            f"bearer={_mask_secret(self.bearer_token)} "
            f"api_key={_mask_secret(self.consumer_key)} "
            f"api_secret={_mask_secret(self.consumer_secret)} "
            f"access_token={_mask_secret(self.access_token)} "
            f"access_secret={_mask_secret(self.access_secret)}"
        )
        self.client = tweepy.Client(
            bearer_token=self.bearer_token,
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            access_token=self.access_token,
            access_token_secret=self.access_secret,
            wait_on_rate_limit=True,
        )
        auth = tweepy.OAuth1UserHandler(
            self.consumer_key,
            self.consumer_secret,
            self.access_token,
            self.access_secret,
        )
        self.v1_api = tweepy.API(auth)

    def search_recent(self, query: str, limit: int = 10) -> list[QuoteCandidate]:
        resp = self.client.search_recent_tweets(
            query=query,
            max_results=min(max(10, limit), 100),
            tweet_fields=[
                "author_id",
                "public_metrics",
                "entities",
                "attachments",
                "referenced_tweets",
                "conversation_id",
                "in_reply_to_user_id",
            ],
            expansions=["author_id", "attachments.media_keys"],
            user_fields=["username"],
            media_fields=["type"],
        )
        users = {u.id: u for u in (resp.includes or {}).get("users", [])} if resp else {}
        media_by_key = {}
        if resp and resp.includes and "media" in resp.includes:
            for m in resp.includes["media"]:
                media_by_key[m.media_key] = m.type
        data = resp.data or []
        out: list[QuoteCandidate] = []
        for t in data:
            author = users.get(t.author_id).username if t.author_id in users else "unknown"
            metrics = t.public_metrics or {}
            media_keys = getattr(getattr(t, "attachments", None), "get", lambda *_: [])("media_keys", [])
            media_types = {media_by_key.get(k) for k in media_keys if media_by_key.get(k)}
            entities = t.entities or {}
            referenced = getattr(t, "referenced_tweets", None) or []
            conversation_id = str(getattr(t, "conversation_id", "") or "")
            in_reply_to_user_id = str(getattr(t, "in_reply_to_user_id", "") or "")
            is_reply = any(getattr(ref, "type", "") == "replied_to" for ref in referenced)
            if conversation_id and conversation_id != str(t.id):
                is_reply = True
            if in_reply_to_user_id:
                is_reply = True
            has_url = bool(entities.get("urls")) or ("http" in (t.text or ""))
            out.append(
                QuoteCandidate(
                    tweet_id=str(t.id),
                    text=t.text,
                    author=author,
                    like_count=int(metrics.get("like_count", 0)),
                    retweet_count=int(metrics.get("retweet_count", 0)),
                    reply_count=int(metrics.get("reply_count", 0)),
                    quote_count=int(metrics.get("quote_count", 0)),
                    has_video=("video" in media_types or "animated_gif" in media_types),
                    has_image=("photo" in media_types),
                    has_url=has_url,
                    is_reply=is_reply,
                    conversation_id=conversation_id,
                    in_reply_to_user_id=in_reply_to_user_id,
                )
            )
        return out

    def upload_media(self, path: str) -> str:
        print(f"[X MEDIA UPLOAD] path={path}")
        media = self.v1_api.media_upload(filename=path)
        print(f"[X MEDIA UPLOAD] ok media_id={media.media_id_string}")
        return str(media.media_id_string)

    def create_post(
        self,
        text: str,
        quote_tweet_id: str | None = None,
        media_paths: list[str] | None = None,
    ) -> str:
        cleaned_text = cleanup_post_text(text)
        kwargs = {"text": cleaned_text}
        if quote_tweet_id:
            kwargs["quote_tweet_id"] = quote_tweet_id
        if media_paths:
            media_ids = []
            for p in media_paths:
                try:
                    media_ids.append(self.upload_media(p))
                except Exception as e:
                    print(f"[media] upload failed: {p} {e}")
            if media_ids:
                kwargs["media_ids"] = media_ids
            else:
                print("[X POST WARN] media_paths were provided but no media_ids were uploaded")
        resp = self.client.create_tweet(**kwargs)
        return str(resp.data.get("id")) if resp and resp.data else ""

    def create_reply(self, text: str, in_reply_to_tweet_id: str) -> str:
        cleaned_text = cleanup_post_text(text)
        resp = self.client.create_tweet(text=cleaned_text, in_reply_to_tweet_id=in_reply_to_tweet_id)
        return str(resp.data.get("id")) if resp and resp.data else ""

    def search_multi(self, queries: Iterable[str], per_query: int = 10) -> list[QuoteCandidate]:
        out: list[QuoteCandidate] = []
        for q in queries:
            out.extend(self.search_recent(q, limit=per_query))
        return out

    def recent_self_posts(self, limit: int = 10) -> list[str]:
        try:
            me = self.client.get_me(user_auth=True, user_fields=["username"])
            user_id = getattr(getattr(me, "data", None), "id", None)
            if not user_id:
                return []
            resp = self.client.get_users_tweets(
                id=user_id,
                max_results=min(max(5, limit), 100),
                exclude=["replies", "retweets"],
                tweet_fields=["created_at"],
                user_auth=True,
            )
            data = resp.data or []
            return [t.text for t in data if getattr(t, "text", "").strip()]
        except Exception as e:
            print(f"[X RECENT POSTS ERROR] {e}")
            return []

    @staticmethod
    def _metric_dict(value) -> dict:
        if isinstance(value, dict):
            return value
        return getattr(value, "data", None) or getattr(value, "__dict__", {}) or {}

    def self_post_metrics(self, limit: int = 100) -> list[dict]:
        try:
            me = self.client.get_me(user_auth=True, user_fields=["username"])
            user_id = getattr(getattr(me, "data", None), "id", None)
            if not user_id:
                return []
            resp = self.client.get_users_tweets(
                id=user_id,
                max_results=min(max(10, limit), 100),
                exclude=["replies", "retweets"],
                tweet_fields=["created_at", "public_metrics", "non_public_metrics", "organic_metrics", "attachments"],
                expansions=["attachments.media_keys"],
                user_auth=True,
            )
            out: list[dict] = []
            for tweet in resp.data or []:
                public = self._metric_dict(getattr(tweet, "public_metrics", {}) or {})
                non_public = self._metric_dict(getattr(tweet, "non_public_metrics", {}) or {})
                organic = self._metric_dict(getattr(tweet, "organic_metrics", {}) or {})
                attachments = getattr(tweet, "attachments", None) or {}
                media_keys = []
                if hasattr(attachments, "get"):
                    media_keys = attachments.get("media_keys", []) or []
                created_at = getattr(tweet, "created_at", None)
                if isinstance(created_at, datetime):
                    created_at_value = created_at.isoformat()
                else:
                    created_at_value = str(created_at or "")
                out.append(
                    {
                        "tweet_id": str(getattr(tweet, "id", "") or ""),
                        "posted_at": created_at_value,
                        "text": cleanup_post_text(getattr(tweet, "text", "") or ""),
                        "has_media": bool(media_keys),
                        "impressions": int(non_public.get("impression_count") or organic.get("impression_count") or public.get("impression_count") or 0),
                        "likes": int(public.get("like_count", 0) or 0),
                        "reposts": int(public.get("retweet_count", 0) or 0),
                        "replies": int(public.get("reply_count", 0) or 0),
                        "bookmarks": int(non_public.get("bookmark_count") or 0),
                        "metrics_updated_at": datetime.now().isoformat(),
                    }
                )
            return out
        except Exception as e:
            print(f"[X METRICS ERROR] {e}")
            return []
