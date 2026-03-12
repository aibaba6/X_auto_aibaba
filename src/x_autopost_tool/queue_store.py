from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, request

import yaml


def queue_sync_enabled() -> bool:
    return bool(os.getenv("XAP_QUEUE_SYNC_URL")) and bool(os.getenv("XAP_QUEUE_SYNC_TOKEN"))


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
    queue = payload.get("queue", [])
    return queue if isinstance(queue, list) else []


def _remote_save(items: list[dict]) -> None:
    body = json.dumps({"queue": items}, ensure_ascii=False).encode("utf-8")
    req = request.Request(_remote_url(), headers=_remote_headers(), data=body, method="POST")
    with request.urlopen(req, timeout=15) as resp:
        resp.read()


def load_queue_items(queue_path: str | None) -> list[dict]:
    if not queue_sync_enabled():
        return _local_load(queue_path)
    try:
        return _remote_load()
    except error.HTTPError as e:
        print(f"[QUEUE SYNC ERROR] load http={e.code}")
    except Exception as e:
        print(f"[QUEUE SYNC ERROR] load {e}")
    return []


def save_queue_items(queue_path: str | None, items: list[dict]) -> None:
    if not queue_sync_enabled():
        _local_save(queue_path, items)
        return
    try:
        _remote_save(items)
    except error.HTTPError as e:
        print(f"[QUEUE SYNC ERROR] save http={e.code}")
    except Exception as e:
        print(f"[QUEUE SYNC ERROR] save {e}")
