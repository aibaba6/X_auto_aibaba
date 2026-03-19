from __future__ import annotations

import re
import unicodedata

from .text_normalize import cleanup_post_text


JP_CHAR_RE = re.compile(r"[ぁ-んァ-ン一-龠]")
TAG_RE = re.compile(r"#\S+")
MULTISPACE_RE = re.compile(r"[ \t\u3000]+")
BROKEN_JP_SPACE_RE = re.compile(r"(?<=[ぁ-んァ-ン一-龠])\s+(?=[ぁ-んァ-ン一-龠])")
BROKEN_QUOTE_SPACE_RE = re.compile(r'"\s+|\s+"')
BROKEN_PAREN_SPACE_RE = re.compile(r"（\s+|\s+）")
BROKEN_EN_SINGLE_RE = re.compile(r"\b([A-Za-z]{2,})\s+([A-Za-z])\b")
BROKEN_EN_PAIR_RE = re.compile(r"\b([A-Za-z])\s+([A-Za-z]{2,})\b")


def _clean_fragment(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = MULTISPACE_RE.sub(" ", value)
    value = BROKEN_JP_SPACE_RE.sub("", value)
    value = BROKEN_QUOTE_SPACE_RE.sub('"', value)
    value = BROKEN_PAREN_SPACE_RE.sub(lambda m: "（" if "（" in m.group(0) else "）", value)
    for _ in range(3):
        repaired = BROKEN_EN_SINGLE_RE.sub(r"\1\2", value)
        repaired = BROKEN_EN_PAIR_RE.sub(r"\1\2", repaired)
        if repaired == value:
            break
        value = repaired
    value = value.strip()
    return value


def _clean_tags(tags: str) -> list[str]:
    found = [part.strip() for part in TAG_RE.findall(tags or "")]
    deduped: list[str] = []
    seen: set[str] = set()
    for tag in found:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
        if len(deduped) >= 3:
            break
    return deduped


def format_quote_post(
    english_quote: str,
    translation: str,
    author: str,
    interpretation_lines: list[str],
    tags: str,
) -> str:
    english = _clean_fragment(english_quote).strip('"')
    translation_value = _clean_fragment(translation).strip("（）")
    author_value = _clean_fragment(author)
    body_lines = [_clean_fragment(line) for line in interpretation_lines if _clean_fragment(line)]
    tag_lines = _clean_tags(tags)
    quote_line = f"\"{english}\""
    translation_line = f"（{translation_value}）"
    parts = [quote_line, translation_line, "", author_value]
    if body_lines:
        parts.extend([""] + body_lines)
    if tag_lines:
        parts.extend([""] + tag_lines)
    text = "\n".join(parts)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return cleanup_post_text(text)


def validate_quote_post(text: str) -> tuple[bool, dict[str, bool]]:
    raw = (text or "").strip()
    lines = [line.strip() for line in raw.splitlines()]
    non_empty = [line for line in lines if line]
    english = bool(non_empty) and non_empty[0].startswith('"') and non_empty[0].endswith('"')
    translation = len(non_empty) >= 2 and non_empty[1].startswith("（") and non_empty[1].endswith("）")
    author = len(non_empty) >= 3 and not non_empty[2].startswith("#") and "（" not in non_empty[2] and '"' not in non_empty[2]
    isolated_brackets = any(line in {"（", "）", "(", ")"} for line in non_empty)
    broken_jp = bool(BROKEN_JP_SPACE_RE.search(raw))
    broken_en = bool(BROKEN_EN_SINGLE_RE.search(raw) or BROKEN_EN_PAIR_RE.search(raw))
    order_ok = english and translation and author
    spacing_ok = not isolated_brackets and not broken_jp and not broken_en
    return (
        order_ok and spacing_ok,
        {
            "english": english,
            "translation": translation,
            "author": author,
            "spacing_ok": spacing_ok,
        },
    )
