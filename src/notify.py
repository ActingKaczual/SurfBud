"""Notify layer per spec §4: pluggable channel (ntfy now, Twilio later),
2/day cap, quiet hours 9pm-7am with overnight queue."""
import datetime as dt
import json
import os

import requests

SENT_FILE = "state/sent.json"


def _state():
    try:
        with open(SENT_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sent": [], "queue": []}


def _save(s):
    os.makedirs("state", exist_ok=True)
    with open(SENT_FILE, "w") as f:
        json.dump(s, f, indent=1)


def _send_ntfy(title, body, click=None):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print(f"[dry-run push] {title}: {body[:80]}")
        return
    # HTTP headers are latin-1 only; strip emoji from the title.
    safe_title = title.encode("latin-1", "ignore").decode("latin-1").strip()
    headers = {"Title": safe_title or "Surf Bud",
               "Priority": "high", "Tags": "ocean"}
    if click:
        headers["Click"] = click.encode("latin-1", "ignore").decode("latin-1")
    requests.post(f"https://ntfy.sh/{topic}",
                  data=body.encode("utf-8"), headers=headers, timeout=30)

# Twilio swap point: implement _send_sms(title, body) and change SEND below.
SEND = _send_ntfy


def push(title, body, click=None, cfg=None):
    """Push respecting quiet hours and daily cap; queue what can't go now."""
    cfg = cfg or {"max_pushes_per_day": 2, "quiet_hours": [21, 7]}
    s = _state()
    now = dt.datetime.now()
    today = now.strftime("%Y-%m-%d")
    q_start, q_end = cfg["quiet_hours"]
    in_quiet = now.hour >= q_start or now.hour < q_end
    sent_today = sum(1 for x in s["sent"] if x["day"] == today)

    if in_quiet:
        s["queue"].append({"title": title, "body": body, "click": click})
        _save(s)
        print(f"[queued: quiet hours] {title}")
        return False
    if sent_today >= cfg["max_pushes_per_day"]:
        s["queue"].append({"title": title, "body": body, "click": click})
        _save(s)
        print(f"[queued: daily cap] {title}")
        return False

    SEND(title, body, click)
    s["sent"].append({"day": today, "title": title,
                      "at": now.strftime("%H:%M")})
    s["sent"] = s["sent"][-60:]
    _save(s)
    return True


def flush_queue(cfg):
    """Called at the start of each run: drain queued pushes within caps."""
    s = _state()
    queue, s["queue"] = s["queue"], []
    _save(s)
    for item in queue:
        push(item["title"], item["body"], item.get("click"), cfg)
