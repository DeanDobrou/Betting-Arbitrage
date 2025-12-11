"""
Webhook notification utility for sending arbitrage opportunities to n8n.
"""
import requests
from typing import List, Dict, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


def send_to_webhook(webhook_url: str, opportunities: List[Dict]) -> bool:
    """
    Send arbitrage opportunities to n8n webhook.

    Args:
        webhook_url: The n8n webhook URL
        opportunities: List of arbitrage opportunity dictionaries

    Returns:
        True if successful, False otherwise
    """
    if not webhook_url:
        logger.debug("No webhook URL configured, skipping webhook notification")
        return False

    if not opportunities:
        logger.info("No opportunities to send to webhook")
        return True

    try:
        payload = {
            "count": len(opportunities),
            "opportunities": opportunities
        }

        logger.info(f"Sending {len(opportunities)} opportunities to webhook: {webhook_url}")

        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        if response.status_code == 200:
            logger.info(f"Successfully sent {len(opportunities)} opportunities to n8n webhook")
            return True
        else:
            logger.error(
                f"Webhook request failed with status {response.status_code}: {response.text}"
            )
            return False

    except requests.exceptions.Timeout:
        logger.error(f"Webhook request timed out after 10 seconds: {webhook_url}")
        return False
    except requests.exceptions.ConnectionError:
        logger.error(f"Could not connect to webhook URL: {webhook_url}")
        logger.error("Make sure n8n is running and the webhook is active")
        return False
    except Exception as e:
        logger.error(f"Error sending to webhook: {e}")
        return False


def send_opportunity_to_webhook(webhook_url: str, opportunity: Dict) -> bool:
    """
    Send a single arbitrage opportunity to n8n webhook.

    Args:
        webhook_url: The n8n webhook URL
        opportunity: Single arbitrage opportunity dictionary

    Returns:
        True if successful, False otherwise
    """
    return send_to_webhook(webhook_url, [opportunity])
