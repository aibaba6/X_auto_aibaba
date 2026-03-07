from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from pathlib import Path
import re
from typing import Any

import yaml


WS_RE = re.compile(r"\s+")
HASHTAG_RE = re.compile(r"(?:^|\s)#\w+")
PUNCT_RE = re.compile(r"[、。,.!！?？:：;；「」『』（）\(\)\[\]\-ー〜~・]+")


@dataclass
class MemoryStore:
    path: Path
    fingerprints: set[str]


def normalize_text(text: str) -> str:
    t = text.lower().strip()
    t = HASHTAG_RE.sub(" ", t)
    t = PUNCT_RE.sub(" ", t)
    t = WS_RE.sub(" ", t)
    return t.strip()


def fingerprint(text: str) -> str:
    base = normalize_text(text)
    return sha1(base.encode("utf-8")).hexdigest()


def load_memory(path: str) -> MemoryStore:
    p = Path(path)
    if not p.exists():
        return MemoryStore(path=p, fingerprints=set())
    try:
        data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        values = data.get("fingerprints", []) if isinstance(data, dict) else []
        fps = {str(v) for v in values if v}
        return MemoryStore(path=p, fingerprints=fps)
    except Exception:
        return MemoryStore(path=p, fingerprints=set())


def save_memory(store: MemoryStore) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fingerprints": sorted(store.fingerprints)}
    store.path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def is_duplicate(text: str, store: MemoryStore) -> bool:
    if not text.strip():
        return False
    return fingerprint(text) in store.fingerprints


def register_text(text: str, store: MemoryStore) -> None:
    if not text.strip():
        return
    store.fingerprints.add(fingerprint(text))

