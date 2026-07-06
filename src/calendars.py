"""Two calendar feeds per spec §6: ocean-missions.ics + lake-sessions.ics.
Window holds (multi-day), stable UIDs so events update in place, cancelled
events prefixed [CANCELLED] rather than deleted."""
import datetime as dt
import hashlib


def _fold(line):
    out = []
    while len(line.encode()) > 73:
        out.append(line[:73])
        line = " " + line[73:]
    out.append(line)
    return "\r\n".join(out)


def _esc(text):
    return (text.replace("\\", "\\\\").replace("\n", "\\n")
            .replace(",", "\\,").replace(";", "\\;"))


def build(events, front, path):
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = "Ocean Missions" if front == "ocean" else "Lake Sessions"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             f"PRODID:-//surf-bud//{front}//EN",
             f"X-WR-CALNAME:{name}", "X-WR-TIMEZONE:America/New_York"]
    for ev in events:
        if ev["front"] != front or ev["state"] in ("PAST",):
            continue
        uid = hashlib.md5(ev["key"].encode()).hexdigest()
        start = ev["first_day"].replace("-", "")
        end = (dt.date.fromisoformat(ev["last_day"])
               + dt.timedelta(days=1)).strftime("%Y%m%d")
        cancelled = ev["state"] == "CANCELLED"
        title = (f"{'[CANCELLED] ' if cancelled else ''}🌊 "
                 f"{ev.get('best_spot', ev['class'])} · "
                 f"{ev.get('grade', '?').upper()} · bust {ev.get('bust', '?')}%")
        desc = ev.get("briefing") or ev.get("summary", "")
        if ev.get("fare_note"):
            desc += "\n\n" + ev["fare_note"]
        lines += ["BEGIN:VEVENT", f"UID:{uid}@surf-bud",
                  f"DTSTAMP:{now}",
                  f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}",
                  _fold(f"SUMMARY:{_esc(title)}"),
                  _fold(f"DESCRIPTION:{_esc(desc)}"),
                  f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    with open(path, "w", newline="") as f:
        f.write("\r\n".join(lines) + "\r\n")
