"""
Discord webhook integration for EliteMining
Allows users to share mining reports to Discord channels via webhooks
"""

import json
import re
import requests
from datetime import datetime
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


def extract_ship_type(full_ship_name: str) -> str:
    """Extract ship type from full ship name"""
    if not full_ship_name or full_ship_name == "Unknown Ship":
        return "Unknown Ship"
    
    # Ship names are typically: "Name - Ship Type"
    # Examples: 
    # "Mega Bumper - Type-11 Prospector" -> "Type-11 Prospector"
    # "Grabber - Imperial Cutter" -> "Imperial Cutter"
    
    if " - " in full_ship_name:
        parts = full_ship_name.split(" - ", 1)  # Split on first " - " only
        if len(parts) == 2:
            return parts[1].strip()  # Return the ship type part
    
    # If no " - " separator, return the full name as fallback
    return full_ship_name


def get_material_breakdown(session_data: dict) -> str:
    """Extract material breakdown from session data"""
    import re
    
    try:
        # First try to get from materials_breakdown field (preferred - has tonnage and yields)
        materials_breakdown = session_data.get('materials_breakdown', '').strip()
        if materials_breakdown and materials_breakdown != '—':
            # Format: "Platinum: 225.0t (15.2%/64.9t/h); Bromellite: 240.0t (18.7%/506.5t/h)"
            # Convert to more readable format
            materials = []
            if ';' in materials_breakdown:
                # Multiple materials separated by semicolons
                for material_info in materials_breakdown.split(';'):
                    material_info = material_info.strip()
                    if ':' in material_info and 't (' in material_info:
                        # Parse "Platinum: 225.0t (15.2%/64.9t/h)"
                        name = material_info.split(':')[0].strip()
                        # Get the part after the colon
                        after_colon = material_info.split(':', 1)[1].strip()
                        # Extract tonnage and rate
                        if 't (' in after_colon and 't/h)' in after_colon:
                            tons = after_colon.split('t (')[0].strip()
                            # Extract rate: from "(15.2%/64.9t/h)" get "64.9t/h"
                            rate_section = after_colon.split('t (')[1]  # "15.2%/64.9t/h)"
                            # Find the t/h part - look for pattern like "64.9t/h)"
                            rate_match = re.search(r'(\d+\.?\d*)t/h\)', rate_section)
                            if rate_match:
                                rate_value = rate_match.group(1)
                                materials.append(f"{name} {tons}t @ {rate_value} t/hr")
                            else:
                                materials.append(f"{name} {tons}t")
                        else:
                            materials.append(material_info.strip())
            else:
                # Single material or different format
                if ':' in materials_breakdown and 't (' in materials_breakdown:
                    name = materials_breakdown.split(':')[0].strip()
                    after_colon = materials_breakdown.split(':', 1)[1].strip()
                    if 't (' in after_colon and 't/h)' in after_colon:
                        tons = after_colon.split('t (')[0].strip()
                        rate_section = after_colon.split('t (')[1]
                        rate_match = re.search(r'(\d+\.?\d*)t/h\)', rate_section)
                        if rate_match:
                            rate_value = rate_match.group(1)
                            materials.append(f"{name} {tons}t @ {rate_value} t/hr")
                        else:
                            materials.append(f"{name} {tons}t")
                else:
                    materials.append(materials_breakdown)
            
            if materials:
                return '\n'.join(materials)
        
        # Fallback: try to get from cargo field
        cargo_info = session_data.get('cargo', '').strip()
        if cargo_info and cargo_info != '—':
            return cargo_info.replace('; ', '\n')
        
        # Last resort: try to parse from report content
        report_content = session_data.get('report_content', '')
        if report_content and "REFINED MINERALS" in report_content:
            lines = report_content.split('\n')
            materials = []
            in_minerals_section = False
            
            for line in lines:
                line = line.strip()
                if "=== REFINED MINERALS ===" in line:
                    in_minerals_section = True
                    continue
                elif "===" in line and in_minerals_section:
                    break
                elif in_minerals_section and line and not line.startswith("="):
                    if " - " in line and "t (" in line:
                        # Parse line like "- Platinum 225t (1321.43 t/hr)"
                        material_part = line.replace("- ", "").strip()
                        if "t (" in material_part:
                            name_tons = material_part.split("t (")[0]
                            rate_part = material_part.split("t (")[1].replace(")", "")
                            materials.append(f"{name_tons}t @ {rate_part}")
            
            if materials:
                return '\n'.join(materials)
        
        # Return empty string if no material data found
        return ""
        
    except Exception as e:
        print(f"[DEBUG] Error extracting material breakdown: {e}")
        return ""


def parse_mineral_performance_from_report(report_content: str) -> dict:
    """Extract mineral performance stats (tons, hits, tons/asteroid) from a report"""
    if not report_content:
        return {}

    performance = {}
    in_analysis = False
    in_performance = False
    current_material = None

    for line in report_content.splitlines():
        stripped = line.strip()
        if not in_analysis:
            if "=== MINERAL ANALYSIS ===" in line:
                in_analysis = True
            continue

        if not in_performance:
            if "--- Mineral Performance ---" in line:
                in_performance = True
            continue

        if stripped.startswith("===") and "MINERAL ANALYSIS" not in stripped:
            break

        if stripped.endswith(":") and not stripped.startswith("•"):
            current_material = stripped.rstrip(":")
            performance[current_material] = {"tons": None, "hits": None, "tons_per_hit": None}
            continue

        if not current_material or not stripped.startswith("•"):
            continue

        value_part = stripped.split(":", 1)[1].strip() if ":" in stripped else ""

        if "Tons/Hit" in stripped or "Tons/Asteroid" in stripped:
            match = re.search(r"(\d+\.?\d*)", value_part)
            if match:
                try:
                    performance[current_material]["tons_per_hit"] = float(match.group(1))
                except Exception:
                    pass
        elif "Tons:" in stripped and "t" in value_part:
            tons_match = re.search(r"(\d+\.?\d*)", value_part)
            if tons_match:
                try:
                    performance[current_material]["tons"] = float(tons_match.group(1))
                except Exception:
                    pass
        elif "Hits:" in stripped or "Finds:" in stripped:
            hits_match = re.search(r"(\d+)", value_part)
            if hits_match:
                try:
                    performance[current_material]["hits"] = int(hits_match.group(1))
                except Exception:
                    pass

    return performance


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


def format_mining_report_embed(session_data: dict) -> dict:
    """Format mining session data as a Discord embed"""
    
    # Extract data with defaults
    system = session_data.get('system', 'Unknown')
    body = session_data.get('body', 'Unknown')
    duration = session_data.get('duration', '0:00:00')
    tons = session_data.get('tons', '0')
    tph = session_data.get('tph', '0')
    full_ship_name = session_data.get('ship_name', session_data.get('ship', 'Unknown Ship'))  # Get full ship name
    ship_type = extract_ship_type(full_ship_name)  # Extract just the ship type
    materials = session_data.get('materials', '0')
    hit_rate = session_data.get('hit_rate', '0%')
    quality = session_data.get('quality', '0%')
    date = session_data.get('date', datetime.now().strftime('%Y-%m-%d %H:%M'))
    discord_username = session_data.get('discord_username', 'Anonymous Miner')
    discord_comment = session_data.get('discord_comment', '')
    prospectors_used = session_data.get('prospectors_used', session_data.get('prospects', '0'))
    asteroids_prospected = '0'  # Default value for asteroids prospected
    
    # If we have report content, try to extract both values from it
    if 'report_content' in session_data and session_data['report_content']:
        import re
        report_content = session_data['report_content']
        
        # Extract "Prospector Limpets Used: X" from CARGO MATERIAL BREAKDOWN section
        limpets_match = re.search(r'Prospector Limpets Used:\s*(\d+)', report_content)
        if limpets_match:
            prospectors_used = limpets_match.group(1)
        
        # Extract "Asteroids Prospected: X" from MINERAL ANALYSIS section
        asteroids_match = re.search(r'Asteroids Prospected:\s*(\d+)', report_content)
        if asteroids_match:
            asteroids_prospected = asteroids_match.group(1)
    
    # Get material breakdown from session data
    material_breakdown = get_material_breakdown(session_data)
    
    # Compute derived total hits and tons per asteroid where possible
    def _derive_hits(sd: dict):
        # Prefer explicit total_finds, else derive from asteroids_prospected * hit_rate
        total = sd.get('total_finds')
        try:
            if total not in (None, '', '—'):
                val = int(float(str(total).strip()))
                # If explicit is 0, try to derive
                if val > 0:
                    return val
        except Exception:
            pass
        # Derive
        try:
            ap = sd.get('asteroids_prospected') or sd.get('asteroids') or sd.get('prospects')
            hr = sd.get('hit_rate') or sd.get('hit_rate_percent')
            if ap is None or ap == '' or hr is None or hr == '':
                return None
            ap_int = int(str(ap).strip())
            hr_val = float(str(hr).replace('%', '').strip())
            derived = int(round(ap_int * (hr_val / 100.0)))
            return derived if derived > 0 else None
        except Exception:
            return None

    def _compute_tpa(sd: dict, hits: int | None):
        try:
            total_raw = sd.get('total_tons') if sd.get('total_tons') is not None else sd.get('tons') if sd.get('tons') is not None else sd.get('total') if sd.get('total') is not None else 0
            total = float(str(total_raw).replace('t', '').replace(',', '').strip())
            if hits and hits > 0:
                return total / hits
            # fallback to asteroids prospected
            ap = sd.get('asteroids_prospected') or sd.get('asteroids') or sd.get('prospects')
            try:
                ap_int = int(str(ap).strip())
            except Exception:
                ap_int = 0
            if ap_int > 0:
                return total / ap_int
            return None
        except Exception:
            return None

    total_hits_derived = _derive_hits(session_data)
    tons_per_asteroid = _compute_tpa(session_data, total_hits_derived)

    # Include computed values in the session data for portability/use in embeds
    if total_hits_derived is not None:
        session_data['total_finds'] = total_hits_derived
    if tons_per_asteroid is not None:
        session_data['tons_per'] = f"{tons_per_asteroid:.1f}t"

    # Build description with username, optional comment, and material breakdown
    description = f"System/Ring: **{system}** at **{body}**\n\n**Shared by:** {discord_username}"
    if discord_comment:
        description += f"\n**Comment:** {discord_comment}"
    
    if material_breakdown:
        description += f"\n\n**Materials Mined:**\n{material_breakdown}"
    
    mineral_perf_stats = parse_mineral_performance_from_report(session_data.get('report_content', ''))
    perf_lines = []
    for name, stats in mineral_perf_stats.items():
        details = []
        tons = stats.get('tons')
        if tons is not None:
            details.append(f"{tons:.1f}t")
        tons_per_hit = stats.get('tons_per_hit')
        hits = stats.get('hits')
        if tons_per_hit is None and hits and tons is not None:
            try:
                tons_per_hit = tons / hits
            except Exception:
                tons_per_hit = None
        if tons_per_hit is not None:
            details.append(f"{tons_per_hit:.2f} t/asteroid")
        if details:
            perf_lines.append(f"{name}: {' | '.join(details)}")
    if perf_lines:
        description += "\n\n**Mineral Performance**\n" + "\n".join(perf_lines)

    # Create Discord embed
    try:
        tons_value = float(str(tons).replace('t', ''))
    except Exception:
        tons_value = 0.0
    embed = {
        "title": f"Elite Mining Report - {system}",
        "description": description,
        "color": 0x00ff00 if tons_value > 0 else 0xff6600,  # Green if successful, orange if no mining
        "timestamp": datetime.now().isoformat(),
        "fields": [
            {
                "name": "Duration",
                "value": duration,
                "inline": True
            },
            {
                "name": "Total Mined",
                "value": f"{tons} tons",
                "inline": True
            },
            {
                "name": "Rate",
                "value": f"{tph} t/hr",
                "inline": True
            },
            {
                "name": "Ship",
                "value": ship_type,
                "inline": True
            },
            {
                "name": "Minerals",
                "value": f"{materials} types",
                "inline": True
            },
            {
                "name": "Prospected",
                "value": str(prospectors_used),
                "inline": True
            },
            {
                "name": "Asteroids Prospected",
                "value": str(asteroids_prospected),
                "inline": True
            },
            {
                "name": "Hit Rate (% Above Min Threshold)",
                "value": hit_rate,
                "inline": True
            }
            ,
            {
                "name": "Total Asteroids Mined",
                "value": str(session_data.get('total_finds', '—')),
                "inline": True
            },
            {
                "name": "Tons/Asteroid",
                "value": str(session_data.get('tons_per', '—')),
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
            "name": "Avg Quality (All Prospected Asteroids)",
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
    
    # Use hardcoded webhook URL
    webhook_url = DISCORD_WEBHOOK_URL
    
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