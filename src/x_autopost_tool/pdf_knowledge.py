from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("XAP_DATA_DIR", str(PROJECT_ROOT))).resolve()
PDF_STORE_DIR = DATA_ROOT / "pdf_library"
PDF_INDEX_PATH = PDF_STORE_DIR / "index.json"


def _ensure_store() -> None:
    PDF_STORE_DIR.mkdir(parents=True, exist_ok=True)


def _clean_text(text: str) -> str:
    t = (text or "").replace("\x00", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def load_pdf_index() -> list[dict]:
    _ensure_store()
    if not PDF_INDEX_PATH.exists():
        return []
    try:
        data = json.loads(PDF_INDEX_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            upgraded: list[dict] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                if "priority" not in item:
                    item["priority"] = 3
                if "scope" not in item:
                    item["scope"] = "all"
                upgraded.append(item)
            return upgraded
    except Exception:
        pass
    return []


def save_pdf_index(index: list[dict]) -> None:
    _ensure_store()
    PDF_INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def ingest_pdf_bytes(content: bytes, original_name: str) -> dict:
    try:
        from pypdf import PdfReader
    except Exception:
        raise RuntimeError("pypdf が未インストールです。`pip install -r requirements.txt` を実行してください。")

    _ensure_store()
    doc_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]
    pdf_name = f"{doc_id}.pdf"
    txt_name = f"{doc_id}.txt"
    pdf_path = PDF_STORE_DIR / pdf_name
    txt_path = PDF_STORE_DIR / txt_name

    pdf_path.write_bytes(content)

    reader = PdfReader(str(pdf_path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    raw_text = "\n\n".join(pages)
    cleaned = _clean_text(raw_text)
    txt_path.write_text(cleaned, encoding="utf-8")

    excerpt = cleaned[:220].replace("\n", " ")
    item = {
        "id": doc_id,
        "original_name": original_name or "uploaded.pdf",
        "pdf_file": pdf_name,
        "txt_file": txt_name,
        "pages": len(reader.pages),
        "char_count": len(cleaned),
        "excerpt": excerpt,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "priority": 3,
        "scope": "all",
    }
    index = load_pdf_index()
    index.insert(0, item)
    save_pdf_index(index)
    return item


def delete_pdf_doc(doc_id: str) -> bool:
    index = load_pdf_index()
    kept: list[dict] = []
    target: dict | None = None
    for item in index:
        if str(item.get("id")) == doc_id and target is None:
            target = item
        else:
            kept.append(item)
    if target is None:
        return False

    for key in ("pdf_file", "txt_file"):
        name = str(target.get(key) or "").strip()
        if not name:
            continue
        p = (PDF_STORE_DIR / name).resolve()
        if PDF_STORE_DIR.resolve() in p.parents and p.exists():
            p.unlink()

    save_pdf_index(kept)
    return True


def update_pdf_doc_settings(doc_id: str, priority: int, scope: str) -> dict | None:
    scope = (scope or "").strip().lower()
    if scope not in {"all", "morning"}:
        scope = "all"
    p = max(1, min(5, int(priority)))

    index = load_pdf_index()
    updated: dict | None = None
    for item in index:
        if str(item.get("id")) == doc_id:
            item["priority"] = p
            item["scope"] = scope
            updated = item
            break
    if updated is None:
        return None
    save_pdf_index(index)
    return updated


def get_pdf_knowledge_snippets(
    max_docs: int = 3,
    max_chars_per_doc: int = 700,
    slot_name: str = "morning",
) -> list[str]:
    slot = (slot_name or "morning").strip().lower()
    index = load_pdf_index()
    eligible: list[dict] = []
    for item in index:
        scope = str(item.get("scope") or "all").strip().lower()
        if scope == "all" or (scope == "morning" and slot == "morning"):
            eligible.append(item)

    eligible.sort(
        key=lambda x: (
            int(x.get("priority", 3)),
            str(x.get("uploaded_at") or ""),
        ),
        reverse=True,
    )
    eligible = eligible[: max(0, max_docs)]

    out: list[str] = []
    for item in eligible:
        txt_file = str(item.get("txt_file") or "").strip()
        if not txt_file:
            continue
        txt_path = PDF_STORE_DIR / txt_file
        if not txt_path.exists():
            continue
        text = _clean_text(txt_path.read_text(encoding="utf-8"))
        if not text:
            continue
        snippet = text[: max(120, max_chars_per_doc)]
        title = str(item.get("original_name") or "PDF")
        scope = str(item.get("scope") or "all")
        prio = int(item.get("priority", 3))
        out.append(f"[{title} | priority={prio} | scope={scope}] {snippet}")
    return out
