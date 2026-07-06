"""Data sources: Open-Meteo dual-model marine sweep, wind, NHC tropical feed."""
import requests

MARINE = "https://marine-api.open-meteo.com/v1/marine"
FORECAST = "https://api.open-meteo.com/v1/forecast"
NHC = "https://www.nhc.noaa.gov/CurrentStorms.json"
MODELS = ["ecmwf_wam025", "ncep_gfswave025"]   # dual model -> bust signal


def _get(url, params=None, timeout=40):
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def marine_point(lat, lon, days=10):
    """Return {model: [(iso_hour, height_m, period_s, dir_deg), ...]}.
    Falls back to best_match single-model if the dual-model call fails."""
    base = {
        "latitude": lat, "longitude": lon,
        "hourly": "swell_wave_height,swell_wave_period,swell_wave_direction",
        "forecast_days": days, "timezone": "America/New_York",
    }
    try:
        data = _get(MARINE, {**base, "models": ",".join(MODELS)})
        h = data["hourly"]
        out = {}
        for m in MODELS:
            hh = h.get(f"swell_wave_height_{m}")
            pp = h.get(f"swell_wave_period_{m}")
            dd = h.get(f"swell_wave_direction_{m}")
            if hh:
                out[m] = list(zip(h["time"], hh, pp, dd))
        if out:
            return out
    except requests.RequestException:
        pass
    data = _get(MARINE, base)  # single-model fallback
    h = data["hourly"]
    return {"best_match": list(zip(h["time"], h["swell_wave_height"],
                                   h["swell_wave_period"],
                                   h["swell_wave_direction"]))}


def wind_point(lat, lon, days=10):
    """[(iso_hour, speed_mph, dir_deg)]"""
    data = _get(FORECAST, {
        "latitude": lat, "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "mph", "forecast_days": days,
        "timezone": "America/New_York",
    })
    h = data["hourly"]
    return list(zip(h["time"], h["wind_speed_10m"], h["wind_direction_10m"]))


def tropical_storms():
    """Active Atlantic-basin systems from NHC. [] on any failure."""
    try:
        data = _get(NHC)
        return [s for s in data.get("activeStorms", [])
                if str(s.get("id", "")).lower().startswith("al")]
    except Exception:
        return []
