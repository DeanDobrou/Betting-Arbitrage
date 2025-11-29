from __future__ import annotations
from typing import List, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, Response
from core.models import Event, Market

ATHENS = ZoneInfo("Europe/Athens")

BOOKMAKER = "novibet"
COUPON_PAGE = "https://www.novibet.gr/stoixima/podosfairo/4372606/coupon"
API_PREFIX = "https://www.novibet.gr/spt/feed/marketviews/location/v2/4324/5117425/0/"

def _to_athens(dt_iso: Optional[str]) -> Optional[datetime]:
    if not dt_iso:
        return None
    dt = datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ATHENS)

def _extract_events(payload) -> List[Event]:
    items = []
    if isinstance(payload, list) and payload:
        for bv in payload[0].get("betViews", []):
            items.extend(bv.get("items", []))
    elif isinstance(payload, dict):
        items = payload.get("items", payload.get("events", [])) or []

    out: List[Event] = []
    today = datetime.now(ATHENS).date()

    for ev in items:
        addc = ev.get("additionalCaptions") or {}
        home = addc.get("competitor1") or ev.get("home") or ev.get("homeTeam")
        away = addc.get("competitor2") or ev.get("away") or ev.get("awayTeam")
        start = _to_athens(ev.get("startDateTime"))
        if not (home and away and start):
            continue
        if start.date() != today:
            continue

        league = ev.get("competitionCaption") or ev.get(
            "competitionHistoryCaption")

        m_1x2 = next((m for m in ev.get("markets", []) if m.get(
            "betTypeSysname") == "SOCCER_MATCH_RESULT"), None)
        if not m_1x2:
            continue

        outcomes = {}
        for bi in m_1x2.get("betItems", []):
            code, price = bi.get("code"), bi.get("price")
            if code in ("1", "X", "2") and price:
                outcomes[code] = float(price)
        if not outcomes:
            continue

        market = Market(key="1x2", outcomes=outcomes)
        out.append(Event(
            booker="novibet",
            event_id=str(ev.get("eventBetContextId") or ev.get("id") or ""),
            league=league,
            home=str(home),
            away=str(away),
            start=start,
            markets={"1x2": market},
        ))
    return out

def fetch_today() -> List[Event]:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False, slow_mo=50)
        ctx = browser.new_context(locale="el-GR", timezone_id="Europe/Athens")
        page = ctx.new_page()

        json_resp: Optional[Response] = None

        def on_response(resp: Response):
            nonlocal json_resp
            if resp.url.startswith(API_PREFIX) and "application/json" in resp.headers.get("content-type", ""):
                json_resp = resp

        page.on("response", on_response)
        page.goto(COUPON_PAGE, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)

        if not json_resp:
            page.reload(wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

        if not json_resp:
            browser.close()
            raise RuntimeError(
                "Did not capture the marketviews/location JSON. Interact manually if needed.")

        payload = json_resp.json()
        events = _extract_events(payload)
        browser.close()
        return events
