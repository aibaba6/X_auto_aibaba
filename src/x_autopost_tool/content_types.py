from __future__ import annotations

import random

from .llm import normalize_x_post_text
from .models import ContentItem, DraftPost
from .quote_format import format_quote_post, validate_quote_post


MORNING_BASIC_TOPICS = [
    {
        "title": "余白は情報の優先順位を見せる",
        "insight": "詰め込みより、判断しやすい順番を先に作るほうが伝わりやすい。",
        "action": "要素を1つ減らし、主役と脇役の差だけ整える。",
        "tags": "#デザイン基礎 #UIデザイン #情報設計",
    },
    {
        "title": "視線誘導は大きさより配置順",
        "insight": "強い要素を増やすより、読む順番を固定したほうが崩れにくい。",
        "action": "見出し → 補足 → CTA の順でコントラストを並べる。",
        "tags": "#レイアウト #視線設計 #デザイン基礎",
    },
    {
        "title": "色数を減らすと意図が残る",
        "insight": "色を足すほど説明が必要になり、判断が遅れやすい。",
        "action": "強調色を1色に絞り、役割をラベル化する。",
        "tags": "#配色 #UI設計 #デザイン応用",
    },
]

MORNING_QUOTES = [
    {
        "quote": "Good design is as little design as possible.",
        "translation": "良いデザインは、必要以上に足さない状態に近い。",
        "author": "Dieter Rams",
        "interpretation": "足し算より、何を残すかの判断に設計力が出ます。",
        "action": "画面の要素を削る前に、役割が重複している場所を見つける。",
        "tags": "#デザイン思考 #UIデザイン #実務",
    },
    {
        "quote": "Design is not just what it looks like and feels like. Design is how it works.",
        "translation": "デザインは見た目や感触だけではない。どう機能するかだ。",
        "author": "Steve Jobs",
        "interpretation": "見た目を整える前に、使い方の筋が通っているかを確認する必要があります。",
        "action": "画面を磨く前に、1操作ごとの迷いがないかを先に見る。",
        "tags": "#UX設計 #プロダクトデザイン #実務",
    },
    {
        "quote": "Simplicity is about subtracting the obvious and adding the meaningful.",
        "translation": "シンプルさは、当たり前を削り、本当に意味のある差を残すこと。",
        "author": "John Maeda",
        "interpretation": "削るだけでは足りず、意味が伝わる差を残す必要があります。",
        "action": "消す要素と強める要素を1つずつ決めて比較する。",
        "tags": "#デザイン応用 #ミニマル #UI設計",
    },
    {
        "quote": "Complicating is easy, simplifying is difficult.",
        "translation": "複雑にするのは簡単だが、単純にするのは難しい。",
        "author": "Bruno Munari",
        "interpretation": "要素を増やすより、判断を減らす設計のほうが難しく、価値も出やすいです。",
        "action": "説明が長い画面ほど、減らせる選択肢を先に探す。",
        "tags": "#情報設計 #デザイン思考 #制作フロー",
    },
    {
        "quote": "Design is a way of life, a point of view.",
        "translation": "デザインは生き方であり、ものの見方そのものだ。",
        "author": "Paul Rand",
        "interpretation": "表層の装飾ではなく、どこに視点を置くかが設計に出ます。",
        "action": "画面を直す前に、誰の判断を助けたいのかを言葉にする。",
        "tags": "#デザイン思考 #ブランド設計 #実務",
    },
]

EVENING_ARUARU = [
    {
        "title": "修正依頼が3件同時に来る夕方",
        "body": "優先順位を決める5分が、だいたい一番効く。\n先に手を付ける1件を固定すると、流れが戻りやすい。",
        "tags": "#デザイナーあるある #制作現場 #仕事術",
    },
    {
        "title": "締切前ほど細部が気になる",
        "body": "最後の30分で1pxに引っ張られる現象、わりと共通です。\n直す理由が言える1箇所に絞ると、戻りが減ります。",
        "tags": "#制作フロー #UIデザイン #仕事あるある",
    },
    {
        "title": "良い案ほど最初は伝わりにくい",
        "body": "案の熱量が先に走ると、判断基準の共有が追いつかない。\n図を1枚足すだけで、会話の速度が変わることがあります。",
        "tags": "#提案資料 #デザイン思考 #仕事あるある",
    },
]

EVENING_DAILY = [
    {
        "hook": "作業ログを見返すと、迷った場所が毎回似ている",
        "body": "技術より先に、判断基準が曖昧な場所で止まっていることが多いです。\n次に迷わない条件を1行だけ残すと、翌日の初速が上がります。",
        "tags": "#制作フロー #継続改善 #デザイン実務",
    },
    {
        "hook": "進んだ量より、判断が減った量のほうが効く日がある",
        "body": "作業量が多くても、迷いが残ると前進感は薄くなります。\n決めない論点を先に外すだけで、画面はかなり整います。",
        "tags": "#仕事術 #デザイン現場 #小さな改善",
    },
    {
        "hook": "説明に時間がかかる日は、案より基準が散っている",
        "body": "デザインの良し悪しより、どこを見るかが揃っていないことがあります。\nスクショ1枚に理由を1行添えるだけで、会話が短くなります。",
        "tags": "#デザイン実務 #コミュニケーション #仕事術",
    },
]


def _trend_body(item: ContentItem) -> str:
    title = item.title.replace("\n", " ").strip()
    summary = item.summary.replace("\n", " ").strip()[:90]
    return (
        f"{title} は、見た目より使いどころの設計が問われる流れです。\n"
        f"{summary} を見ると、機能追加より体験の整理で差が付きやすい。\n"
        "流行を追うなら、表現より先に誰の判断を軽くするかを見る。"
    )


def _normalize(text: str, slot_name: str) -> str:
    return normalize_x_post_text(text, slot_name=slot_name)


def _draft(text: str, reason: str, content_type: str, topic: str, claim: str, structure: str) -> DraftPost:
    return DraftPost(
        text=text,
        reason=reason,
        content_type=content_type,
        topic=topic,
        claim=claim,
        structure=structure,
    )


def build_morning_type_drafts(
    seed: int,
    max_candidates: int = 6,
    preferred_types: list[str] | None = None,
) -> list[DraftPost]:
    rng = random.Random(seed)
    drafts: list[DraftPost] = []
    order = preferred_types[:] if preferred_types else ["basic", "quote"]
    rng.shuffle(order)
    for content_type in order:
        pool = MORNING_BASIC_TOPICS if content_type == "basic" else MORNING_QUOTES
        indices = list(range(len(pool)))
        rng.shuffle(indices)
        for idx in indices:
            item = pool[idx]
            if content_type == "basic":
                text = _normalize(
                    f"{item['title']}\n\n{item['insight']}\n{item['action']}\n\n{item['tags']}",
                    slot_name="morning",
                )
                drafts.append(_draft(text, "morning-basic", "basic", item["title"], item["action"], "一言断言型"))
            else:
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
                drafts.append(_draft(text, "morning-quote", "quote", item["author"], item["interpretation"], "引用解釈型"))
    return drafts[:max_candidates]


def build_evening_type_drafts(
    items: list[ContentItem],
    seed: int,
    max_candidates: int = 9,
    preferred_types: list[str] | None = None,
) -> list[DraftPost]:
    rng = random.Random(seed)
    drafts: list[DraftPost] = []
    type_order = preferred_types[:] if preferred_types else ["daily", "trend", "aruaru"]
    if not preferred_types:
        rng.shuffle(type_order)
    for content_type in type_order:
        if content_type == "aruaru":
            pool = EVENING_ARUARU[:]
            rng.shuffle(pool)
            for item in pool:
                text = _normalize(f"{item['title']}\n\n{item['body']}\n\n{item['tags']}", slot_name="evening")
                drafts.append(_draft(text, "evening-aruaru", "aruaru", item["title"], item["body"], "作業現場描写型"))
        elif content_type == "daily":
            pool = EVENING_DAILY[:]
            rng.shuffle(pool)
            for item in pool:
                text = _normalize(f"{item['hook']}\n\n{item['body']}\n\n{item['tags']}", slot_name="evening")
                drafts.append(_draft(text, "evening-daily", "daily", item["hook"], item["body"], "観察型"))
        else:
            trend_items = items[: min(3, len(items))]
            for item in trend_items:
                text = _normalize(f"{_trend_body(item)}\n\n#デザイントレンド #UX #プロダクト", slot_name="evening")
                drafts.append(_draft(text, f"evening-trend:{item.title}", "trend", item.title, item.summary[:80], "比較型"))
    return drafts[:max_candidates]


def build_quote_fallback_drafts(seed: int, max_candidates: int = 4) -> list[DraftPost]:
    return build_morning_type_drafts(seed=seed, max_candidates=max_candidates, preferred_types=["quote"])
