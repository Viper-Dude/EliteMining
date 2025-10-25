"""
Discord webhook integration for EliteMining
Allows users to share mining reports to Discord channels via webhooks
"""

import requests
import json
from datetime import datetime
from config import _load_cfg


def get_config_value(key: str, default=None):
    """Helper function to get config values"""
    cfg = _load_cfg()
    return cfg.get(key, default)


def is_discord_enabled() -> bool:
    """Check if Discord integration is enabled and configured"""
    enabled = get_config_value("discord_enabled", False)
    webhook_url = get_config_value("discord_webhook_url", "")
    return enabled and webhook_url.strip() != ""


def validate_webhook_url(url: str) -> bool:
    """Validate that the webhook URL is a valid Discord webhook"""
    if not url or not url.strip():
        return False
    
    url = url.strip()
    return url.startswith("https://discord.com/api/webhooks/") or url.startswith("https://discordapp.com/api/webhooks/")


def format_mining_report_embed(session_data: dict) -> dict:
    """Format mining session data as a Discord embed"""
    
    # Extract data with defaults
    system = session_data.get('system', 'Unknown')
    body = session_data.get('body', 'Unknown')
    duration = session_data.get('duration', '0:00:00')
    tons = session_data.get('tons', '0')
    tph = session_data.get('tph', '0')
    ship = session_data.get('ship', 'Unknown Ship')
    materials = session_data.get('materials', '0')
    hit_rate = session_data.get('hit_rate', '0%')
    quality = session_data.get('quality', '0%')
    date = session_data.get('date', datetime.now().strftime('%Y-%m-%d %H:%M'))
    
    # Create Discord embed
    embed = {
        "title": f"🚀 Elite Mining Report - {system}",
        "description": f"Community mining session completed in **{system}** at **{body}**",
        "color": 0x00ff00 if float(tons.replace('t', '')) > 0 else 0xff6600,  # Green if successful, orange if no mining
        "timestamp": datetime.now().isoformat(),
        "fields": [
            {
                "name": "⏱️ Duration",
                "value": duration,
                "inline": True
            },
            {
                "name": "⚖️ Total Mined",
                "value": f"{tons}",
                "inline": True
            },
            {
                "name": "📈 Rate",
                "value": f"{tph}",
                "inline": True
            },
            {
                "name": "🚢 Ship",
                "value": ship,
                "inline": True
            },
            {
                "name": "💎 Materials",
                "value": f"{materials} types",
                "inline": True
            },
            {
                "name": "🎯 Hit Rate",
                "value": hit_rate,
                "inline": True
            }
        ],
        "footer": {
            "text": "EliteMining Community - Elite Dangerous Mining Assistant",
            "icon_url": "https://raw.githubusercontent.com/Viper-Dude/EliteMining/main/app/Images/EliteMining_Icon_64.png"
        }
    }
    
    # Add quality field if available
    if quality and quality != "0%":
        embed["fields"].append({
            "name": "⭐ Avg Quality",
            "value": quality,
            "inline": True
        })
    
    return embed


def send_discord_report(session_data: dict) -> tuple[bool, str]:
    """
    Send mining report to Discord via webhook
    
    Args:
        session_data: Dictionary containing session information
        
    Returns:
        tuple: (success: bool, message: str)
    """
    
    # Check if Discord is enabled
    if not is_discord_enabled():
        return False, "Discord integration is not enabled or configured"
    
    webhook_url = get_config_value("discord_webhook_url", "")
    
    # Validate webhook URL
    if not validate_webhook_url(webhook_url):
        return False, "Invalid Discord webhook URL"
    
    try:
        # Create embed
        embed = format_mining_report_embed(session_data)
        
        # Prepare Discord payload
        payload = {
            "embeds": [embed],
            "username": "EliteMining Community",
            "avatar_url": "https://raw.githubusercontent.com/Viper-Dude/EliteMining/main/app/Images/EliteMining_Icon_64.png"
        }
        
        # Send to Discord
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        if response.status_code == 204:
            return True, "Report posted to Discord successfully!"
        elif response.status_code == 429:
            return False, "Rate limited by Discord. Please try again later."
        else:
            return False, f"Discord error: {response.status_code}"
            
    except requests.exceptions.Timeout:
        return False, "Request timed out. Check your internet connection."
    except requests.exceptions.RequestException as e:
        return False, f"Network error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


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