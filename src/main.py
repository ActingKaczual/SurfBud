"""SURF BUD orchestrator. Two engines, event-first, per the spec."""
import datetime as dt
import json
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(__file__))
import sources, scoring, events as ev_store, notify, calendars, briefing, fares  # noqa


def _windows(day_grades, min_grade="fair"):
    """Group consecutive days at min_grade+ into windows.
    Returns [(first_day, last_day, [days])]."""
    order = {"poor": 0, "fair": 1, "good": 2, "epic": 3}
    good = sorted(d for d, g in day_grades.items()
                  if order[g] >= order[min_grade])
    wins, cur = [], []
    for d in good:
        if cur and (dt.date.fromisoformat(d)
                    - dt.date.fromisoformat(cur[-1])).days > 1:
            wins.append(cur)
            cur = []
        cur.append(d)
    if cur:
        wins.append(cur)
    return [(w[0], w[-1], w) for w in wins]


def _classify(first_day, stats, tropical_active):
    lead = (dt.date.fromisoformat(first_day) - dt.date.today()).days
    p = max((s["p_mean"] for s in stats), default=0)
    if tropical_active and p >= 11:
        return "tropical"
    if p >= 12:
        return "winter_groundswell"
    if p >= 9:
        return "noreaster"
    return "windswell"


def ocean_engine(cfg, spots, store, tropical):
    profile = cfg["profile"]
    weights = cfg["weights"]
    transitions = []
    for spot in [s for s in spots if s["front"] == "ocean"]:
        try:
            marine = sources.marine_point(spot["lat"], spot["lon"])
            wind = sources.wind_point(spot["lat"], spot["lon"])
        except Exception as e:
            print(f"[warn] {spot['name']}: {e}")
            continue
        days = scoring.day_stats(marine, wind, spot.get("swell_window_deg"))
        grades = {d: scoring.grade_day(s, profile, spot.get("best_wind_deg"))
                  for d, s in days.items()}
        for first, last, win_days in _windows(grades, "fair"):
            lead = (dt.date.fromisoformat(first) - dt.date.today()).days
            if lead < 0:
                continue
            stats = [days[d] for d in win_days]
            cls = _classify(first, stats, bool(tropical))
            best_grade = max((grades[d] for d in win_days),
                             key=lambda g: ["poor", "fair", "good", "epic"].index(g))
            bust = scoring.bust_pct(stats, lead)
            fit = scoring.fit_pct(stats, profile)
            clean_frac = sum(1 for s in stats
                             if s["wind_med"] <= profile["wind_clean_max_mph"]) / len(stats)
            raw, ta = scoring.composite(
                weights, 1 - bust / 100, len(win_days), clean_frac,
                fit / 100, spot.get("drive_hours"))
            payload = {
                "grade": best_grade, "bust": bust, "fit": fit,
                "score_raw": raw, "score_travel_adj": ta,
                "best_spot": spot["name"],
                "summary": (f"{spot['name']} · {first} to {last} · "
                            f"{best_grade.upper()} · fit {fit}% · bust {bust}% · "
                            f"{stats[0]['h_mean']:.1f}m @ {stats[0]['p_mean']:.0f}s"),
                "travel": spot.get("travel"),
                "dest_airport": spot.get("dest_airport"),
                "spot_notes": spot.get("notes", ""),
                "drive_hours": spot.get("drive_hours"),
            }
            key = f"ocean:{spot['name']}:{first}"
            horizons = cfg["event_classes"][cls]["horizons"]
            ev, transition = ev_store.upsert(store, key, cls, "ocean",
                                             first, last, payload, horizons)
            if transition:
                transitions.append((ev, transition))
    return transitions


def lake_engine(cfg, spots, store):
    rules = cfg["lake_rules"]
    transitions = []
    for pt in cfg["lake_grid"]:
        try:
            wind = sources.wind_point(pt["lat"], pt["lon"], days=5)
        except Exception as e:
            print(f"[warn] lake {pt['name']}: {e}")
            continue
        by_day = {}
        for t, spd, wdir in wind:
            hour = int(t[11:13])
            if hour not in scoring.DAYLIGHT or spd is None:
                continue
            if spd >= rules["min_wind_mph"] and \
                    scoring.in_arc(wdir, rules["wind_dir_deg"]):
                by_day.setdefault(t[:10], []).append(spd)
        grades = {}
        for d, hrs in by_day.items():
            if len(hrs) >= rules["min_sustained_hours"]:
                grades[d] = "good" if max(hrs) >= rules["min_wind_mph"] + 7 \
                    else "fair"
        for first, last, win_days in _windows(grades, "fair"):
            lead = (dt.date.fromisoformat(first) - dt.date.today()).days
            if lead < 0:
                continue
            best = max((grades[d] for d in win_days),
                       key=lambda g: ["poor", "fair", "good", "epic"].index(g))
            bust = min(90, 20 + lead * 12)   # lake wind: short-lead only
            payload = {
                "grade": best, "bust": bust, "fit": 60,
                "best_spot": f"Lake Ontario · {pt['name']}",
                "summary": (f"Lake wind event · {pt['name']} · {first} to "
                            f"{last} · {best.upper()} · bust {bust}%"),
                "travel": "drive", "spot_notes": "east end wind event",
            }
            key = f"lake:{pt['name']}:{first}"
            horizons = cfg["event_classes"]["lake_wind"]["horizons"]
            ev, transition = ev_store.upsert(store, key, "lake_wind", "lake",
                                             first, last, payload, horizons)
            if transition:
                transitions.append((ev, transition))
    return transitions


def alert_policy(cfg, ev, transition):
    """Spec §4: what deserves a push vs digest-only."""
    if ev["front"] == "lake":
        gate = cfg["alerts"]["lake_push_min_grade"]
        order = {"poor": 0, "fair": 1, "good": 2, "epic": 3}
        if order[ev["grade"]] < order[gate]:
            return False
    if transition == "NEW" and ev["state"] == "WHISPER":
        return False                      # whispers: dashboard/outlook only
    if transition in ("NEW", "ADVANCE") and ev["state"] in ("HEADS_UP",
                                                            "CONFIRMED"):
        return True
    if transition == "CANCEL":
        return True                       # cancels change the go/no-go
    return False                          # up/downgrades -> calendar/digest


def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    with open("spots.yaml") as f:
        spots = yaml.safe_load(f)["spots"]

    notify.flush_queue(cfg["alerts"])
    store = ev_store.load()
    tropical = sources.tropical_storms()
    if tropical:
        names = ", ".join(s.get("name", "?") for s in tropical)
        print(f"[tropical] active: {names}")

    transitions = ocean_engine(cfg, spots, store, tropical)
    transitions += lake_engine(cfg, spots, store)
    ev_store.sweep_past(store)

    for ev, tr in transitions:
        stage = ev["state"]
        if stage == "CONFIRMED" and ev.get("travel") in ("fly", "fly_or_drive") \
                and cfg["fares"]["enabled"] and ev.get("dest_airport"):
            f = fares.snapshot(cfg["fares"], ev["dest_airport"],
                               ev["first_day"], ev["last_day"])
            ev["fare_note"] = f"Fare: {f['note']}  {f['link']}"
        if stage in ("HEADS_UP", "CONFIRMED") and not ev.get("briefing"):
            ev["briefing"] = briefing.write_briefing(
                {k: ev[k] for k in ("class", "state", "first_day", "last_day",
                                    "grade", "fit", "bust", "best_spot",
                                    "summary", "drive_hours") if k in ev},
                ev.get("spot_notes", ""))
        if alert_policy(cfg, ev, tr):
            label = {"HEADS_UP": "HEADS UP", "CONFIRMED": "CONFIRMED",
                     "CANCELLED": "CANCELLED"}.get(stage, stage)
            title = f"🌊 {label} · {ev['best_spot']}"
            body = ev["summary"]
            if ev.get("state") == "HEADS_UP":
                body += "\n(speculative, will confirm or cancel)"
            click = None
            if ev.get("fare_note"):
                click = ev["fare_note"].split()[-1]
            notify.push(title, body, click, cfg["alerts"])

    # Weekly outlook: Sunday, only when something's brewing (spec §4)
    now = dt.datetime.now()
    if now.strftime("%A") == cfg["alerts"]["outlook_day"] and now.hour < 12:
        act = ev_store.active(store)
        if act:
            lines = [e["summary"] for e in
                     sorted(act, key=lambda e: e["first_day"])][:6]
            notify.push("🌊 Week ahead · both fronts",
                        "\n".join(lines), None, cfg["alerts"])

    calendars.build(list(store.values()), "ocean", "ocean-missions.ics")
    calendars.build(list(store.values()), "lake", "lake-sessions.ics")

    # Dashboard state (Phase 2 reads this; harmless to publish now)
    with open("state/dashboard.json", "w") as f:
        json.dump({"updated": now.isoformat(timespec="minutes"),
                   "active": ev_store.active(store),
                   "tropical": [s.get("name") for s in tropical]}, f, indent=1)

    ev_store.save(store)
    print(f"Run complete. {len(ev_store.active(store))} active events.")


if __name__ == "__main__":
    main()
