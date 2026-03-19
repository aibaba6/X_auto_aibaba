from __future__ import annotations

import re


HASHTAG_LINE_RE = re.compile(r"^\s*#")
BULLET_LINE_RE = re.compile(r"^\s*(?:[-*•]|[0-9]+\.)\s+")
URL_FRAGMENT_RE = re.compile(r"(https?://|www\.)[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]*$")
MULTISPACE_RE = re.compile(r"[ \t\u3000]+")
JP_INTERNAL_SPACE_RE = re.compile(r"(?<=[ぁ-んァ-ン一-龠])\s+(?=[ぁ-んァ-ン一-龠])")
JP_PUNCT_SPACE_RE = re.compile(r"\s+(?=[、。！？：；）】」』])")
OPEN_BRACKET_SPACE_RE = re.compile(r"(?<=[（【「『])\s+")
LINE_EDGE_SPACE_RE = re.compile(r"[ \t]+\n|\n[ \t]+")

OPENING_BRACKETS = ("(", "（", "「", "『", "【", "《", "〈", "[")
CLOSING_PREFIXES = ("、", "。", "！", "?", "？", "!", "）", "」", "』", "】", "》", "〉", "]")
PARTICLE_ENDINGS = (
    "は",
    "が",
    "を",
    "に",
    "へ",
    "で",
    "と",
    "も",
    "の",
    "や",
    "から",
    "まで",
    "より",
    "だけ",
    "ほど",
    "など",
    "って",
    "て",
)
SENTENCE_ENDINGS = ("。", "！", "?", "？", "!")


def _is_special_line(line: str) -> bool:
    stripped = line.strip()
    return bool(HASHTAG_LINE_RE.match(stripped) or BULLET_LINE_RE.match(stripped))


def _ends_with_particle(line: str) -> bool:
    stripped = line.rstrip()
    return any(stripped.endswith(token) for token in PARTICLE_ENDINGS)


def _looks_like_url_join(prev: str, nxt: str) -> bool:
    left = prev.rstrip()
    right = nxt.lstrip()
    return bool(URL_FRAGMENT_RE.search(left)) and bool(re.match(r"^[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", right))


def _join_lines(prev: str, nxt: str) -> str:
    left = prev.rstrip()
    right = nxt.lstrip()
    if not left:
        return right
    if not right:
        return left
    if _looks_like_url_join(left, right):
        return f"{left}{right}"
    if left.endswith(OPENING_BRACKETS) or right.startswith(CLOSING_PREFIXES) or _ends_with_particle(left):
        return f"{left}{right}"
    if left[-1].isalnum() and right[0].isalnum():
        return f"{left} {right}"
    return f"{left}{right}"


def _should_keep_break(prev: str, nxt: str) -> bool:
    left = prev.strip()
    right = nxt.strip()
    if not left or not right:
        return True
    if _is_special_line(left) or _is_special_line(right):
        return True
    if HASHTAG_LINE_RE.match(right):
        return True
    if left.endswith(SENTENCE_ENDINGS):
        return True
    if len(left) <= 14 and not _ends_with_particle(left):
        return True
    return False


def _cleanup_paragraph(lines: list[str]) -> list[str]:
    cleaned = [ln.strip() for ln in lines if ln.strip()]
    if not cleaned:
        return []
    if len(cleaned) == 1:
        return cleaned
    out: list[str] = []
    current = cleaned[0]
    for nxt in cleaned[1:]:
        if _should_keep_break(current, nxt):
            out.append(current)
            current = nxt
        else:
            current = _join_lines(current, nxt)
    out.append(current)
    return out


def cleanup_post_linebreaks(text: str) -> str:
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""
    lines = raw.split("\n")
    blocks: list[str] = []
    bucket: list[str] = []
    for line in lines:
        if not line.strip():
            if bucket:
                blocks.append("\n".join(_cleanup_paragraph(bucket)))
                bucket = []
            blocks.append("")
            continue
        bucket.append(line)
    if bucket:
        blocks.append("\n".join(_cleanup_paragraph(bucket)))

    merged: list[str] = []
    blank_pending = False
    for block in blocks:
        if block == "":
            if merged:
                blank_pending = True
            continue
        if blank_pending and merged:
            merged.append("")
        merged.append(block)
        blank_pending = False
    return "\n".join(merged).strip()


def cleanup_post_text(text: str) -> str:
    """
    Normalize visible spacing without changing meaning.
    Rules:
    - remove needless spaces between Japanese characters
    - remove spaces before Japanese punctuation / after opening brackets
    - trim spaces around newlines and line ends
    - preserve normal English word spacing
    """
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = cleanup_post_linebreaks(raw)
    before = value
    value = LINE_EDGE_SPACE_RE.sub("\n", value)
    value = JP_INTERNAL_SPACE_RE.sub("", value)
    value = JP_PUNCT_SPACE_RE.sub("", value)
    value = OPEN_BRACKET_SPACE_RE.sub("", value)
    value = MULTISPACE_RE.sub(" ", value)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    print(f"[TEXT CLEANUP] spacing_fix_applied={'yes' if value != before else 'no'}")
    return value
