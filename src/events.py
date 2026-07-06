"""Event state machine per spec §2.
WHISPER -> HEADS_UP -> CONFIRMED -> (UPGRADED|DOWNGRADED|CANCELLED) -> PAST
Events persist in state/events.json; every transition appends to
state/events.log for spot memory."""
import datetime as dt
import json
import os

STATES = ["WHISPER", "HEADS_UP", "CONFIRMED", "UPGRADED", "DOWNGRADED",
          "CANCELLED", "PAST"]
EVENTS_FILE = "state/events.json"
LOG_FILE = "state/events.log"


def load():
    try:
        with open(EVENTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(events):
    os.makedirs("state", exist_ok=True)
    with open(EVENTS_FILE, "w") as f:
        json.dump(events, f, indent=1, sort_keys=True)


def log(line):
    os.makedirs("state", exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(LOG_FILE, "a") as f:
        f.write(f"{stamp}  {line}\n")


def stage_for(lead_days, horizons):
    """Map days-until-arrival onto whisper/heads_up/confirmed thresholds."""
    whisper, heads, confirmed = horizons
    if lead_days <= confirmed:
        return "CONFIRMED"
    if lead_days <= heads:
        return "HEADS_UP"
    if whisper and lead_days <= whisper:
        return "WHISPER"
    return None


def upsert(events, key, cls, front, first_day, last_day, payload, horizons):
    """Create or advance an event. Returns (event, transition) where
    transition is None or one of NEW/ADVANCE/UPGRADE/DOWNGRADE/CANCEL."""
    today = dt.date.today()
    lead = (dt.date.fromisoformat(first_day) - today).days
    target = stage_for(lead, horizons)
    ev = events.get(key)

    if ev is None:
        if target is None:
            return None, None
        ev = {"key": key, "class": cls, "front": front, "state": target,
              "first_day": first_day, "last_day": last_day,
              "created": today.isoformat(), **payload}
        events[key] = ev
        log(f"NEW {target} {key} grade={payload.get('grade')} "
            f"bust={payload.get('bust')}%")
        return ev, "NEW"

    prev_grade = ev.get("grade")
    order = {"poor": 0, "fair": 1, "good": 2, "epic": 3}
    ev.update(payload)
    ev["first_day"], ev["last_day"] = first_day, last_day
    transition = None

    if payload.get("grade") == "poor" and ev["state"] in ("HEADS_UP", "CONFIRMED"):
        ev["state"] = "CANCELLED"
        transition = "CANCEL"
    elif target and STATES.index(target) > STATES.index(ev["state"]) \
            and ev["state"] in ("WHISPER", "HEADS_UP"):
        ev["state"] = target
        transition = "ADVANCE"
    elif prev_grade and payload.get("grade") and \
            order[payload["grade"]] > order[prev_grade]:
        transition = "UPGRADE"
    elif prev_grade and payload.get("grade") and \
            order[payload["grade"]] < order[prev_grade]:
        transition = "DOWNGRADE"

    if transition:
        log(f"{transition} {ev['state']} {key} grade={payload.get('grade')} "
            f"bust={payload.get('bust')}%")
    return ev, transition


def sweep_past(events):
    """Move finished events to PAST."""
    today = dt.date.today().isoformat()
    for ev in events.values():
        if ev["state"] not in ("PAST", "CANCELLED") and ev["last_day"] < today:
            ev["state"] = "PAST"
            log(f"PAST {ev['key']}")


def active(events):
    return [e for e in events.values()
            if e["state"] in ("WHISPER", "HEADS_UP", "CONFIRMED",
                              "UPGRADED", "DOWNGRADED")]
