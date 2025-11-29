from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, Response

from core.models import Event, Market

BOOKMAKER = "bwin"
ATHENS = ZoneInfo("Europe/Athens")

COUPON_URL = "https://www.bwin.gr/el/sports/%CF%80%CE%BF%CE%B4%CF%8C%CF%83%CF%86%CE%B1%CE%B9%CF%81%CE%BF-4/%CE%BA%CE%BF%CF%85%CF%80%CF%8C%CE%BD%CE%B9%CE%B1/%CF%83%CE%B7%CE%BC%CE%B5%CF%81%CE%B9%CE%BD%CE%BF%CE%AF-%CE%B1%CE%B3%CF%8E%CE%BD%CE%B5%CF%82-1"
API_URL_PREFIX = "https://www.bwin.gr/cds-api/coupons/fixtures"


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


def _extract_events(payload: dict) -> List[Event]:
    """Extract events from bwin coupons API response."""
    out: List[Event] = []

    # Fixtures are nested under fixturePage
    fixture_page = payload.get("fixturePage", {})
    fixtures = fixture_page.get("fixtures", [])

    for fx in fixtures:
        # Get start time
        start = _parse_start(fx.get("startDate"))
        if not start:
            continue

        # Get participants (home/away)
        participants = fx.get("participants", [])
        if len(participants) < 2:
            continue

        home = participants[0].get("name", {}).get("value")
        away = participants[1].get("name", {}).get("value")

        if not home or not away:
            continue

        # Get league
        league = None
        competition = fx.get("competition", {})
        if competition:
            league = competition.get("name", {}).get("value")

        # Get 1X2 market from optionMarkets
        option_markets = fx.get("optionMarkets", [])
        market_1x2 = None

        for market in option_markets:
            # Check if this is main market (isMain: true)
            if not market.get("isMain"):
                continue

            options = market.get("options", [])
            if len(options) != 3:
                continue

            # Extract odds from the 3 options
            outcomes = {}
            for opt in options:
                source_name = opt.get("sourceName", {}).get("value", "")
                name_value = opt.get("name", {}).get("value", "")
                price = opt.get("price", {})
                odds = price.get("odds")

                if odds is None:
                    continue

                # Use sourceName (which is "1", "X", "2") or fallback to checking name
                if source_name == "1":
                    outcomes["1"] = float(odds)
                elif source_name == "2":
                    outcomes["2"] = float(odds)
                elif name_value == "X" or "X" in name_value:
                    outcomes["X"] = float(odds)

            if len(outcomes) == 3:
                market_1x2 = Market(key="1x2", outcomes=outcomes)
                break

        if not market_1x2:
            continue

        event_id = fx.get("id", "")

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
    """Fetch today's football matches from bwin."""
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

        page.on("response", on_response)
        page.goto(COUPON_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        # Keep clicking "load more" until it's no longer visible
        while True:
            try:
                load_more = page.locator("ms-grid-show-more").first
                if load_more.is_visible(timeout=2000):
                    load_more.click()
                    page.wait_for_timeout(2000)
                else:
                    break
            except Exception:
                break

        if not all_responses:
            browser.close()
            raise RuntimeError("Did not capture any bwin coupons API response.")

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
