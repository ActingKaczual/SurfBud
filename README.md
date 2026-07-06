# Surf Bud — event-first, two-front

Watches EVENTS (storms upstream, swell arrivals downstream), not spot lists.
Ocean engine finds quality missions; lake engine tracks maintenance sessions.
Full design: surf-bud-spec.md (chat deliverable).

## Setup
1. ntfy app -> subscribe to an unguessable topic name.
2. GitHub: public repo, push these files, add secrets:
   NTFY_TOPIC (required), ANTHROPIC_API_KEY (AI briefings, optional),
   AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET (fares, optional).
   Missing optional secrets degrade gracefully.
3. Run the workflow once manually (Actions tab).
4. Google Calendar -> Add calendar -> From URL, twice:
   https://raw.githubusercontent.com/YOU/REPO/main/ocean-missions.ics
   https://raw.githubusercontent.com/YOU/REPO/main/lake-sessions.ics

## How it behaves
- WHISPER events log silently (calendar/outlook only). HEADS UP pushes once,
  labeled speculative. CONFIRMED pushes with full briefing + fare snapshot on
  fly spots. Cancels push; up/downgrades update the calendar quietly.
- Max 2 pushes/day. Quiet 9pm-7am; overnight alerts queue for the 7am run.
- Lake events push only at good+; otherwise digest and calendar.
- Sunday outlook sent only when events are active.
- Bust % = GFS vs ECMWF disagreement + lead-time decay.

## Your levers
- spots.yaml: the roster and YOUR local knowledge notes (feed briefings).
- config.yaml: grid points, thresholds, weights, caps, quiet hours.
- Tell Claude your post-session debriefs; it distills them into spots.yaml.

## Phase 1.5+ (per spec)
Twilio SMS swap (src/notify.py has the swap point), dashboard reading
state/dashboard.json (already published), 2-tap ratings, silent learning.
