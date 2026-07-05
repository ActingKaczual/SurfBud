"""Scoring: grade, fit %, bust %, weighted composite per spec §3."""
import datetime as dt

GRADES = ["poor", "fair", "good", "epic"]
DAYLIGHT = range(6, 19)


def in_arc(deg, arc):
    if deg is None or arc is None:
        return True
    start, end = arc
    deg %= 360
    return start <= deg <= end if start <= end else deg >= start or deg <= end


def day_stats(model_series, wind_series, swell_arc):
    """Collapse hourly dual-model data into per-day stats.
    Returns {date: {h_mean, h_spread, p_mean, p_spread, wind_med, wind_dir,
                    dir_ok_frac}} using daylight hours only."""
    wind = {t: (s, d) for t, s, d in wind_series}
    days = {}
    per_hour = {}  # iso_hour -> list[(h, p, d)] across models
    for series in model_series.values():
        for t, h, p, d in series:
            if h is None or int(t[11:13]) not in DAYLIGHT:
                continue
            per_hour.setdefault(t, []).append((h, p or 0, d))
    for t, vals in per_hour.items():
        date = t[:10]
        hs = [v[0] for v in vals]
        ps = [v[1] for v in vals]
        dir_ok = sum(1 for v in vals if in_arc(v[2], swell_arc)) / len(vals)
        w = wind.get(t, (None, None))
        days.setdefault(date, []).append({
            "h": sum(hs) / len(hs), "h_spread": max(hs) - min(hs),
            "p": sum(ps) / len(ps), "p_spread": max(ps) - min(ps),
            "wind": w[0], "wind_dir": w[1], "dir_ok": dir_ok,
        })
    out = {}
    for date, hours in days.items():
        n = len(hours)
        out[date] = {
            "h_mean": sum(x["h"] for x in hours) / n,
            "h_spread": sum(x["h_spread"] for x in hours) / n,
            "p_mean": sum(x["p"] for x in hours) / n,
            "p_spread": sum(x["p_spread"] for x in hours) / n,
            "wind_med": sorted((x["wind"] or 0) for x in hours)[n // 2],
            "wind_dir": hours[n // 2]["wind_dir"],
            "dir_ok_frac": sum(x["dir_ok"] for x in hours) / n,
            "hours": n,
        }
    return out


def grade_day(st, profile, best_wind_arc):
    """poor/fair/good/epic for one day at one spot."""
    h, p = st["h_mean"], st["p_mean"]
    lo, hi = profile["size_sweet_m"]
    olo, ohi = profile["size_ok_m"]
    if h < olo * 0.7 or st["dir_ok_frac"] < 0.3:
        return "poor"
    size_pts = 2 if lo <= h <= hi else (1 if olo <= h <= ohi else 0)
    period_pts = 2 if p >= profile["min_period_pref_s"] + 3 else \
                 (1 if p >= profile["min_period_pref_s"] else 0)
    wind_clean = st["wind_med"] is not None and (
        st["wind_med"] <= profile["wind_clean_max_mph"]
        or in_arc(st["wind_dir"], best_wind_arc))
    wind_ok = st["wind_med"] is None or st["wind_med"] <= profile["wind_ok_max_mph"]
    wind_pts = 2 if wind_clean else (1 if wind_ok else 0)
    total = size_pts + period_pts + wind_pts
    if total >= 6:
        return "epic"
    if total >= 4:
        return "good"
    if total >= 2:
        return "fair"
    return "poor"


def bust_pct(stats_list, lead_days):
    """Model disagreement + lead-time decay -> 5..95 %."""
    if not stats_list:
        return 90
    h_sp = sum(s["h_spread"] for s in stats_list) / len(stats_list)
    p_sp = sum(s["p_spread"] for s in stats_list) / len(stats_list)
    h_m = max(0.1, sum(s["h_mean"] for s in stats_list) / len(stats_list))
    spread = min(50, (h_sp / h_m) * 60 + p_sp * 3)
    lead = max(0, lead_days - 2) * 6
    return int(max(5, min(95, spread + lead)))


def fit_pct(stats_list, profile):
    """Personal-fit % from rider profile."""
    if not stats_list:
        return 0
    score = 0.0
    lo, hi = profile["size_sweet_m"]
    for s in stats_list:
        pts = 0.0
        if lo <= s["h_mean"] <= hi:
            pts += 0.45
        elif profile["size_ok_m"][0] <= s["h_mean"] <= profile["size_ok_m"][1]:
            pts += 0.25
        if s["p_mean"] >= profile["min_period_pref_s"]:
            pts += 0.25
        if s["wind_med"] is not None and s["wind_med"] <= profile["wind_clean_max_mph"]:
            pts += 0.20
        pts += 0.10 * s["dir_ok_frac"]
        score += pts
    return int(100 * score / len(stats_list))


def composite(weights, confidence, window_days, wind_clean_frac, wave_fit,
              drive_hours):
    """Weighted score 0-100, your ranked weight order. Also returns
    travel-adjusted score."""
    travel_eff = 1.0 if not drive_hours else max(0.2, 1 - (drive_hours / 10))
    raw = 100 * (
        weights["confidence"] * confidence
        + weights["window_consistency"] * min(1.0, window_days / 3)
        + weights["wind_cleanliness"] * wind_clean_frac
        + weights["wave_match"] * wave_fit
        + weights["travel_efficiency"] * travel_eff)
    ta = raw if not drive_hours else raw / max(1.0, drive_hours)
    return int(raw), round(ta, 1)
