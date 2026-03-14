from __future__ import annotations

from datetime import datetime
import base64
import json
from pathlib import Path
import os
import re
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


VISUAL_MODES = {
    "auto": "Auto rotate visual style per post.",
    "design_case": "Design case style visual with UI fragments and annotations.",
    "diagram": "Concept diagram/infographic style to explain structure.",
    "editorial": "Editorial art direction style with strong typography.",
    "photo": "Photo-based realistic scene with clean composition.",
}

NANOBANANA_PRO_DEFAULT_MODEL = "gemini-3-pro-image-preview"

STOPWORDS = {
    "です",
    "ます",
    "する",
    "した",
    "して",
    "いる",
    "ある",
    "こと",
    "もの",
    "ため",
    "よう",
    "今日",
    "今後",
    "まず",
    "直近",
    "だけ",
    "十分",
    "感じる",
    "サイン",
    "流れ",
}

TONE_RULES = [
    ("encouraging", ["大丈夫", "OK", "十分", "一歩", "少しずつ", "続け", "積み上げ"]),
    ("analytical", ["設計", "構造", "整理", "比較", "改善", "見返", "違和感", "言語化"]),
    ("practical", ["まず", "手順", "工程", "自動化", "運用", "効率", "レビュー時間"]),
    ("urgent", ["速報", "今すぐ", "急い", "見逃せ", "大きい変化"]),
    ("reflective", ["今夜", "振り返", "判断", "記録", "1行", "終わり"]),
]


def _extract_keywords(post_text: str, limit: int = 5) -> list[str]:
    # Simple keyword extraction for Japanese/ASCII mixed text.
    text = re.sub(r"#[^\s]+", "", post_text)
    text = re.sub(r"[・:：,，。\.\n\r\t\-\(\)\[\]\"'「」『』!?！？]", " ", text)
    tokens = [t.strip() for t in text.split(" ") if len(t.strip()) >= 2]
    uniq = []
    seen = set()
    for t in tokens:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(t)
        if len(uniq) >= limit:
            break
    return uniq


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def resolve_nanobanana_pro_settings() -> dict[str, str | bool]:
    api_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("NANOBANANA_API_KEY") or "").strip()
    model = (os.getenv("NANOBANANA_MODEL") or NANOBANANA_PRO_DEFAULT_MODEL).strip() or NANOBANANA_PRO_DEFAULT_MODEL
    api_url = (
        os.getenv("NANOBANANA_API_URL")
        or f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    ).strip()
    fallback_allowed = _env_flag("NANOBANANA_ALLOW_FALLBACK", default=False)
    freepik_ready = bool((os.getenv("FREEPIK_API_KEY") or "").strip())
    return {
        "api_key": api_key,
        "model": model,
        "api_url": api_url,
        "fallback_allowed": fallback_allowed,
        "freepik_ready": freepik_ready,
    }


def _normalize_post_text(post_text: str) -> str:
    text = re.sub(r"https?://\S+", "", post_text or "")
    text = re.sub(r"#[^\s]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_sentences(post_text: str, limit: int = 3) -> list[str]:
    text = _normalize_post_text(post_text)
    parts = re.split(r"[。\n!?！？]+", text)
    out = []
    for part in parts:
        sentence = part.strip(" ・-")
        if len(sentence) < 6:
            continue
        out.append(sentence)
        if len(out) >= limit:
            break
    return out


def _guess_slot(post_text: str) -> str:
    text = post_text or ""
    if any(token in text for token in ["今夜", "夕方", "仕事終わり", "一日", "振り返", "終わり"]):
        return "evening"
    if any(token in text for token in ["今日のAI", "ニュース", "速報", "動向", "トピック"]):
        return "noon"
    return "morning"


def _pick_focus_sentence(post_text: str) -> str:
    sentences = _extract_sentences(post_text, limit=4)
    if not sentences:
        return _normalize_post_text(post_text)[:120]
    scored = []
    for sentence in sentences:
        score = 0
        if any(token in sentence for token in ["設計", "改善", "運用", "自動化", "判断", "制作", "見返", "振り返"]):
            score += 3
        if any(token in sentence for token in ["まずは", "してみて", "残して", "見たい", "見返し"]):
            score += 2
        score += min(len(sentence), 80) / 40
        scored.append((score, sentence))
    scored.sort(reverse=True)
    return scored[0][1]


def _classify_theme(post_text: str) -> str:
    text = _normalize_post_text(post_text)
    if any(token in text for token in ["自動化", "運用", "工程", "効率", "レビュー時間"]):
        return "workflow improvement with AI"
    if any(token in text for token in ["設計", "UI", "レイアウト", "制作物", "デザイン"]):
        return "design review and output quality"
    if any(token in text for token in ["ニュース", "動向", "予測", "トピック"]):
        return "AI trend summary and outlook"
    if any(token in text for token in ["振り返", "判断", "積み上げ", "今夜", "続け"]):
        return "steady progress and reflection"
    return "practical creative work with AI"


def _classify_tone(post_text: str) -> str:
    text = _normalize_post_text(post_text)
    for tone, rules in TONE_RULES:
        if any(token in text for token in rules):
            return tone
    return "calm and thoughtful"


def _build_core_message(post_text: str) -> str:
    focus = _pick_focus_sentence(post_text)
    action = _pick_action_sentence(post_text)
    if focus and action and action not in focus:
        return f"{focus[:120]} / {action[:90]}"
    if focus:
        return focus[:150]
    return "Show one concrete insight and one clear next step."


def _select_concept_pattern(post_text: str) -> str:
    text = _normalize_post_text(post_text)
    if any(token in text for token in ["比較", "違い", "before", "after", "改善", "見返", "惜しい"]):
        return "comparison"
    if any(token in text for token in ["感情", "余白", "空気感", "今夜", "振り返", "続け", "判断"]):
        return "symbolic"
    return "direct"


def _select_visual_mode(post_text: str, visual_mode: str) -> str:
    if visual_mode in VISUAL_MODES and visual_mode != "auto":
        return visual_mode
    text = _normalize_post_text(post_text)
    pattern = _select_concept_pattern(text)
    if any(token in text for token in ["工程", "フロー", "自動化", "比較", "整理", "構造"]):
        return "diagram"
    if any(token in text for token in ["設計", "UI", "制作物", "レイアウト", "デザイン"]):
        return "design_case"
    if pattern == "symbolic":
        if any(token in text for token in ["今夜", "振り返", "空気感", "余白"]):
            return "photo"
        return "editorial"
    return "photo"


def _pick_action_sentence(post_text: str) -> str:
    sentences = _extract_sentences(post_text, limit=5)
    for sentence in sentences:
        if any(token in sentence for token in ["まず", "してみて", "残して", "見返し", "言語化", "試して", "自動化"]):
            return sentence
    return sentences[-1] if sentences else ""


def _build_subject_line(post_text: str) -> str:
    focus = _pick_focus_sentence(post_text)
    if not focus:
        return "A calm visual about improving creative work with AI."
    return (
        "Main message: "
        + focus[:160]
        + ". Show the concrete situation behind this idea rather than an abstract generic AI image."
    )


def _build_action_line(post_text: str) -> str:
    action = _pick_action_sentence(post_text)
    if not action:
        return "Suggested action: show one small next step that feels practical and realistic."
    return "Suggested action in the image concept: " + action[:160]


def _build_scene_direction(post_text: str, visual_mode: str) -> str:
    text = _normalize_post_text(post_text)
    slot = _guess_slot(text)
    scene_bits: list[str] = []

    if any(token in text for token in ["設計", "UI", "レイアウト", "制作物", "アウトプット", "デザイン"]):
        scene_bits.append(
            "Scene idea: a designer's workspace with wireframes, UI cards, layout blocks, notes, and a visible review process."
        )
    if any(token in text for token in ["自動化", "運用", "工程", "フロー", "効率", "レビュー時間"]):
        scene_bits.append(
            "Scene idea: a workflow board or process map showing one manual step becoming streamlined and easier to review."
        )
    if any(token in text for token in ["振り返", "判断", "積み上げ", "続け", "今夜", "1行", "記録"]):
        scene_bits.append(
            "Scene idea: an evening desk with a notebook, one short written reflection, warm light, and a calm sense of progress."
        )
    if any(token in text for token in ["ニュース", "動向", "予測", "トピック", "今日のAI"]):
        scene_bits.append(
            "Scene idea: a concise editorial summary board with layered information cards and a future-looking perspective."
        )

    if not scene_bits:
        if slot == "evening":
            scene_bits.append("Scene idea: a quiet evening work desk with one completed task and one note for tomorrow.")
        elif slot == "noon":
            scene_bits.append("Scene idea: a clean editorial information board that summarizes one current AI shift.")
        else:
            scene_bits.append("Scene idea: a bright morning desk scene focused on reviewing and improving work.")

    if visual_mode == "diagram":
        scene_bits.append(
            "Translate the scene into a structured diagram with blocks, flow, grouping, and clear visual hierarchy."
        )
    elif visual_mode == "design_case":
        scene_bits.append(
            "Translate the scene into UI fragments, composition studies, review notes, and before/after layout comparisons."
        )
    elif visual_mode == "editorial":
        scene_bits.append(
            "Translate the scene into an editorial composition with a strong focal area and expressive negative space."
        )
    elif visual_mode == "photo":
        scene_bits.append(
            "Translate the scene into a realistic physical environment with believable materials, lighting, and objects."
        )

    return " ".join(scene_bits[:3])


def _build_constraint_line(post_text: str) -> str:
    keywords = [kw for kw in _extract_keywords(post_text, limit=8) if kw not in STOPWORDS]
    if not keywords:
        return "Important motifs: design review, improvement, process clarity, calm focus."
    return "Important motifs to preserve: " + ", ".join(keywords[:6]) + "."


def _pick_auto_mode(post_text: str) -> str:
    return _select_visual_mode(post_text, "auto")


def _build_avoid_list(post_text: str, visual_mode: str, concept_pattern: str) -> list[str]:
    avoid = [
        "generic futuristic AI imagery, robots, glowing brains, floating holograms",
        "readable text, logos, watermarks, branded UI, tiny labels",
        "overcrowded composition with too many elements or unclear focal point",
    ]
    text = _normalize_post_text(post_text)
    if concept_pattern == "comparison":
        avoid[2] = "vague abstract shapes that hide the contrast or comparison"
    elif concept_pattern == "symbolic":
        avoid[2] = "self-indulgent abstract art that looks beautiful but does not convey the message"
    if visual_mode == "photo":
        avoid.append("ad-like glossy product staging that feels disconnected from the post meaning")
    elif visual_mode == "diagram":
        avoid.append("decorative icons and complex chart details that reduce instant readability")
    return avoid[:4]


def _build_visual_strategy(post_text: str, visual_mode: str, concept_pattern: str) -> str:
    theme = _classify_theme(post_text)
    if concept_pattern == "comparison":
        concept = "comparison expression"
        objective = "show a clear difference between the weaker state and the improved state in one glance"
    elif concept_pattern == "symbolic":
        concept = "symbolic expression"
        objective = "use one grounded scene or object metaphor with enough realism to communicate instantly"
    else:
        concept = "direct expression"
        objective = "show the core message as a concrete scene, workflow, or object arrangement"
    style = {
        "design_case": "modern design-case layout",
        "diagram": "minimal structured diagram",
        "editorial": "modern conceptual editorial art direction",
        "photo": "clean realistic photo direction",
    }.get(visual_mode, "clear social-media visual")
    return f"{concept} with {style}; prioritize instant readability for SNS, match the theme '{theme}', and {objective}"


def build_nano_banana_prompt_payload(post_text: str, visual_mode: str = "auto") -> dict[str, object]:
    normalized = _normalize_post_text(post_text)
    mode = _select_visual_mode(normalized, visual_mode)
    tone = _classify_tone(normalized)
    theme = _classify_theme(normalized)
    core_message = _build_core_message(normalized)
    concept_pattern = _select_concept_pattern(normalized)
    visual_strategy = _build_visual_strategy(normalized, mode, concept_pattern)
    avoid = _build_avoid_list(normalized, mode, concept_pattern)

    base = (
        "Create a single image for an SNS post. "
        "The image must communicate the main idea immediately even without text. "
        "Prioritize clarity, relevance to the post, strong stopping power in a social feed, and clean composition. "
        "Choose one clear focal message only. "
        "Keep the element count low and avoid abstract ambiguity."
    )
    style = {
        "design_case": (
            "Use a modern design-case direction with UI fragments, layout review artifacts, spacing studies, and restrained color accents."
        ),
        "diagram": (
            "Use a minimal explanatory diagram style with clean hierarchy, before/after contrast or step relationships, and no tiny labels."
        ),
        "editorial": (
            "Use a modern conceptual editorial style with strong focal composition, controlled symbolism, and meaningful negative space."
        ),
        "photo": (
            "Use a realistic photographic direction with believable objects, natural lighting, and a concrete scene tied to the post."
        ),
    }.get(mode, "Use a clean, modern, highly legible social-media visual style.")
    concept = {
        "direct": "Visual approach: direct expression. Show the message as a concrete scene or workflow artifact.",
        "comparison": "Visual approach: comparison expression. Make the difference or improvement instantly understandable in one glance.",
        "symbolic": "Visual approach: symbolic expression. Use one grounded metaphor or everyday scene that still feels immediately readable.",
    }[concept_pattern]
    subject = _build_subject_line(normalized)
    action = _build_action_line(normalized)
    scene = _build_scene_direction(normalized, mode)
    constraints = _build_constraint_line(normalized)
    avoid_line = "Avoid: " + "; ".join(avoid) + "."
    tone_line = f"Emotional tone: {tone}."
    core_line = f"Core message to visualize: {core_message}."
    context = f"Post context summary: {normalized[:280]}"

    prompt_en = " ".join([base, style, concept, tone_line, core_line, subject, action, scene, constraints, avoid_line, context])
    prompt_ja = (
        f"SNS投稿向けに、主題「{theme}」を一目で伝える1枚画像を作成してください。"
        f"感情トーンは{tone}。"
        f"中心メッセージは「{core_message}」。"
        f"ビジュアル方針は{visual_strategy}。"
        "文字に頼らず、画像単体で意味が伝わる構図にしてください。"
        "要素は絞り、視認性を高く保ち、抽象的すぎる表現は避けてください。"
        f"避ける表現: {'、'.join(avoid)}。"
    )

    return {
        "theme": theme,
        "tone": tone,
        "core_message": core_message,
        "visual_strategy": visual_strategy,
        "avoid": avoid,
        "nano_banana_prompt_ja": prompt_ja,
        "nano_banana_prompt_en": prompt_en,
    }


def build_morning_image_prompt(post_text: str, visual_mode: str = "auto") -> tuple[str, str]:
    payload = build_nano_banana_prompt_payload(post_text, visual_mode=visual_mode)
    mode = _select_visual_mode(post_text, visual_mode)
    return str(payload["nano_banana_prompt_en"]), mode


def generate_image_with_nanobanana(
    post_text: str, output_dir: str, visual_mode: str = "auto"
) -> tuple[str | None, str, str]:
    """
    Requires env var:
      NANOBANANA_CMD_TEMPLATE
    Example:
      NANOBANANA_CMD_TEMPLATE='nanobanana --prompt "{prompt}" --out "{output}"'
    """
    tpl = os.getenv("NANOBANANA_CMD_TEMPLATE", "").strip()
    fallback_freepik = bool((os.getenv("FREEPIK_API_KEY") or "").strip())
    if not tpl:
        if fallback_freepik:
            return generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
        return None, "auto", "NANOBANANA_CMD_TEMPLATE is not set"

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"morning_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    prompt, used_mode = build_morning_image_prompt(post_text, visual_mode=visual_mode)
    prompt = prompt.replace('"', "'")
    cmd = tpl.format(prompt=prompt, output=str(out_path))

    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            print(f"[media] nanobanana failed: {err[:300]}")
            if fallback_freepik:
                print("[media] falling back to Freepik Mystic")
                return generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
            return None, used_mode, err[:1200]
        if not out_path.exists():
            print("[media] nanobanana finished but output not found")
            if fallback_freepik:
                print("[media] output missing, falling back to Freepik Mystic")
                return generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
            return None, used_mode, "output file was not created"
        return str(out_path), used_mode, ""
    except Exception as e:
        print(f"[media] nanobanana exception: {e}")
        if fallback_freepik:
            print("[media] exception, falling back to Freepik Mystic")
            return generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
        return None, used_mode, str(e)


def generate_image_with_nanobanana_pro_api(
    post_text: str,
    output_dir: str,
    visual_mode: str = "auto",
    timeout_sec: int = 120,
) -> tuple[str | None, str, str, dict[str, object]]:
    settings = resolve_nanobanana_pro_settings()
    api_key = str(settings["api_key"])
    fallback_freepik = bool(settings["fallback_allowed"]) and bool(settings["freepik_ready"])
    prompt_payload = build_nano_banana_prompt_payload(post_text, visual_mode=visual_mode)
    used_mode = _select_visual_mode(post_text, visual_mode)
    meta: dict[str, object] = {
        "provider_requested": "nanobanana_pro",
        "provider_used": "nanobanana_pro",
        "model_requested": str(settings["model"]),
        "model_used": str(settings["model"]),
        "api_url": str(settings["api_url"]),
        "fallback_allowed": bool(settings["fallback_allowed"]),
        "fallback_used": False,
        "prompt_payload": prompt_payload,
    }
    if not api_key:
        if fallback_freepik:
            out, mode, err = generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
            meta.update({"provider_used": "freepik_mystic", "model_used": "freepik_mystic", "fallback_used": True})
            return out, mode, err, meta
        return None, used_mode, "GOOGLE_API_KEY is not set", meta

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = str(prompt_payload["nano_banana_prompt_en"])

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    req = Request(
        str(settings["api_url"]),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    print(
        f"[media] nanobanana_pro request model={settings['model']} "
        f"fallback_allowed={'yes' if fallback_freepik else 'no'} visual_mode={used_mode}"
    )

    try:
        with urlopen(req, timeout=max(30, timeout_sec)) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        if fallback_freepik:
            print(f"[media] nanobanana_pro_api http {e.code}, falling back to Freepik")
            out, mode, err = generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
            meta.update({"provider_used": "freepik_mystic", "model_used": "freepik_mystic", "fallback_used": True})
            return out, mode, err, meta
        return None, used_mode, f"Nano Banana Pro HTTP {e.code}: {detail[:800]}", meta
    except URLError as e:
        if fallback_freepik:
            print("[media] nanobanana_pro_api url error, falling back to Freepik")
            out, mode, err = generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
            meta.update({"provider_used": "freepik_mystic", "model_used": "freepik_mystic", "fallback_used": True})
            return out, mode, err, meta
        return None, used_mode, f"Nano Banana Pro URL error: {e}", meta
    except Exception as e:
        if fallback_freepik:
            print("[media] nanobanana_pro_api exception, falling back to Freepik")
            out, mode, err = generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
            meta.update({"provider_used": "freepik_mystic", "model_used": "freepik_mystic", "fallback_used": True})
            return out, mode, err, meta
        return None, used_mode, f"Nano Banana Pro exception: {e}", meta

    candidates = body.get("candidates") or []
    image_bytes: bytes | None = None
    mime_type = "image/png"
    for candidate in candidates:
        content = (candidate or {}).get("content") or {}
        for part in content.get("parts") or []:
            inline = (part or {}).get("inlineData") or {}
            data = str(inline.get("data") or "").strip()
            if not data:
                continue
            mime_type = str(inline.get("mimeType") or mime_type).strip() or mime_type
            try:
                image_bytes = base64.b64decode(data)
                break
            except Exception:
                continue
        if image_bytes:
            break

    if not image_bytes:
        if fallback_freepik:
            print("[media] nanobanana_pro_api no image data, falling back to Freepik")
            out, mode, err = generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
            meta.update({"provider_used": "freepik_mystic", "model_used": "freepik_mystic", "fallback_used": True})
            return out, mode, err, meta
        return None, used_mode, f"Nano Banana Pro response did not include image data: {body}", meta

    suffix = ".png"
    if "jpeg" in mime_type or "jpg" in mime_type:
        suffix = ".jpg"
    elif "webp" in mime_type:
        suffix = ".webp"
    out_path = out_dir / f"nanobanana_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"
    out_path.write_bytes(image_bytes)
    return str(out_path), used_mode, "", meta


def generate_image_with_freepik_mystic(
    post_text: str,
    output_dir: str,
    visual_mode: str = "auto",
    timeout_sec: int = 120,
) -> tuple[str | None, str, str]:
    """
    Freepik Mystic API:
      POST /v1/ai/mystic
      GET  /v1/ai/mystic/{task-id}
    """
    api_key = (os.getenv("FREEPIK_API_KEY") or "").strip()
    if not api_key:
        return None, "freepik_mystic", "FREEPIK_API_KEY is not set"

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"freepik_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    prompt, used_mode = build_morning_image_prompt(post_text, visual_mode=visual_mode)
    payload = json.dumps({"prompt": prompt}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-freepik-api-key": api_key,
    }

    try:
        req = Request("https://api.freepik.com/v1/ai/mystic", data=payload, headers=headers, method="POST")
        with urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        task_id = str(((body or {}).get("data") or {}).get("task_id") or "").strip()
        if not task_id:
            return None, used_mode, f"task_id not found in response: {body}"
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        return None, used_mode, f"Freepik create HTTP {e.code}: {detail[:600]}"
    except URLError as e:
        return None, used_mode, f"Freepik create URL error: {e}"
    except Exception as e:
        return None, used_mode, f"Freepik create exception: {e}"

    deadline = time.time() + max(20, timeout_sec)
    poll_url = f"https://api.freepik.com/v1/ai/mystic/{task_id}"
    last_status = "CREATED"
    while time.time() < deadline:
        try:
            req2 = Request(poll_url, headers=headers, method="GET")
            with urlopen(req2, timeout=30) as resp2:
                data = json.loads(resp2.read().decode("utf-8"))
            item = (data or {}).get("data") or {}
            last_status = str(item.get("status") or "").upper()
            generated = item.get("generated") or []
            if last_status == "COMPLETED" and generated:
                image_url = str(generated[0]).strip()
                if not image_url:
                    return None, used_mode, "Freepik completed but generated URL is empty"
                req_img = Request(image_url, method="GET")
                with urlopen(req_img, timeout=30) as img:
                    out_path.write_bytes(img.read())
                return str(out_path), used_mode, ""
            if last_status in {"FAILED", "CANCELED", "CANCELLED"}:
                return None, used_mode, f"Freepik task failed: {item}"
        except HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")
            return None, used_mode, f"Freepik status HTTP {e.code}: {detail[:600]}"
        except Exception as e:
            return None, used_mode, f"Freepik status exception: {e}"
        time.sleep(3)

    return None, used_mode, f"Freepik task timeout (last_status={last_status})"
