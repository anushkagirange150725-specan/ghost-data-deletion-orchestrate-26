from __future__ import annotations
import json
import os
import shutil
import subprocess
from .data import DATASET, REPO

CACHE = os.path.join(REPO, "code", "cache", "document_text.json")
DOC_EXT = (".pdf", ".png", ".jpg", ".jpeg")


def pdf_text(path: str) -> str:
    from pypdf import PdfReader
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def image_text(path: str) -> str:
    exe = shutil.which("tesseract")
    if not exe:
        return ""
    run = subprocess.run([exe, path, "-"], capture_output=True, text=True, encoding="utf-8", timeout=180)
    return run.stdout


def document_texts(files: dict) -> dict:
    """file_id -> extracted text for every PDF / image, cached on disk after the first run."""
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as fh:
            cache = json.load(fh)
    out = {}
    for fid, meta in files.items():
        rel = meta["file_path"]
        ext = os.path.splitext(rel)[1].lower()
        if ext not in DOC_EXT:
            continue
        if not cache.get(rel):
            path = os.path.join(DATASET, rel)
            cache[rel] = pdf_text(path) if ext == ".pdf" else image_text(path)
        out[fid] = cache[rel]
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=1, sort_keys=True)
    return out