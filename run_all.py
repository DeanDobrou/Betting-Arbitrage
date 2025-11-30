from pathlib import Path
from typing import List
from scrapers import novibet, stoiximan, bet365, bwin, pamestoixima
from core.models import Event
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

SCRAPERS = [
    novibet,
    stoiximan,
    bet365,
    bwin,
    pamestoixima,
]


def ensure_data_directories():
    """Create data directories if they don't exist."""
    Path(settings.RAW_DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.MATCHED_DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.OPPORTUNITIES_DIR).mkdir(parents=True, exist_ok=True)


def save_events(bookmaker: str, events: List[Event]):
    """
    Save events to NDJSON file in raw data directory.

    Args:
        bookmaker: Name of the bookmaker
        events: List of events to save
    """
    filepath = Path(settings.RAW_DATA_DIR) / f"{bookmaker}.ndjson"
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            for e in events:
                f.write(e.model_dump_json() + "\n")
        logger.info(f"Saved {len(events)} events for {bookmaker} -> {filepath}")
    except Exception as e:
        logger.error(f"Failed to save events for {bookmaker}: {e}")


def main():
    """Main function to fetch today's matches from all bookmakers."""
    logger.info("Starting scraping process for all bookmakers")
    ensure_data_directories()

    total_events = 0
    successful_scrapers = 0

    for scraper in SCRAPERS:
        logger.info(f"Processing {scraper.BOOKMAKER}...")
        try:
            events = scraper.fetch_today()
            if events:
                save_events(scraper.BOOKMAKER, events)
                total_events += len(events)
                successful_scrapers += 1
            else:
                logger.warning(f"No events found for {scraper.BOOKMAKER}")
        except Exception as e:
            logger.error(f"Failed to scrape {scraper.BOOKMAKER}: {e}", exc_info=True)

    logger.info(f"Scraping completed: {successful_scrapers}/{len(SCRAPERS)} scrapers successful, {total_events} total events")


if __name__ == "__main__":
    main()
