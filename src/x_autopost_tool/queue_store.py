from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, request

import yaml


def _item_debug_line(item: dict) -> str:
    if not isinstance(item, dict):
        return "invalid-item"
    return (
        f"id={str(item.get('id', '')).strip() or '-'} "
        f"slot={str(item.get('slot', '')).strip() or '-'} "
        f"schedule_at={str(item.get('schedule_at', '')).strip() or '-'} "
        f"status={str(item.get('status', '')).strip() or '-'} "
        f"posted={'yes' if item.get('posted') else 'no'}"
    )


def _log_queue_items(prefix: str, items: list[dict], limit: int = 8) -> None:
    print(f"{prefix} count={len(items)}")
    for item in items[:limit]:
        print(f"[QUEUE SYNC ITEM] {_item_debug_line(item)}")
    if len(items) > limit:
        print(f"{prefix} truncated={len(items) - limit}")


def _mask_env(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return "missing"
    if len(raw) <= 10:
        return f"len={len(raw)}:{raw[:2]}...{raw[-2:]}"
    return f"len={len(raw)}:{raw[:6]}...{raw[-4:]}"


def queue_sync_enabled() -> bool:
    url = os.getenv("XAP_QUEUE_SYNC_URL", "").strip()
    token = os.getenv("XAP_QUEUE_SYNC_TOKEN", "").strip()
    enabled = bool(url) and bool(token)
    print(
        "[QUEUE SYNC DEBUG] "
        f"enabled={'yes' if enabled else 'no'} "
        f"url={_mask_env(url)} "
        f"token={_mask_env(token)}"
    )
    return enabled


def _local_load(queue_path: str | None) -> list[dict]:
    if not queue_path:
        return []
    path = Path(queue_path)
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _local_save(queue_path: str | None, items: list[dict]) -> None:
    if not queue_path:
        return
    path = Path(queue_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(items, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _remote_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.getenv('XAP_QUEUE_SYNC_TOKEN', '').strip()}",
        "Content-Type": "application/json",
    }


def _remote_url() -> str:
    return os.getenv("XAP_QUEUE_SYNC_URL", "").strip()


def _remote_load() -> list[dict]:
    req = request.Request(_remote_url(), headers=_remote_headers(), method="GET")
    with request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict):
        print(
            "[QUEUE SYNC LOAD] "
            f"ok keys={','.join(sorted(payload.keys()))} "
            f"queue_type={type(payload.get('queue')).__name__}"
        )
    queue = payload.get("queue", [])
    if isinstance(queue, list):
        _log_queue_items("[QUEUE SYNC LOAD]", queue)
    return queue if isinstance(queue, list) else []


def _remote_save(items: list[dict]) -> None:
    body = json.dumps({"queue": items}, ensure_ascii=False).encode("utf-8")
    req = request.Request(_remote_url(), headers=_remote_headers(), data=body, method="POST")
    with request.urlopen(req, timeout=15) as resp:
        resp.read()


def load_queue_items(queue_path: str | None) -> list[dict]:
    if not queue_sync_enabled():
        items = _local_load(queue_path)
        _log_queue_items("[QUEUE LOCAL LOAD]", items)
        return items
    try:
        return _remote_load()
    except error.HTTPError as e:
        print(f"[QUEUE SYNC ERROR] load http={e.code}")
    except Exception as e:
        print(f"[QUEUE SYNC ERROR] load {e}")
    fallback = _local_load(queue_path)
    print(f"[QUEUE SYNC FALLBACK] used=yes local_count={len(fallback)}")
    if fallback:
        _log_queue_items("[QUEUE SYNC FALLBACK]", fallback)
    return fallback


def save_queue_items(queue_path: str | None, items: list[dict]) -> None:
    if not queue_sync_enabled():
        _log_queue_items("[QUEUE LOCAL SAVE]", items)
        _local_save(queue_path, items)
        return
    try:
        _remote_save(items)
        _log_queue_items("[QUEUE SYNC SAVE]", items)
    except error.HTTPError as e:
        print(f"[QUEUE SYNC ERROR] save http={e.code}")
    except Exception as e:
        print(f"[QUEUE SYNC ERROR] save {e}")
    _local_save(queue_path, items)
