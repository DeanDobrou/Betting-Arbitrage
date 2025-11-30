from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, Response

from core.models import Event, Market

BOOKMAKER = "pamestoixima"
ATHENS = ZoneInfo("Europe/Athens")

COUPON_URL = "https://www.pamestoixima.gr/next24hCoupon"
API_URL_PREFIX = "https://capi.pamestoixima.gr/content-service/api/v1/q/getEventsNew"


def _parse_start(dt_iso: Optional[str]) -> Optional[datetime]:
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
    """Extract events from Pame Stoixima API response."""
    out: List[Event] = []

    data = payload.get("data", {})
    events = data.get("events", [])

    for ev in events:
        # Get start time
        start = _parse_start(ev.get("startTime"))
        if not start:
            continue

        # Filter by time: today + 3 hours into next day
        if not _is_within_time_filter(start):
            continue

        # Get teams
        teams = ev.get("teams", [])
        if len(teams) < 2:
            continue

        home_team = next((t for t in teams if t.get("side") == "HOME"), None)
        away_team = next((t for t in teams if t.get("side") == "AWAY"), None)

        if not home_team or not away_team:
            continue

        home = home_team.get("name")
        away = away_team.get("name")

        if not home or not away:
            continue

        # Get league from type.name
        league = None
        type_obj = ev.get("type", {})
        if type_obj:
            league = type_obj.get("name")

        # Find 1X2 market (MATCH_RESULT)
        markets = ev.get("markets", [])
        market_1x2 = None

        for market in markets:
            group_code = market.get("groupCode")
            if group_code != "MATCH_RESULT":
                continue

            outcomes_list = market.get("outcomes", [])
            if len(outcomes_list) != 3:
                continue

            # Extract odds from outcomes
            outcomes = {}
            for outcome in outcomes_list:
                sub_type = outcome.get("subType", "")
                prices = outcome.get("prices", [])

                if not prices:
                    continue

                # Get decimal odds from first price
                decimal_odds = prices[0].get("decimal")
                if decimal_odds is None:
                    continue

                # Map subType to 1/X/2
                if sub_type == "H":  # Home
                    outcomes["1"] = float(decimal_odds)
                elif sub_type == "D":  # Draw
                    outcomes["X"] = float(decimal_odds)
                elif sub_type == "A":  # Away
                    outcomes["2"] = float(decimal_odds)

            if len(outcomes) == 3:
                market_1x2 = Market(key="1x2", outcomes=outcomes)
                break

        if not market_1x2:
            continue

        event_id = ev.get("id", "")

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
    """Fetch today's football matches from Pame Stoixima."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        ctx = browser.new_context(locale="el-GR", timezone_id="Europe/Athens")
        page = ctx.new_page()

        all_responses: List[Response] = []

        def on_response(resp: Response):
            if resp.url.startswith(API_URL_PREFIX) and "application/json" in (
                resp.headers.get("content-type") or ""
            ):
                all_responses.append(resp)

        # Set up response interceptor before navigating
        page.on("response", on_response)

        page.goto(COUPON_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Click the "'Ολα" (All) button to get all 24-hour matches
        try:
            # The button text is 'Ολα (with apostrophe)
            all_btn = page.locator(".MuiTab-root:has-text(\"'Ολα\")").first
            if all_btn.is_visible(timeout=2000):
                all_btn.click()
                page.wait_for_timeout(3000)
        except Exception:
            # If button not found or already selected, continue
            pass

        page.wait_for_timeout(2000)

        if not all_responses:
            browser.close()
            raise RuntimeError("Did not capture any Pame Stoixima API response.")

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
