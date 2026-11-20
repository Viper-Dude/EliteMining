"""
Discord webhook integration for EliteMining
Allows users to share mining reports to Discord channels via webhooks
"""

import json
import os
import requests
from config import _load_cfg

# Import webhook URL from separate secrets file (not committed to git)
try:
    from discord_secrets import DISCORD_WEBHOOK_URL
except ImportError:
    # Fallback if secrets file doesn't exist
    DISCORD_WEBHOOK_URL = ""


def get_config_value(key: str, default=None):
    """Helper function to get config values"""
    cfg = _load_cfg()
    return cfg.get(key, default)


def is_discord_enabled() -> bool:
    """Check if Discord integration is enabled and configured"""
    # Always enabled since webhook is hardcoded
    return True


def validate_webhook_url(url: str) -> bool:
    """Validate that the webhook URL is a valid Discord webhook"""
    if not url or not url.strip():
        return False
    
    url = url.strip()
    return url.startswith("https://discord.com/api/webhooks/") or url.startswith("https://discordapp.com/api/webhooks/")


def send_mining_card(card_path: str, content: str = "") -> tuple[bool, str]:
    """Post a mining card PNG with a message to the mining reports channel."""
    webhook_url = DISCORD_WEBHOOK_URL
    if not validate_webhook_url(webhook_url):
        return False, "Invalid Discord webhook URL"
    try:
        with open(card_path, 'rb') as fh:
            response = requests.post(
                webhook_url,
                data={"payload_json": json.dumps({
                    "username": "EliteMining Community",
                    "avatar_url": "https://raw.githubusercontent.com/Viper-Dude/EliteMining/main/app/Images/EliteMining_Icon_64.png",
                    "content": content,
                })},
                files={"file": (os.path.basename(card_path), fh, "image/png")},
                timeout=15
            )
        if response.status_code in (200, 204):
            return True, "Card posted to Discord"
        return False, f"Discord error: {response.status_code}"
    except (OSError, requests.exceptions.RequestException) as e:
        return False, f"Could not post card: {e}"


def test_discord_webhook(webhook_url: str) -> tuple[bool, str]:
    """
    Test a Discord webhook URL
    
    Args:
        webhook_url: The webhook URL to test
        
    Returns:
        tuple: (success: bool, message: str)
    """
    
    if not validate_webhook_url(webhook_url):
        return False, "Invalid Discord webhook URL format"
    
    try:
        # Send test message
        test_payload = {
            "content": "🧪 **EliteMining Discord Test**\n\nWebhook is working correctly! You can now share mining reports to this channel.",
            "username": "EliteMining",
            "avatar_url": "https://raw.githubusercontent.com/Viper-Dude/EliteMining/main/app/Images/EliteMining_Icon_64.png"
        }
        
        response = requests.post(
            webhook_url,
            json=test_payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 204:
            return True, "Webhook test successful!"
        elif response.status_code == 429:
            return False, "Rate limited by Discord. Please try again later."
        else:
            return False, f"Test failed: HTTP {response.status_code}"
            
    except requests.exceptions.Timeout:
        return False, "Request timed out. Check your internet connection."
    except requests.exceptions.RequestException as e:
        return False, f"Network error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"