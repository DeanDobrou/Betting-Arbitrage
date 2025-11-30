# Betting Arbitrage

A betting arbitrage project for Greek bookmakers, focusing on football matches. This tool scrapes today's football matches from multiple Greek betting sites, matches common events across bookmakers, and will identify arbitrage opportunities in 1X2 markets (home win, draw, away win).

## What is Betting Arbitrage?

Betting arbitrage (also known as sure betting) is a strategy where you place bets on all possible outcomes of an event to guarantee a profit regardless of the result.

## Installation

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/DeanDobrou/Betting-Arbitrage.git
cd betting-arbitrage
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

4. (Optional) Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your preferred settings
```

## Usage

### Running All Scrapers

To fetch today's matches from all bookmakers:

```bash
python run_all.py
```

This will:
- Open browser windows for each bookmaker (non-headless by default)
- Intercept API responses to extract match data
- Save raw events to `data/raw/{bookmaker}.ndjson`
- Display summary of matches fetched from each bookmaker

## How It Works

### 1. Scraping
Each scraper uses Playwright to:
- Open the bookmaker's "today's matches" page
- Intercept API requests containing match data
- Parse the response to extract:
  - Home and away team names
  - Match start time (converted to Athens timezone)
  - League/competition name
  - 1X2 odds (home win, draw, away win)

### 2. Data Storage
- Raw events are saved as newline-delimited JSON (NDJSON)
- Each bookmaker gets a separate file: `{bookmaker}.ndjson`

## License

This project is for educational purposes only. Please ensure you comply with the terms of service of all bookmakers and local gambling regulations.
