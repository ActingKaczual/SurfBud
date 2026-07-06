"""Fare snapshot for fly-relevant CONFIRMED events (spec §7: informational
auto, booking needs your tap)."""
import datetime as dt
import os
import urllib.parse

import requests

TOKEN_URL = "https://test.api.amadeus.com/v1/security/oauth2/token"
SEARCH_URL = "https://test.api.amadeus.com/v2/shopping/flight-offers"
# Production keys: swap test.api.amadeus.com -> api.amadeus.com


def gflights_link(origin, dest, depart, ret):
    q = f"Flights from {origin} to {dest} on {depart} through {ret}"
    return "https://www.google.com/travel/flights?q=" + urllib.parse.quote(q)


def snapshot(cfg, dest, first_day, last_day):
    """Best fare across origins, arriving day before first good day."""
    cid = os.environ.get("AMADEUS_CLIENT_ID")
    sec = os.environ.get("AMADEUS_CLIENT_SECRET")
    d = dt.date.fromisoformat(first_day)
    dep = (d - dt.timedelta(days=1)).isoformat()
    ret = (dt.date.fromisoformat(last_day) + dt.timedelta(days=1)).isoformat()
    fallback_link = gflights_link(cfg["origins"][0], dest, dep, ret)
    if not (cid and sec):
        return {"note": "fares not configured", "link": fallback_link}
    try:
        tok = requests.post(TOKEN_URL, data={
            "grant_type": "client_credentials",
            "client_id": cid, "client_secret": sec}, timeout=30)
        tok.raise_for_status()
        token = tok.json()["access_token"]
    except requests.RequestException:
        return {"note": "fare auth failed", "link": fallback_link}
    best = None
    for origin in cfg["origins"]:
        try:
            r = requests.get(SEARCH_URL, params={
                "originLocationCode": origin, "destinationLocationCode": dest,
                "departureDate": dep, "returnDate": ret, "adults": 1,
                "currencyCode": cfg["currency"],
                "maxPrice": cfg["max_price_usd"], "max": 2,
            }, headers={"Authorization": f"Bearer {token}"}, timeout=30)
            r.raise_for_status()
            for offer in r.json().get("data", []):
                price = float(offer["price"]["grandTotal"])
                if best is None or price < best["price"]:
                    best = {"origin": origin, "price": price}
        except requests.RequestException:
            continue
    if not best:
        return {"note": f"no fare under ${cfg['max_price_usd']}",
                "link": fallback_link}
    best["link"] = gflights_link(best["origin"], dest, dep, ret)
    best["note"] = f"${best['price']:.0f} from {best['origin']}"
    return best
