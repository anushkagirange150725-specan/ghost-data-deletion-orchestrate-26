from __future__ import annotations
import csv
import os
from datetime import datetime, timezone

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATASET = os.path.join(REPO, "dataset")


def ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value.strip(), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def load(name: str) -> list[dict]:
    with open(os.path.join(DATASET, name), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))