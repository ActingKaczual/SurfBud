"""Plain-language rendering for alerts and digests. ASCII-safe titles."""
import datetime as dt


def band(h_m):
    """Meters -> surfer height band + ft range."""
    if h_m is None:
        return "unknown size"
    ft = h_m * 3.28
    for top, name in [(0.45, "knee-high"), (0.75, "waist-high"),
                      (1.05, "chest-high"), (1.45, "head-high"),
                      (1.95, "overhead"), (99, "well overhead")]:
        if h_m <= top:
            lo, hi = int(ft), int(ft) + 1
            return f"{name} ({max(1, lo)}-{hi} ft)"
    return f"{ft:.0f} ft"


def day_range(first, last):
    """'Sat Jul 11' or 'Sat-Mon, Jul 11-13'."""
    a = dt.date.fromisoformat(first)
    b = dt.date.fromisoformat(last)
    if a == b:
        return a.strftime("%a %b %-d")
    if a.month == b.month:
        return f"{a.strftime('%a')}-{b.strftime('%a')}, {a.strftime('%b %-d')}-{b.day}"
    return f"{a.strftime('%a %b %-d')} - {b.strftime('%a %b %-d')}"


def days_short(first, last):
    a = dt.date.fromisoformat(first)
    b = dt.date.fromisoformat(last)
    return a.strftime("%a") if a == b else f"{a.strftime('%a')}-{b.strftime('%a')}"


def bust_phrase(bust):
    if bust is None:
        return "odds unknown"
    if bust < 20:
        return f"solid bet ({bust}% bust)"
    if bust < 40:
        return f"likely holds ({bust}% bust)"
    if bust < 60:
        return f"coin flip ({bust}% bust)"
    if bust < 80:
        return f"long shot ({bust}% bust)"
    return f"probably fizzles ({bust}% bust)"


# ── Alert lexicon: edit freely, (state, grade) -> prefix ──────────
PREFIXES = {
    ("CONFIRMED", "epic"): "Drop everything",
    ("CONFIRMED", "good"): "It's on",
    ("CONFIRMED", "fair"): "Worth a look",
    ("HEADS_UP", "epic"): "Big one brewing",
    ("HEADS_UP", "good"): "Brewing",
    ("HEADS_UP", "fair"): "Early whisper",
    ("CANCELLED", None): "Called off",
    ("WHISPER", None): "On the radar",
}


# Mission-type signifiers shown before the spot name; edit freely.
TAGS = {
    "lake": "[LAKE]",
    "fly": "[FLY]",
    "fly_or_drive": "[FLY OK]",
}


def mission_tag(ev):
    if ev.get("front") == "lake":
        return TAGS["lake"]
    return TAGS.get(ev.get("travel"), "")


def state_prefix(state, grade=None):
    return (PREFIXES.get((state, grade))
            or PREFIXES.get((state, None))
            or PREFIXES.get((state, "good"))
            or state)


def spot_short(name):
    """'Rockaway Beach (90th St peaks)' -> 'Rockaway'."""
    return name.split("(")[0].split(",")[0].strip()


def ascii_safe(s):
    """Pure ASCII for HTTP headers; ntfy reads them as UTF-8."""
    return s.encode("ascii", "ignore").decode("ascii").strip()


def date_nums(first, last):
    import datetime as _dt
    a = _dt.date.fromisoformat(first); b = _dt.date.fromisoformat(last)
    fa = f"{a.month}/{a.day}"
    return fa if a == b else f"{fa}-{b.month}/{b.day}"


def _wind_line(ev):
    lab = ev.get("wind_label") or "wind"
    lo, hi = ev.get("wind_lo"), ev.get("wind_hi")
    if lo is None:
        return f"{lab.capitalize()} wind."
    rng = f"{lo:.0f}mph" if hi is None or abs(hi - lo) < 1 else f"{lo:.0f}-{hi:.0f}mph"
    return f"{lab.capitalize()} wind ({rng})."


def _fare_short(ev):
    if not ev.get("fare_note"):
        return None
    part = ev["fare_note"].split("  ")[0]          # "Fare: $284 from ITH"
    return part.replace("Fare: ", "")


def _drive_short(ev):
    dh, dm = ev.get("drive_hours"), ev.get("drive_miles")
    if not dh:
        return None
    mi = f" ({dm}mi)" if dm else ""
    return f"{dh:g}hr drive{mi}"


def _travel_line(ev):
    fare, drive = _fare_short(ev), _drive_short(ev)
    travel = ev.get("travel")
    if travel == "fly":
        return f"Fly: {fare}." if fare else "Fly mission, fares pending."
    if travel == "fly_or_drive":
        if fare and drive:
            return f"{drive} or fly: {fare}."
        return f"{drive}." if drive else (f"Fly: {fare}." if fare else "")
    return f"{drive}." if drive else ""


def title(ev):
    reg = f" ({ev['region']})" if ev.get("region") else ""
    tag = mission_tag(ev)
    tag = tag + " " if tag else ""
    return ascii_safe(
        f"{state_prefix(ev['state'], ev.get('grade'))}: "
        f"{tag}{spot_short(ev['best_spot'])}{reg} "
        f"{days_short(ev['first_day'], ev['last_day'])} "
        f"({date_nums(ev['first_day'], ev['last_day'])})")


def body(ev):
    parts = [f"{ev.get('fit', '?')}% go, {ev.get('bust', '?')}% bust.",
             f"{band(ev.get('h_m')).capitalize()}." if ev.get('h_m') else "",
             _wind_line(ev),
             f"Window {ev['tod_window']}." if ev.get("tod_window") else "",
             _travel_line(ev)]
    if ev["state"] == "HEADS_UP":
        parts.append("Speculative; will confirm or call off.")
    parts.append("Tap for digest.")
    return " ".join(p for p in parts if p)
