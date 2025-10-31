"""Application constants and mappings"""

from typing import Dict, List, Optional

# Application info
APP_TITLE = "Elite Mining – Configuration"
APP_VERSION = "v4.3.8"
PRESET_INDENT = "   "

# Firegroup mappings
FIREGROUPS: List[str] = [chr(c) for c in range(ord("A"), ord("H") + 1)]  # A..H
NATO: Dict[str, str] = {
    "A": "Alpha", "B": "Bravo", "C": "Charlie", "D": "Delta",
    "E": "Echo", "F": "Foxtrot", "G": "Golf", "H": "Hotel",
}
NATO_REVERSE: Dict[str, str] = {v.upper(): k for k, v in NATO.items()}  # "ALPHA" -> "A"

# VoiceAttack variable mappings
VA_VARS: Dict[str, Dict[str, Optional[str]]] = {
    "Mining lasers/MVR:": {"fg": "fgLasers", "btn": "btnLasers"},
    "Discovery scanner:": {"fg": "fgDiscoveryScanner", "btn": "btndiscovery"},
    "Prospector limpet:": {"fg": "fgProspector", "btn": "btnprospector"},
    "Pulse wave analyser:": {"fg": "fgPulsewave", "btn": "btnpwa"},
    "Seismic charge launcher:": {"fg": "fgScl", "btn": None},
    "Weapons:": {"fg": "fgWeapons", "btn": None},
    "Sub-surface displacement missile:": {"fg": "fgSsm", "btn": None},
}
VA_TTS_ANNOUNCEMENT = "ttsProspectorAnnouncement"
TOOL_ORDER = list(VA_VARS.keys())

# Announcement Toggles
ANNOUNCEMENT_TOGGLES = {
    "Core Asteroids": (None, "Speak only when a core (motherlode) is detected."),
    "Non-Core Asteroids": (None, "Speak for regular (non-core) prospector results."),
}

# Toggles and Timers
TOGGLES = {
    "Auto Honk": ("toggleHonk.txt", "Enable/disable automatic system honk on entering a new system."),
    "Cargo Scoop": ("cargoScoopToggle.txt", "Retracts the cargo scoop when laser mining is completed."),
    "Headtracker Docking Control": ("toggleHeadtracker.txt", "Enable/disable automatic headtracker docking control (toggles the F9 key)."),
    "Laser Mining Extra": ("laserminingextraToggle.txt", "Adds a second period of laser mining after a pause (see Pause timer)."),
    # "Multi-Session Mode": ("multiSessionMode.txt", "Accumulate statistics across multiple cargo loads without resetting."),  # Removed - only available in Mining Analytics panel
    "Night Vision": ("nightvisionToggle.txt", "Automatically turn on night vision when starting or resetting mining sequence."),
    "Power Settings": ("powersettingsToggle.txt", "Enable = Max power to engines, disable = balance power when laser mining is completed."),
    "Prospector Sequence": ("miningToggle.txt", "Automatically target the prospector after launching it."),
    "Pulse Wave Analyser": ("Pulsewavetoggle.txt", "Switch back to the Pulse Wave Analyser firegroup when laser mining is completed."),
    "Target": ("targetToggle.txt", "Deselect prospector when laser mining is completed."),
}

TIMERS = {
    "Duration for firing mining lasers (first period)": ("delayLaserMining.txt", 1, 50, "Duration for firing mining lasers (first period)."),
    "Pause between laser periods for weapon recharge/cooldown": ("delayPause.txt", 1, 50, "Pause between laser periods for weapon recharge/cooldown (when Laser Mining Extra is enabled)."),
    "Duration for second laser period (If Laser Mining Extra is enabled)": ("delayLaserminingExtra.txt", 1, 50, "Duration for second laser period (when Laser Mining Extra is enabled)."),
    "Delay before selecting prospector target after laser mining": ("delayTarget.txt", 1, 50, "Delay before selecting prospector target after laser mining."),
    "Delay before retracting cargo scoop after mining sequence": ("delayCargoscoop.txt", 1, 50, "Delay before retracting cargo scoop after mining sequence."),
    "Boost Interval (For Core Mining Boost sequense )": ("boostintervalValue.txt", 1, 30, "Interval between boosts when scanning for cores."),
}

# UI Color Schemes
MENU_COLORS = {
    "bg": "#2d2d2d",
    "fg": "#ffffff", 
    "activebackground": "#404040",
    "activeforeground": "#ffffff",
    "selectcolor": "#404040"
}

# Mining Materials Database
MINING_MATERIALS = {
    # Core materials (most common)
    "Painite": {"tier": "core", "typical_yield": "high"},
    "Low Temperature Diamonds": {"tier": "core", "typical_yield": "high"},
    "Void Opals": {"tier": "core", "typical_yield": "high"},
    "Alexandrite": {"tier": "core", "typical_yield": "medium"},
    "Benitoite": {"tier": "core", "typical_yield": "medium"},
    "Bromellite": {"tier": "core", "typical_yield": "medium"},
    "Grandidierite": {"tier": "core", "typical_yield": "medium"},
    "Jadeite": {"tier": "core", "typical_yield": "medium"},
    "Monazite": {"tier": "core", "typical_yield": "medium"},
    "Musgravite": {"tier": "core", "typical_yield": "medium"},
    "Red Beryl": {"tier": "core", "typical_yield": "medium"},
    "Rhodplumsite": {"tier": "core", "typical_yield": "medium"},
    "Serendibite": {"tier": "core", "typical_yield": "medium"},
    
    # Standard materials (laser mining)
    "Platinum": {"tier": "standard", "typical_yield": "high"},
    "Osmium": {"tier": "standard", "typical_yield": "medium"},
    "Gold": {"tier": "standard", "typical_yield": "medium"},
    "Silver": {"tier": "standard", "typical_yield": "medium"},
    "Palladium": {"tier": "standard", "typical_yield": "medium"},
    "Tritium": {"tier": "standard", "typical_yield": "high"},
    "Bauxite": {"tier": "standard", "typical_yield": "medium"},
    "Bertrandite": {"tier": "standard", "typical_yield": "low"},
    "Indite": {"tier": "standard", "typical_yield": "low"},
    "Gallite": {"tier": "standard", "typical_yield": "low"},
    "Coltan": {"tier": "standard", "typical_yield": "low"},
    "Uraninite": {"tier": "standard", "typical_yield": "low"},
    "Lepidolite": {"tier": "standard", "typical_yield": "low"},
    "Cobalt": {"tier": "standard", "typical_yield": "low"},
    "Lithium": {"tier": "standard", "typical_yield": "low"},
    "Titanium": {"tier": "standard", "typical_yield": "low"},
    "Copper": {"tier": "standard", "typical_yield": "low"}
}