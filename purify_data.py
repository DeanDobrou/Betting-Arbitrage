"""
Data purification script - matches events across bookmakers using fuzzy string matching.

This script ONLY handles data purification and matching. Arbitrage detection is separate.

Key features:
- Universal team name normalization (no manual mappings)
- Fuzzy string matching for spelling variations
- Preserves U19/U21/B teams (different teams, not same as parent)
- Time-based matching (events within 15 minutes)
"""
from pathlib import Path
from typing import Dict, List
from datetime import timedelta
from core.models import Event
from core.normalizer import teams_match, normalize_team_name
from core.matcher import load_events_from_ndjson
from config.settings import settings
from utils.logger import get_logger
import json

logger = get_logger(__name__)


class PurifiedEvent:
    """Represents a single football match found across multiple bookmakers."""

    def __init__(self, home: str, away: str, league: str = None):
        self.home = home  # Keep original name from first bookmaker
        self.away = away
        self.league = league
        self.bookmaker_events: Dict[str, Event] = {}

    def add_event(self, event: Event):
        """Add an event from a bookmaker to this purified event."""
        self.bookmaker_events[event.booker] = event

    def get_bookmakers(self) -> List[str]:
        """Get list of bookmakers that have this event."""
        return list(self.bookmaker_events.keys())

    def get_event_for_bookmaker(self, bookmaker: str) -> Event:
        """Get the event from a specific bookmaker."""
        return self.bookmaker_events.get(bookmaker)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "home": self.home,
            "away": self.away,
            "league": self.league,
            "bookmakers": self.get_bookmakers(),
            "events": {
                booker: {
                    "event_id": event.event_id,
                    "home_original": event.home,
                    "away_original": event.away,
                    "start": event.start.isoformat(),
                    "markets": {
                        market_key: {
                            "outcomes": market.outcomes
                        }
                        for market_key, market in event.markets.items()
                    }
                }
                for booker, event in self.bookmaker_events.items()
            }
        }

    def __repr__(self):
        return f"PurifiedEvent({self.home} vs {self.away}, bookmakers={self.get_bookmakers()})"


def events_match(event1: Event, event2: Event,
                 time_threshold_minutes: int = 15,
                 similarity_threshold: int = 65) -> bool:
    """
    Check if two events represent the same football match.

    Args:
        event1: First event
        event2: Second event
        time_threshold_minutes: Max time difference in minutes
        similarity_threshold: Fuzzy matching threshold (0-100)

    Returns:
        True if events match, False otherwise
    """
    # Check if start times are close enough
    time_diff = abs(event1.start - event2.start)
    if time_diff > timedelta(minutes=time_threshold_minutes):
        return False

    # Use fuzzy matching for team names
    home_match = teams_match(event1.home, event2.home,
                             threshold=similarity_threshold)
    away_match = teams_match(event1.away, event2.away,
                             threshold=similarity_threshold)

    return home_match and away_match


def purify_events(events_by_bookmaker: Dict[str, List[Event]],
                  time_threshold: int = 15,
                  similarity_threshold: int = 65) -> List[PurifiedEvent]:
    """
    Match and purify events across multiple bookmakers.

    Args:
        events_by_bookmaker: Dictionary mapping bookmaker name to list of events
        time_threshold: Maximum time difference in minutes to consider same match
        similarity_threshold: Minimum team name similarity (0-100)

    Returns:
        List of purified events found in at least 3 bookmakers (required for arbitrage)
    """
    purified_events: List[PurifiedEvent] = []
    processed_indices: Dict[str, set] = {
        bookmaker: set() for bookmaker in events_by_bookmaker.keys()
    }

    if not events_by_bookmaker:
        return purified_events

    # Use bookmaker with most events as reference (more likely to find matches)
    bookmaker_names = sorted(events_by_bookmaker.keys(),
                             key=lambda x: len(events_by_bookmaker[x]),
                             reverse=True)

    first_bookmaker = bookmaker_names[0]
    first_events = events_by_bookmaker[first_bookmaker]

    logger.info(
        f"Starting purification with {len(first_events)} events from {first_bookmaker}")
    logger.info(f"Bookmaker order (sorted by event count): {bookmaker_names}")

    for i, event1 in enumerate(first_events):
        if i in processed_indices[first_bookmaker]:
            continue

        # Create a new purified event
        purified = PurifiedEvent(
            home=event1.home,
            away=event1.away,
            league=event1.league
        )
        purified.add_event(event1)
        processed_indices[first_bookmaker].add(i)

        # Try to find matches in ALL other bookmakers (not just first match)
        for bookmaker in bookmaker_names[1:]:
            events = events_by_bookmaker[bookmaker]

            for j, event2 in enumerate(events):
                if j in processed_indices[bookmaker]:
                    continue

                if events_match(event1, event2, time_threshold, similarity_threshold):
                    purified.add_event(event2)
                    processed_indices[bookmaker].add(j)

                    logger.debug(
                        f"Matched: {event1.booker} '{event1.home}' vs {event2.booker} '{event2.home}' "
                        f"(normalized: '{normalize_team_name(event1.home)}')"
                    )
                    # DO NOT break - continue searching for matches in remaining bookmakers

        # Only include if found in at least 3 bookmakers (required for arbitrage)
        if len(purified.get_bookmakers()) >= 3:
            purified_events.append(purified)
            logger.info(
                f"Purified event across {len(purified.get_bookmakers())} bookmakers: "
                f"{purified.home} vs {purified.away}"
            )

    return purified_events


def main():
    """Main function to purify data from all bookmakers."""
    logger.info("Starting data purification process")

    # Load events from all bookmakers
    raw_data_dir = Path(settings.RAW_DATA_DIR)
    events_by_bookmaker: Dict[str, List[Event]] = {}

    for ndjson_file in raw_data_dir.glob("*.ndjson"):
        bookmaker = ndjson_file.stem
        events = load_events_from_ndjson(str(ndjson_file))

        if events:
            events_by_bookmaker[bookmaker] = events
            logger.info(f"Loaded {len(events)} events from {bookmaker}")

    if not events_by_bookmaker:
        logger.error("No events found to purify")
        return

    # Purify events across bookmakers
    logger.info(
        f"Purifying events across {len(events_by_bookmaker)} bookmakers")
    purified_events = purify_events(
        events_by_bookmaker,
        time_threshold=15,  # 15 minutes
        similarity_threshold=65  # 65% similarity
    )

    logger.info(
        f"Found {len(purified_events)} purified events across bookmakers")

    # Save purified events
    output_dir = Path(settings.MATCHED_DATA_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "purified_events.ndjson"

    with open(output_file, "w", encoding="utf-8") as f:
        for purified in purified_events:
            f.write(json.dumps(purified.to_dict(), ensure_ascii=False) + "\n")

    logger.info(
        f"Saved {len(purified_events)} purified events to {output_file}")

    # Print summary statistics
    print("\n" + "=" * 80)
    print("DATA PURIFICATION SUMMARY")
    print("=" * 80)
    print(f"\nTotal bookmakers: {len(events_by_bookmaker)}")

    print("\nEvents per bookmaker:")
    for bookmaker, events in events_by_bookmaker.items():
        print(f"  {bookmaker}: {len(events)} events")

    print(
        f"\nPurified events (found in 3+ bookmakers): {len(purified_events)}")

    # Show distribution by number of bookmakers
    bookmaker_counts = {}
    for purified in purified_events:
        count = len(purified.get_bookmakers())
        bookmaker_counts[count] = bookmaker_counts.get(count, 0) + 1

    print("\nDistribution by bookmaker coverage:")
    for count in sorted(bookmaker_counts.keys(), reverse=True):
        print(f"  {count} bookmakers: {bookmaker_counts[count]} events")

    # Show sample purified events
    if purified_events:
        print("\nSample purified events (first 5):")
        for i, purified in enumerate(purified_events[:5], 1):
            print(f"\n  {i}. {purified.home} vs {purified.away}")
            print(f"     League: {purified.league}")
            print(f"     Bookmakers: {', '.join(purified.get_bookmakers())}")

            # Show original names and odds from each bookmaker
            print(f"     Bookmaker details:")
            for booker in purified.get_bookmakers():
                event = purified.get_event_for_bookmaker(booker)
                odds_1x2 = event.markets.get("1x2")
                if odds_1x2:
                    odds_str = f"1={odds_1x2.outcomes['1']:.2f} X={odds_1x2.outcomes['X']:.2f} 2={odds_1x2.outcomes['2']:.2f}"
                else:
                    odds_str = "No 1X2 market"
                print(
                    f"       {booker}: {event.home} vs {event.away} ({odds_str})")

    print("\n" + "=" * 80)
    print(f"\nPurified data saved to: {output_file}")
    print("Next step: Run arbitrage detection on purified events")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
