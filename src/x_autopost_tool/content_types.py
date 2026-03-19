from __future__ import annotations

import random

from .llm import normalize_x_post_text
from .models import ContentItem, DraftPost
from .quote_format import format_quote_post, validate_quote_post


MORNING_TIMELESS = [
    {
        "topic": "余白は情報の優先順位を見せる",
        "insight": "詰め込みを減らすと、何を見るべきかが先に伝わります。",
        "action": "主役と脇役の差だけ整えて比較する。",
        "tags": "#デザイン基礎 #レイアウト #情報設計",
        "structure": "一言断言型",
    },
    {
        "topic": "視線誘導は大きさより順序設計",
        "insight": "強い要素を増やすより、読む順番を固定したほうが崩れにくいです。",
        "action": "見出し → 補足 → CTA の順にコントラストを置く。",
        "tags": "#視線設計 #UIデザイン #タイポグラフィ",
        "structure": "比較型",
    },
    {
        "topic": "色は装飾より役割で決める",
        "insight": "色数が増えるほど判断が遅くなり、主役がぼやけやすいです。",
        "action": "強調色を1色に絞り、意味を固定する。",
        "tags": "#配色 #デザイン原則 #UI設計",
        "structure": "一言断言型",
    },
]

MORNING_PRACTICAL = [
    {
        "topic": "フィードバックが割れたときの整理",
        "insight": "案の良し悪しより、どの基準で見るかが揃っていないことが多いです。",
        "action": "先に判断軸を3つだけ並べてから比較する。",
        "tags": "#デザイン実務 #フィードバック #仕事術",
        "structure": "実務整理型",
    },
    {
        "topic": "修正を始める前の観察",
        "insight": "触る前にズレの理由が言えるだけで、戻りがかなり減ります。",
        "action": "直す理由を1行メモしてから手を動かす。",
        "tags": "#修正対応 #デザイン実務 #制作フロー",
        "structure": "観察型",
    },
    {
        "topic": "UIの違和感の見つけ方",
        "insight": "しっくりこない画面は、要素そのものより比較軸が曖昧なことがあります。",
        "action": "余白、文字サイズ、コントラストのどれがズレているか1つ決める。",
        "tags": "#UI改善 #デザイン実務 #判断基準",
        "structure": "気づき型",
    },
]

MORNING_INSIGHT = [
    {
        "topic": "良いデザインは説明量が少ない",
        "insight": "見た目の派手さより、迷わないことのほうが体験に効きます。",
        "action": "説明が長い画面ほど、判断を1つ減らせるかを見る。",
        "tags": "#UX #設計思考 #デザインメモ",
        "structure": "一言断言型",
    },
    {
        "topic": "デザイン史は今の判断にも効く",
        "insight": "流行の形だけを見るより、なぜその構造が残ったかを見ると再利用しやすいです。",
        "action": "今のUIを、役割の分け方という視点で見直す。",
        "tags": "#デザイン史 #UI設計 #デザイン思考",
        "structure": "解釈型",
    },
]

MORNING_QUOTES = [
    {
        "quote": "Good design is as little design as possible.",
        "translation": "良いデザインは、必要以上に足さない状態に近い。",
        "author": "Dieter Rams",
        "interpretation": "足し算より、何を残すかの判断に設計力が出ます。",
        "action": "役割が重複している要素から先に見直す。",
        "tags": "#デザイン思考 #UIデザイン #実務",
    },
    {
        "quote": "Design is not just what it looks like and feels like. Design is how it works.",
        "translation": "デザインは見た目や感触だけではない。どう機能するかだ。",
        "author": "Steve Jobs",
        "interpretation": "見た目を整える前に、使い方の筋が通っているかを確認する必要があります。",
        "action": "画面を磨く前に、1操作ごとの迷いがないかを見る。",
        "tags": "#UX設計 #プロダクトデザイン #実務",
    },
    {
        "quote": "Design is a way of life, a point of view.",
        "translation": "デザインは生き方であり、ものの見方そのものだ。",
        "author": "Paul Rand",
        "interpretation": "装飾ではなく、どこに視点を置くかが設計に出ます。",
        "action": "誰の判断を助けたいのかを言葉にしてから直す。",
        "tags": "#デザイン思考 #ブランド設計 #実務",
    },
]

EVENING_TIMELESS = [
    {
        "topic": "余白は感覚より順序を整えるために使う",
        "insight": "要素を減らすだけでなく、読む順番を作ると疲れた頭でも入りやすいです。",
        "action": "最後に余白を足す前に、情報の並び順を見直す。",
        "tags": "#レイアウト #デザイン原則 #制作フロー",
        "structure": "比較型",
    },
    {
        "topic": "タイポグラフィは夜ほど差が出る",
        "insight": "判断力が落ちる時間ほど、文字組みの整理が体験を支えます。",
        "action": "文字サイズより先に、行間と情報のまとまりを見る。",
        "tags": "#タイポグラフィ #UIデザイン #デザイン原則",
        "structure": "一言断言型",
    },
]

EVENING_PRACTICAL = [
    {
        "topic": "説明に時間がかかる日は、案より基準が散っている",
        "insight": "デザインの良し悪しより、どこを見るかが揃っていないことがあります。",
        "action": "スクショ1枚に理由を1行添えるだけで会話が短くなります。",
        "tags": "#デザイン実務 #コミュニケーション #仕事術",
        "structure": "観察型",
    },
    {
        "topic": "進んだ量より判断が減った量が効く日がある",
        "insight": "作業量が多くても、迷いが残ると前進感は薄くなります。",
        "action": "決めない論点を先に外すだけで、画面はかなり整います。",
        "tags": "#仕事術 #デザイン現場 #小さな改善",
        "structure": "実務整理型",
    },
    {
        "topic": "修正依頼が重なったら全部を同じ熱量で返さない",
        "insight": "返す順番より、返さない論点を先に決めたほうが崩れにくいです。",
        "action": "次に迷わないメモだけ残して区切る。",
        "tags": "#制作現場 #修正対応 #仕事術",
        "structure": "問題提起型",
    },
]

EVENING_INSIGHT = [
    {
        "topic": "作業ログを見返すと、迷う場所はだいたい同じ",
        "insight": "技術不足より、判断基準が曖昧な場所で止まっていることが多いです。",
        "action": "翌日の自分が迷わない条件を1行だけ残す。",
        "tags": "#制作フロー #継続改善 #デザインメモ",
        "structure": "気づき型",
    },
    {
        "topic": "良い案ほど最初は伝わりにくい",
        "insight": "熱量が先に走ると、判断基準の共有が追いつかないことがあります。",
        "action": "図を1枚足して、見てほしい順番を先に揃える。",
        "tags": "#提案資料 #デザイン思考 #仕事あるある",
        "structure": "気づき型",
    },
]


def _normalize(text: str, slot_name: str) -> str:
    return normalize_x_post_text(text, slot_name=slot_name)


def _draft(
    text: str,
    reason: str,
    content_type: str,
    topic: str,
    claim: str,
    angle: str,
    structure: str,
    pattern_type: str,
) -> DraftPost:
    return DraftPost(
        text=text,
        reason=reason,
        content_type=content_type,
        pattern_type=pattern_type,
        topic=topic,
        claim=claim,
        angle=angle,
        structure=structure,
    )


def _trend_topic_from_item(item: ContentItem) -> tuple[str, str]:
    title = item.title.replace("\n", " ").strip()
    summary = item.summary.replace("\n", " ").strip()[:90]
    topic = f"{title} をデザイン視点で見る"
    body = (
        f"{title} は、表現の新しさより使い方の整理で差が出やすい流れです。\n"
        f"{summary} を見ると、見た目より判断の軽さが評価されやすい。\n"
        "流れを追うなら、誰の迷いを減らしているかを見る。"
    )
    return topic, body


def _latest_topic_from_item(item: ContentItem) -> tuple[str, str]:
    title = item.title.replace("\n", " ").strip()
    summary = item.summary.replace("\n", " ").strip()[:90]
    topic = f"{title} から読む最近のデザインの流れ"
    body = (
        f"{title} は、最近のデザインが派手さより運用と体験の整合へ寄っていることを示しています。\n"
        f"{summary} を見ると、足す方向より削って伝える方向が強い。\n"
        "最新情報を見るときほど、残す判断のほうが参考になります。"
    )
    return topic, body


def _sentence(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    if value[-1] in "。！？":
        return value
    return f"{value}。"


def _build_structured_post(hook: str, body: str, takeaway: str, tags: str, slot_name: str) -> str:
    parts = [_sentence(hook), body.strip(), takeaway.strip()]
    body_text = "\n".join(part for part in parts if part)
    return _normalize(f"{body_text}\n\n{tags}", slot_name=slot_name)


def _static_post(topic: str, insight: str, action: str, tags: str, slot_name: str) -> str:
    return _build_structured_post(topic, insight, action, tags, slot_name)


def _build_quote_drafts(pool: list[dict[str, str]]) -> list[DraftPost]:
    drafts: list[DraftPost] = []
    for item in pool:
        text = format_quote_post(
            item["quote"],
            item["translation"],
            item["author"],
            [item["interpretation"], item["action"]],
            item["tags"],
        )
        ok, checks = validate_quote_post(text)
        print(
            "[QUOTE VALIDATE] "
            f"english={'yes' if checks['english'] else 'no'} "
            f"translation={'yes' if checks['translation'] else 'no'} "
            f"author={'yes' if checks['author'] else 'no'} "
            f"spacing_ok={'yes' if checks['spacing_ok'] else 'no'}"
        )
        print(f"[QUOTE FORMAT] ok={'yes' if ok else 'no'}")
        if not ok:
            print("[QUOTE REPAIR] action=skip_broken_quote")
            continue
        drafts.append(
            _draft(
                text,
                "quote",
                "design",
                item["author"],
                item["interpretation"],
                "言葉を実務判断へ翻訳する",
                "引用解釈型",
                "quote",
            )
        )
    return drafts


def build_morning_type_drafts(
    seed: int,
    max_candidates: int = 8,
    preferred_types: list[str] | None = None,
    items: list[ContentItem] | None = None,
) -> list[DraftPost]:
    rng = random.Random(seed)
    drafts: list[DraftPost] = []
    order = preferred_types[:] if preferred_types else ["latest", "trend", "timeless", "quote", "practical", "insight"]
    rng.shuffle(order)
    for pattern in order:
        if pattern == "timeless":
            pool = MORNING_TIMELESS[:]
            rng.shuffle(pool)
            for item in pool:
                drafts.append(
                    _draft(
                        _static_post(item["topic"], item["insight"], item["action"], item["tags"], "morning"),
                        "morning-timeless",
                        "design",
                        item["topic"],
                        item["action"],
                        "普遍原則を判断軸に戻す",
                        item["structure"],
                        "timeless",
                    )
                )
        elif pattern == "practical":
            pool = MORNING_PRACTICAL[:]
            rng.shuffle(pool)
            for item in pool:
                drafts.append(
                    _draft(
                        _static_post(item["topic"], item["insight"], item["action"], item["tags"], "morning"),
                        "morning-practical",
                        "design",
                        item["topic"],
                        item["action"],
                        "実務の迷いを減らす",
                        item["structure"],
                        "practical",
                    )
                )
        elif pattern == "insight":
            pool = MORNING_INSIGHT[:]
            rng.shuffle(pool)
            for item in pool:
                drafts.append(
                    _draft(
                        _static_post(item["topic"], item["insight"], item["action"], item["tags"], "morning"),
                        "morning-insight",
                        "design",
                        item["topic"],
                        item["action"],
                        "小さな観察を設計に変える",
                        item["structure"],
                        "insight",
                    )
                )
        elif pattern == "quote":
            quote_pool = MORNING_QUOTES[:]
            rng.shuffle(quote_pool)
            drafts.extend(_build_quote_drafts(quote_pool))
        elif pattern in {"latest", "trend"}:
            source_items = (items or [])[: min(4, len(items or []))]
            for item in source_items:
                topic, body = (_latest_topic_from_item(item) if pattern == "latest" else _trend_topic_from_item(item))
                tags = "#デザイン #UIUX #トレンド" if pattern == "trend" else "#デザイン #最新動向 #設計"
                drafts.append(
                    _draft(
                        _normalize(f"{topic}\n\n{body}\n\n{tags}", slot_name="morning"),
                        f"morning-{pattern}:{item.title}",
                        "design",
                        topic,
                        body.split("\n")[-1],
                        "最新の動きを設計視点で解釈する",
                        "解説型",
                        pattern,
                    )
                )
    return drafts[:max_candidates]


def build_evening_type_drafts(
    items: list[ContentItem],
    seed: int,
    max_candidates: int = 10,
    preferred_types: list[str] | None = None,
) -> list[DraftPost]:
    rng = random.Random(seed)
    drafts: list[DraftPost] = []
    order = preferred_types[:] if preferred_types else ["practical", "insight", "latest", "trend", "timeless", "quote"]
    rng.shuffle(order)
    for pattern in order:
        if pattern == "timeless":
            pool = EVENING_TIMELESS[:]
            rng.shuffle(pool)
            for item in pool:
                drafts.append(
                    _draft(
                        _static_post(item["topic"], item["insight"], item["action"], item["tags"], "evening"),
                        "evening-timeless",
                        "design",
                        item["topic"],
                        item["action"],
                        "普遍原則を終業時の判断に戻す",
                        item["structure"],
                        "timeless",
                    )
                )
        elif pattern == "practical":
            pool = EVENING_PRACTICAL[:]
            rng.shuffle(pool)
            for item in pool:
                drafts.append(
                    _draft(
                        _static_post(item["topic"], item["insight"], item["action"], item["tags"], "evening"),
                        "evening-practical",
                        "design",
                        item["topic"],
                        item["action"],
                        "現場で明日すぐ効く判断に寄せる",
                        item["structure"],
                        "practical",
                    )
                )
        elif pattern == "insight":
            pool = EVENING_INSIGHT[:]
            rng.shuffle(pool)
            for item in pool:
                drafts.append(
                    _draft(
                        _static_post(item["topic"], item["insight"], item["action"], item["tags"], "evening"),
                        "evening-insight",
                        "design",
                        item["topic"],
                        item["action"],
                        "日常観察を設計の気づきへ変える",
                        item["structure"],
                        "insight",
                    )
                )
        elif pattern == "quote":
            quote_pool = MORNING_QUOTES[:]
            rng.shuffle(quote_pool)
            drafts.extend(_build_quote_drafts(quote_pool[:2]))
        elif pattern in {"latest", "trend"}:
            source_items = items[: min(4, len(items))]
            for item in source_items:
                topic, body = (_latest_topic_from_item(item) if pattern == "latest" else _trend_topic_from_item(item))
                tags = "#デザイン #仕事術 #最新動向" if pattern == "latest" else "#デザイン #トレンド #プロダクト"
                drafts.append(
                    _draft(
                        _normalize(f"{topic}\n\n{body}\n\n{tags}", slot_name="evening"),
                        f"evening-{pattern}:{item.title}",
                        "design",
                        topic,
                        body.split("\n")[-1],
                        "最新の変化を実務判断へ翻訳する",
                        "解説型",
                        pattern,
                    )
                )
    return drafts[:max_candidates]


def build_quote_fallback_drafts(seed: int, max_candidates: int = 4) -> list[DraftPost]:
    return build_morning_type_drafts(seed=seed, max_candidates=max_candidates, preferred_types=["quote"])
