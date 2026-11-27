"""
Renamed VoiceAttack commands: old CommandString -> new CommandString.
Add an entry whenever a release renames an existing command, so players keep its bindings.
"""

COMMAND_RENAMES = {
    "Say [Toggle;status] for Power settings;Check power settings status;"
    "What is the power settings status": (
        "Say settings for power;Say power setting;Say power settings;"
        "Check power settings;Check power settings status;What are my power settings"
    ),
    "Set Toggle for power settings to [0..1];Enable power settings;"
    "Disable power settings;Turn on power settings;Turn off power settings": (
        "Set power settings to balanced power;Set power settings to balanced;"
        "Set power setting to balanced;Set power settings to maximum power;"
        "Set power settings to max engines;"
        "Set power settings to maximum power to engines;"
        "Set power setting to max engines;"
        "Set power settings to maximum power to shields;"
        "Set power settings to max shields;"
        "Set power settings to maximum power to systems;"
        "Set power setting to max shields"
    ),
    "Set toggle for deselect prospector to [0..1];"
    "Set toggle for auto deselect prospector to [0..1];Enable prospector deselection;"
    "Disable prospector deselection;Turn on prospector deselection;"
    "Turn off prospector deselection": (
        "Enable auto deselect prospector;Disable auto deselect prospector;"
        "Enable prospector deselection;Disable prospector deselection;"
        "Turn on prospector deselection;Turn off prospector deselection"
    ),
    "Set Toggle for pulse wave analyser to [0..1];Enable pulse wave analyser;"
    "Disable pulse wave analyser;Turn on pulse wave analyser;Turn off pulse wave analyser": (
        "Enable return to pulse wave analyser;Disable return to pulse wave analyser;"
        "Enable pulse wave analyser;Disable pulse wave analyser;Turn on pulse wave analyser;"
        "Turn off pulse wave analyser"
    ),
    "Set Toggle for prospector target to [0..1];Set Toggle for target prospector to [0..1];"
    "Enable prospector targeting;Disable prospector targeting;Turn on prospector targeting;"
    "Turn off prospector targeting": (
        "Enable target prospector;Disable target prospector;Enable prospector targeting;"
        "Disable prospector targeting;Turn on prospector targeting;"
        "Turn off prospector targeting"
    ),
    "Set Toggle for nightvision to [0..1];Enable night vision;Disable night vision;"
    "Turn on night vision;Turn off night vision": (
        "Enable auto night vision;Disable auto night vision;Enable night vision;"
        "Disable night vision;Turn on night vision;Turn off night vision"
    ),
    "Set Toggle for mining cycles to [0..1];"
    "Set Toggle for repeated mining cycles to [0..1];Enable repeated mining cycles;"
    "Disable repeated mining cycles;Turn on repeated mining cycles;"
    "Turn off repeated mining cycles": (
        "Enable repeated mining cycles;Disable repeated mining cycles;Enable mining cycles;"
        "Disable mining cycles;Turn on repeated mining cycles;Turn off repeated mining cycles"
    ),
    "Set Toggle for Headtracker to [0..1];Enable headtracker docking control;"
    "Disable headtracker docking control;Turn on headtracker docking control;"
    "Turn off headtracker docking control": (
        "Enable headtracker docking control;Disable headtracker docking control;"
        "Enable headtracker;Disable headtracker;Turn on headtracker docking control;"
        "Turn off headtracker docking control"
    ),
    "Set Toggle for cargo scoop to [0..1];Enable cargo scoop;Disable cargo scoop;"
    "Turn on cargo scoop;Turn off cargo scoop": (
        "Enable retraction of cargo scoop;Disable retraction of cargo scoop;"
        "Enable cargo scoop retraction;Disable cargo scoop retraction;Enable cargo scoop;"
        "Disable cargo scoop;Turn on cargo scoop;Turn off cargo scoop"
    ),
    "Enable Autohonk;Turn on auto honk": (
        "Enable auto honk;Turn on auto honk"
    ),
    "Disable Autohonk;Turn off auto honk": (
        "Disable auto honk;Turn off auto honk"
    ),
    "Set Toggle for FSD Jump Sequence to [0..1];Enable FSD jump sequence;"
    "Disable FSD jump sequence;Turn on FSD jump sequence;Turn off FSD jump sequence": (
        "Enable FSD jump sequence;Disable FSD jump sequence;Enable auto jump;Disable auto jump;"
        "Turn on FSD jump sequence;Turn off FSD jump sequence"
    ),
    "Set Toggle for FSD Jump Sequence System map to [0..1];Enable jump sequence system map;"
    "Disable jump sequence system map;Turn on jump sequence system map;"
    "Turn off jump sequence system map": (
        "Enable open system map;Disable open system map;Enable jump sequence system map;"
        "Disable jump sequence system map;Turn on jump sequence system map;"
        "Turn off jump sequence system map"
    ),
    "Set Toggle for thrust up to [0..1];Enable thrust up;Disable thrust up;"
    "Turn on thrust up;Turn off thrust up": (
        "Enable thrust up;Disable thrust up;Turn on thrust up;Turn off thrust up"
    ),
    "Set Toggle for prospector sequence to [0..1];Enable prospector sequence;"
    "Disable prospector sequence;Turn on prospector sequence;Turn off prospector sequence": (
        "Enable prospector sequence;Disable prospector sequence;Turn on prospector sequence;"
        "Turn off prospector sequence"
    ),
    "Set Toggle for prospector sound effect to [0..1];Enable prospector sound effect;"
    "Disable prospector sound effect;Turn on prospector sound effect;"
    "Turn off prospector sound effect": (
        "Enable prospector sound effect;Disable prospector sound effect;"
        "Turn on prospector sound effect;Turn off prospector sound effect"
    ),
    "Set Toggle for Continuous pulse wave analyser to [0..1];"
    "Enable continuous pulse wave analyser;Disable continuous pulse wave analyser;"
    "Turn on continuous pulse wave analyser;Turn off continuous pulse wave analyser": (
        "Enable continuous pulse wave analyser;Disable continuous pulse wave analyser;"
        "Turn on continuous pulse wave analyser;Turn off continuous pulse wave analyser"
    ),
    "Set Toggle for Continuous prospector sequence to [0..1];"
    "Enable continuous prospector sequence;Disable continuous prospector sequence;"
    "Turn on continuous prospector sequence;Turn off continuous prospector sequence": (
        "Enable continuous prospector sequence;Disable continuous prospector sequence;"
        "Turn on continuous prospector sequence;Turn off continuous prospector sequence"
    ),
    "Say Toggle for auto deselect prospector;Say Toggle for deselect prospector;"
    "Check prospector deselection status;What is the prospector deselection status;"
    "Say status for prospector deselection": (
        "Say settings for auto deselect prospector;Settings for auto deselect prospector;"
        "Say settings for prospector deselection;Check prospector deselection status;"
        "What is the prospector deselection status;Say status for prospector deselection"
    ),
    "Say Toggle for pulse wave Analyser;Say Toggle for pulse wave;"
    "Check pulse wave analyser status;What is the pulse wave analyser status;"
    "Say status for pulse wave analyser": (
        "Say settings for pulse wave analyser;Settings for pulse wave analyser;"
        "Check pulse wave analyser status;What is the pulse wave analyser status;"
        "Say status for pulse wave analyser"
    ),
    "Say Toggle for Prospector Target;Say Toggle for target prospector;"
    "Check prospector targeting status;What is the prospector targeting status;"
    "Say status for prospector targeting": (
        "Say settings for target prospector;Settings for target prospector;"
        "Say settings for prospector targeting;Check prospector targeting status;"
        "What is the prospector targeting status;Say status for prospector targeting"
    ),
    "Say Toggle for nightvision;Check night vision status;What is the night vision status;"
    "Say status for night vision": (
        "Say settings for night vision;Settings for night vision;Check night vision status;"
        "What is the night vision status;Say status for night vision"
    ),
    "Say Toggle for mining cycles;Say Toggle for repeated mining cycles;Say repeats [0..1];"
    "Check repeated mining cycles status;What is the repeated mining cycles status;"
    "Say status for repeated mining cycles": (
        "Say settings for repeated mining cycles;Settings for repeated mining cycles;"
        "Say settings for mining cycles;Check repeated mining cycles status;"
        "What is the repeated mining cycles status;Say status for repeated mining cycles"
    ),
    "Say Toggle for Headtracker;Check headtracker docking control status;"
    "What is the headtracker docking control status;"
    "Say status for headtracker docking control": (
        "Say settings for headtracker;Settings for headtracker;"
        "Say settings for headtracker docking control;Check headtracker docking control status;"
        "What is the headtracker docking control status;"
        "Say status for headtracker docking control"
    ),
    "Say Toggle for cargo scoop;Check cargo scoop status;What is the cargo scoop status;"
    "Say status for cargo scoop": (
        "Say settings for cargo scoop;Settings for cargo scoop;Check cargo scoop status;"
        "What is the cargo scoop status;Say status for cargo scoop"
    ),
    "Say toggle for autohonk;Say status for auto honk": (
        "Say settings for auto honk;Settings for auto honk;Say status for auto honk"
    ),
    "Say Toggle for FSD jump sequence;Check FSD jump sequence status;"
    "What is the FSD jump sequence status;Say status for FSD jump sequence": (
        "Say settings for FSD jump sequence;Settings for FSD jump sequence;"
        "Check FSD jump sequence status;What is the FSD jump sequence status;"
        "Say status for FSD jump sequence"
    ),
    "Say Toggle for FSD jump sequence system map;Check jump sequence system map status;"
    "What is the jump sequence system map status;Say status for jump sequence system map": (
        "Say settings for open system map;Settings for open system map;"
        "Say settings for jump sequence system map;Check jump sequence system map status;"
        "What is the jump sequence system map status;Say status for jump sequence system map"
    ),
    "Say Toggle for thrust up;Check thrust up status;What is the thrust up status;"
    "Say status for thrust up": (
        "Say settings for thrust up;Settings for thrust up;Check thrust up status;"
        "What is the thrust up status;Say status for thrust up"
    ),
    "Say Toggle for Prospector Sequence;Check prospector sequence status;"
    "What is the prospector sequence status;Say status for prospector sequence": (
        "Say settings for prospector sequence;Settings for prospector sequence;"
        "Check prospector sequence status;What is the prospector sequence status;"
        "Say status for prospector sequence"
    ),
    "Say Toggle for sound effect;Say Toggle for prospector sound effect;"
    "Check prospector sound effect status;What is the prospector sound effect status;"
    "Say status for prospector sound effect": (
        "Say settings for prospector sound effect;Settings for prospector sound effect;"
        "Say settings for sound effect;Check prospector sound effect status;"
        "What is the prospector sound effect status;Say status for prospector sound effect"
    ),
    "Say Toggle for Continuous Pulse wave Analyser;"
    "Check continuous pulse wave analyser status;"
    "What is the continuous pulse wave analyser status;"
    "Say status for continuous pulse wave analyser": (
        "Say settings for continuous pulse wave analyser;"
        "Settings for continuous pulse wave analyser;"
        "Check continuous pulse wave analyser status;"
        "What is the continuous pulse wave analyser status;"
        "Say status for continuous pulse wave analyser"
    ),
    "Say toggle for Continuous prospector sequence;"
    "Check continuous prospector sequence status;"
    "What is the continuous prospector sequence status;"
    "Say status for continuous prospector sequence": (
        "Say settings for continuous prospector sequence;"
        "Settings for continuous prospector sequence;"
        "Check continuous prospector sequence status;"
        "What is the continuous prospector sequence status;"
        "Say status for continuous prospector sequence"
    ),
}
