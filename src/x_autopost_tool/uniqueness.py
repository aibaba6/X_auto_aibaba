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
SENTENCE_SPLIT_RE = re.compile(r"(?:\n+|(?<=[。！？!?]))")
JP_TOKEN_RE = re.compile(r"[ぁ-んァ-ン一-龠a-z0-9]{2,}")
ACTION_HINT_RE = re.compile(r"(行動|今日は|今週|先に|まず|1つ|ひとつ|試す|比較|確認|メモ|見直|整え|固定|絞)")
FILLER_RE = re.compile(r"(です|ます|でした|ですね|ですよね|だけ|こと|もの|よう|ため|ので|から|まず|先に|今日は|今週)")
STOPWORDS = {
    "これ",
    "それ",
    "ため",
    "ので",
    "よう",
    "こと",
    "もの",
    "ここ",
    "今回",
    "今日",
    "いま",
    "今",
    "直近",
    "です",
    "ます",
    "でした",
    "ですね",
}


@dataclass
class DuplicateCheckResult:
    strict_duplicate: bool
    loose_duplicate: bool
    strict_fingerprint: str
    loose_fingerprint: str
    normalized_text: str
    loose_normalized_text: str


@dataclass
class SemanticSignature:
    topic: str
    pattern: str
    core_claim: str
    action_takeaway: str
    topic_key: str
    claim_key: str
    action_key: str
    semantic_fingerprint: str


@dataclass
class SemanticCheckResult:
    duplicate: bool
    reason: str
    candidate: SemanticSignature
    matched_entry: dict[str, Any] | None


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


def _body_without_tags(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = URL_RE.sub(" ", t)
    t = HASHTAG_RE.sub(" ", t)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def _semantic_sentences(text: str) -> list[str]:
    body = _body_without_tags(text)
    parts = [part.strip(" ・-") for part in SENTENCE_SPLIT_RE.split(body) if part and part.strip(" ・-")]
    return [part for part in parts if part]


def _semantic_tokens(text: str) -> list[str]:
    base = unicodedata.normalize("NFKC", text or "").lower()
    tokens = [tok for tok in JP_TOKEN_RE.findall(base) if tok and tok not in STOPWORDS]
    return tokens


def _semantic_key(text: str, limit: int = 6) -> str:
    tokens = []
    seen: set[str] = set()
    for token in _semantic_tokens(text):
        stem = FILLER_RE.sub("", token).strip()
        if len(stem) < 2 or stem in seen:
            continue
        seen.add(stem)
        tokens.append(stem)
        if len(tokens) >= limit:
            break
    return " ".join(tokens)


def _semantic_pattern(sentences: list[str]) -> str:
    if not sentences:
        return "empty"
    first = sentences[0]
    last = sentences[-1]
    has_scene = any(k in first for k in ["とき", "日", "夕方", "朝", "依頼", "判断", "締切", "修正"])
    has_action = any(ACTION_HINT_RE.search(s) for s in sentences[1:]) or bool(ACTION_HINT_RE.search(last))
    has_compare = any("より" in s or "だけ" in s or "絞" in s for s in sentences)
    pattern = ["scene" if has_scene else "direct", "compare" if has_compare else "insight", "action" if has_action else "close"]
    return ">".join(pattern)


def semantic_signature(text: str) -> SemanticSignature:
    sentences = _semantic_sentences(text)
    topic = sentences[0] if sentences else _body_without_tags(text)[:60]
    action_sentence = ""
    for sentence in reversed(sentences):
        if ACTION_HINT_RE.search(sentence):
            action_sentence = sentence
            break
    if not action_sentence and len(sentences) >= 2:
        action_sentence = sentences[-1]
    core_claim = sentences[1] if len(sentences) >= 2 else topic
    if action_sentence and core_claim == action_sentence and len(sentences) >= 3:
        core_claim = sentences[-2]
    topic_key = _semantic_key(topic, limit=6)
    claim_key = _semantic_key(core_claim, limit=7)
    action_key = _semantic_key(action_sentence, limit=6)
    pattern = _semantic_pattern(sentences)
    composite = "|".join([topic_key, claim_key, action_key, pattern])
    signature = SemanticSignature(
        topic=topic.strip(),
        pattern=pattern,
        core_claim=core_claim.strip(),
        action_takeaway=action_sentence.strip(),
        topic_key=topic_key,
        claim_key=claim_key,
        action_key=action_key,
        semantic_fingerprint=sha1(composite.encode("utf-8")).hexdigest(),
    )
    print(
        "[SEMANTIC SUMMARY] "
        f"topic={signature.topic[:80]} "
        f"claim={signature.core_claim[:80]} "
        f"takeaway={signature.action_takeaway[:80]}"
    )
    return signature


def _token_overlap_score(a: str, b: str) -> float:
    a_tokens = set(_semantic_tokens(a))
    b_tokens = set(_semantic_tokens(b))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / max(1, min(len(a_tokens), len(b_tokens)))


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


def semantic_duplicate_check(
    text: str,
    store: HistoryStore,
    *,
    slot: str | None = None,
    recent_limit: int = 24,
) -> SemanticCheckResult:
    candidate = semantic_signature(text)
    relevant_entries = [entry for entry in store.entries if not slot or str(entry.get("slot", "")).strip() == slot]
    relevant_entries = relevant_entries[-recent_limit:]
    print(f"[SEMANTIC LOAD] history_count={len(relevant_entries)}")
    for entry in reversed(relevant_entries):
        topic_key = str(entry.get("semantic_topic_key", "")).strip()
        claim_key = str(entry.get("semantic_claim_key", "")).strip()
        action_key = str(entry.get("semantic_action_key", "")).strip()
        pattern = str(entry.get("semantic_pattern", "")).strip()
        entry_topic = str(entry.get("semantic_topic", entry.get("topic", ""))).strip()
        entry_claim = str(entry.get("core_claim", "")).strip()
        entry_takeaway = str(entry.get("action_takeaway", "")).strip()
        topic_dup = bool(topic_key and topic_key == candidate.topic_key)
        claim_dup = bool(claim_key and claim_key == candidate.claim_key)
        action_dup = bool(action_key and action_key == candidate.action_key)
        topic_close = _token_overlap_score(candidate.topic, entry_topic) >= 0.72
        claim_close = _token_overlap_score(candidate.core_claim, entry_claim) >= 0.72
        action_close = _token_overlap_score(candidate.action_takeaway, entry_takeaway) >= 0.7
        same_pattern = bool(pattern and pattern == candidate.pattern)
        is_duplicate = (
            (topic_dup and claim_dup)
            or (topic_dup and action_dup)
            or (topic_close and claim_close)
            or (claim_dup and action_dup and same_pattern)
            or (topic_close and claim_close and action_close)
        )
        print(
            "[SEMANTIC CHECK] "
            f"candidate_topic={candidate.topic[:60]} "
            f"duplicate={'yes' if is_duplicate else 'no'}"
        )
        if is_duplicate:
            reason = "same_topic_claim"
            if topic_dup and action_dup:
                reason = "same_topic_action"
            elif claim_dup and action_dup and same_pattern:
                reason = "same_claim_takeaway_pattern"
            elif topic_close and claim_close and action_close:
                reason = "same_topic_claim_takeaway"
            return SemanticCheckResult(
                duplicate=True,
                reason=reason,
                candidate=candidate,
                matched_entry=entry,
            )
    return SemanticCheckResult(
        duplicate=False,
        reason="",
        candidate=candidate,
        matched_entry=None,
    )


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
        print("[SEMANTIC LOAD] history_count=0")
        return HistoryStore(path=p, entries=[])
    try:
        data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        values = data.get("entries", []) if isinstance(data, dict) else []
        entries = [v for v in values if isinstance(v, dict)]
        print(f"[UNIQUE LOAD] history_count={len(entries)}")
        print(f"[SEMANTIC LOAD] history_count={len(entries)}")
        return HistoryStore(path=p, entries=entries)
    except Exception:
        print("[UNIQUE LOAD] history_count=0")
        print("[SEMANTIC LOAD] history_count=0")
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


def semantic_summaries(store: HistoryStore, slot: str | None = None, limit: int = 8) -> list[str]:
    relevant = [entry for entry in store.entries if not slot or str(entry.get("slot", "")).strip() == slot]
    summaries: list[str] = []
    for entry in reversed(relevant[-limit:]):
        topic = str(entry.get("semantic_topic", entry.get("topic", ""))).strip()
        claim = str(entry.get("core_claim", "")).strip()
        takeaway = str(entry.get("action_takeaway", "")).strip()
        pattern = str(entry.get("semantic_pattern", entry.get("pattern_id", ""))).strip()
        if topic or claim or takeaway:
            summaries.append(
                " / ".join(part for part in [topic, claim, takeaway, pattern] if part)
            )
    return summaries


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
    semantic = semantic_signature(raw)
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
            "topic": topic or semantic.topic,
            "tags": extract_tags(raw),
            "pattern_id": pattern_id or semantic.pattern,
            "semantic_topic": semantic.topic,
            "semantic_pattern": semantic.pattern,
            "core_claim": semantic.core_claim,
            "action_takeaway": semantic.action_takeaway,
            "semantic_topic_key": semantic.topic_key,
            "semantic_claim_key": semantic.claim_key,
            "semantic_action_key": semantic.action_key,
            "semantic_fingerprint": semantic.semantic_fingerprint,
        }
    )
