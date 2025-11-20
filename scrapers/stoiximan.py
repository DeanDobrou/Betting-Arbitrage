from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from models import Event, Market

BOOKMAKER = "stoiximan"

ATHENS = ZoneInfo("Europe/Athens")
COUPON_URL = "https://www.stoiximan.gr/sport/podosfairo/kouponi-agones-simera/"


def _ms_to_athens(ts_ms: Optional[int]) -> Optional[datetime]:
    if not ts_ms:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=ATHENS)


def _extract_events_from_state(state: dict) -> List[Event]:
    out: List[Event] = []
    today = datetime.now(ATHENS).date()

    data = state.get("data") or {}
    blocks = data.get("blocks") or []

    for block in blocks:
        league_name = block.get("name")
        events = block.get("events") or []

        for ev in events:
            start = _ms_to_athens(ev.get("startTime"))
            if not start:
                continue
            if start.date() != today:
                continue

            short = ev.get("shortName") or ev.get("name") or ""
            home = away = None
            if " - " in short:
                home, away = short.split(" - ", 1)

            mres = next(
                (m for m in (ev.get("markets") or [])
                 if m.get("type") == "MRES"),
                None,
            )
            if not mres:
                continue

            if (not home or not away) and mres.get("selections"):
                sels = mres["selections"]
                if len(sels) >= 3:
                    home = home or sels[0].get("fullName")
                    away = away or sels[2].get("fullName")

            if not (home and away):
                continue

            outcomes: Dict[str, float] = {}
            for sel in mres.get("selections") or []:
                code = sel.get("name")
                price = sel.get("price")
                if code in ("1", "X", "2") and price is not None:
                    try:
                        outcomes[code] = float(price)
                    except (TypeError, ValueError):
                        pass

            if not outcomes:
                continue

            market = Market(key="1x2", outcomes=outcomes)
            event_id = str(ev.get("id") or "")

            out.append(
                Event(
                    booker=BOOKMAKER,
                    event_id=event_id,
                    league=league_name,
                    home=str(home),
                    away=str(away),
                    start=start,
                    markets={"1x2": market},
                )
            )

    return out


def fetch_today() -> List[Event]:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=50,
        )
        ctx = browser.new_context(
            locale="el-GR",
            timezone_id="Europe/Athens",
        )
        page = ctx.new_page()

        page.goto(COUPON_URL, wait_until="domcontentloaded")

        page.wait_for_function("() => window['initial_state'] !== undefined")

        state = page.evaluate("() => window['initial_state']")
        events = _extract_events_from_state(state)

        browser.close()
        return events
