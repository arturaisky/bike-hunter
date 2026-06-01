import json
import os

STORAGE_FILE = "seen_listings.json"


def load_seen() -> set:
    if not os.path.exists(STORAGE_FILE):
        return set()
    with open(STORAGE_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(seen: set) -> None:
    with open(STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f)


def is_new(link: str, seen: set) -> bool:
    return link not in seen


def mark_seen(link: str, seen: set) -> None:
    seen.add(link)
