from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, Response

from core.models import Event, Market

BOOKMAKER = "betsson"
ATHENS = ZoneInfo("Europe/Athens")

COUPON_URL = "https://www.betsson.gr/el/stoixima/arxizi-sintoma/1440"
API_URL_PREFIX = "https://www.betsson.gr/api/sb/v1/widgets/events-table"


def _parse_iso_timestamp(dt_iso: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string to Athens timezone."""
    if not dt_iso:
        return None
    try:
        dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ATHENS)
    except ValueError:
        return None


def _is_within_time_filter(start: datetime) -> bool:
    """
    Check if event should be included.
    Include: today's matches + up to 3 hours into the next day.
    """
    now = datetime.now(ATHENS)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_day_cutoff = today_start + timedelta(days=1, hours=3)

    return today_start <= start <= next_day_cutoff


def _extract_events(payload: dict) -> List[Event]:
    """Extract events from Betsson API response."""
    out: List[Event] = []

    # Get events array
    events_data = payload.get("data", {})
    events_list = events_data.get("events", [])

    for ev in events_list:
        # Get start time
        start = _parse_iso_timestamp(ev.get("startDate"))
        if not start:
            continue

        # Filter by time: today + 3 hours into next day
        if not _is_within_time_filter(start):
            continue

        # Get participants (home/away)
        participants = ev.get("participants", [])
        if len(participants) < 2:
            continue

        # Participants are ordered by sortOrder
        home_participant = next((p for p in participants if p.get("side") == 1), None)
        away_participant = next((p for p in participants if p.get("side") == 2), None)

        if not home_participant or not away_participant:
            continue

        home = home_participant.get("label")
        away = away_participant.get("label")

        if not home or not away:
            continue

        # Get league
        league = ev.get("competitionName")

        # Get event ID
        event_id = ev.get("id")
        if not event_id:
            continue

        # Extract 1X2 odds from selections
        # The odds are in a separate array in the payload
        # We need to match by event ID
        market_1x2 = None

        # Check if there are selections in the payload
        selections = events_data.get("selections", [])

        # Find selections for this event (marketId contains the event id)
        event_selections = [s for s in selections if event_id in s.get("marketId", "")]

        # Find HOME, DRAW, AWAY selections
        odds_1 = None
        odds_x = None
        odds_2 = None

        for sel in event_selections:
            template_id = sel.get("selectionTemplateId", "")
            odds_value = sel.get("odds")

            if odds_value is None:
                continue

            if template_id == "HOME":
                odds_1 = float(odds_value)
            elif template_id == "DRAW":
                odds_x = float(odds_value)
            elif template_id == "AWAY":
                odds_2 = float(odds_value)

        # Only include if we have all 3 odds
        if odds_1 is not None and odds_x is not None and odds_2 is not None:
            outcomes = {
                "1": odds_1,
                "X": odds_x,
                "2": odds_2,
            }
            market_1x2 = Market(key="1x2", outcomes=outcomes)

        if not market_1x2:
            continue

        out.append(
            Event(
                booker=BOOKMAKER,
                event_id=str(event_id),
                league=league,
                home=home,
                away=away,
                start=start,
                markets={"1x2": market_1x2},
            )
        )

    return out


def fetch_today() -> List[Event]:
    """Fetch today's football matches from Betsson."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        ctx = browser.new_context(locale="el-GR", timezone_id="Europe/Athens")
        page = ctx.new_page()

        all_responses: List[Response] = []

        def on_response(resp: Response):
            # Check if URL contains the API path
            if API_URL_PREFIX in resp.url and "application/json" in (
                resp.headers.get("content-type") or ""
            ):
                all_responses.append(resp)

        # Set up response interceptor before navigating
        page.on("response", on_response)

        page.goto(COUPON_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # Scroll down to trigger lazy loading
        try:
            for _ in range(5):
                page.evaluate("window.scrollBy(0, 1000)")
                page.wait_for_timeout(1000)
        except Exception:
            pass

        # Wait for all API calls to complete
        page.wait_for_timeout(3000)

        if not all_responses:
            browser.close()
            raise RuntimeError("Did not capture any Betsson API response.")

        # Combine all events from all API responses
        all_events: List[Event] = []
        seen_ids = set()

        for resp in all_responses:
            try:
                payload = resp.json()
                events = _extract_events(payload)
                for event in events:
                    if event.event_id not in seen_ids:
                        all_events.append(event)
                        seen_ids.add(event.event_id)
            except Exception:
                continue

        browser.close()
        return all_events
