from typing import List, Dict, Set
from datetime import timedelta
from core.models import Event
import logging

logger = logging.getLogger(__name__)


class MatchedEvent:
    """Represents a single football match found across multiple bookmakers."""

    def __init__(self, home: str, away: str, league: str = None):
        self.home = home
        self.away = away
        self.league = league
        self.bookmaker_events: Dict[str, Event] = {}

    def add_event(self, event: Event):
        """Add an event from a bookmaker to this matched event."""
        self.bookmaker_events[event.booker] = event

    def get_bookmakers(self) -> Set[str]:
        """Get set of bookmakers that have this event."""
        return set(self.bookmaker_events.keys())

    def get_event_for_bookmaker(self, bookmaker: str) -> Event:
        """Get the event from a specific bookmaker."""
        return self.bookmaker_events.get(bookmaker)

    def has_complete_1x2_markets(self) -> bool:
        """Check if all bookmaker events have complete 1X2 markets."""
        for event in self.bookmaker_events.values():
            market = event.markets.get("1x2")
            if not market:
                return False
            if not all(k in market.outcomes for k in ["1", "X", "2"]):
                return False
        return True

    def __repr__(self):
        return f"MatchedEvent({self.home} vs {self.away}, bookmakers={list(self.get_bookmakers())})"


class EventMatcher:
    """Matches events across multiple bookmakers using simple string matching."""

    def __init__(self, time_threshold_minutes: int = 15):
        """
        Initialize the event matcher.

        Args:
            time_threshold_minutes: Max time difference to consider events as same match
        """
        self.time_threshold = timedelta(minutes=time_threshold_minutes)

    def events_match(self, event1: Event, event2: Event) -> bool:
        """
        Check if two events represent the same football match.

        Args:
            event1: First event
            event2: Second event

        Returns:
            True if events match, False otherwise
        """
        # Check if start times are close enough
        time_diff = abs(event1.start - event2.start)
        if time_diff > self.time_threshold:
            return False

        # Simple case-insensitive string matching for team names
        if event1.home.lower().strip() != event2.home.lower().strip():
            return False

        if event1.away.lower().strip() != event2.away.lower().strip():
            return False

        return True

    def match_events(self, events_by_bookmaker: Dict[str, List[Event]]) -> List[MatchedEvent]:
        """
        Match events across multiple bookmakers.

        Args:
            events_by_bookmaker: Dictionary mapping bookmaker name to list of events

        Returns:
            List of matched events found in at least 2 bookmakers
        """
        matched_events: List[MatchedEvent] = []
        processed_indices: Dict[str, Set[int]] = {
            bookmaker: set() for bookmaker in events_by_bookmaker.keys()
        }

        bookmaker_names = list(events_by_bookmaker.keys())

        # Iterate through first bookmaker's events
        if not bookmaker_names:
            return matched_events

        first_bookmaker = bookmaker_names[0]
        first_events = events_by_bookmaker[first_bookmaker]

        for i, event1 in enumerate(first_events):
            if i in processed_indices[first_bookmaker]:
                continue

            # Create a new matched event
            matched = MatchedEvent(
                home=event1.home,
                away=event1.away,
                league=event1.league
            )
            matched.add_event(event1)
            processed_indices[first_bookmaker].add(i)

            # Try to find matches in other bookmakers
            for bookmaker in bookmaker_names[1:]:
                events = events_by_bookmaker[bookmaker]

                for j, event2 in enumerate(events):
                    if j in processed_indices[bookmaker]:
                        continue

                    if self.events_match(event1, event2):
                        matched.add_event(event2)
                        processed_indices[bookmaker].add(j)
                        logger.debug(f"Matched: {event1.booker} vs {event2.booker} - {event1.home} vs {event1.away}")
                        break

            # Only include if found in at least 2 bookmakers
            if len(matched.get_bookmakers()) >= 2:
                matched_events.append(matched)
                logger.info(f"Match found across {len(matched.get_bookmakers())} bookmakers: {matched.home} vs {matched.away}")

        return matched_events

    def filter_complete_markets(self, matched_events: List[MatchedEvent]) -> List[MatchedEvent]:
        """
        Filter matched events to only include those with complete 1X2 markets.

        Args:
            matched_events: List of matched events

        Returns:
            Filtered list with only complete markets
        """
        complete = [me for me in matched_events if me.has_complete_1x2_markets()]
        logger.info(f"Filtered {len(complete)}/{len(matched_events)} events with complete 1X2 markets")
        return complete


def load_events_from_ndjson(filepath: str) -> List[Event]:
    """
    Load events from NDJSON file.

    Args:
        filepath: Path to NDJSON file

    Returns:
        List of Event objects
    """
    events = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    event = Event.model_validate_json(line)
                    events.append(event)
    except FileNotFoundError:
        logger.warning(f"File not found: {filepath}")
    except Exception as e:
        logger.error(f"Error loading events from {filepath}: {e}")

    return events
