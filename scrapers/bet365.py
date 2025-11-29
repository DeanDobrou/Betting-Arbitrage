# scrapers/bet365.py
from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright, Response

from core.models import Event, Market

BOOKMAKER = "bet365"
BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"

ATHENS = ZoneInfo("Europe/Athens")

MAIN_URL = "https://www.bet365.gr/#/AC/B1/C1/D1002/G40/J99/Q1/I1/F^24/"
API_URL_PREFIX = "https://www.bet365.gr/matchmarketscontentapi/soccerupcomingmatches"


def _fractional_to_decimal(frac: str) -> Optional[float]:
    """Convert fractional odds like '8/5' to decimal odds (1 + 8/5 = 2.6)."""
    if not frac or "/" not in frac:
        return None
    try:
        num, den = frac.split("/", 1)
        n, d = int(num), int(den)
        return 1.0 + n / d
    except Exception:
        return None


def _bc_to_athens(bc: str) -> Optional[datetime]:
    """Convert Bet365 BC timestamp (YYYYMMDDHHMMSS) to an aware Athens datetime."""
    if not bc or len(bc) != 14:
        return None
    try:
        dt = datetime.strptime(bc, "%Y%m%d%H%M%S")
        return dt.replace(tzinfo=ATHENS)
    except ValueError:
        return None


def _parse_feed(text: str) -> List[Event]:
    """
    Decode Bet365's compact text feed into Event objects.

    The response is a single string made of segments separated by '|'.
    Each segment has a type prefix and semicolon-separated key=value fields,
    for example: 'PA;ID=...;NA=Home;N2=Away;FS=0;MP=0;BC=20251121170000;FI=12345;OD=8/5;...'.

    The main types used here are:
        - MG: market group (league/competition). Collect ID and name (NA/L3)
            and N2/N3/EX, which represent the labels for 1, X, 2.
        - MA: associates a fixture ID (FI) with a market group (MG).
        - PA: participant/odds records. One PA line per fixture contains NA/N2/BC/FS/MP
            which give us the home team, away team, start time, and match state.
            Additional PA lines with OD provide fractional odds, which we map in
            the order defined by the MG labels (N2, N3, EX) into the 1X2 market.

    A fixture is considered valid if:
        - it has home, away, and start time,
        - the date equals "today" in Athens,
        - it has at least three odds (for 1, X, 2),
        - and it is not live: we only keep fixtures where MP is missing or "0"
            and FS is missing or "0", basically pre-match only.
    """
    segments = text.split("|")

    mg_config: Dict[str, Dict[str, str]] = {}
    mg_league: Dict[str, str] = {}

    fixtures: Dict[str, Dict[str, object]] = {}
    odds_by_fi: Dict[str, List[float]] = {}

    current_mg_id: Optional[str] = None

    for seg in segments:
        if not seg:
            continue
        parts = seg.split(";")
        if not parts:
            continue

        tag = parts[0]

        fields: Dict[str, str] = {}
        for p in parts[1:]:
            if not p:
                continue
            if "=" in p:
                k, v = p.split("=", 1)
                fields[k] = v

        if tag == "MG":
            mg_id = fields.get("ID")
            if mg_id:
                mg_config[mg_id] = fields
                current_mg_id = mg_id
                league_name = fields.get("NA") or fields.get("L3")
                if league_name:
                    mg_league[mg_id] = league_name

        elif tag == "MA":
            fi = fields.get("FI")
            if not fi:
                continue
            mg_id = fields.get("MA") or current_mg_id
            fx = fixtures.setdefault(fi, {})
            if mg_id:
                fx["mg_id"] = mg_id

        elif tag == "PA":
            fi = fields.get("FI")
            if not fi:
                continue

            if "NA" in fields and "N2" in fields:
                fx = fixtures.setdefault(fi, {})
                fx["home"] = fields.get("NA")
                fx["away"] = fields.get("N2")
                fx["desc"] = fields.get("FD")
                bc = fields.get("BC")
                start = _bc_to_athens(bc) if bc else None
                if start:
                    fx["start"] = start
                if "MP" in fields:
                    fx["mp"] = fields["MP"]
                if "FS" in fields:
                    fx["fs"] = fields["FS"]

            if "OD" in fields:
                dec = _fractional_to_decimal(fields["OD"])
                if dec is None:
                    continue
                odds_by_fi.setdefault(fi, []).append(dec)

    out: List[Event] = []
    today = datetime.now(ATHENS).date()

    for fi, fx in fixtures.items():
        start = fx.get("start")
        home = fx.get("home")
        away = fx.get("away")

        if not (start and home and away):
            continue

        if isinstance(start, datetime) and start.date() != today:
            continue

        mp = str(fx.get("mp")) if fx.get("mp") is not None else "0"
        fs = str(fx.get("fs")) if fx.get("fs") is not None else "0"
        if mp != "0" or fs != "0":
            continue

        prices = odds_by_fi.get(fi)
        if not prices or len(prices) < 3:
            continue

        mg_id = fx.get("mg_id")
        league = None
        if isinstance(mg_id, str):
            league = mg_league.get(mg_id)

        labels: List[str] = []
        if isinstance(mg_id, str):
            cfg = mg_config.get(mg_id, {})
            for key in ("N2", "N3", "EX"):
                lab = cfg.get(key)
                if lab:
                    labels.append(lab)

        if len(labels) != 3:
            labels = ["1", "X", "2"]

        outcomes: Dict[str, float] = {}
        for i, lab in enumerate(labels):
            if i < len(prices):
                outcomes[lab] = prices[i]

        if len(outcomes) < 3:
            continue

        market = Market(key="1x2", outcomes=outcomes)

        out.append(
            Event(
                booker=BOOKMAKER,
                event_id=str(fi),
                league=league,
                home=str(home),
                away=str(away),
                start=start,
                markets={"1x2": market},
            )
        )

    return out

def fetch_today() -> List[Event]:
    """Open Bet365 with Brave, capture the soccerupcomingmatches feed, and return today's non-live 1X2 events."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=100,
            executable_path=BRAVE_PATH,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-web-security",
                "--disable-site-isolation-trials",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        ctx = browser.new_context(
            locale="el-GR",
            timezone_id="Europe/Athens",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Brave Chrome/142.0.0.0 Safari/537.36"
            ),
        )

        page = ctx.new_page()

        feed_resp: Optional[Response] = None

        def on_response(resp: Response):
            nonlocal feed_resp
            if resp.url.startswith(API_URL_PREFIX) and resp.status == 200:
                feed_resp = resp

        page.on("response", on_response)

        page.goto(MAIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        if not feed_resp:
            try:
                resp = page.wait_for_response(
                    lambda r: r.url.startswith(API_URL_PREFIX),
                    timeout=15000,
                )
                if resp.status == 200:
                    feed_resp = resp
            except Exception:
                pass

        if not feed_resp:
            browser.close()
            raise RuntimeError(
                "Did not see soccerupcomingmatches request (status 200).")

        text = feed_resp.text()

        if not text or not text.startswith("F|"):
            snippet = text[:200] if text else "EMPTY"
            browser.close()
            raise RuntimeError(
                f"Bet365 feed not in expected format. First bytes: {snippet!r}"
            )

        events = _parse_feed(text)
        browser.close()
        return events
