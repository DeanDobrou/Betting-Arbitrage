from __future__ import annotations

from typing import List, Optional
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, Response

from core.models import Event, Market

BOOKMAKER = "fonbet"
ATHENS = ZoneInfo("Europe/Athens")

SPORTS_URL = "https://fonbet.gr/sports/football"
API_URL_PREFIX = "https://line21.gr-resource.com/events/listBase"

# Factor IDs for 1X2 market
FACTOR_HOME = 921
FACTOR_DRAW = 922
FACTOR_AWAY = 923


def _parse_timestamp(ts: Optional[int]) -> Optional[datetime]:
    """Parse Unix timestamp to Athens timezone."""
    if not ts:
        return None
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.astimezone(ATHENS)
    except (ValueError, OSError):
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
    """Extract football events from Fonbet API response."""
    out: List[Event] = []

    events_list = payload.get("events", [])
    custom_factors = payload.get("customFactors", [])

    factors_map = {}
    for cf in custom_factors:
        event_id = cf.get("e")
        if event_id:
            factors_map[event_id] = cf.get("factors", [])

    for ev in events_list:

        start_ts = ev.get("startTime")
        start = _parse_timestamp(start_ts)
        if not start:
            continue

        if not _is_within_time_filter(start):
            continue

        home = ev.get("team1")
        away = ev.get("team2")

        if not home or not away:
            continue

        event_id = ev.get("id")
        if not event_id:
            continue

        factors = factors_map.get(event_id, [])

        odds_1 = None
        odds_x = None
        odds_2 = None

        for factor in factors:
            factor_id = factor.get("f")
            odds_value = factor.get("v")

            if odds_value is None:
                continue

            if factor_id == FACTOR_HOME:
                odds_1 = float(odds_value)
            elif factor_id == FACTOR_DRAW:
                odds_x = float(odds_value)
            elif factor_id == FACTOR_AWAY:
                odds_2 = float(odds_value)

        if odds_1 is None or odds_x is None or odds_2 is None:
            continue

        outcomes = {
            "1": odds_1,
            "X": odds_x,
            "2": odds_2,
        }

        market_1x2 = Market(key="1x2", outcomes=outcomes)

        out.append(
            Event(
                booker=BOOKMAKER,
                event_id=str(event_id),
                league=None,
                home=home,
                away=away,
                start=start,
                markets={"1x2": market_1x2},
            )
        )

    return out


def fetch_today() -> List[Event]:
    """Fetch today's football matches from Fonbet."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        ctx = browser.new_context(locale="el-GR", timezone_id="Europe/Athens")
        page = ctx.new_page()

        all_responses: List[Response] = []

        def on_response(resp: Response):
            if "events/listBase" in resp.url and "application/json" in (
                resp.headers.get("content-type") or ""
            ):
                all_responses.append(resp)

        page.goto(SPORTS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        try:
            lang_switcher = page.locator(".language-switcher-wrapper").first
            if lang_switcher.is_visible(timeout=2000):
                lang_switcher.click()
                page.wait_for_timeout(1000)

                greek_option = page.locator("span:has-text('Ελληνικά')").first
                if greek_option.is_visible(timeout=2000):
                    greek_option.click()
                    page.wait_for_timeout(3000)
        except Exception:
            pass

        page.on("response", on_response)

        page.goto(SPORTS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        try:
            for _ in range(5):
                page.evaluate("window.scrollBy(0, 1000)")
                page.wait_for_timeout(1000)
        except Exception:
            pass

        page.wait_for_timeout(3000)

        if not all_responses:
            browser.close()
            raise RuntimeError("Did not capture any Fonbet API response.")

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
