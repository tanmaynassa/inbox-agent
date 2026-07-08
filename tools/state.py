"""
Persistent state for the inbox agent - tracks which emails have already
been classified (so frequent polling doesn't reprocess/re-notify about the
same email) and stores today's decisions for the daily summary to read.

Simple JSON file, one entry per day - fine at personal-inbox volume,
no real database needed for this.
"""
import json
import os
from datetime import datetime

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")


def _today_path(date_str: str = None) -> str:
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    os.makedirs(STATE_DIR, exist_ok=True)
    return os.path.join(STATE_DIR, f"{date_str}.json")


def get_processed_ids(date_str: str = None) -> set:
    path = _today_path(date_str)
    if not os.path.exists(path):
        return set()
    with open(path, "r") as f:
        entries = json.load(f)
    return {e["id"] for e in entries}


def mark_processed(entry: dict, date_str: str = None):
    """entry: {id, subject, sender, action, reason, timestamp}"""
    path = _today_path(date_str)
    entries = []
    if os.path.exists(path):
        with open(path, "r") as f:
            entries = json.load(f)
    entries.append(entry)
    with open(path, "w") as f:
        json.dump(entries, f, indent=2)


def get_todays_entries(date_str: str = None) -> list:
    path = _today_path(date_str)
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)
