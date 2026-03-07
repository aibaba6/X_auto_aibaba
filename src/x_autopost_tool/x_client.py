from __future__ import annotations

import os
from typing import Iterable

import tweepy

from .models import QuoteCandidate


class XClient:
    def __init__(self) -> None:
        self.consumer_key = os.getenv("X_API_KEY")
        self.consumer_secret = os.getenv("X_API_SECRET")
        self.access_token = os.getenv("X_ACCESS_TOKEN")
        self.access_secret = os.getenv("X_ACCESS_SECRET")
        self.client = tweepy.Client(
            bearer_token=os.getenv("X_BEARER_TOKEN"),
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
            tweet_fields=["author_id", "public_metrics", "entities", "attachments"],
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
                )
            )
        return out

    def upload_media(self, path: str) -> str:
        media = self.v1_api.media_upload(filename=path)
        return str(media.media_id_string)

    def create_post(
        self,
        text: str,
        quote_tweet_id: str | None = None,
        media_paths: list[str] | None = None,
    ) -> str:
        kwargs = {"text": text}
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
        resp = self.client.create_tweet(**kwargs)
        return str(resp.data.get("id")) if resp and resp.data else ""

    def create_reply(self, text: str, in_reply_to_tweet_id: str) -> str:
        resp = self.client.create_tweet(text=text, in_reply_to_tweet_id=in_reply_to_tweet_id)
        return str(resp.data.get("id")) if resp and resp.data else ""

    def search_multi(self, queries: Iterable[str], per_query: int = 10) -> list[QuoteCandidate]:
        out: list[QuoteCandidate] = []
        for q in queries:
            out.extend(self.search_recent(q, limit=per_query))
        return out
