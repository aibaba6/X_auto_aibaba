from __future__ import annotations

import json
import random
import re
import shlex
import shutil
import subprocess
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

from dotenv import dotenv_values, load_dotenv
from flask import Flask, jsonify, request, send_from_directory

import os
import tweepy
import yaml
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.getenv("XAP_DATA_DIR", str(ROOT))).resolve()
UI_DIR = ROOT / "ui"
CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"
QUEUE_PATH = DATA_ROOT / "queue_plan.json"
ENV_KEYS = [
    "OPENAI_API_KEY",
    "X_BEARER_TOKEN",
    "X_API_KEY",
    "X_API_SECRET",
    "X_ACCESS_TOKEN",
    "X_ACCESS_SECRET",
    "XAP_QUEUE_SYNC_URL",
    "XAP_QUEUE_SYNC_TOKEN",
    "NANOBANANA_CMD_TEMPLATE",
    "FREEPIK_API_KEY",
    "GOOGLE_API_KEY",
]
ACCOUNT_REQUIRED_KEYS = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]
QUEUE_MEDIA_DIR = DATA_ROOT / "queue_media"

load_dotenv(ENV_PATH)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.x_autopost_tool.collectors import fetch_rss_items, filter_blocked
from src.x_autopost_tool.content_types import build_evening_type_drafts, build_morning_type_drafts, build_quote_fallback_drafts
from src.x_autopost_tool.llm import build_post_drafts, normalize_x_post_text
from src.x_autopost_tool.media_tools import (
    build_nano_banana_prompt_payload,
    generate_image_with_freepik_mystic,
    generate_image_with_nanobanana,
    generate_image_with_nanobanana_pro_api,
    resolve_nanobanana_pro_settings,
)
from src.x_autopost_tool.pdf_knowledge import (
    delete_pdf_doc,
    get_pdf_knowledge_snippets,
    ingest_pdf_bytes,
    load_pdf_index,
    update_pdf_doc_settings,
)
from src.x_autopost_tool.schedule_utils import format_datetime_local_input, serialize_scheduled_datetime
from src.x_autopost_tool.settings import load_config
from src.x_autopost_tool.text_normalize import cleanup_post_linebreaks, cleanup_post_text
from src.x_autopost_tool.uniqueness import (
    MemoryStore,
    append_history,
    duplicate_check,
    evening_duplicate_check,
    history_content_types,
    history_fingerprints,
    history_pattern_types,
    history_idea_keys,
    history_topics,
    loose_fingerprint,
    load_history,
    load_memory,
    register_text,
    semantic_duplicate_check,
    semantic_signature,
    semantic_stage_check,
    semantic_summaries,
    save_history,
    save_memory,
    strict_fingerprint,
)

app = Flask(__name__, static_folder=str(UI_DIR), static_url_path="")


def _openai_client() -> OpenAI:
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.errorhandler(405)
def handle_405(e):
    if request.path.startswith("/api/"):
        allow = ",".join(sorted(getattr(e, "valid_methods", []) or []))
        return (
            jsonify(
                {
                    "ok": False,
                    "message": f"Method Not Allowed: {request.path} はこのHTTPメソッドに対応していません。",
                    "allow": allow,
                }
            ),
            405,
        )
    return e


@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "message": f"Not Found: {request.path} が見つかりません。"}), 404
    return e


def _x_client() -> tweepy.Client:
    return tweepy.Client(
        bearer_token=os.getenv("X_BEARER_TOKEN"),
        consumer_key=os.getenv("X_API_KEY"),
        consumer_secret=os.getenv("X_API_SECRET"),
        access_token=os.getenv("X_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCESS_SECRET"),
        wait_on_rate_limit=True,
    )


def _x_api_v1() -> tweepy.API:
    auth = tweepy.OAuth1UserHandler(
        consumer_key=os.getenv("X_API_KEY"),
        consumer_secret=os.getenv("X_API_SECRET"),
        access_token=os.getenv("X_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCESS_SECRET"),
    )
    return tweepy.API(auth)


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def _load_env_map() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    raw = dotenv_values(ENV_PATH)
    return {k: str(v) for k, v in raw.items() if v is not None}


def _save_env_map(env_map: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in env_map.items() if v]
    ENV_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _load_config_map() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def _save_config_map(config_map: dict) -> None:
    CONFIG_PATH.write_text(
        yaml.safe_dump(config_map, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _load_media_config() -> dict:
    conf = _load_config_map()
    media = conf.get("media", {}) or {}
    return {
        "enabled": bool(media.get("enabled", False)),
        "morning_generate_image": bool(media.get("morning_generate_image", False)),
        "morning_image_provider": str(media.get("morning_image_provider", "nanobanana_pro")),
        "morning_image_output_dir": str(media.get("morning_image_output_dir", "generated_media")),
        "noon_reply_source_link": bool(media.get("noon_reply_source_link", True)),
    }


def _style_reference_posts_from_config() -> list[str]:
    conf = _load_config_map()
    generation = conf.get("generation", {}) or {}
    refs = generation.get("style_reference_posts", [])
    return refs if isinstance(refs, list) else []


def _pdf_knowledge_for_prompt(slot_name: str, max_docs: int = 3, max_chars_per_doc: int = 600) -> list[str]:
    try:
        return get_pdf_knowledge_snippets(
            max_docs=max_docs,
            max_chars_per_doc=max_chars_per_doc,
            slot_name=slot_name,
        )
    except Exception:
        return []


def _safe_media_url(path: str) -> str:
    p = Path(path).resolve()
    if ROOT.resolve() in p.parents or p == ROOT.resolve():
        rel = p.relative_to(ROOT.resolve())
        return f"/api/media/{rel.as_posix()}"
    if DATA_ROOT.resolve() in p.parents or p == DATA_ROOT.resolve():
        rel = p.relative_to(DATA_ROOT.resolve())
        return f"/api/data-media/{rel.as_posix()}"
    raise ValueError("invalid media path")


def _queue_media_meta(path: str) -> dict:
    p = Path(path).resolve()
    payload = {"media_path": str(p), "media_name": p.name}
    try:
        payload["media_url"] = _safe_media_url(str(p))
    except Exception:
        payload["media_url"] = ""
    return payload


def _validate_queue_media_path(raw_path: str) -> str:
    value = str(raw_path or "").strip()
    if not value:
        return ""
    p = Path(value).resolve()
    if ROOT.resolve() not in p.parents and DATA_ROOT.resolve() not in p.parents:
        raise ValueError("invalid media path")
    return str(p)


def _persist_queue_media(raw_path: str) -> str:
    value = _validate_queue_media_path(raw_path)
    if not value:
        return ""
    p = Path(value).resolve()
    if not p.exists():
        raise ValueError("media file does not exist")
    if DATA_ROOT.resolve() in p.parents or p == DATA_ROOT.resolve():
        return str(p)
    QUEUE_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", p.stem).strip("._") or "queue_media"
    target = QUEUE_MEDIA_DIR / f"{safe_stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{p.suffix.lower()}"
    shutil.copy2(p, target)
    print(f"[QUEUE MEDIA PERSIST] src={p} dst={target}")
    return str(target)


def _semantic_domain_guard(topic: str, text: str) -> tuple[bool, str]:
    """
    Detect obvious domain drift for this account's core domain (design/AI).
    Returns (ok, reason).
    """
    t = topic.lower()
    body = text.lower()

    # Special guard: 「余白」 is often mis-generated as life-hack/time-management.
    if "余白" in topic:
        design_signals = ["レイアウト", "タイポ", "余白", "可読性", "視線", "情報設計", "ui", "ux", "グリッド"]
        lifehack_signals = ["時間管理", "朝活", "タスク", "生産性", "一日", "習慣", "日常"]
        has_design = any(k in text for k in design_signals)
        has_lifehack = any(k in text for k in lifehack_signals)
        if has_lifehack and not has_design:
            return (False, "余白テーマが生活ハック文脈へ逸脱しています。デザイン文脈に固定してください。")

    # Generic guard: when topic mentions design/AI, avoid generic self-help tone only.
    if any(k in t for k in ["デザイン", "ui", "ux", "ai", "余白", "配色", "タイポ"]):
        domain_signals = ["デザイン", "ui", "ux", "レイアウト", "可読性", "情報設計", "配色", "タイポ", "ai", "モデル", "運用"]
        if not any(k in body for k in domain_signals):
            return (False, "投稿が専門ドメイン要素を欠いています。")
    return (True, "")


def _load_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    try:
        data = yaml.safe_load(QUEUE_PATH.read_text(encoding="utf-8")) or []
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_queue(items: list[dict]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(yaml.safe_dump(items, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _queue_item_id(raw_id: str | None = None) -> str:
    value = str(raw_id or "").strip()
    return value or f"queue_{uuid.uuid4().hex[:12]}"


def _queue_sync_authorized() -> bool:
    expected = os.getenv("XAP_QUEUE_SYNC_TOKEN", "").strip()
    provided = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return bool(expected) and provided == expected


def _weekday_key(d: date) -> str:
    keys = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    return keys[d.weekday()]


def _days_from_unit(unit: str, count: int) -> int:
    if unit == "days":
        return count
    if unit == "weeks":
        return count * 7
    if unit == "months":
        return count * 30
    return count


def _max_count_by_unit(unit: str) -> int:
    if unit == "days":
        return 31
    return 12


def _fallback_plan_text(slot: str, weekday_theme: str) -> str:
    if slot == "morning":
        return f"{weekday_theme}。朝枠は学び重視で、保存したくなる実務示唆を1本投稿。"
    if slot == "noon":
        return (
            "AIニュースは、機能数より運用に乗る速度が差になりやすい流れです。\n"
            "次の3-6ヶ月は、要約精度より『どの判断を任せるか』の設計で差が開きそう。\n"
            "1工程だけ、AIに渡す入力と確認観点をセットで見直します。\n\n"
            "#AIニュース #デザイン #業務改善"
        )
    return "夕方は共感ベースで1本。冷静に振り返れる短文で、明日に繋がる行動提案を入れる。"


NOON_PLACEHOLDER_VARIANTS = [
    "【投稿直前生成】この枠はAIニュースを投稿時刻の直前に要約して作成します。\n- 収集タイミング: 投稿予定の約{minutes_before}分前\n- 仕上げ: 要点要約 + 今後の予測 + 今日の小さな行動\n- 形式: 通常投稿、リンクなし",
    "【直前更新】昼枠は投稿予定時刻の少し前にAIニュースを取り込み、要点を短く整理して投稿します。\n- 更新タイミング: 約{minutes_before}分前\n- 含める内容: いま重要な変化 / これからの予測 / 今日の実験\n- URLは本文に入れません",
    "【最新反映】この昼投稿は固定文ではなく、直前に集めたAIニュースから組み立てます。\n- 取得タイミング: 投稿予定の約{minutes_before}分前\n- 構成: 要約 / 今後の見立て / 小さな行動\n- 仕上げはリンクなしの通常投稿です",
]


def _jit_noon_placeholder(minutes_before: int, variant: int = 0) -> str:
    template = NOON_PLACEHOLDER_VARIANTS[variant % len(NOON_PLACEHOLDER_VARIANTS)]
    return template.format(minutes_before=minutes_before)


def _shuffled_indices(length: int, seed: int) -> list[int]:
    order = list(range(length))
    random.Random(seed).shuffle(order)
    return order


def _rotation_start(seed: int, length: int) -> int:
    if length <= 0:
        return 0
    return seed % length


def _seen_keys(text: str) -> set[str]:
    value = (text or "").strip()
    if not value:
        return set()
    semantic = semantic_signature(value)
    return {
        f"strict:{strict_fingerprint(value)}",
        f"loose:{loose_fingerprint(value)}",
        f"hook:{semantic.hook_key}",
        f"topic:{semantic.topic_key}",
        f"claim:{semantic.claim_key}",
        f"structure:{semantic.structure}",
        f"takeaway:{semantic.takeaway_key}",
    }


def _remember_seen(text: str, seen_fingerprints: set[str]) -> None:
    seen_fingerprints.update(_seen_keys(text))


def _planner_seen_keys(history, slot: str, queue_items: list[dict] | None = None) -> set[str]:
    seen: set[str] = set()
    for entry in history.entries:
        if str(entry.get("slot", "")).strip() != slot:
            continue
        text = str(entry.get("text", "")).strip()
        if text:
            seen.update(_seen_keys(text))
    for item in queue_items or []:
        if str(item.get("slot", "")).strip() != slot:
            continue
        if bool(item.get("posted", False)):
            continue
        text = str(item.get("text", "")).strip()
        if text:
            seen.update(_seen_keys(text))
    return seen


def _is_used_before(
    text: str,
    memory: MemoryStore,
    seen_fingerprints: set[str],
    history=None,
    slot: str = "",
    generation_level: str = "strict",
) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    result = duplicate_check(value, memory)
    semantic = semantic_signature(value)
    print(
        "[HISTORY CHECK] "
        f"strict_dup={'yes' if result.strict_duplicate else 'no'} "
        f"loose_dup={'yes' if result.loose_duplicate else 'no'}"
    )
    if result.strict_duplicate:
        print("[UNIQUE REJECT] reason=strict_duplicate")
        return True
    if result.loose_duplicate:
        print("[UNIQUE REJECT] reason=loose_duplicate")
        return True
    seen_key_map = {
        f"strict:{result.strict_fingerprint}": "history_strict_duplicate",
        f"loose:{result.loose_fingerprint}": "history_loose_duplicate",
        f"hook:{semantic.hook_key}": "history_hook_duplicate",
        f"topic:{semantic.topic_key}": "history_topic_duplicate",
        f"claim:{semantic.claim_key}": "history_claim_duplicate",
        f"structure:{semantic.structure}": "history_structure_duplicate",
        f"takeaway:{semantic.takeaway_key}": "history_takeaway_duplicate",
    }
    matched = [reason for key, reason in seen_key_map.items() if key in seen_fingerprints]
    if matched:
        print(f"[UNIQUE REJECT] reason={matched[0]}")
        return True
    if history is not None:
        if slot == "evening" and generation_level == "strict":
            evening = evening_duplicate_check(value, history)
            if evening.duplicate:
                print(f"[EVENING REJECT] reason={evening.reason}")
                return True
        stage = semantic_stage_check(value, history, slot=slot or None)
        if stage.duplicate:
            print(f"[SEMANTIC REJECT] reason={stage.reason}")
            return True
        if stage.warning:
            print(f"[SEMANTIC CHECK] warning=yes reason={stage.reason}")
            if generation_level == "strict":
                return True
    return False


MORNING_EVERGREEN_TOPICS = [
    {
        "title": "余白は“飾り”ではなく情報設計",
        "insight": "詰め込みすぎると理解コストが上がり、離脱が増える。",
        "action": "要素を1つ減らし、余白を8pxだけ増やして比較する。",
        "tags": "#デザイン基礎 #UIデザイン #情報設計",
    },
    {
        "title": "フォント選定は可読性が先",
        "insight": "雰囲気より本文サイズ・行間・字間の整合で読みやすさが決まる。",
        "action": "本文14-16pxで2パターンを並べ、30秒読了率を確認する。",
        "tags": "#タイポグラフィ #デザイン基礎 #UX",
    },
    {
        "title": "色は“意味”で使う",
        "insight": "色数が多いほど迷いが増え、重要情報が埋もれやすい。",
        "action": "強調色を1色に絞り、注意/成功/補助の役割を定義する。",
        "tags": "#配色 #デザイン基礎 #UI設計",
    },
    {
        "title": "視線誘導はサイズ差より順序設計",
        "insight": "大きい文字だけでは読ませたい順は作れない。",
        "action": "見出し→補足→CTAの順にコントラストを付けて再配置する。",
        "tags": "#レイアウト #デザイン基礎 #視線設計",
    },
    {
        "title": "写真は品質より役割一致",
        "insight": "綺麗な写真でも文脈とズレると体験が弱くなる。",
        "action": "感情訴求用か情報補足用かを先に決めてから差し替える。",
        "tags": "#ビジュアル設計 #デザイン応用 #UX",
    },
    {
        "title": "グリッドは自由を制限するためではない",
        "insight": "揃える基準があるほど、崩す意図が伝わる。",
        "action": "8ptグリッドで一度整列し、意図的に崩す1箇所を決める。",
        "tags": "#グリッド #デザイン基礎 #実務",
    },
    {
        "title": "“しっくりこない”は言語化不足",
        "insight": "違和感の理由を言葉にできると改善スピードが上がる。",
        "action": "迷った画面で『何が惜しいか』を3行メモしてから修正する。",
        "tags": "#デザイン思考 #デザイン豆知識 #制作フロー",
    },
    {
        "title": "マイクロコピーは体験の最後の設計",
        "insight": "ボタン文言1つで迷いと離脱は大きく変わる。",
        "action": "CTA文言を『する』から『得られる結果』に書き換えてAB比較する。",
        "tags": "#UXライティング #デザイン応用 #CV改善",
    },
]


def _morning_evergreen_post(index: int, variant: int = 0) -> str:
    t = MORNING_EVERGREEN_TOPICS[index % len(MORNING_EVERGREEN_TOPICS)]
    variants = [
        (
            f"🔍 {t['title']}\n\n"
            f"・{t['insight']}\n"
            "・意外とここを整えるだけで、見やすさと信頼感は変わります。\n\n"
            f"まずは {t['action']}\n\n"
            f"{t['tags']}"
        ),
        (
            f"{t['title']}\n\n"
            f"{t['insight']}\n"
            "派手な改善より、基礎を1つ整えた方が全体の印象は変わりやすいです。\n\n"
            f"{t['action']}\n\n"
            f"{t['tags']}"
        ),
        (
            f"{t['title']}\n\n"
            f"{t['insight']}\n"
            "触る場所を増やす前に、土台を1つだけ整えるのが近道。\n\n"
            f"{t['action']}\n\n"
            f"{t['tags']}"
        ),
    ]
    return variants[variant % len(variants)]


EVENING_ARUARU_TOPICS = [
    {
        "title": "修正依頼が3件同時に来る夕方",
        "body": "優先順位を決める5分が、だいたい一番効く。\n先に“手を付ける1件”を固定すると、気持ちがだいぶ落ち着きます。",
        "tags": "#デザイナーあるある #制作現場 #仕事術",
        "structure": "作業現場描写型",
    },
    {
        "title": "『なんか違う』と言われたとき",
        "body": "言語化が難しい日はありますよね。\n責めるより、まず基準を一緒に揃えると前に進みやすいです。",
        "tags": "#デザインあるある #コミュニケーション #デザイン実務",
        "structure": "観察型",
    },
    {
        "title": "締切前ほど細部が気になる",
        "body": "最後の30分で1pxを追い続ける現象、わりとみんな通る道。\n“直す理由が言える1箇所だけ”に絞ると戻りにくいです。",
        "tags": "#デザイナーあるある #UIデザイン #制作フロー",
        "structure": "失敗型",
    },
    {
        "title": "良い案ほど最初は伝わりにくい",
        "body": "熱量が先行して、説明が追いつかないことがある。\n図を1枚足すだけで、空気が変わることあります。",
        "tags": "#仕事あるある #提案資料 #デザイン思考",
        "structure": "気づき型",
    },
    {
        "title": "疲れてる日に限って判断が増える",
        "body": "そんな日は“決めない勇気”も大事。\n明日の自分が判断しやすいように、論点だけメモして終えるのもありです。",
        "tags": "#デザイン現場 #仕事あるある #継続改善",
        "structure": "逆説型",
    },
    {
        "title": "確認待ちが一気に返ってくる夕方",
        "body": "返答が重なるほど、全部同じ熱量で返すと崩れやすい。\n返す順番より、返さない論点を先に決めるほうが安定します。",
        "tags": "#制作現場 #コミュニケーション #仕事あるある",
        "structure": "比較型",
    },
    {
        "title": "デザインより説明に時間がかかる日",
        "body": "詰まっているのは案ではなく、判断基準かもしれません。\nスクショ1枚に理由を1行添えるだけで会話が進みやすくなります。",
        "tags": "#提案資料 #デザイン実務 #仕事術",
        "structure": "一言断言型",
    },
    {
        "title": "手を動かした量のわりに進んだ感じがしない",
        "body": "作業量と前進感は、案外一致しません。\n次に迷わない状態まで整理できていれば、その日は十分進んでいます。",
        "tags": "#制作フロー #継続改善 #仕事あるある",
        "structure": "観察型",
    },
]


def _evening_aruaru_post(index: int, variant: int = 0) -> str:
    t = EVENING_ARUARU_TOPICS[index % len(EVENING_ARUARU_TOPICS)]
    variants = [
        f"{t['title']}\n\n{t['body']}\n\n{t['tags']}",
        f"{t['title']}\n\n{t['body']}\n1つだけ判断を固定すると、崩れにくくなります。\n\n{t['tags']}",
        f"{t['title']}\n\n{t['body']}\n次に迷わない一言だけ残せば、流れは切れません。\n\n{t['tags']}",
        f"{t['title']}\n\n{t['body']}\n全部を進めるより、止める論点を決めたほうが整います。\n\n{t['tags']}",
    ]
    return variants[variant % len(variants)]


EVENING_FALLBACK_OPENERS = [
    "小さな改善を1つ残せたら十分です。",
    "手が止まる日は、無理に進めないほうがうまくいくことがあります。",
    "夕方の修正は、勢いより優先順位が効きます。",
    "うまく進まない日は、設計が悪いのではなく疲れているだけのこともあります。",
    "完璧に終わらない日があっても大丈夫です。",
]

EVENING_FALLBACK_BODIES = [
    "明日に渡すメモを1行だけ書いて終わりにします。",
    "判断だけ先にメモして、作業は明日の自分に渡すのも手です。",
    "『直す理由が言える1箇所』だけ整えて締めます。",
    "まずは論点を2つに絞って、続きは明日に回す判断もありです。",
    "『次に迷わないメモ』を残せたら、それで十分。",
]

EVENING_FALLBACK_TAGS = [
    "#デザイン #制作フロー #継続改善",
    "#デザイン実務 #仕事術 #継続改善",
    "#デザイン #制作現場 #仕事あるある",
    "#デザイン現場 #仕事術 #制作フロー",
    "#デザイン #継続改善 #仕事あるある",
]

GUARANTEED_MORNING_POST = (
    "情報を足す前に、役割の重なりを減らすほうが整います。\n"
    "主役と脇役の差だけ見直す。\n\n"
    "#デザイン基礎\n#UIデザイン\n#情報設計"
)

GUARANTEED_EVENING_POST = (
    "進んだ量より、迷いを減らせた日のほうが次につながります。\n"
    "次に迷わない一言だけ残して終える。\n\n"
    "#デザイン実務\n#制作フロー\n#継続改善"
)


def _evening_fallback_post(d: date, variant: int = 0) -> str:
    base = d.toordinal() + variant * 7
    opener = EVENING_FALLBACK_OPENERS[base % len(EVENING_FALLBACK_OPENERS)]
    body = EVENING_FALLBACK_BODIES[(base // len(EVENING_FALLBACK_OPENERS)) % len(EVENING_FALLBACK_BODIES)]
    tags = EVENING_FALLBACK_TAGS[(base // 3) % len(EVENING_FALLBACK_TAGS)]
    return f"{opener}\n{body}\n\n{tags}"


def _rotated_items(items: list, seed: int, take: int = 8) -> list:
    if not items:
        return []
    n = len(items)
    start = seed % n
    ordered = items[start:] + items[:start]
    return ordered[: min(take, len(ordered))]


def _unique_or_fallback(
    text: str,
    slot: str,
    d: date,
    weekday_theme: str,
    memory: MemoryStore,
    local_fp: set[str],
    history_fp: set[str] | None = None,
    history=None,
) -> str:
    used_fp = history_fp or set()
    candidate = text.strip()
    if candidate and not _is_used_before(candidate, memory, used_fp, history=history, slot=slot):
        if not (_seen_keys(candidate) & local_fp):
            _remember_seen(candidate, local_fp)
            print(f"[UNIQUE PICKED] fingerprint={strict_fingerprint(candidate)}")
            semantic = semantic_duplicate_check(candidate, history, slot=slot) if history is not None else None
            if semantic is not None:
                print(f"[SEMANTIC PICKED] topic={semantic.candidate.topic[:80]}")
            return candidate

    if slot == "morning":
        candidate = ""
        for topic_idx in range(len(MORNING_EVERGREEN_TOPICS)):
            for variant in range(3):
                alt = normalize_x_post_text(_morning_evergreen_post(topic_idx, variant), slot_name="morning")
                if _is_used_before(alt, memory, used_fp, history=history, slot=slot) or (_seen_keys(alt) & local_fp):
                    continue
                candidate = alt
                break
            if candidate:
                break
        if not candidate:
            candidate = (
                f"デザインの見直しは、足す前に役割を分けるほうが整います。\n"
                f"{weekday_theme}は、主役と脇役の差を1つだけ見直す。\n\n"
                "#デザイン基礎\n#UIデザイン\n#情報設計"
            )
    elif slot == "noon":
        candidate = _jit_noon_placeholder(30)
    else:
        candidate = _evening_fallback_post(d)
        if _is_used_before(candidate, memory, used_fp, history=history, slot=slot):
            for i in range(len(EVENING_FALLBACK_OPENERS) * len(EVENING_FALLBACK_BODIES)):
                alt = _evening_fallback_post(d, variant=i + 1)
                if not _is_used_before(alt, memory, used_fp, history=history, slot=slot):
                    candidate = alt
                    break
    if _is_used_before(candidate, memory, used_fp, history=history, slot=slot) or (_seen_keys(candidate) & local_fp):
        if slot == "morning":
            candidate = normalize_x_post_text(GUARANTEED_MORNING_POST, slot_name="morning")
        elif slot == "evening":
            candidate = normalize_x_post_text(GUARANTEED_EVENING_POST, slot_name="evening")
        else:
            print(f"[UNIQUE HOLD] reason=no_unique_candidate slot={slot}")
            print(f"[SEMANTIC HOLD] reason=no_semantically_unique_candidate slot={slot}")
            return ""
        print(f"[FALLBACK USED] type={slot}-guaranteed")
    _remember_seen(candidate, local_fp)
    print(f"[UNIQUE PICKED] fingerprint={strict_fingerprint(candidate)}")
    if history is not None:
        semantic = semantic_duplicate_check(candidate, history, slot=slot)
        print(f"[SEMANTIC PICKED] topic={semantic.candidate.topic[:80]}")
    return candidate


@app.get("/api/env")
def api_get_env():
    env_map = _load_env_map()
    payload = {}
    for key in ENV_KEYS:
        value = env_map.get(key, "")
        payload[key] = {"is_set": bool(value), "masked": _mask_secret(value)}
    return jsonify({"ok": True, "env": payload})


@app.post("/api/env")
def api_save_env():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400

    incoming = request.json.get("env", {})
    if not isinstance(incoming, dict):
        return jsonify({"ok": False, "message": "envはオブジェクト形式で指定してください。"}), 400

    env_map = _load_env_map()
    for key in ENV_KEYS:
        if key not in incoming:
            continue
        value = str(incoming.get(key, "")).strip()
        if value:
            env_map[key] = value
            os.environ[key] = value
        elif key in env_map:
            # 空文字を送ると削除
            env_map.pop(key, None)
            os.environ.pop(key, None)

    _save_env_map(env_map)
    return jsonify({"ok": True, "message": ".env を保存しました。"})


@app.get("/api/media_config")
def api_get_media_config():
    return jsonify({"ok": True, "media": _load_media_config()})


@app.post("/api/media_config")
def api_save_media_config():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400
    incoming = request.json.get("media", {})
    if not isinstance(incoming, dict):
        return jsonify({"ok": False, "message": "mediaはオブジェクト形式で指定してください。"}), 400

    conf = _load_config_map()
    media = conf.get("media", {}) or {}
    media["enabled"] = bool(incoming.get("enabled", media.get("enabled", False)))
    media["morning_generate_image"] = bool(
        incoming.get("morning_generate_image", media.get("morning_generate_image", False))
    )
    media["morning_image_provider"] = str(
        incoming.get("morning_image_provider", media.get("morning_image_provider", "nanobanana_pro"))
    ).strip() or "nanobanana_pro"
    media["morning_image_output_dir"] = str(
        incoming.get("morning_image_output_dir", media.get("morning_image_output_dir", "generated_media"))
    ).strip() or "generated_media"
    media["noon_reply_source_link"] = bool(
        incoming.get("noon_reply_source_link", media.get("noon_reply_source_link", True))
    )
    conf["media"] = media
    _save_config_map(conf)
    return jsonify({"ok": True, "message": "media設定を保存しました。", "media": media})


@app.get("/api/pdf_library")
def api_get_pdf_library():
    docs = load_pdf_index()
    return jsonify({"ok": True, "docs": docs})


@app.post("/api/pdf_library/upload")
def api_upload_pdf():
    file = request.files.get("pdf")
    if not file:
        return jsonify({"ok": False, "message": "PDFファイルを選択してください。"}), 400
    name = (file.filename or "").strip()
    if not name.lower().endswith(".pdf"):
        return jsonify({"ok": False, "message": "PDFのみアップロードできます。"}), 400
    try:
        content = file.read()
        if not content:
            return jsonify({"ok": False, "message": "空のファイルです。"}), 400
        doc = ingest_pdf_bytes(content, original_name=name)
        return jsonify({"ok": True, "message": "PDFをストックしました。", "doc": doc, "docs": load_pdf_index()})
    except Exception as e:
        return jsonify({"ok": False, "message": f"PDF取り込みエラー: {e}"}), 400


@app.delete("/api/pdf_library/<doc_id>")
def api_delete_pdf(doc_id: str):
    ok = delete_pdf_doc(doc_id)
    if not ok:
        return jsonify({"ok": False, "message": "対象PDFが見つかりません。"}), 404
    return jsonify({"ok": True, "message": "PDFを削除しました。", "docs": load_pdf_index()})


@app.post("/api/pdf_library/settings")
def api_update_pdf_settings():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400
    doc_id = str(request.json.get("doc_id", "")).strip()
    if not doc_id:
        return jsonify({"ok": False, "message": "doc_id を指定してください。"}), 400
    try:
        priority = int(request.json.get("priority", 3))
    except Exception:
        priority = 3
    scope = str(request.json.get("scope", "all")).strip().lower()
    if scope not in {"all", "morning"}:
        return jsonify({"ok": False, "message": "scope は all / morning を指定してください。"}), 400
    updated = update_pdf_doc_settings(doc_id, priority=priority, scope=scope)
    if updated is None:
        return jsonify({"ok": False, "message": "対象PDFが見つかりません。"}), 404
    return jsonify({"ok": True, "message": "PDF設定を更新しました。", "doc": updated, "docs": load_pdf_index()})


@app.post("/api/draft_lab_generate")
def api_draft_lab_generate():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400

    topic = str(request.json.get("topic", "")).strip()
    slot = str(request.json.get("slot", "morning")).strip()
    if not topic:
        return jsonify({"ok": False, "message": "テーマ/キーワードを入力してください。"}), 400
    if slot not in {"morning", "noon", "evening"}:
        slot = "morning"
    if not os.getenv("OPENAI_API_KEY"):
        return jsonify({"ok": False, "message": "OPENAI_API_KEY が未設定です。"}), 400

    slot_spec = {
        "morning": "170-280文字。基礎・応用・豆知識で有益、保存したくなる内容。",
        "noon": "90-180文字。AIニュース要約 + 今後の予測 + 今日の行動、リンクなし。",
        "evening": "110-220文字。共感ベースでゆるめ。デザイナーあるある・仕事あるある。",
    }[slot]
    slot_extra = (
        "- デザイナーあるある・仕事あるあるの小さな情景を1つ入れる\n"
        "- 読者が『わかる』と思える共感優先。教訓の押し付けはしない\n"
        "- 攻撃的/煽り口調は禁止。やさしい締めにする\n"
    ) if slot == "evening" else ""
    style_refs = _style_reference_posts_from_config()
    pdf_knowledge = _pdf_knowledge_for_prompt(slot_name=slot, max_docs=3, max_chars_per_doc=550)

    prompt = (
        "以下の条件でX投稿文を1本だけ作成してください。\n"
        f"- スロット: {slot}\n"
        f"- 文字数: {slot_spec}\n"
        "- アカウント軸: AI とデザインの実務知見\n"
        "- 最初にテーマの定義を1行で固定し、最後まで同じ意味で使う\n"
        "- 比喩で別領域へ飛ばさない（例: デザイン用語を生活ハック化しない）\n"
        "- 冷静さの中に僅かなカジュアルさ\n"
        "- 改行で2-4段落、必要なら短い箇条書き1-3項目\n"
        "- 絵文字は0-2個\n"
        "- ハッシュタグは文末に2-3個\n"
        "- ハッシュタグは本文の最後から2回改行して、独立した1行で配置\n"
        "- 「デザイナーあるある:」「豆知識:」「基礎:」「応用:」のような説明ラベルは書かない\n"
        "- 語尾は「〜だ。」を避け、「です。」または体言止め（例: 〜が肝心。）を混ぜる\n"
        "- URLは本文に含めない\n"
        f"- 文体参照（過去投稿サンプル）: {json.dumps(style_refs[:6], ensure_ascii=False)}\n"
        f"- PDFストック知見（参考）: {json.dumps(pdf_knowledge, ensure_ascii=False)}\n"
        "- 最新性が必要な内容はニュース/X由来を優先し、PDFは基礎知識や補足説明に使う\n"
        "- 上のサンプルの改行リズム・語尾の温度感・言葉選びを優先して合わせる\n"
        f"{slot_extra}"
        f"- テーマ: {topic}\n\n"
        'JSONで返す: {"text":"...","reason":"..."}'
    )

    try:
        res = _openai_client().responses.create(
            model="gpt-4.1-mini",
            input=[
                {"role": "system", "content": "あなたはX運用の編集者です。"},
                {"role": "user", "content": prompt},
            ],
        )
        data = json.loads(res.output_text)
        text = normalize_x_post_text(str(data.get("text", "")).strip(), slot_name=slot)
        reason = str(data.get("reason", "")).strip()
        if not text:
            return jsonify({"ok": False, "message": "投稿文の生成結果が空でした。"}), 400
        ok, why = _semantic_domain_guard(topic, text)
        if not ok:
            repair_prompt = (
                "次の投稿文を、意味破綻を直して1本に書き直してください。\n"
                f"- 元テーマ: {topic}\n"
                f"- 修正理由: {why}\n"
                "- テーマ語の意味を固定する\n"
                "- 本文は日本語、改行2-4段落、必要なら短い箇条書き\n"
                "- ハッシュタグ2-3個、URLなし\n\n"
                f"元文:\n{text}\n\n"
                'JSONで返す: {"text":"...","reason":"..."}'
            )
            repaired = _openai_client().responses.create(
                model="gpt-4.1-mini",
                input=[
                    {"role": "system", "content": "あなたはX運用の編集者です。"},
                    {"role": "user", "content": repair_prompt},
                ],
            )
            d2 = json.loads(repaired.output_text)
            text2 = normalize_x_post_text(str(d2.get("text", "")).strip(), slot_name=slot)
            reason2 = str(d2.get("reason", "")).strip() or reason
            if text2:
                text = text2
                reason = f"{reason2} / semantic-fix"
        return jsonify({"ok": True, "text": text, "reason": reason})
    except Exception as e:
        return jsonify({"ok": False, "message": f"投稿文生成エラー: {e}"}), 400


@app.post("/api/generate_image")
def api_generate_image():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400
    text = str(request.json.get("text", "")).strip()
    visual_mode = str(request.json.get("visual_mode", "auto")).strip() or "auto"
    if not text:
        return jsonify({"ok": False, "message": "投稿文が空です。"}), 400
    conf = _load_media_config()
    provider = str(conf.get("morning_image_provider", "nanobanana_pro")).strip() or "nanobanana_pro"
    prompt_payload = build_nano_banana_prompt_payload(text, visual_mode=visual_mode)
    generation_meta = {
        "provider_requested": provider,
        "provider_used": provider,
        "model_requested": "",
        "model_used": "",
        "fallback_allowed": False,
        "fallback_used": False,
        "prompt_payload": prompt_payload,
    }
    if provider == "nanobanana_pro":
        nb_settings = resolve_nanobanana_pro_settings()
        generation_meta.update(
            {
                "model_requested": str(nb_settings["model"]),
                "model_used": str(nb_settings["model"]),
                "fallback_allowed": bool(nb_settings["fallback_allowed"]),
            }
        )
        if not str(nb_settings["api_key"]).strip():
            if not (bool(nb_settings["fallback_allowed"]) and bool(nb_settings["freepik_ready"])):
                return jsonify({"ok": False, "message": "GOOGLE_API_KEY が未設定です。"}), 400
    elif provider == "nanobanana_cmd":
        tpl = (os.getenv("NANOBANANA_CMD_TEMPLATE") or "").strip()
        freepik_ready = bool((os.getenv("FREEPIK_API_KEY") or "").strip())
        if not tpl:
            if not freepik_ready:
                return jsonify({"ok": False, "message": "NANOBANANA_CMD_TEMPLATE が未設定です。"}), 400
        try:
            parts = shlex.split(tpl) if tpl else []
        except Exception:
            return jsonify({"ok": False, "message": "NANOBANANA_CMD_TEMPLATE の書式が不正です。"}), 400
        if tpl and not parts:
            return jsonify({"ok": False, "message": "NANOBANANA_CMD_TEMPLATE が空です。"}), 400
        cmd = parts[0] if parts else ""
        if cmd and not shutil.which(cmd) and not freepik_ready:
            return jsonify(
                {
                    "ok": False,
                    "message": f"Nano Banana CLI が見つかりません: `{cmd}`。インストール後に再実行してください。",
                }
            ), 400
    elif provider == "freepik_mystic":
        if not (os.getenv("FREEPIK_API_KEY") or "").strip():
            return jsonify({"ok": False, "message": "FREEPIK_API_KEY が未設定です。"}), 400
    else:
        return jsonify({"ok": False, "message": f"未対応プロバイダです: {provider}"}), 400

    output_dir = conf.get("morning_image_output_dir") or "generated_media"
    try:
        output = None
        used_mode = visual_mode
        err_detail = ""
        retries = 3
        for i in range(retries):
            if provider == "freepik_mystic":
                out, mode, err = generate_image_with_freepik_mystic(text, str(output_dir), visual_mode=visual_mode)
                meta = {
                    **generation_meta,
                    "provider_used": "freepik_mystic",
                    "model_used": "freepik_mystic",
                }
            elif provider == "nanobanana_pro":
                out, mode, err, meta = generate_image_with_nanobanana_pro_api(
                    text, str(output_dir), visual_mode=visual_mode
                )
            else:
                out, mode, err = generate_image_with_nanobanana(text, str(output_dir), visual_mode=visual_mode)
                meta = {
                    **generation_meta,
                    "provider_used": "nanobanana_cmd",
                    "model_used": "nanobanana_cmd",
                }
            output, used_mode, err_detail = out, mode, err
            generation_meta = meta
            if output:
                break
            detail_lower = (err_detail or "").lower()
            transient = any(k in detail_lower for k in ["503", "unavailable", "high demand", "try again later"])
            if not transient or i == retries - 1:
                break
            # Exponential backoff: 2s, 4s, 8s
            time.sleep(2 ** (i + 1))

        if not output:
            detail = (err_detail or "").strip()
            if len(detail) > 300:
                detail = detail[:300] + "..."
            low = detail.lower()
            transient = any(k in low for k in ["503", "unavailable", "high demand", "try again later"])
            retry_after_sec = 600 if transient else 0
            status = 503 if transient else 400
            return jsonify(
                {
                    "ok": False,
                    "message": (
                        "画像生成に失敗しました。"
                        + (f" 詳細: {detail}" if detail else "NANOBANANA_CMD_TEMPLATE と CLI 実行可否を確認してください。")
                    ),
                    "retry_after_sec": retry_after_sec,
                    **generation_meta,
                }
            ), status
        print(
            f"[api_generate_image] requested={generation_meta['provider_requested']} "
            f"used={generation_meta['provider_used']} model={generation_meta['model_used']} "
            f"fallback={'yes' if generation_meta['fallback_used'] else 'no'}"
        )
        return jsonify(
            {
                "ok": True,
                "path": output,
                "url": _safe_media_url(output),
                "visual_mode": used_mode,
                **generation_meta,
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "message": f"画像生成エラー: {e}"}), 400


@app.post("/api/generate_image_prompt")
def api_generate_image_prompt():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400
    text = str(request.json.get("text", "")).strip()
    visual_mode = str(request.json.get("visual_mode", "auto")).strip() or "auto"
    if not text:
        return jsonify({"ok": False, "message": "投稿文が空です。"}), 400
    try:
        payload = build_nano_banana_prompt_payload(text, visual_mode=visual_mode)
        return jsonify({"ok": True, **payload})
    except Exception as e:
        return jsonify({"ok": False, "message": f"画像プロンプト解析エラー: {e}"}), 400


@app.get("/api/media/<path:relpath>")
def api_media_file(relpath: str):
    target = (ROOT / relpath).resolve()
    root_resolved = ROOT.resolve()
    if root_resolved not in target.parents:
        return jsonify({"ok": False, "message": "invalid path"}), 400
    return send_from_directory(str(target.parent), target.name)


@app.get("/api/data-media/<path:relpath>")
def api_data_media_file(relpath: str):
    target = (DATA_ROOT / relpath).resolve()
    data_resolved = DATA_ROOT.resolve()
    if data_resolved not in target.parents:
        return jsonify({"ok": False, "message": "invalid path"}), 400
    return send_from_directory(str(target.parent), target.name)


@app.post("/api/queue_media_upload")
def api_queue_media_upload():
    file = request.files.get("media")
    if not file or not file.filename:
        return jsonify({"ok": False, "message": "画像ファイルを選択してください。"}), 400
    safe_name = Path(file.filename).name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return jsonify({"ok": False, "message": "画像は png/jpg/jpeg/webp/gif のみ対応です。"}), 400
    QUEUE_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    stem = Path(safe_name).stem or "queue_media"
    saved = QUEUE_MEDIA_DIR / f"{stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
    file.save(saved)
    meta = _queue_media_meta(str(saved))
    return jsonify({"ok": True, "message": "添付画像を保存しました。", **meta})


@app.post("/api/plan_preview")
def api_plan_preview():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400
    if not CONFIG_PATH.exists():
        return jsonify({"ok": False, "message": "config.yaml がありません。"}), 400

    unit = str(request.json.get("unit", "days"))
    count = int(request.json.get("count", 7))
    every_day = bool(request.json.get("every_day", True))
    start_date_str = str(request.json.get("start_date", date.today().isoformat()))
    generation_nonce = int(request.json.get("generation_nonce", 0) or 0)
    start_date = date.fromisoformat(start_date_str)

    if unit not in {"days", "weeks", "months"}:
        return jsonify({"ok": False, "message": "unitは days/weeks/months"}), 400
    max_count = _max_count_by_unit(unit)
    if count < 1 or count > max_count:
        return jsonify({"ok": False, "message": f"{unit} のcountは1〜{max_count}で指定してください。"}), 400

    config = load_config(str(CONFIG_PATH))
    memory = load_memory(config.uniqueness_memory_path)
    history = load_history(config.post_history_path)
    queue_items = _load_queue()
    print(f"[HISTORY LOAD] count={len(history.entries)}")
    posted_morning_fp = _planner_seen_keys(history, "morning", queue_items)
    posted_noon_fp = _planner_seen_keys(history, "noon", queue_items)
    posted_evening_fp = _planner_seen_keys(history, "evening", queue_items)
    recent_content_types_by_slot = {
        "morning": history_pattern_types(history, slot="morning", limit=6),
        "noon": history_content_types(history, slot="noon", limit=6),
        "evening": history_pattern_types(history, slot="evening", limit=6),
    }
    recent_topics_by_slot = {
        "morning": history_topics(history, slot="morning"),
        "evening": history_topics(history, slot="evening"),
    }
    total_days = _days_from_unit(unit, count)
    slots = config.required_daily_slots or ["morning", "noon", "evening"]
    items = fetch_rss_items(config.rss_feeds, max_items=config.max_input_items)
    items = filter_blocked(items, config.blocked_keywords)
    recent_posts_by_slot = {
        "morning": [
            str(entry.get("text", "")).strip()
            for entry in reversed(history.entries)
            if str(entry.get("slot", "")).strip() == "morning" and str(entry.get("text", "")).strip()
        ][:8],
        "noon": [
            str(entry.get("text", "")).strip()
            for entry in reversed(history.entries)
            if str(entry.get("slot", "")).strip() == "noon" and str(entry.get("text", "")).strip()
        ][:8],
        "evening": [
            str(entry.get("text", "")).strip()
            for entry in reversed(history.entries)
            if str(entry.get("slot", "")).strip() == "evening" and str(entry.get("text", "")).strip()
        ][:8],
    }
    recent_semantics_by_slot = {
        "morning": semantic_summaries(history, slot="morning", limit=8),
        "noon": semantic_summaries(history, slot="noon", limit=8),
        "evening": semantic_summaries(history, slot="evening", limit=8),
    }
    recent_idea_keys_by_slot = {
        "morning": history_idea_keys(history, slot="morning", limit=40),
        "evening": history_idea_keys(history, slot="evening", limit=40),
    }

    plan = []
    local_fp: set[str] = set()
    generation_seed = generation_nonce * 101
    for i in range(total_days):
        d = start_date + timedelta(days=i)
        if not every_day and d.weekday() >= 5:
            continue
        weekday = _weekday_key(d)
        weekday_theme = config.weekly_themes.get(weekday, "通常テーマ")

        for slot in slots:
            print(f"[GEN START] slot={slot} type=planner")
            slot_profile = config.slot_profiles.get(slot, {})
            slot_style = str(slot_profile.get("style", "通常枠"))
            slot_min_chars = int(slot_profile.get("min_chars", config.min_post_chars))
            slot_max_chars = int(slot_profile.get("max_chars", config.max_post_chars))
            slot_time = str(slot_profile.get("time", "09:00"))
            latest_share_mode = bool(slot_profile.get("latest_share_mode", True if slot == "noon" else False))
            latest_capture_minutes = int(slot_profile.get("latest_capture_minutes_before", 30))
            slot_pdf_knowledge = _pdf_knowledge_for_prompt(slot_name=slot, max_docs=3, max_chars_per_doc=700)

            if slot == "morning":
                picked = None
                picked_draft = None
                morning_seed = d.toordinal() * 11 + i + generation_seed
                morning_batches = [
                    ("strict", build_morning_type_drafts(morning_seed, max_candidates=10, items=items)),
                    ("relaxed", build_morning_type_drafts(morning_seed + 17, max_candidates=10, preferred_types=["timeless", "practical", "insight", "quote", "latest", "trend"], items=items)),
                    ("forced", build_quote_fallback_drafts(morning_seed + 29, max_candidates=4)),
                ]
                for level, drafts in morning_batches:
                    print(f"[GEN LEVEL] {level}")
                    print(f"[GEN CANDIDATES] count={len(drafts)}")
                    for attempt, draft in enumerate(drafts, start=1):
                        print(f"[UNIQUE RETRY] attempt={attempt}")
                        candidate = draft.text
                        print(f"[SEMANTIC RETRY] attempt={attempt}")
                        recent_types = recent_content_types_by_slot["morning"][-1:]
                        pattern_key = (draft.pattern_type or draft.content_type or "").strip().lower()
                        topic_key = (draft.topic or "").strip().lower()
                        idea_key = (
                            (draft.topic or "").strip().lower(),
                            (draft.claim or "").strip().lower(),
                            (draft.angle or "").strip().lower(),
                        )
                        if topic_key and topic_key in recent_topics_by_slot["morning"]:
                            print("[DUPLICATE REJECT] reason=topic_duplicate")
                            continue
                        if any(idea_key) and idea_key in recent_idea_keys_by_slot["morning"]:
                            print("[DUPLICATE REJECT] reason=idea_duplicate")
                            continue
                        if level != "forced" and pattern_key and pattern_key in recent_types:
                            print(f"[UNIQUE REJECT] reason=content_type_repeat type={pattern_key}")
                            continue
                        if not _is_used_before(candidate, memory, posted_morning_fp, history=history, slot="morning", generation_level=level):
                            if not (_seen_keys(candidate) & local_fp):
                                _remember_seen(candidate, local_fp)
                                print(f"[UNIQUE PICKED] fingerprint={strict_fingerprint(candidate)}")
                                semantic = semantic_duplicate_check(candidate, history, slot="morning")
                                print(f"[SEMANTIC PICKED] topic={semantic.candidate.topic[:80]}")
                                if draft.pattern_type or draft.content_type:
                                    print(f"[PATTERN PICK] slot=morning pattern={draft.pattern_type or draft.content_type}")
                                if draft.content_type:
                                    print(f"[PICKED TYPE] type={draft.content_type}")
                                    recent_content_types_by_slot["morning"].append(draft.pattern_type or draft.content_type)
                                if topic_key:
                                    recent_topics_by_slot["morning"].add(topic_key)
                                if any(idea_key):
                                    recent_idea_keys_by_slot["morning"].add(idea_key)
                                picked = candidate
                                picked_draft = draft
                                break
                    if picked:
                        break
                if not picked:
                    picked = _unique_or_fallback(
                        "",
                        "morning",
                        d,
                        weekday_theme,
                        memory,
                        local_fp,
                        posted_morning_fp,
                        history=history,
                    )
                    if picked and not picked_draft:
                        picked_draft = type("DraftLike", (), {"content_type": "design", "pattern_type": "timeless"})()
                text = picked
                plan.append(
                    {
                        "date": d.isoformat(),
                        "time": slot_time,
                        "slot": slot,
                        "theme": {
                            "latest": "latest / 最近のデザイン潮流",
                            "trend": "trend / 話題をデザイン視点で解釈",
                            "timeless": "timeless / 普遍的な設計原則",
                            "quote": "quote / デザイナーの言葉",
                            "practical": "practical / 実務判断",
                            "insight": "insight / 小さな気づき",
                        }.get(getattr(picked_draft, "pattern_type", ""), "timeless / 普遍的な設計原則"),
                        "content_type": getattr(picked_draft, "content_type", "design"),
                        "pattern_type": getattr(picked_draft, "pattern_type", "timeless"),
                        "text": text,
                        "refresh_mode": "",
                    }
                )
                continue

            if slot == "evening":
                picked = None
                picked_draft = None
                evening_seed = d.toordinal() * 17 + i + generation_seed
                evening_batches = [
                    ("strict", build_evening_type_drafts(items, evening_seed, max_candidates=12, preferred_types=["practical", "insight", "latest", "trend", "timeless", "quote"])),
                    ("relaxed", build_evening_type_drafts(items, evening_seed + 19, max_candidates=12, preferred_types=["practical", "insight", "trend", "timeless", "latest", "quote"])),
                    ("forced", build_evening_type_drafts(items, evening_seed + 31, max_candidates=8, preferred_types=["trend", "practical", "insight", "quote"]) + build_quote_fallback_drafts(evening_seed + 43, max_candidates=2)),
                ]
                for level, drafts in evening_batches:
                    print(f"[GEN LEVEL] {level}")
                    print(f"[GEN CANDIDATES] count={len(drafts)}")
                    for attempt, draft in enumerate(drafts, start=1):
                        print(f"[UNIQUE RETRY] attempt={attempt}")
                        candidate = draft.text
                        print(f"[SEMANTIC RETRY] attempt={attempt}")
                        recent_types = recent_content_types_by_slot["evening"][-2:]
                        pattern_key = (draft.pattern_type or draft.content_type or "").strip().lower()
                        topic_key = (draft.topic or "").strip().lower()
                        idea_key = (
                            (draft.topic or "").strip().lower(),
                            (draft.claim or "").strip().lower(),
                            (draft.angle or "").strip().lower(),
                        )
                        if topic_key and topic_key in recent_topics_by_slot["evening"]:
                            print("[DUPLICATE REJECT] reason=topic_duplicate")
                            continue
                        if any(idea_key) and idea_key in recent_idea_keys_by_slot["evening"]:
                            print("[DUPLICATE REJECT] reason=idea_duplicate")
                            continue
                        if level != "forced" and pattern_key and pattern_key in recent_types:
                            print(f"[UNIQUE REJECT] reason=content_type_repeat type={pattern_key}")
                            continue
                        if not _is_used_before(candidate, memory, posted_evening_fp, history=history, slot="evening", generation_level=level):
                            if not (_seen_keys(candidate) & local_fp):
                                _remember_seen(candidate, local_fp)
                                print(f"[UNIQUE PICKED] fingerprint={strict_fingerprint(candidate)}")
                                semantic = semantic_duplicate_check(candidate, history, slot="evening")
                                print(f"[SEMANTIC PICKED] topic={semantic.candidate.topic[:80]}")
                                if draft.pattern_type or draft.content_type:
                                    print(f"[PATTERN PICK] slot=evening pattern={draft.pattern_type or draft.content_type}")
                                if draft.content_type:
                                    print(f"[PICKED TYPE] type={draft.content_type}")
                                    recent_content_types_by_slot["evening"].append(draft.pattern_type or draft.content_type)
                                if topic_key:
                                    recent_topics_by_slot["evening"].add(topic_key)
                                if any(idea_key):
                                    recent_idea_keys_by_slot["evening"].add(idea_key)
                                if draft.topic:
                                    print(f"[TOPIC] {draft.topic[:120]}")
                                if draft.structure:
                                    print(f"[STRUCTURE] {draft.structure}")
                                if draft.pattern_type == "trend" and draft.topic:
                                    print(f"[TREND SOURCE] {draft.topic[:120]}")
                                print(
                                    f"[EVENING PICKED] hook={semantic.candidate.hook[:60]} "
                                    f"structure={semantic.candidate.structure}"
                                )
                                picked = candidate
                                picked_draft = draft
                                break
                    if picked:
                        break
                if not picked:
                    picked = _unique_or_fallback(
                        "",
                        "evening",
                        d,
                        weekday_theme,
                        memory,
                        local_fp,
                        posted_evening_fp,
                        history=history,
                    )
                    if picked and not picked_draft:
                        picked_draft = type("DraftLike", (), {"content_type": "design", "pattern_type": "practical"})()
                if not picked:
                    print(f"[NO POST GENERATED] reason=planner_evening_fallback_empty slot={slot}")
                    print(f"[EVENING HOLD] reason=no_unique_evening_candidate date={d.isoformat()}")
                text = picked
                plan.append(
                    {
                        "date": d.isoformat(),
                        "time": slot_time,
                        "slot": slot,
                        "theme": {
                            "latest": "latest / 最近のデザイン潮流",
                            "trend": "trend / 話題をデザイン視点で解釈",
                            "timeless": "timeless / 普遍的な設計原則",
                            "quote": "quote / デザイナーの言葉",
                            "practical": "practical / 実務判断",
                            "insight": "insight / 小さな気づき",
                        }.get(getattr(picked_draft, "pattern_type", ""), "practical / 実務判断"),
                        "content_type": getattr(picked_draft, "content_type", "design"),
                        "pattern_type": getattr(picked_draft, "pattern_type", "practical"),
                        "text": text,
                        "refresh_mode": "",
                    }
                )
                continue

            if slot == "noon" and latest_share_mode:
                text = _jit_noon_placeholder(latest_capture_minutes, variant=generation_nonce + i)
            else:
                text = ""
                if items and os.getenv("OPENAI_API_KEY"):
                    for attempt in range(4):
                        print(f"[UNIQUE RETRY] attempt={attempt + 1}")
                        print(f"[SEMANTIC RETRY] attempt={attempt + 1}")
                        subset = _rotated_items(items, seed=(i * 7 + attempt * 3 + generation_seed), take=8)
                        try:
                            drafts = build_post_drafts(
                                model=config.model,
                                items=subset,
                                tone=config.tone,
                                audience=config.audience,
                                prediction_horizon=config.prediction_horizon,
                                post_style_template=config.post_style_template,
                                voice_guide=config.voice_guide,
                                style_reference_posts=config.style_reference_posts,
                                weekday_theme=weekday_theme,
                                slot_name=slot,
                                slot_style=slot_style,
                                slot_min_chars=slot_min_chars,
                                slot_max_chars=slot_max_chars,
                                max_posts=3,
                                knowledge_snippets=slot_pdf_knowledge,
                                recent_self_posts=recent_posts_by_slot.get(slot, []),
                                recent_semantic_summaries=recent_semantics_by_slot.get(slot, []),
                            )
                            unique = None
                            rotation = _rotation_start(generation_nonce + i + attempt, len(drafts))
                            ordered_drafts = drafts[rotation:] + drafts[:rotation]
                            for dft in ordered_drafts:
                                if not _is_used_before(dft.text, memory, posted_noon_fp, history=history, slot=slot):
                                    if not (_seen_keys(dft.text) & local_fp):
                                        _remember_seen(dft.text, local_fp)
                                        print(f"[UNIQUE PICKED] fingerprint={strict_fingerprint(dft.text)}")
                                        semantic = semantic_duplicate_check(dft.text, history, slot=slot)
                                        print(f"[SEMANTIC PICKED] topic={semantic.candidate.topic[:80]}")
                                        unique = dft.text
                                        break
                            if unique:
                                text = unique
                                break
                        except Exception:
                            continue
                if not text:
                    history_fp = posted_noon_fp if slot == "noon" else None
                    text = _unique_or_fallback(
                        _fallback_plan_text(slot, weekday_theme),
                        slot,
                        d,
                        weekday_theme,
                        memory,
                        local_fp,
                        history_fp,
                        history=history,
                    )
                if not text:
                    print(f"[UNIQUE HOLD] reason=no_unique_candidate slot={slot} date={d.isoformat()}")
                    print(f"[SEMANTIC HOLD] reason=no_semantically_unique_candidate slot={slot} date={d.isoformat()}")

            plan.append(
                {
                    "date": d.isoformat(),
                    "time": slot_time,
                    "slot": slot,
                    "theme": "news / AIニュース + 今後の予測" if slot == "noon" else weekday_theme,
                    "content_type": "news" if slot == "noon" else "",
                    "text": text,
                    "refresh_mode": "jit_noon" if (slot == "noon" and latest_share_mode) else "",
                }
            )

    return jsonify({"ok": True, "count": len(plan), "plan": plan, "generation_nonce": generation_nonce})


@app.get("/api/target_account")
def api_get_target_account():
    conf = _load_config_map()
    handle = str(conf.get("profile", {}).get("account_handle", "")).strip()
    return jsonify({"ok": True, "account_handle": handle})


@app.post("/api/target_account")
def api_set_target_account():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400
    handle = str(request.json.get("account_handle", "")).strip()
    if not handle:
        return jsonify({"ok": False, "message": "account_handle を入力してください。"}), 400
    if not handle.startswith("@"):
        handle = f"@{handle}"

    conf = _load_config_map()
    profile = conf.get("profile", {}) or {}
    profile["account_handle"] = handle
    conf["profile"] = profile
    _save_config_map(conf)
    return jsonify({"ok": True, "account_handle": handle, "message": "運用対象アカウントを保存しました。"})


@app.post("/api/verify_target_account")
def api_verify_target_account():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400
    handle = str(request.json.get("account_handle", "")).strip()
    if not handle:
        return jsonify({"ok": False, "message": "account_handle を入力してください。"}), 400
    username = handle[1:] if handle.startswith("@") else handle

    def _ok_payload(user):
        metrics = user.public_metrics or {}
        return {
            "ok": True,
            "username": user.username,
            "name": user.name,
            "followers": metrics.get("followers_count", 0),
            "tweet_count": metrics.get("tweet_count", 0),
            "verified": bool(getattr(user, "verified", False)),
        }

    # 1) bearer token で確認
    bearer = os.getenv("X_BEARER_TOKEN")
    if bearer:
        try:
            read_client = tweepy.Client(bearer_token=bearer, wait_on_rate_limit=True)
            res = read_client.get_user(username=username, user_fields=["public_metrics", "verified"])
            if res and res.data:
                return jsonify(_ok_payload(res.data))
        except Exception:
            # bearerで失敗した場合は user auth へフォールバック
            pass

    # 2) user auth で確認（X_API_KEY など）
    try:
        res = _x_client().get_user(username=username, user_fields=["public_metrics", "verified"], user_auth=True)
        if not res or not res.data:
            return jsonify({"ok": False, "message": "該当アカウントが見つかりませんでした。"}), 404
        return jsonify(_ok_payload(res.data))
    except Exception as e:
        return jsonify(
            {
                "ok": False,
                "message": (
                    "アカウント確認エラー: 403が続く場合、X Developer Portalで"
                    "同一Project配下のAppキー/トークン（Bearer, API Key, Access Token）を再発行して設定してください。"
                    f" 詳細: {e}"
                ),
            }
        ), 400


@app.get("/api/queue")
def api_get_queue():
    queue = []
    for item in _load_queue():
        row = dict(item)
        row["id"] = _queue_item_id(row.get("id"))
        row["schedule_at"] = serialize_scheduled_datetime(str(row.get("schedule_at", "")).strip()) or str(
            row.get("schedule_at", "")
        ).strip()
        row["schedule_at_local"] = format_datetime_local_input(row["schedule_at"])
        row["status"] = str(row.get("status", "scheduled")).strip() or "scheduled"
        row["posted"] = bool(row.get("posted", False))
        media_path = str(row.get("media_path", "")).strip()
        if media_path:
            try:
                row.update(_queue_media_meta(media_path))
            except Exception:
                row["media_url"] = ""
                row["media_name"] = Path(media_path).name
        else:
            row["media_url"] = ""
            row["media_name"] = ""
        queue.append(row)
    return jsonify({"ok": True, "queue": queue})


@app.post("/api/queue")
def api_save_queue():
    if not request.is_json:
        return jsonify({"ok": False, "message": "JSONで送信してください。"}), 400
    queue = request.json.get("queue", [])
    if not isinstance(queue, list):
        return jsonify({"ok": False, "message": "queueは配列で指定してください。"}), 400

    conf = load_config(str(CONFIG_PATH)) if CONFIG_PATH.exists() else None
    memory = load_memory(conf.uniqueness_memory_path) if conf else load_memory("post_memory.yaml")
    normalized = []
    invalid_items: list[str] = []
    for item in queue:
        if not isinstance(item, dict):
            continue
        raw_schedule_at = str(item.get("schedule_at", "")).strip()
        schedule_at = serialize_scheduled_datetime(raw_schedule_at, conf)
        slot = str(item.get("slot", "")).strip()
        theme = str(item.get("theme", "")).strip()
        text = str(item.get("text", "")).strip()
        refresh_mode = str(item.get("refresh_mode", "")).strip()
        allow_empty_text = refresh_mode == "jit_noon"
        item_id = _queue_item_id(item.get("id"))
        if not schedule_at:
            invalid_items.append(f"id={item_id}:invalid_schedule_at:{raw_schedule_at or '-'}")
            continue
        if not slot or (not text and not allow_empty_text):
            invalid_items.append(f"id={item_id}:missing_required_fields")
            continue
        raw_media_path = str(item.get("media_path", "")).strip()
        try:
            persisted_media_path = _persist_queue_media(raw_media_path)
        except Exception as e:
            print(f"[QUEUE MEDIA DROP] schedule_at={schedule_at} slot={slot} path={raw_media_path} err={e}")
            persisted_media_path = ""
        normalized.append(
            {
                "id": _queue_item_id(item.get("id")),
                "schedule_at": schedule_at,
                "slot": slot,
                "theme": theme,
                "text": text,
                "reply_text": str(item.get("reply_text", "")).strip(),
                "media_source": str(item.get("media_source", "")).strip() or ("existing" if item.get("media_path") else "none"),
                "media_prompt": str(item.get("media_prompt", "")).strip(),
                "media_visual_mode": str(item.get("media_visual_mode", "auto")).strip() or "auto",
                "media_path": persisted_media_path,
                "source_tweet_id": str(item.get("source_tweet_id", "")).strip(),
                "source_author": str(item.get("source_author", "")).strip(),
                "last_refreshed_at": str(item.get("last_refreshed_at", "")).strip(),
                "refresh_mode": refresh_mode,
                "status": str(item.get("status", "scheduled")).strip() or "scheduled",
                "posted": bool(item.get("posted", False)),
                "posted_at": str(item.get("posted_at", "")).strip(),
            }
        )

    if invalid_items:
        return (
            jsonify({"ok": False, "message": "保存できないキュー項目があります。", "invalid_items": invalid_items}),
            400,
        )

    _save_queue(normalized)
    for item in normalized:
        if str(item.get("refresh_mode", "")).strip() == "jit_noon":
            continue
        register_text(str(item.get("text", "")), memory)
    save_memory(memory)
    queue = []
    for item in normalized:
        row = dict(item)
        row["schedule_at_local"] = format_datetime_local_input(str(row.get("schedule_at", "")).strip(), conf)
        media_path = str(row.get("media_path", "")).strip()
        if media_path:
            try:
                row.update(_queue_media_meta(media_path))
            except Exception:
                row["media_url"] = ""
                row["media_name"] = Path(media_path).name
        else:
            row["media_url"] = ""
            row["media_name"] = ""
        queue.append(row)
    return jsonify({"ok": True, "message": f"{len(normalized)}件のキューを保存しました。", "queue": queue})


@app.get("/api/internal/queue")
def api_internal_get_queue():
    if not _queue_sync_authorized():
        return jsonify({"ok": False, "message": "unauthorized"}), 401
    return api_get_queue()


@app.post("/api/internal/queue")
def api_internal_save_queue():
    if not _queue_sync_authorized():
        return jsonify({"ok": False, "message": "unauthorized"}), 401
    return api_save_queue()


@app.get("/")
def index():
    return send_from_directory(UI_DIR, "index.html")


@app.get("/api/account")
def api_account():
    missing = [k for k in ACCOUNT_REQUIRED_KEYS if not os.getenv(k)]
    if missing:
        return jsonify({"ok": False, "missing": missing, "message": "環境変数が不足しています。"}), 400

    try:
        me = _x_client().get_me(user_auth=True, user_fields=["username", "name", "public_metrics"])
        if not me or not me.data:
            return jsonify({"ok": False, "message": "Xアカウント情報を取得できませんでした。"}), 400
        user = me.data
        metrics = user.public_metrics or {}
        return jsonify(
            {
                "ok": True,
                "username": user.username,
                "name": user.name,
                "followers": metrics.get("followers_count", 0),
                "following": metrics.get("following_count", 0),
                "tweet_count": metrics.get("tweet_count", 0),
            }
        )
    except Exception as e:
        return jsonify({"ok": False, "message": f"X連動エラー: {e}"}), 400


@app.post("/api/run_dry")
def api_run_dry():
    slot = request.json.get("slot", "morning") if request.is_json else "morning"
    if slot not in {"morning", "noon", "evening"}:
        return jsonify({"ok": False, "message": "slotは morning/noon/evening のみ"}), 400

    if not CONFIG_PATH.exists():
        return jsonify({"ok": False, "message": "config.yaml がありません。config.example.yaml から作成してください。"}), 400

    cmd = [
        "python3",
        "-m",
        "src.x_autopost_tool.main",
        "--config",
        str(CONFIG_PATH),
        "--slot",
        slot,
        "run-once",
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return jsonify({"ok": proc.returncode == 0, "slot": slot, "output": out[-12000:]})


@app.post("/api/test_post")
def api_test_post():
    if request.is_json:
        text = str(request.json.get("text", "")).strip()
        source_url = str(request.json.get("source_url", "")).strip()
        attach_source_reply = bool(request.json.get("attach_source_reply", False))
        media_path = str(request.json.get("media_path", "")).strip()
        file = None
    else:
        text = str(request.form.get("text", "")).strip()
        source_url = str(request.form.get("source_url", "")).strip()
        attach_source_reply = str(request.form.get("attach_source_reply", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        media_path = str(request.form.get("media_path", "")).strip()
        file = request.files.get("media")

    if not text:
        return jsonify({"ok": False, "message": "投稿本文が空です。"}), 400
    text = cleanup_post_text(text)
    if len(text) > 280:
        return jsonify({"ok": False, "message": f"文字数が280を超えています: {len(text)}"}), 400

    missing = [k for k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"] if not os.getenv(k)]
    if missing:
        return jsonify({"ok": False, "message": f"投稿用キーが不足しています: {', '.join(missing)}"}), 400

    try:
        resp = None
        if file and file.filename:
            upload_dir = DATA_ROOT / "tmp_uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            safe_name = Path(file.filename).name
            suffix = Path(safe_name).suffix
            stem = Path(safe_name).stem or "upload"
            local_path = upload_dir / f"{stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
            file.save(local_path)
            media = _x_api_v1().media_upload(filename=str(local_path))
            resp = _x_client().create_tweet(text=text, media_ids=[media.media_id_string], user_auth=True)
            try:
                local_path.unlink(missing_ok=True)
            except Exception:
                pass
        elif media_path:
            p = Path(media_path).resolve()
            if ROOT.resolve() not in p.parents:
                return jsonify({"ok": False, "message": "media_path が不正です。"}), 400
            if not p.exists():
                return jsonify({"ok": False, "message": "media_path のファイルが存在しません。"}), 400
            media = _x_api_v1().media_upload(filename=str(p))
            resp = _x_client().create_tweet(text=text, media_ids=[media.media_id_string], user_auth=True)
        else:
            resp = _x_client().create_tweet(text=text, user_auth=True)
        tweet_id = str(resp.data.get("id")) if resp and resp.data else ""
        if attach_source_reply and source_url and tweet_id:
            reply = cleanup_post_text(f"出典メモ: {source_url}")
            _x_client().create_tweet(text=reply, in_reply_to_tweet_id=tweet_id, user_auth=True)
        me = _x_client().get_me(user_auth=True, user_fields=["username"])
        username = me.data.username if me and me.data else ""
        tweet_url = f"https://x.com/{username}/status/{tweet_id}" if username and tweet_id else ""
        conf = load_config(str(CONFIG_PATH)) if CONFIG_PATH.exists() else None
        memory = load_memory(conf.uniqueness_memory_path) if conf else load_memory("post_memory.yaml")
        register_text(text, memory)
        save_memory(memory)
        history = load_history(conf.post_history_path) if conf else load_history("post_history.yaml")
        append_history(
            text,
            history,
            slot="manual",
            source="test-post",
            tweet_id=tweet_id,
            posted_at=datetime.now().isoformat(),
            content_type="manual",
            pattern_type="manual",
        )
        save_history(history)
        return jsonify({"ok": True, "tweet_id": tweet_id, "tweet_url": tweet_url, "message": "試験投稿しました。"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"試験投稿エラー: {e}"}), 400


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8787"))
    app.run(host=host, port=port, debug=False, use_reloader=False)
