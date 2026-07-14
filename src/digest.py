"""Digest site per event, served by GitHub Pages from docs/.
Zero dependencies, inline CSS, mobile-first."""
import datetime as dt
import hashlib
import html
import os

import humanize as hz

CSS = """
:root{--bg:#0C1D27;--panel:#122733;--line:#22404F;--ink:#E8ECE9;
--dim:#8FA6AE;--buoy:#F5B82E;--marker:#C4452F}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,
system-ui,sans-serif;padding:20px 16px 60px;max-width:640px;margin:0 auto}
h1{font-size:26px;line-height:1.15;margin:4px 0 2px}
h2{font-size:13px;color:var(--buoy);letter-spacing:.12em;
text-transform:uppercase;margin:26px 0 10px}
a{color:var(--buoy);text-decoration:none}
.kicker{font-size:12px;color:var(--marker);letter-spacing:.14em;
text-transform:uppercase}
.card{background:var(--panel);border:1px solid var(--line);
border-radius:10px;padding:14px 16px;margin:10px 0;display:block;color:var(--ink)}
.dim{color:var(--dim);font-size:14px}
.big{font-size:20px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{padding:8px 6px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--dim);font-weight:500;font-size:12px;text-transform:uppercase;
letter-spacing:.08em}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;
font-size:12px;font-weight:600;letter-spacing:.05em}
.b-conf{background:var(--buoy);color:var(--bg)}
.b-heads{background:var(--line);color:var(--ink)}
.b-canc{background:var(--marker);color:var(--ink)}
.brief{white-space:pre-wrap;border-left:3px solid var(--buoy);
padding-left:14px;margin:8px 0}
footer{margin-top:36px;font-size:12px;color:var(--dim)}
"""


def _uid(key):
    return hashlib.md5(key.encode()).hexdigest()[:10]


def event_url(base, key):
    return f"{base}/event-{_uid(key)}.html"


def _badge(state):
    cls = {"CONFIRMED": "b-conf", "HEADS_UP": "b-heads",
           "CANCELLED": "b-canc"}.get(state, "b-heads")
    return f'<span class="badge {cls}">{hz.state_prefix(state)}</span>'


def _page(title_txt, inner):
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title_txt)}</title><style>{CSS}</style></head>"
            f"<body>{inner}<footer>Surf Bud - generated "
            f"{dt.datetime.now().strftime('%b %d, %I:%M %p ET')}</footer>"
            f"</body></html>")


def _event_page(ev, base):
    e = lambda s: html.escape(str(s or ""))
    day_rows = ""
    for d in ev.get("day_grades", []):
        day_rows += (f"<tr><td>{e(hz.day_range(d['date'], d['date']))}</td>"
                     f"<td>{e(d['grade'].upper())}</td></tr>")
    fare = (f"<h2>Getting there</h2><div class='card'>{e(ev['fare_note'])}"
            f"</div>") if ev.get("fare_note") else ""
    brief = (f"<h2>The story</h2><div class='brief'>{e(ev['briefing'])}"
             f"</div>") if ev.get("briefing") else ""
    inner = f"""
<div class="kicker">{e(ev['class'].replace('_',' '))} - {e(ev['front'])} front</div>
<h1>{e(ev['best_spot'])}</h1>
<div class="dim">{e(hz.day_range(ev['first_day'], ev['last_day']))}</div>
<p style="margin:12px 0">{_badge(ev['state'])}</p>
<div class="card">
  <div class="big">{e(hz.band(ev.get('h_m')))}
  {'at ' + format(ev['p_s'], '.0f') + 's' if ev.get('p_s') else ''}</div>
  <div class="dim">{e(hz.bust_phrase(ev.get('bust')).capitalize())} -
  fits your profile {e(ev.get('fit','?'))}%</div>
</div>
{brief}
<h2>Day by day</h2>
<table><tr><th>Day</th><th>Call</th></tr>{day_rows or
'<tr><td colspan=2 class=dim>window details in next run</td></tr>'}</table>
<h2>Scores</h2>
<div class="card dim">Raw quality {e(ev.get('score_raw','?'))}/100 -
travel-adjusted {e(ev.get('score_travel_adj','?'))} per hour
{f"- {ev['drive_hours']} hr drive" if ev.get('drive_hours') else ''}</div>
{fare}
<p style="margin-top:24px"><a href="{base}/index.html">&larr; all events</a></p>
"""
    return _page(f"{ev['best_spot']} - Surf Bud", inner)


def build_site(events, base):
    os.makedirs("docs", exist_ok=True)
    open("docs/.nojekyll", "w").close()
    cards = ""
    live = [ev for ev in events.values() if ev["state"] != "PAST"]
    live.sort(key=lambda x: x["first_day"])
    for ev in live:
        url = f"event-{_uid(ev['key'])}.html"
        with open(f"docs/{url}", "w") as f:
            f.write(_event_page(ev, base))
        e = lambda s: html.escape(str(s or ""))
        cards += f"""<a class="card" href="{url}">
<div class="dim">{e(ev['front'].upper())} - {e(hz.day_range(ev['first_day'],
ev['last_day']))}</div>
<div class="big">{e(hz.spot_short(ev['best_spot']))}</div>
<div>{_badge(ev['state'])} <span class="dim">
{e(hz.band(ev.get('h_m')))} - {e(hz.bust_phrase(ev.get('bust')))}</span></div>
</a>"""
    if not cards:
        cards = ("<div class='card dim'>Nothing brewing on either front. "
                 "Silence is information.</div>")
    inner = (f"<div class='kicker'>Both fronts</div><h1>Surf Bud</h1>"
             f"<div class='dim'>Active events</div>{cards}")
    with open("docs/index.html", "w") as f:
        f.write(_page("Surf Bud - digest", inner))
