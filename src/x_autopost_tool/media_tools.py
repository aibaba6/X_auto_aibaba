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

    keywords = _extract_keywords(post_text, limit=5)
    keyword_line = ", ".join(keywords) if keywords else "design, UI, clarity"

    base = (
        "Create one original visual concept for an X post about AI/design practice. "
        "Keep the visual minimal and clean, with low element count and clear whitespace. "
        "Do not render readable text. "
        "No logo, no emblem, no badge, no icon mark, no watermark, no brand names, no signature. "
        "Avoid unexplained symbols or decorative marks that add noise. "
        "High quality composition, clear focal point, natural lighting, modern art direction. "
        "Output a single image."
    )

    if mode == "design_case":
        style = (
            "Visual style: design case snapshot. "
            "Show UI mock fragments, spacing guides, and before/after contrast blocks. "
            "Use restrained neutral palette with one accent color. "
            "Prefer simple blocks and spacing over symbolic marks."
        )
    elif mode == "diagram":
        style = (
            "Visual style: conceptual diagram. "
            "Use geometric blocks, arrows, layers, and hierarchy to explain relationships. "
            "Keep it minimal and readable without text-heavy labels. "
            "Use neutral primitives, not icon-like symbols."
        )
    elif mode == "editorial":
        style = (
            "Visual style: editorial layout. "
            "Strong composition, abstract forms, magazine-like negative space, "
            "balanced rhythm and contrast. "
            "No monogram-like marks or pseudo logos."
        )
    else:
        style = (
            "Visual style: realistic photo direction. "
            "Professional desk/workspace scene or product-like close-up that symbolizes the topic. "
            "Natural material, soft shadows, documentary-like realism. "
            "No signage, no brand marks, no printed logos."
        )

    context = (
        f"Topic keywords: {keyword_line}. "
        f"Post context summary: {post_text[:280]}"
    )
    return f"{base} {style} {context}", mode


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
