import json
import sys
import io
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from config.settings import settings
from utils.webhook import send_to_webhook

# Ensure UTF-8 encoding for Greek text
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def find_best_odds(purified_event: dict) -> Dict[str, dict]:
    """
    Find the best odds for each outcome (1, X, 2) across all bookmakers.

    Returns:
        Dict with keys '1', 'X', '2', each containing:
        - 'odds': the best odds value
        - 'bookmaker': which bookmaker offers it
    """
    best_odds = {
        '1': {'odds': 0.0, 'bookmaker': None},
        'X': {'odds': 0.0, 'bookmaker': None},
        '2': {'odds': 0.0, 'bookmaker': None}
    }

    events = purified_event.get('events', {})

    for bookmaker, event_data in events.items():
        markets = event_data.get('markets', {})
        market_1x2 = markets.get('1x2')

        if not market_1x2:
            continue

        outcomes = market_1x2.get('outcomes', {})

        for outcome in ['1', 'X', '2']:
            odds = outcomes.get(outcome)
            if odds and odds > best_odds[outcome]['odds']:
                best_odds[outcome]['odds'] = odds
                best_odds[outcome]['bookmaker'] = bookmaker

    return best_odds


def calculate_arbitrage(best_odds: Dict[str, dict], total_stake: float = 1000) -> Optional[dict]:
    """
    Calculate if an arbitrage opportunity exists.

    Args:
        best_odds: Dict with best odds for each outcome
        total_stake: Total amount to stake (default 1000 euros)

    Returns:
        None if no arbitrage exists, or dict with:
        - 'arbitrage_percentage': profit margin as percentage
        - 'total_inverse': sum of inverses (< 1 means arbitrage)
        - 'stake_distribution': how to distribute total_stake
        - 'profit': guaranteed profit for total_stake
        - 'unique_bookmakers': number of unique bookmakers needed
        - 'is_executable': whether the arbitrage can actually be executed
    """
    odds_1 = best_odds['1']['odds']
    odds_X = best_odds['X']['odds']
    odds_2 = best_odds['2']['odds']

    # Check if all odds are available
    if not (odds_1 and odds_X and odds_2):
        return None

    # Calculate sum of inverse odds
    total_inverse = (1/odds_1) + (1/odds_X) + (1/odds_2)

    # Arbitrage exists when total_inverse < 1
    if total_inverse >= 1:
        return None

    # Check how many unique bookmakers are needed
    bookmakers_needed = {
        best_odds['1']['bookmaker'],
        best_odds['X']['bookmaker'],
        best_odds['2']['bookmaker']
    }
    unique_bookmakers = len(bookmakers_needed)

    # Arbitrage is only executable if we need at least 2 different bookmakers
    # (Can't bet on multiple outcomes of same event at same bookmaker)
    is_executable = unique_bookmakers >= 2

    # Calculate arbitrage percentage (profit margin)
    arbitrage_percentage = ((1 / total_inverse) - 1) * 100

    # Calculate stake distribution for total_stake
    stake_1 = (1/odds_1) / total_inverse * total_stake
    stake_X = (1/odds_X) / total_inverse * total_stake
    stake_2 = (1/odds_2) / total_inverse * total_stake

    # Calculate guaranteed profit
    profit = (total_stake / total_inverse) - total_stake

    return {
        'arbitrage_percentage': round(arbitrage_percentage, 2),
        'total_inverse': round(total_inverse, 4),
        'stake_distribution': {
            '1': round(stake_1, 2),
            'X': round(stake_X, 2),
            '2': round(stake_2, 2)
        },
        'profit': round(profit, 2),
        'total_stake': total_stake,
        'unique_bookmakers': unique_bookmakers,
        'is_executable': is_executable
    }


def find_all_arbitrage_opportunities(input_file: Path) -> List[dict]:
    """
    Find all arbitrage opportunities in purified events.

    Returns list of arbitrage opportunities with full details.
    """
    opportunities = []

    if not input_file.exists():
        print(f"Error: Input file not found: {input_file}")
        return opportunities

    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                purified_event = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Warning: Invalid JSON on line {line_num}: {e}")
                continue

            # Find best odds across bookmakers
            best_odds = find_best_odds(purified_event)

            # Calculate arbitrage
            arbitrage = calculate_arbitrage(best_odds)

            # Only include executable arbitrage opportunities
            if arbitrage and arbitrage['is_executable']:
                # Extract start time from first available event
                start_time = None
                events = purified_event.get('events', {})
                if events:
                    first_event = next(iter(events.values()))
                    start_time = first_event.get('start')

                opportunity = {
                    'home': purified_event.get('home'),
                    'away': purified_event.get('away'),
                    'start': start_time,
                    'bookmakers': purified_event.get('bookmakers', []),
                    'best_odds': {
                        '1': {
                            'odds': best_odds['1']['odds'],
                            'bookmaker': best_odds['1']['bookmaker']
                        },
                        'X': {
                            'odds': best_odds['X']['odds'],
                            'bookmaker': best_odds['X']['bookmaker']
                        },
                        '2': {
                            'odds': best_odds['2']['odds'],
                            'bookmaker': best_odds['2']['bookmaker']
                        }
                    },
                    'arbitrage_percentage': arbitrage['arbitrage_percentage'],
                    'total_inverse': arbitrage['total_inverse'],
                    'total_stake': arbitrage['total_stake'],
                    'stake_distribution': arbitrage['stake_distribution'],
                    'profit': arbitrage['profit'],
                    'unique_bookmakers': arbitrage['unique_bookmakers'],
                    'is_executable': arbitrage['is_executable']
                }

                opportunities.append(opportunity)

    return opportunities


def main():
    """Main function to find and save arbitrage opportunities."""
    # Paths
    input_file = Path('data/matched/purified_events.ndjson')
    output_dir = Path('data/arbitrage')
    output_file = output_dir / 'opportunities.ndjson'

    print("=" * 60)
    print("ARBITRAGE DETECTION")
    print("=" * 60)
    print()

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find arbitrage opportunities
    print(f"Reading purified events from: {input_file}")
    opportunities = find_all_arbitrage_opportunities(input_file)

    print(f"\nFound {len(opportunities)} arbitrage opportunities!")
    print()

    if opportunities:
        # Sort by arbitrage percentage (highest profit first)
        opportunities.sort(key=lambda x: x['arbitrage_percentage'], reverse=True)

        # Save to file
        with open(output_file, 'w', encoding='utf-8') as f:
            for opp in opportunities:
                f.write(json.dumps(opp, ensure_ascii=False) + '\n')

        print(f"Saved opportunities to: {output_file}")
        print()

        # Send to n8n webhook if configured
        if settings.N8N_WEBHOOK_URL:
            print(f"Sending to n8n webhook: {settings.N8N_WEBHOOK_URL}")
            webhook_success = send_to_webhook(settings.N8N_WEBHOOK_URL, opportunities)
            if webhook_success:
                print(f"✓ Successfully sent {len(opportunities)} opportunities to n8n")
            else:
                print("✗ Failed to send to n8n webhook (check logs)")
            print()
        else:
            print("Note: N8N_WEBHOOK_URL not configured. Set it in .env to enable n8n integration.")
            print()
        print("=" * 60)
        print("TOP ARBITRAGE OPPORTUNITIES")
        print("=" * 60)
        print()

        # Display top 10 opportunities
        for i, opp in enumerate(opportunities[:10], 1):
            total_stake = opp['total_stake']
            unique_bookmakers = opp['unique_bookmakers']
            print(f"{i}. {opp['home']} vs {opp['away']}")
            print(f"   Profit: {opp['arbitrage_percentage']:.2f}% (€{opp['profit']:.2f} per €{total_stake:.0f})")
            print(f"   Bookmakers needed: {unique_bookmakers}")
            print(f"   Best odds:")
            print(f"     1 (Home): {opp['best_odds']['1']['odds']} @ {opp['best_odds']['1']['bookmaker']}")
            print(f"     X (Draw): {opp['best_odds']['X']['odds']} @ {opp['best_odds']['X']['bookmaker']}")
            print(f"     2 (Away): {opp['best_odds']['2']['odds']} @ {opp['best_odds']['2']['bookmaker']}")
            print(f"   Stake distribution (per €{total_stake:.0f} total):")
            print(f"     Bet €{opp['stake_distribution']['1']:.2f} on 1 @ {opp['best_odds']['1']['bookmaker']}")
            print(f"     Bet €{opp['stake_distribution']['X']:.2f} on X @ {opp['best_odds']['X']['bookmaker']}")
            print(f"     Bet €{opp['stake_distribution']['2']:.2f} on 2 @ {opp['best_odds']['2']['bookmaker']}")
            print()
    else:
        print("No arbitrage opportunities found in current data.")
        print()
        print("Note: Arbitrage opportunities are rare and usually have")
        print("very small profit margins (< 1-2%). Also, bookmakers")
        print("may limit accounts that consistently exploit arbitrage.")

    print("=" * 60)


if __name__ == '__main__':
    main()
