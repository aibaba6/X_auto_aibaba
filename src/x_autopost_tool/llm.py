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
LEADING_BANNED_PHRASE_RE = re.compile(
    r"^\s*(今日は|今回は|ここで|まずは|〜してみましょう|してみましょう|していきます|見ていきます|考えていきます)\s*"
)
LOW_DENSITY_PHRASES = [
    "今日は",
    "今回は",
    "ここで",
    "まずは",
    "してみましょう",
    "していきます",
]
CONCLUSION_HINTS = [
    "重要",
    "肝",
    "本質",
    "結局",
    "必要",
    "効く",
    "決まる",
    "左右",
    "変わる",
    "設計",
    "改善",
    "順序",
    "比較",
]


def _client() -> OpenAI:
    return OpenAI()


def _slot_default_tags(slot_name: str) -> list[str]:
    if slot_name == "morning":
        return ["#デザイン基礎", "#UIデザイン", "#情報設計"]
    if slot_name == "noon":
        return ["#AI", "#AIニュース", "#デザイン"]
    return ["#デザイナーあるある", "#デザイン", "#仕事あるある"]


def _strip_banned_leading_phrases(text: str) -> str:
    cleaned = (text or "").strip()
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = LEADING_BANNED_PHRASE_RE.sub("", cleaned).lstrip("、。・:： ")
    return cleaned.strip()


def _sentences_from_body(text: str) -> list[str]:
    body = HASHTAG_RE.sub("", text or "").strip()
    parts = re.split(r"(?<=[。！？])|\n+", body)
    return [p.strip() for p in parts if p and p.strip()]


def _is_conclusion_like(sentence: str) -> bool:
    s = sentence.strip()
    if len(s) < 10:
        return False
    if "?" in s or "？" in s:
        return False
    return any(hint in s for hint in CONCLUSION_HINTS) or "は" in s


def _reorder_to_conclusion_first(text: str) -> str:
    sentences = _sentences_from_body(text)
    if len(sentences) < 2:
        return text.strip()
    first = sentences[0]
    if _is_conclusion_like(first):
        return text.strip()
    for idx, sentence in enumerate(sentences[1:], start=1):
        if _is_conclusion_like(sentence):
            reordered = [sentence] + sentences[:idx] + sentences[idx + 1 :]
            tag_match = re.search(r"(\n\n#[\s\S]+)$", text.strip())
            tag_block = tag_match.group(1) if tag_match else ""
            body = "\n".join(reordered).strip()
            return f"{body}{tag_block}".strip()
    return text.strip()


def enforce_post_density_rules(text: str, slot_name: str = "morning") -> str:
    raw = (text or "").strip()
    body, _, tail = raw.partition("\n\n#")
    body = _strip_banned_leading_phrases(body)
    lines = []
    for ln in body.splitlines():
        cleaned = ln.strip()
        cleaned = _strip_banned_leading_phrases(cleaned)
        for phrase in LOW_DENSITY_PHRASES:
            if cleaned.startswith(phrase):
                cleaned = cleaned[len(phrase) :].lstrip("、。・:： ")
        lines.append(cleaned)
    body = "\n".join([ln for ln in lines if ln]).strip()
    body = _reorder_to_conclusion_first(body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if tail:
        return f"{body}\n\n#{tail}".strip()
    return body


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
        cleaned = _strip_banned_leading_phrases(cleaned)
        lines.append(cleaned)
    body = "\n".join(lines)
    body = enforce_post_density_rules(body, slot_name=slot_name)
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
    recent_self_posts: list[str] | None = None,
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
    recent_posts = recent_self_posts or []

    prompt = f"""
対象読者: {audience}
文体: {tone}
予測レンジ: {prediction_horizon}
投稿テンプレート: {json.dumps(post_style_template, ensure_ascii=False)}
文体ガイド: {json.dumps(voice_guide, ensure_ascii=False)}
文体参照（過去投稿サンプル）: {json.dumps(style_reference_posts[:6], ensure_ascii=False)}
PDFストック知見（参考）: {json.dumps(ksn[:4], ensure_ascii=False)}
直近の自分の投稿（重複回避用）: {json.dumps(recent_posts[:8], ensure_ascii=False)}
曜日テーマ: {weekday_theme}
投稿枠: {slot_name}
投稿枠ルール: {slot_style}

以下の情報を元に、X投稿案を{max_posts}本作ってください。
各投稿は日本語{slot_min_chars}-{slot_max_chars}文字、1つの具体的示唆と1つの予測を含める。
次の4要素を自然に含めること: 事実 / 示唆 / 予測 / 行動。
本文は自然文のみ。`事実:` や `示唆:` のようなラベルを書かないこと。
「デザイナーあるある:」「豆知識:」「基礎:」「応用:」などの見出しラベルは禁止。
禁止導入語: 「今日は」「今回は」「ここで」「まずは」「〜してみましょう」「〜していきます」。
文章構造は必ず「結論 → 理由 → 具体的な設計・行動」。
講義型ではなく洞察型にすること。1文目は説明の前置きではなく、最も言いたい結論を書くこと。
意味のない接続語や前置きを削り、SNS投稿として密度を高くすること。
抽象語だけで逃げず、設計・判断・比較・行動のどれかが見える文にすること。
最新性が必要な内容はニュース/X由来を優先し、PDFは基礎知識・背景の補強に使うこと。
冷静さの中に、僅かなゆるさ・カジュアルさを入れること。
語尾は「〜だ。」を避け、「です。」または体言止め（例: 〜が肝心。）をバランスよく使うこと。
過去投稿サンプルのニュアンス・言葉遣い・改行リズムを優先して踏襲すること。
ただし、直近の自分の投稿と同じ切り口・同じ主張・同じ言い回しは避けること。
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


def build_noon_news_post(
    model: str,
    items: list[ContentItem],
    tone: str,
    audience: str,
    prediction_horizon: str,
    weekday_theme: str,
    recent_self_posts: list[str] | None = None,
) -> DraftPost | None:
    payload = [
        {
            "title": i.title,
            "summary": i.summary[:320],
            "url": i.url,
        }
        for i in items[:5]
    ]
    if not payload:
        return None

    prompt = f"""
対象読者: {audience}
文体: {tone}
曜日テーマ: {weekday_theme}
予測レンジ: {prediction_horizon}
直近の自分の投稿（重複回避用）: {json.dumps((recent_self_posts or [])[:6], ensure_ascii=False)}

以下のニュース候補を材料に、昼枠向けのX投稿文を1本だけ作成してください。
- 日本語90-180文字
- AIニュースの要点を最初の1-2文で簡潔に要約
- その後に「これからどう効いてくるか」の予測を1文入れる
- 最後に、実務者が今日試せる小さな行動を1文入れる
- 「今日は」「今回は」「ここで」「まずは」「〜してみましょう」「〜していきます」は使わない
- 1文目は必ず結論
- URLは本文に含めない
- 引用投稿前提ではなく、通常投稿として成立させる
- 冷静で実務的、少しカジュアル
- 同じ語尾を連続させない
- 2-4段落、必要なら短い箇条書き1-2項目
- ハッシュタグは文末に2-3個
- JSONのみで返す: {{"text":"...","reason":"..."}}

ニュース候補:
{json.dumps(payload, ensure_ascii=False)}
""".strip()

    res = _client().responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    parsed: dict[str, Any] = json.loads(res.output_text)
    text = normalize_x_post_text(str(parsed.get("text", "")).strip(), slot_name="noon")
    text = URL_RE.sub("", text).strip()
    if not text:
        return None
    return DraftPost(text=text, reason=str(parsed.get("reason", "")).strip() or "noon-news")
