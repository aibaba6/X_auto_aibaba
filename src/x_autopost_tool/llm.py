from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from .models import ContentItem, DraftPost, QuoteCandidate


SYSTEM_PROMPT = """あなたはX運用の編集者です。事実を過度に断定せず、短文で価値を出してください。"""
URL_RE = re.compile(r"https?://\S+")
HASHTAG_RE = re.compile(r"#([^\s#]+)")
LEADING_LABEL_RE = re.compile(
    r"^\s*(デザイナーあるある|あるある|豆知識|基礎|応用|ポイント|結論)\s*[：:]\s*",
    re.IGNORECASE,
)
COPULA_DA_RE = re.compile(r"([^\n。！？]{1,40})だ。")


def _client() -> OpenAI:
    return OpenAI()


def _slot_default_tags(slot_name: str) -> list[str]:
    if slot_name == "morning":
        return ["#デザイン基礎", "#UIデザイン", "#情報設計"]
    if slot_name == "noon":
        return ["#AI", "#AIニュース", "#デザイン"]
    return ["#デザイナーあるある", "#デザイン", "#仕事あるある"]


def normalize_x_post_text(text: str, slot_name: str = "morning") -> str:
    """
    Enforce:
    - hashtags: 2-3
    - hashtag line is separated from body by two newlines
    """
    raw = (text or "").strip()
    tags_found = [f"#{m.group(1)}" for m in HASHTAG_RE.finditer(raw)]
    # Remove hashtags from body so we can place them at the end consistently.
    body = HASHTAG_RE.sub("", raw)
    # Remove explicit section labels the user does not want in copy.
    lines = []
    for ln in body.splitlines():
        cleaned = LEADING_LABEL_RE.sub("", ln).strip()
        cleaned = cleaned.replace("豆知識として、", "").replace("豆知識として", "")
        cleaned = cleaned.replace("デザイナーあるあるとして、", "").replace("デザイナーあるあるとして", "")
        lines.append(cleaned)
    body = "\n".join(lines)
    # Tone normalization: avoid hard "〜だ。", prefer "です。" or concise ending.
    # Keep meaning while softening tone for this account style.
    body = COPULA_DA_RE.sub(r"\1です。", body)
    body = re.sub(r"[ \t]+$", "", body, flags=re.MULTILINE).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)

    tags: list[str] = []
    seen = set()
    for t in tags_found:
        if t not in seen:
            seen.add(t)
            tags.append(t)
    for d in _slot_default_tags(slot_name):
        if len(tags) >= 2:
            break
        if d not in seen:
            seen.add(d)
            tags.append(d)
    if len(tags) > 3:
        tags = tags[:3]
    if len(tags) < 2:
        # Final fallback for extreme cases
        for d in ["#デザイン", "#AI"]:
            if d not in seen:
                tags.append(d)
                seen.add(d)
            if len(tags) >= 2:
                break

    tag_line = " ".join(tags[:3])
    if body:
        return f"{body}\n\n{tag_line}"
    return tag_line


def build_post_drafts(
    model: str,
    items: list[ContentItem],
    tone: str,
    audience: str,
    prediction_horizon: str,
    post_style_template: list[str],
    voice_guide: list[str],
    style_reference_posts: list[str],
    weekday_theme: str,
    slot_name: str,
    slot_style: str,
    slot_min_chars: int,
    slot_max_chars: int,
    max_posts: int,
    knowledge_snippets: list[str] | None = None,
) -> list[DraftPost]:
    payload = [
        {
            "title": i.title,
            "summary": i.summary[:400],
            "url": i.url,
        }
        for i in items
    ]

    ksn = knowledge_snippets or []

    prompt = f"""
対象読者: {audience}
文体: {tone}
予測レンジ: {prediction_horizon}
投稿テンプレート: {json.dumps(post_style_template, ensure_ascii=False)}
文体ガイド: {json.dumps(voice_guide, ensure_ascii=False)}
文体参照（過去投稿サンプル）: {json.dumps(style_reference_posts[:6], ensure_ascii=False)}
PDFストック知見（参考）: {json.dumps(ksn[:4], ensure_ascii=False)}
曜日テーマ: {weekday_theme}
投稿枠: {slot_name}
投稿枠ルール: {slot_style}

以下の情報を元に、X投稿案を{max_posts}本作ってください。
各投稿は日本語{slot_min_chars}-{slot_max_chars}文字、1つの具体的示唆と1つの予測を含める。
次の4要素を自然に含めること: 事実 / 示唆 / 予測 / 行動。
本文は自然文のみ。`事実:` や `示唆:` のようなラベルを書かないこと。
「デザイナーあるある:」「豆知識:」「基礎:」「応用:」などの見出しラベルは禁止。
最新性が必要な内容はニュース/X由来を優先し、PDFは基礎知識・背景の補強に使うこと。
冷静さの中に、僅かなゆるさ・カジュアルさを入れること。
語尾は「〜だ。」を避け、「です。」または体言止め（例: 〜が肝心。）をバランスよく使うこと。
過去投稿サンプルのニュアンス・言葉遣い・改行リズムを優先して踏襲すること。
改行で読みやすくすること（2-4段落、1段落1-2文）。
必要に応じて箇条書きは1-3項目まで（長い箇条書きは禁止）。
中黒（・）や短い記号で読みやすくしてよい。
絵文字は0-2個まで。
ハッシュタグは文末に2-3個。
ハッシュタグは本文の最後から2回改行して、独立した1行で配置する。
JSONのみで返す: {{"posts":[{{"text":"...","reason":"..."}}]}}

情報:
{json.dumps(payload, ensure_ascii=False)}
""".strip()

    res = _client().responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    content = res.output_text
    parsed: dict[str, Any] = json.loads(content)
    posts = []
    for p in parsed.get("posts", []):
        txt = normalize_x_post_text(str(p["text"]), slot_name=slot_name)
        posts.append(DraftPost(text=txt, reason=p.get("reason", "")))
    return posts[:max_posts]


def build_quote_post(model: str, candidate: QuoteCandidate, tone: str, audience: str) -> str:
    prompt = f"""
対象読者: {audience}
文体: {tone}

次の投稿を引用する前提で、引用コメント案を1本作成してください。
- 日本語80-180文字
- 投稿内容を肯定的に受け止める
- 相手への敬意を保つ
- 原文の要点をなぞるだけで終わらせず、新しい知見・別角度の補足を1つ入れる
- 今後どう広がるか、3〜6ヶ月の予測を短く1つ入れる
- URLを本文に含めない
- 断定しすぎない
- 2〜4段落で読みやすく改行する
- ハッシュタグは文末に2〜3個
- 出力は本文のみ

投稿者: @{candidate.author}
原文: {candidate.text}
""".strip()

    res = _client().responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    text = normalize_x_post_text(res.output_text.strip(), slot_name="noon")
    text = URL_RE.sub("", text).strip()
    return text
