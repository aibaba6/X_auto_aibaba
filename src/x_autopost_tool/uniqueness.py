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
ACTION_HINT_RE = re.compile(r"(行動|先に|まず|1つ|ひとつ|試す|比較|確認|メモ|見直|整え|固定|絞|減ら|増や|置く|残す|決める)")
FILLER_RE = re.compile(r"(です|ます|でした|ですね|ですよね|だけ|こと|もの|よう|ため|ので|から|まず|先に|今日|今週|朝)")
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
    hook: str
    topic: str
    claim: str
    structure: str
    takeaway: str
    hook_key: str
    topic_key: str
    claim_key: str
    takeaway_key: str
    semantic_fingerprint: str


@dataclass
class SemanticCheckResult:
    duplicate: bool
    reason: str
    candidate: SemanticSignature
    matched_entry: dict[str, Any] | None


@dataclass
class SemanticStageCheckResult:
    duplicate: bool
    warning: bool
    reason: str
    candidate: SemanticSignature
    matched_entry: dict[str, Any] | None


@dataclass
class EveningDuplicateCheckResult:
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
    joined = " ".join(sentences)
    if "失敗" in joined or "違う" in joined or "ズレ" in joined:
        return "失敗型"
    if "より" in joined or "比較" in joined:
        return "比較型"
    if any(k in first for k in ["とき", "依頼", "締切", "夕方", "朝", "場面", "状況"]):
        return "問題提起型"
    if len(first) <= 20:
        return "一言断言型"
    return "気づき型"


def _semantic_topic_text(hook: str, claim: str) -> str:
    tokens: list[str] = []
    for token in _semantic_tokens(f"{hook} {claim}"):
        stem = FILLER_RE.sub("", token).strip()
        if len(stem) < 2 or stem in tokens:
            continue
        tokens.append(stem)
        if len(tokens) >= 3:
            break
    return " / ".join(tokens) or claim[:28] or hook[:28]


def semantic_signature(text: str) -> SemanticSignature:
    sentences = _semantic_sentences(text)
    hook = sentences[0] if sentences else _body_without_tags(text)[:60]
    action_sentence = ""
    for sentence in reversed(sentences):
        if ACTION_HINT_RE.search(sentence):
            action_sentence = sentence
            break
    if not action_sentence and len(sentences) >= 2:
        action_sentence = sentences[-1]
    claim = sentences[1] if len(sentences) >= 2 else hook
    if action_sentence and claim == action_sentence and len(sentences) >= 3:
        claim = sentences[-2]
    topic = _semantic_topic_text(hook, claim)
    structure = _semantic_pattern(sentences)
    hook_key = _semantic_key(hook, limit=6)
    topic_key = _semantic_key(topic, limit=4)
    claim_key = _semantic_key(claim, limit=7)
    takeaway_key = _semantic_key(action_sentence, limit=6)
    composite = "|".join([hook_key, topic_key, claim_key, takeaway_key, structure])
    signature = SemanticSignature(
        hook=hook.strip(),
        topic=topic.strip(),
        claim=claim.strip(),
        structure=structure,
        takeaway=action_sentence.strip(),
        hook_key=hook_key,
        topic_key=topic_key,
        claim_key=claim_key,
        takeaway_key=takeaway_key,
        semantic_fingerprint=sha1(composite.encode("utf-8")).hexdigest(),
    )
    print(
        "[SEMANTIC SUMMARY] "
        f"hook={signature.hook[:80]} "
        f"topic={signature.topic[:80]} "
        f"claim={signature.claim[:80]} "
        f"takeaway={signature.takeaway[:80]}"
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
        hook_key = str(entry.get("semantic_hook_key", "")).strip()
        topic_key = str(entry.get("semantic_topic_key", "")).strip()
        claim_key = str(entry.get("semantic_claim_key", "")).strip()
        takeaway_key = str(entry.get("semantic_takeaway_key", entry.get("semantic_action_key", ""))).strip()
        structure = str(entry.get("semantic_structure", entry.get("semantic_pattern", ""))).strip()
        entry_hook = str(entry.get("semantic_hook", "")).strip()
        entry_topic = str(entry.get("semantic_topic", entry.get("topic", ""))).strip()
        entry_claim = str(entry.get("semantic_claim", entry.get("core_claim", ""))).strip()
        entry_takeaway = str(entry.get("semantic_takeaway", entry.get("action_takeaway", ""))).strip()
        hook_dup = bool(hook_key and hook_key == candidate.hook_key)
        topic_dup = bool(topic_key and topic_key == candidate.topic_key)
        claim_dup = bool(claim_key and claim_key == candidate.claim_key)
        takeaway_dup = bool(takeaway_key and takeaway_key == candidate.takeaway_key)
        hook_close = _token_overlap_score(candidate.hook, entry_hook) >= 0.76
        topic_close = _token_overlap_score(candidate.topic, entry_topic) >= 0.72
        claim_close = _token_overlap_score(candidate.claim, entry_claim) >= 0.72
        takeaway_close = _token_overlap_score(candidate.takeaway, entry_takeaway) >= 0.7
        same_structure = bool(structure and structure == candidate.structure)
        is_duplicate = (
            hook_dup
            or claim_dup
            or (hook_close and topic_close)
            or topic_dup
            or claim_close
            or (topic_close and claim_close)
            or (topic_dup and takeaway_dup)
            or (claim_dup and takeaway_dup and same_structure)
            or (topic_close and claim_close and takeaway_close)
        )
        print(
            "[SEMANTIC CHECK] "
            f"candidate_topic={candidate.topic[:60]} "
            f"duplicate={'yes' if is_duplicate else 'no'}"
        )
        if is_duplicate:
            reason = "hook_duplicate" if hook_dup or hook_close else "topic_duplicate"
            if claim_dup or claim_close:
                reason = "claim_duplicate"
            elif topic_dup or topic_close:
                reason = "topic_duplicate"
            elif takeaway_dup or takeaway_close:
                reason = "takeaway_duplicate"
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


def semantic_stage_check(
    text: str,
    store: HistoryStore,
    *,
    slot: str | None = None,
    recent_limit: int = 24,
) -> SemanticStageCheckResult:
    candidate = semantic_signature(text)
    relevant_entries = [entry for entry in store.entries if not slot or str(entry.get("slot", "")).strip() == slot]
    relevant_entries = relevant_entries[-recent_limit:]
    warning_match: dict[str, Any] | None = None
    warning_reason = ""
    for entry in reversed(relevant_entries):
        hook_key = str(entry.get("semantic_hook_key", "")).strip()
        topic_key = str(entry.get("semantic_topic_key", "")).strip()
        claim_key = str(entry.get("semantic_claim_key", "")).strip()
        takeaway_key = str(entry.get("semantic_takeaway_key", entry.get("semantic_action_key", ""))).strip()
        structure = str(entry.get("semantic_structure", entry.get("semantic_pattern", ""))).strip()
        entry_hook = str(entry.get("semantic_hook", "")).strip()
        entry_topic = str(entry.get("semantic_topic", entry.get("topic", ""))).strip()
        entry_claim = str(entry.get("semantic_claim", entry.get("core_claim", ""))).strip()
        entry_takeaway = str(entry.get("semantic_takeaway", entry.get("action_takeaway", ""))).strip()
        same_structure = bool(structure and structure == candidate.structure)
        hook_exact = bool(hook_key and hook_key == candidate.hook_key)
        topic_exact = bool(topic_key and topic_key == candidate.topic_key)
        claim_exact = bool(claim_key and claim_key == candidate.claim_key)
        takeaway_exact = bool(takeaway_key and takeaway_key == candidate.takeaway_key)
        hook_close = _token_overlap_score(candidate.hook, entry_hook) >= 0.82
        topic_close = _token_overlap_score(candidate.topic, entry_topic) >= 0.72
        claim_close = _token_overlap_score(candidate.claim, entry_claim) >= 0.72
        takeaway_close = _token_overlap_score(candidate.takeaway, entry_takeaway) >= 0.72
        hard_duplicate = (
            hook_exact
            or (topic_exact and claim_exact)
            or (claim_exact and same_structure)
            or (hook_close and claim_close and same_structure)
            or (
                bool(str(entry.get("semantic_fingerprint", "")).strip())
                and str(entry.get("semantic_fingerprint", "")).strip() == candidate.semantic_fingerprint
            )
        )
        if hard_duplicate:
            reason = "hook_duplicate" if hook_exact or hook_close else "semantic_duplicate"
            if claim_exact:
                reason = "claim_duplicate"
            elif topic_exact:
                reason = "topic_duplicate"
            return SemanticStageCheckResult(True, True, reason, candidate, entry)
        if not warning_match and (topic_exact or claim_exact or topic_close or claim_close or takeaway_exact or takeaway_close or same_structure):
            warning_match = entry
            if claim_exact or claim_close:
                warning_reason = "claim_near_duplicate"
            elif topic_exact or topic_close:
                warning_reason = "topic_near_duplicate"
            elif same_structure:
                warning_reason = "structure_near_duplicate"
            else:
                warning_reason = "takeaway_near_duplicate"
    return SemanticStageCheckResult(False, bool(warning_match), warning_reason, candidate, warning_match)


def recent_evening_signatures(store: HistoryStore, limit: int = 10) -> list[dict[str, str]]:
    relevant = [entry for entry in store.entries if str(entry.get("slot", "")).strip() == "evening"]
    sliced = relevant[-limit:]
    print(f"[EVENING UNIQUE LOAD] history_count={len(sliced)}")
    results: list[dict[str, str]] = []
    for entry in sliced:
        results.append(
            {
                "hook": str(entry.get("semantic_hook", "")).strip(),
                "topic": str(entry.get("semantic_topic", entry.get("topic", ""))).strip(),
                "claim": str(entry.get("semantic_claim", entry.get("core_claim", ""))).strip(),
                "structure": str(entry.get("semantic_structure", entry.get("semantic_pattern", ""))).strip(),
                "takeaway": str(entry.get("semantic_takeaway", entry.get("action_takeaway", ""))).strip(),
            }
        )
    return results


def evening_duplicate_check(
    text: str,
    store: HistoryStore,
    *,
    recent_limit: int = 10,
) -> EveningDuplicateCheckResult:
    candidate = semantic_signature(text)
    relevant_entries = [entry for entry in store.entries if str(entry.get("slot", "")).strip() == "evening"]
    relevant_entries = relevant_entries[-recent_limit:]
    print(f"[EVENING UNIQUE LOAD] history_count={len(relevant_entries)}")
    for entry in reversed(relevant_entries):
        entry_hook = str(entry.get("semantic_hook", "")).strip()
        entry_topic = str(entry.get("semantic_topic", entry.get("topic", ""))).strip()
        entry_claim = str(entry.get("semantic_claim", entry.get("core_claim", ""))).strip()
        entry_structure = str(entry.get("semantic_structure", entry.get("semantic_pattern", ""))).strip()
        entry_takeaway = str(entry.get("semantic_takeaway", entry.get("action_takeaway", ""))).strip()
        hook_dup = _token_overlap_score(candidate.hook, entry_hook) >= 0.76
        topic_dup = _token_overlap_score(candidate.topic, entry_topic) >= 0.72
        claim_dup = _token_overlap_score(candidate.claim, entry_claim) >= 0.72
        structure_dup = bool(candidate.structure and entry_structure and candidate.structure == entry_structure)
        takeaway_dup = _token_overlap_score(candidate.takeaway, entry_takeaway) >= 0.72
        print(f"[EVENING HOOK CHECK] candidate={candidate.hook[:60]} duplicate={'yes' if hook_dup else 'no'}")
        print(
            f"[EVENING STRUCTURE CHECK] candidate={candidate.structure} duplicate={'yes' if structure_dup else 'no'}"
        )
        print(
            "[EVENING SEMANTIC CHECK] "
            f"topic={candidate.topic[:50]} claim={candidate.claim[:50]} "
            f"duplicate={'yes' if (topic_dup or claim_dup) else 'no'}"
        )
        if hook_dup:
            return EveningDuplicateCheckResult(True, "hook_duplicate", candidate, entry)
        if claim_dup:
            return EveningDuplicateCheckResult(True, "claim_duplicate", candidate, entry)
        if topic_dup:
            return EveningDuplicateCheckResult(True, "semantic_duplicate", candidate, entry)
        if structure_dup and (claim_dup or takeaway_dup or topic_dup):
            return EveningDuplicateCheckResult(True, "structure_duplicate", candidate, entry)
        if structure_dup and takeaway_dup:
            return EveningDuplicateCheckResult(True, "structure_duplicate", candidate, entry)
    return EveningDuplicateCheckResult(False, "", candidate, None)


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


def history_content_types(store: HistoryStore, slot: str | None = None, limit: int | None = None) -> list[str]:
    relevant = [entry for entry in store.entries if not slot or str(entry.get("slot", "")).strip() == slot]
    if limit is not None:
        relevant = relevant[-limit:]
    values: list[str] = []
    for entry in relevant:
        content_type = str(entry.get("content_type", "")).strip().lower()
        if content_type:
            values.append(content_type)
    return values


def semantic_summaries(store: HistoryStore, slot: str | None = None, limit: int = 8) -> list[str]:
    relevant = [entry for entry in store.entries if not slot or str(entry.get("slot", "")).strip() == slot]
    summaries: list[str] = []
    for entry in reversed(relevant[-limit:]):
        content_type = str(entry.get("content_type", "")).strip()
        hook = str(entry.get("semantic_hook", "")).strip()
        topic = str(entry.get("semantic_topic", entry.get("topic", ""))).strip()
        claim = str(entry.get("semantic_claim", entry.get("core_claim", ""))).strip()
        takeaway = str(entry.get("semantic_takeaway", entry.get("action_takeaway", ""))).strip()
        pattern = str(entry.get("semantic_structure", entry.get("semantic_pattern", entry.get("pattern_id", "")))).strip()
        if hook or topic or claim or takeaway or content_type:
            summaries.append(
                " / ".join(part for part in [content_type, hook, topic, claim, takeaway, pattern] if part)
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
    content_type: str = "",
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
            "content_type": content_type,
            "tweet_id": tweet_id,
            "created_at": created_at or posted_at,
            "posted_at": posted_at,
            "topic": topic or semantic.topic,
            "tags": extract_tags(raw),
            "pattern_id": pattern_id or semantic.structure,
            "semantic_hook": semantic.hook,
            "semantic_topic": semantic.topic,
            "semantic_claim": semantic.claim,
            "semantic_structure": semantic.structure,
            "semantic_takeaway": semantic.takeaway,
            "core_claim": semantic.claim,
            "action_takeaway": semantic.takeaway,
            "semantic_hook_key": semantic.hook_key,
            "semantic_topic_key": semantic.topic_key,
            "semantic_claim_key": semantic.claim_key,
            "semantic_takeaway_key": semantic.takeaway_key,
            "semantic_action_key": semantic.takeaway_key,
            "semantic_fingerprint": semantic.semantic_fingerprint,
        }
    )
