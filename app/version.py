"""
Version management for Elite Mining application
"""

__version__ = "4.3.2"
__build_date__ = "2025-10-17"
__config_version__ = "4.1.7"  # Config schema version - increment when config structure changes

# Update server configuration
UPDATE_CHECK_URL = "https://api.github.com/repos/Viper-Dude/EliteMining/releases/latest"
UPDATE_CHECK_INTERVAL = 24 * 60 * 60  # Check once per day (in seconds)

def get_version():
    """Get current application version"""
    return __version__

def get_build_date():
    """Get build date"""
    return __build_date__

def get_config_version():
    """Get current config schema version"""
    return __config_version__
