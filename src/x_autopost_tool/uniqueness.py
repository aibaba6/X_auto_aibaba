from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
import re
import unicodedata
from typing import Any

import yaml


WS_RE = re.compile(r"\s+")
URL_RE = re.compile(r"https?://\S+")
HASHTAG_RE = re.compile(r"(?:^|\s)#[^\s#]+")
TRAILING_ENDING_RE = re.compile(r"(ですね|ですよね|です。|です|でした。|でした|ます。|ます|かも。|かも)+$")
PUNCT_STRICT_RE = re.compile(r"[、。,.!！?？:：;；「」『』（）()\[\]{}<>＜＞【】《》〈〉…・]+")
PUNCT_LOOSE_RE = re.compile(r"[^0-9a-zA-Zぁ-んァ-ン一-龠]+")
TAG_SPLIT_RE = re.compile(r"#([^\s#]+)")


@dataclass
class DuplicateCheckResult:
    strict_duplicate: bool
    loose_duplicate: bool
    strict_fingerprint: str
    loose_fingerprint: str
    normalized_text: str
    loose_normalized_text: str


@dataclass
class MemoryStore:
    path: Path
    strict_fingerprints: set[str]
    loose_fingerprints: set[str]


@dataclass
class HistoryStore:
    path: Path
    entries: list[dict[str, Any]]


def _normalize_base(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = URL_RE.sub(" ", t)
    t = HASHTAG_RE.sub(" ", t)
    t = t.lower().strip()
    return t


def _normalize_text_strict(text: str) -> str:
    t = _normalize_base(text)
    t = TRAILING_ENDING_RE.sub("", t)
    t = PUNCT_STRICT_RE.sub(" ", t)
    t = WS_RE.sub(" ", t)
    return t.strip()


def _normalize_text_loose(text: str) -> str:
    t = _normalize_base(text)
    t = TRAILING_ENDING_RE.sub("", t)
    t = PUNCT_LOOSE_RE.sub("", t)
    return t.strip()


def normalize_text(text: str) -> str:
    value = _normalize_text_strict(text)
    print(f"[UNIQUE NORMALIZE] strict={value[:120]}")
    return value


def normalize_text_loose(text: str) -> str:
    value = _normalize_text_loose(text)
    print(f"[UNIQUE NORMALIZE] loose={value[:120]}")
    return value


def strict_fingerprint(text: str) -> str:
    return sha1(_normalize_text_strict(text).encode("utf-8")).hexdigest()


def loose_fingerprint(text: str) -> str:
    return sha1(_normalize_text_loose(text).encode("utf-8")).hexdigest()


def fingerprint(text: str) -> str:
    return strict_fingerprint(text)


def extract_tags(text: str) -> list[str]:
    found = [m.group(1).strip().lower() for m in TAG_SPLIT_RE.finditer(text or "")]
    return [t for t in found if t]


def duplicate_check(text: str, store: MemoryStore) -> DuplicateCheckResult:
    strict_norm = normalize_text(text)
    loose_norm = normalize_text_loose(text)
    strict_fp = sha1(strict_norm.encode("utf-8")).hexdigest()
    loose_fp = sha1(loose_norm.encode("utf-8")).hexdigest()
    result = DuplicateCheckResult(
        strict_duplicate=strict_fp in store.strict_fingerprints,
        loose_duplicate=loose_fp in store.loose_fingerprints,
        strict_fingerprint=strict_fp,
        loose_fingerprint=loose_fp,
        normalized_text=strict_norm,
        loose_normalized_text=loose_norm,
    )
    print(
        "[UNIQUE CHECK] "
        f"candidate={result.normalized_text[:80]} "
        f"strict_dup={'yes' if result.strict_duplicate else 'no'} "
        f"loose_dup={'yes' if result.loose_duplicate else 'no'}"
    )
    return result


def load_memory(path: str) -> MemoryStore:
    p = Path(path)
    if not p.exists():
        print("[UNIQUE LOAD] history_count=0")
        return MemoryStore(path=p, strict_fingerprints=set(), loose_fingerprints=set())
    try:
        data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            print("[UNIQUE LOAD] history_count=0")
            return MemoryStore(path=p, strict_fingerprints=set(), loose_fingerprints=set())
        strict_values = data.get("strict_fingerprints", [])
        loose_values = data.get("loose_fingerprints", [])
        legacy_values = data.get("fingerprints", [])
        strict_fps = {str(v) for v in strict_values if v} | {str(v) for v in legacy_values if v}
        loose_fps = {str(v) for v in loose_values if v} | {str(v) for v in legacy_values if v}
        print(f"[UNIQUE LOAD] history_count={max(len(strict_fps), len(loose_fps))}")
        return MemoryStore(path=p, strict_fingerprints=strict_fps, loose_fingerprints=loose_fps)
    except Exception:
        print("[UNIQUE LOAD] history_count=0")
        return MemoryStore(path=p, strict_fingerprints=set(), loose_fingerprints=set())


def save_memory(store: MemoryStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "strict_fingerprints": sorted(store.strict_fingerprints),
        "loose_fingerprints": sorted(store.loose_fingerprints),
    }
    store.path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def is_duplicate(text: str, store: MemoryStore) -> bool:
    if not text.strip():
        return False
    result = duplicate_check(text, store)
    return result.strict_duplicate or result.loose_duplicate


def register_text(text: str, store: MemoryStore) -> DuplicateCheckResult | None:
    if not text.strip():
        return None
    result = duplicate_check(text, store)
    store.strict_fingerprints.add(result.strict_fingerprint)
    store.loose_fingerprints.add(result.loose_fingerprint)
    return result


def load_history(path: str) -> HistoryStore:
    p = Path(path)
    if not p.exists():
        print("[UNIQUE LOAD] history_count=0")
        return HistoryStore(path=p, entries=[])
    try:
        data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        values = data.get("entries", []) if isinstance(data, dict) else []
        entries = [v for v in values if isinstance(v, dict)]
        print(f"[UNIQUE LOAD] history_count={len(entries)}")
        return HistoryStore(path=p, entries=entries)
    except Exception:
        print("[UNIQUE LOAD] history_count=0")
        return HistoryStore(path=p, entries=[])


def save_history(store: HistoryStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entries": store.entries[-2000:]}
    store.path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def history_fingerprints(store: HistoryStore, slot: str | None = None, mode: str = "strict") -> set[str]:
    out: set[str] = set()
    key = "strict_fingerprint" if mode == "strict" else "loose_fingerprint"
    legacy_key = "fingerprint"
    for entry in store.entries:
        if slot and str(entry.get("slot", "")).strip() != slot:
            continue
        fp = str(entry.get(key, "")).strip() or str(entry.get(legacy_key, "")).strip()
        if fp:
            out.add(fp)
    return out


def history_topics(store: HistoryStore, slot: str | None = None) -> set[str]:
    out: set[str] = set()
    for entry in store.entries:
        if slot and str(entry.get("slot", "")).strip() != slot:
            continue
        topic = str(entry.get("topic", "")).strip().lower()
        if topic:
            out.add(topic)
    return out


def append_history(
    text: str,
    store: HistoryStore,
    *,
    slot: str = "",
    source: str = "",
    tweet_id: str = "",
    posted_at: str = "",
    created_at: str = "",
    topic: str = "",
    pattern_id: str = "",
) -> None:
    raw = (text or "").strip()
    if not raw:
        return
    strict_norm = normalize_text(raw)
    loose_norm = normalize_text_loose(raw)
    store.entries.append(
        {
            "text": raw,
            "normalized_text": strict_norm,
            "loose_normalized_text": loose_norm,
            "strict_fingerprint": sha1(strict_norm.encode("utf-8")).hexdigest(),
            "loose_fingerprint": sha1(loose_norm.encode("utf-8")).hexdigest(),
            "fingerprint": sha1(strict_norm.encode("utf-8")).hexdigest(),
            "slot": slot,
            "source": source,
            "tweet_id": tweet_id,
            "created_at": created_at or posted_at,
            "posted_at": posted_at,
            "topic": topic,
            "tags": extract_tags(raw),
            "pattern_id": pattern_id,
        }
    )
