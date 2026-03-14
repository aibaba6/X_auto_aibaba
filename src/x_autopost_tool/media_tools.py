from __future__ import annotations

from datetime import datetime
import base64
import hashlib
import json
from pathlib import Path
import os
import random
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
    # Rotate style by hash + current day so repeated topics still vary over time.
    seed_src = f"{datetime.now().strftime('%Y-%m-%d')}::{post_text[:120]}"
    seed = int(hashlib.sha256(seed_src.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed)
    pool = ["design_case", "diagram", "editorial", "photo"]
    return pool[rng.randrange(0, len(pool))]


def build_morning_image_prompt(post_text: str, visual_mode: str = "auto") -> tuple[str, str]:
    mode = visual_mode if visual_mode in VISUAL_MODES else "auto"
    if mode == "auto":
        mode = _pick_auto_mode(post_text)
    normalized = _normalize_post_text(post_text)

    base = (
        "Create one original visual concept for an X post about practical AI/design work. "
        "The image must match the specific message of the post, not a generic futuristic AI illustration. "
        "Prefer a concrete situation, desk scene, workflow artifact, or visual metaphor directly implied by the post. "
        "Keep the visual simple, polished, and easy to understand at a glance on social media. "
        "No readable text inside the image. "
        "No logo, no emblem, no badge, no watermark, no brand names, no signature. "
        "Avoid robots, glowing brains, random holograms, floating app icons, stock-crypto visuals, and meaningless abstract tech patterns. "
        "Output a single image."
    )

    if mode == "design_case":
        style = (
            "Visual style: design case snapshot. "
            "Show UI mock fragments, spacing studies, layout review artifacts, and tangible design decisions. "
            "Use restrained neutral palette with one accent color. "
            "Prefer simple blocks, surfaces, and review materials over symbolic marks."
        )
    elif mode == "diagram":
        style = (
            "Visual style: conceptual diagram. "
            "Use geometric blocks, arrows, lanes, layers, and hierarchy to explain the exact process or comparison implied by the post. "
            "Keep it minimal and readable without text-heavy labels. "
            "Use neutral primitives, not icon-like symbols."
        )
    elif mode == "editorial":
        style = (
            "Visual style: editorial layout. "
            "Strong composition, abstract forms, magazine-like negative space, "
            "balanced rhythm and contrast, grounded in the post's actual subject. "
            "No monogram-like marks or pseudo logos."
        )
    else:
        style = (
            "Visual style: realistic photo direction. "
            "Professional desk/workspace scene or object arrangement that directly represents the post's main point. "
            "Natural materials, soft shadows, documentary-like realism. "
            "No signage, no brand marks, no printed logos."
        )

    subject = _build_subject_line(normalized)
    action = _build_action_line(normalized)
    scene = _build_scene_direction(normalized, mode)
    constraints = _build_constraint_line(normalized)
    context = f"Post context summary: {normalized[:280]}"
    return f"{base} {style} {subject} {action} {scene} {constraints} {context}", mode


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
) -> tuple[str | None, str, str]:
    api_key = (os.getenv("GOOGLE_API_KEY") or os.getenv("NANOBANANA_API_KEY") or "").strip()
    fallback_freepik = bool((os.getenv("FREEPIK_API_KEY") or "").strip())
    if not api_key:
        if fallback_freepik:
            return generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
        return None, "auto", "GOOGLE_API_KEY is not set"

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt, used_mode = build_morning_image_prompt(post_text, visual_mode=visual_mode)

    model = (os.getenv("NANOBANANA_MODEL") or "gemini-2.0-flash-preview-image-generation").strip()
    base_url = (
        os.getenv("NANOBANANA_API_URL")
        or f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    ).strip()
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    req = Request(
        f"{base_url}?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=max(30, timeout_sec)) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")
        if fallback_freepik:
            print(f"[media] nanobanana_pro_api http {e.code}, falling back to Freepik")
            return generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
        return None, used_mode, f"Nano Banana Pro HTTP {e.code}: {detail[:800]}"
    except URLError as e:
        if fallback_freepik:
            print("[media] nanobanana_pro_api url error, falling back to Freepik")
            return generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
        return None, used_mode, f"Nano Banana Pro URL error: {e}"
    except Exception as e:
        if fallback_freepik:
            print("[media] nanobanana_pro_api exception, falling back to Freepik")
            return generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
        return None, used_mode, f"Nano Banana Pro exception: {e}"

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
            return generate_image_with_freepik_mystic(post_text, output_dir, visual_mode=visual_mode)
        return None, used_mode, f"Nano Banana Pro response did not include image data: {body}"

    suffix = ".png"
    if "jpeg" in mime_type or "jpg" in mime_type:
        suffix = ".jpg"
    elif "webp" in mime_type:
        suffix = ".webp"
    out_path = out_dir / f"nanobanana_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}"
    out_path.write_bytes(image_bytes)
    return str(out_path), used_mode, ""


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
