"""AI briefing layer per spec §5: rules detect, Claude writes the briefing.
Runs without an API key (falls back to templated summary)."""
import json
import os

import requests

API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"

SYSTEM = """You write surf mission briefings for P.W., an Ithaca NY based
longboarder/midlength rider. Voice: direct, warm, zero hype, honest about
uncertainty. Given structured event data, spot notes, and rider context,
write a briefing with: the synoptic story in plain language (why this swell
exists), the call (which spot, which days, expected conditions), the hedge
(what could bust it, reference the bust %), and the mission plan (leave-by
time from Ithaca for the drive hours given, sleep suggestion, session timing
around daylight, one food stop idea if you know the area). Under 180 words.
No markdown headers, no bullet lists. Prose."""


def write_briefing(event_json, spot_notes, profile_note=""):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(API, timeout=60, headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": MODEL, "max_tokens": 400,
            "system": SYSTEM,
            "messages": [{"role": "user", "content":
                f"EVENT:\n{json.dumps(event_json, indent=1)}\n\n"
                f"SPOT NOTES:\n{spot_notes}\n\n{profile_note}"}],
        })
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])
    except Exception as e:
        print(f"[warn] briefing failed: {e}")
        return None
