# run_all.py
from scrapers import novibet  # add more when ready
from models import Event

SCRAPERS = [
    novibet,
    # stoiximan,
    # pamestoixima,
]

def save_events(bookmaker: str, events: list[Event]):
    filepath = f"data/{bookmaker}.ndjson"
    with open(filepath, "w", encoding="utf-8") as f:
        for e in events:
            f.write(e.model_dump_json() + "\n")
    print(f"[✔] Saved {len(events)} events → {filepath}")


def main():
    print("Fetching today's matches from all bookmakers...\n")

    for scraper in SCRAPERS:
        print(f"> {scraper.BOOKMAKER} ...")
        try:
            events = scraper.fetch_today()
            save_events(scraper.BOOKMAKER, events)
        except Exception as e:
            print(f"[ERROR] {scraper.BOOKMAKER}: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
