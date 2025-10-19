# <img src="https://github.com/Viper-Dude/EliteMining/blob/main/app/Images/logo_multi.ico" width="32" height="32"> EliteMining

[![Discord](https://img.shields.io/badge/Discord%20Community-Join%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/8fmpUpn5HJ)

**EliteMining** optimizes your mining efficiency with live analytics, automated announcements, performance tracking, and a comprehensive hotspot finder with 32,000+ mining locations as a standalone application. Optional VoiceAttack integration enables voice/hotkey mining sequences for complete hands-free operation.

---

<details>
<summary>Table of Contents</summary>

- [Usage Options](#usage-options)  
- [Features](#features)  
- [Requirements](#requirements)  
- [Installation](#installation)  
- [EliteMining App](#elitemining-app)  
- [Hotspot Finder](#hotspot-finder)  
- [Getting Started](#getting-started)  
  - [EliteMining GUI](#elitemining-gui)  
  - [Backup & Restore](#backup--restore)  
- [Commands](#commands)  
- [Mining Presets](#mining-presets)  
- [Usage Tips](#usage-tips)  
- [Known Limitations](#known-limitations)  
- [Training Speech Recognition](#training-speech-recognition)  
- [In Development](#in-development)  
- [Contact](#contact)  
- [License](#license--third-party-notices)  
- [Credits](#credits)  

</details>

---

## Usage Options

### VoiceAttack Integration (Full Automation)  
Complete voice/hotkey-controlled mining with automated sequences and announcements.  

### Standalone Mode (Manual Control)  
The EliteMining App works independently for announcements, reports, and tracking. VoiceAttack is not required.  

[Back to Top](#elitemining)

---

## Features

### With VoiceAttack Integration
All features below **plus** voice/hotkey automation:
- Voice/hotkey mining sequences  
- Automated collector & prospector deployment  
- Smart targeting & laser management  
- Custom commands & presets
- Ship presets
- Includes [EliteAPI by Somfic](https://docs.somfic.dev/projects/eliteva) (bundled with installer)

### Standalone (Without VoiceAttack)
Full-featured mining companion with GUI controls:
- Real-time mining statistics  
- Automated cargo monitoring  
- Mining announcements & notifications  
- **Engineering materials tracking** – Monitor raw materials by grade
- Session tracking & history  
- Ship configuration management  
- GUI for firegroups, timers, toggles, and announcements  
- **Detailed HTML Reports** – Generate detailed reports with charts, screenshots, and analytics tooltips  
- **Hotspot Finder** – Search 32,000+ mining hotspots by minerals, ring type, and distance with detailed location data  
- **Backup & Restore** – Save and restore full setup including settings, bookmarks, and reports  

[Back to Top](#elitemining)

---

## Requirements
<details>
<summary>Click to expand</summary>

**Essential:**  
- **Elite Dangerous** (PC version)  

**For VoiceAttack Integration:**  
- **[EliteVA (API) by Somfic](https://docs.somfic.dev/projects/eliteva)** *(included in installer)*  
- **[VoiceAttack](https://voiceattack.com/)** – Paid version  
- **Microphone** for voice commands  

### Keybind Requirement for EliteVA  
EliteVA requires the `Custom.binds` file:  

1. Open **Elite Dangerous → Options → Controls**  
2. Set preset to **Custom**  
3. Save — this creates/updates `Custom.binds`  

### Custom Keybinds for Mining Control  
VoiceAttack profile includes a dedicated **"Custom Keybinds for Mining Control"** category. Configure your mining hotkeys here instead of searching through the entire profile.

**Note:** VoiceAttack is optional. EliteMining App can run standalone.  

</details>

[Back to Top](#elitemining)

---

## Installation

- **Installer:** Run `EliteMiningSetup.exe` (includes VoiceAttack profile)  

> **Antivirus Notice:** If your antivirus flags the application, this is a common false positive with Python-compiled apps - simply add an exclusion for the installation folder.
> 
> **After Updates and New Installs:** System/ring location may appear empty until you relog into Elite Dangerous (one-time refresh).

### Included Components  
The installer bundles the **EliteVA plugin**. No separate download required.  

### VoiceAttack Profile Installation  
1. Open VoiceAttack → **Profile > Import Profile**  
2. Select **EliteMining-Profile.vap**  
3. Configure your mining hotkeys in the **"Custom Keybinds for Mining Control"** category

[Back to Top](#elitemining)

---

## EliteMining App  

The **EliteMining App** lets you adjust firegroups, toggles, timers, and announcements via GUI. It can run standalone without VoiceAttack.  

### Launching  
- VoiceAttack: **"Open EliteMining"**  
- Keyboard: **Right Alt + Right Shift + C**  
- Direct: `\EliteMining\Configurator\EliteMining.exe` or desktop icon (if installed)  

[Back to Top](#elitemining)

---

## Hotspot Finder

The Hotspot Finder provides access to a comprehensive database of 32,000+ confirmed mining hotspots with detailed location data, minerals information, and intelligent filtering capabilities.

### Key Features
- **Search Planetary Rings** – Find optimal mining rings (Ice, Metal Rich, Rocky, Metallic)
- **Filter by Minerals** – Search for specific minerals (Painite, Platinum, Low Temperature Diamonds, etc.)
- **Pre-loaded Database** – 32,000+ hotspots with minerals types, ring densities
- **Auto-Import & Tracking** – Automatically imports hotspots from journal files and tracks new discoveries
- **Distance-Based Results** – Filter by jump range to find nearby opportunities
- **Ring Composition Details** – View ring density and distance from arrival
- **Smart Sorting** – Results ranked by distance, hotspot overlaps, and ring density

Automatically imports hotspots from your Elite Dangerous journal files and continuously tracks newly discovered locations.

<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/ring_finder.png" width="600"><br>  
*Hotspot Finder showing search results with minerals filters and distance calculations.*

[Back to Top](#elitemining)

---

## Getting Started
<details open>
<summary>Click to expand</summary>

### Firegroup (FG) Setup  
| Component | FG | Fire Button | Notes |
|-----------|----|-------------|-------|
| Mining Lasers (MVR) | Preset/Command | Primary | – |
| Discovery Scanner | Preset/Command | Secondary | – |
| Prospector Limpet Controller | Same as PWA | Secondary | Must set manually |
| Pulse Wave Analyser | Preset/Command | Primary | – |
| Seismic Charge Launcher | Preset/Command | – | – |
| Weapons | Preset/Command | – | – |
| Sub-surface Displ Missile | Preset/Command | – | – |
| Collector Limpet Controller | Preset/Command | – | Must set manually |

### Key / HOTAS Bindings  
| Action | Description |
|--------|-------------|
| Stop profiles command | Stops all running commands |
| Start Mining Sequence | Starts laser mining |
| Reset Mining Sequence | Stops/resets mining |
| Deploy Seismic Charge Launcher | Switch to launcher |
| Deploy Sub-surface Displ Missile | Switch to SSDM |
| Deploy Weapons | Switch to weapons |
| Start Scanning for Cores | Scanning sequence |
| Stop Scanning for Cores | Stops scanning |
| Clear and Jump | Clears mass lock & jumps |
| TrackIR Integration | Pause toggle = **F9** |

</details>

[Back to Top](#elitemining)

---

### EliteMining GUI  

#### Main Window (Dashboard) & Firegroups  
<img src="Screenshot/configurator-main.png" width="600"><br>  
*EliteMining App layout with firegroups & buttons.*  

#### Timers/Toggles Tab  
<img src="Screenshot/configurator-timers_toggles.png" width="600"><br>  
*Configure timers and toggles for automation.*  

---

### Mining Session Tab  

#### Announcement Panel  
<img src="Screenshot/mining-announcement.png" width="600"><br>  
*Controls announcements, thresholds, and filters.*  

<img src="Screenshot/txt_overlay.png" width="600"><br>  
*Text overlay showing real-time mining announcements in-game.*  

#### Mining Session  
<img src="Screenshot/mining-session.png" width="600"><br>  
*Tracks time, prospector reports, minerals, and progress.*  

<img src="Screenshot/dashboard-graphs_yield_timeline_comparison.png" width="600"><br>  
*Yield comparisons across sessions.*  

<img src="Screenshot/dashboard-graphs_material_comparison.png" width="600"><br>  
*Minerals collection comparisons.*  

#### Reports 
<img src="Screenshot/mining-reports.png" width="600"><br>  
*Detailed mining statistics and summaries.*  

#### Detailed HTML Reports  
*HTML reports with charts and statistics.*  

> **Work in Progress:** The detailed HTML report system is under active development. New features and improvements are being added regularly. Report layouts, analytics calculations, and data presentation may change in future updates.

Generate comprehensive HTML reports with interactive charts, mining analytics, and session comments. Features include:
- **Dark/Light Theme Toggle** - Switch between themes with one click  
- **Session Comments** - Add notes and observations to your reports  
- **Visual Charts** - Minerals breakdowns and performance graphs  
- **Screenshot Integration** - Attach screenshots to document your sessions  
- **Overall Statistics** - Compare current session to your mining history
- **Analytics Tooltips** - Hover explanations for all efficiency metrics
- **Clickable Images** - Charts and screenshots expand to full size
- **Data Preservation** - Reports protected during software updates
- **Export Options** - CSV, HTML, and PDF formats available

**File Locations:**
- Reports saved to: `Reports/Mining Session/`
- Screenshots: `Reports/Mining Session/Detailed Reports/Screenshots/`
- Performance graphs: `Reports/Mining Session/Graphs/`  

Right-click any mining session to generate a detailed report, add screenshots, or manage existing reports. All reports are saved with your session data and can be opened directly from the reports tab.

<details>
<summary>📸 View HTML Report Screenshots</summary>

<img src="Screenshot/html_report_1.png" width="250"> <img src="Screenshot/html_report_2.png" width="250"> <img src="Screenshot/html_report_3.png" width="250">

*Click images to view full size*

</details>

#### Bookmarks  
<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/mining-session_bookmarks.png" width="600"><br>  
*Save, search, and manage mining spots.*  

#### Comprehensive Analytics  
<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/mining-session_statistic.png" width="600"><br>  
*Session statistics: yields, hit rates, and comparisons.*  

---

#### Settings Tab  
<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/configurator-options.png" width="600" height="400"><br>  
*UI and announcement preferences.*  

[Back to Top](#elitemining)

---

### Backup & Restore 
- Easily save and restore your complete EliteMining setup including settings, bookmarks, and reports. Create timestamped backups before updates or quickly restore previous configurations with one click.  

<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/backup.png" width="350"><br>  

[Back to Top](#elitemining)

---

## Commands
<details>
<summary>Click to expand</summary>

### Status Checks  
| Spoken Command | Description |
|----------------|-------------|
| "Say firegroup for weapons" | Reports FG for weapons |
| "Say firegroup for mining lasers" | Reports FG for lasers |
| "Say firegroup for SSDM" | Reports FG for SSDMs |
| "Say firegroup for PWA" | Reports FG for PWA |
| "Say toggle for cargo scoop" | Reports toggle status |
| "Say timer for laser mining" | Reports active timer |

### Firegroup & Parameter Commands  
| Spoken Command | Description |
|----------------|-------------|
| "Set firegroup for Discovery Scanner to [A–H]" | Assigns Discovery Scanner |
| "Set firegroup for mining lasers to [A–H]" | Assigns Mining Lasers |
| "Set firegroup for PWA to [A–H]" | Assigns PWA |
| "Set firegroup for Seismic Launcher to [A–H]" | Assigns Launcher |
| "Set firegroup for SSDM to [A–H]" | Assigns SSDM |
| "Set firegroup for weapons to [A–H]" | Assigns weapons |

### Miscellaneous  
| Spoken Command | Description |
|----------------|-------------|
| "Landing Request" | Requests docking |
| "Enable/Disable Autohonk" | Toggles auto scan |

</details>

[Back to Top](#elitemining)

---

## Mining Presets
<details>
<summary>Click to expand</summary>

### Hazardous Mining Preset  
- **Command:** `"Set mining configuration for 3 x haz"`  
- Pre-configured firegroups, timers, and toggles for HAZ mining.  

### Customization  
- Create presets for different ships  
- Adjust firegroups/timers on-the-fly  
- Modify via built-in commands  

</details>

[Back to Top](#elitemining)

---

## Usage Tips
- **Short press** → Starts command  
- **Long press** → Stops/resets command  
- Enable **"Shortcut is invoked when long-pressed"** in VoiceAttack  

[Back to Top](#elitemining)

---

## Known Limitations
- **Only works with in-game keybinds (HOTAS setup manual)**
- **There may be conflicts with HCS VoicePack commands, but these can be easily adjusted manually in the EliteMining Profile within VoiceAttack.**
- **Works with EDCopilot**

> **Note:** VoiceAttack startup warnings about EliteVA plugin bindings are normal due to recent Elite Dangerous changes and can be safely ignored - they don't impact EliteMining voice commands.

[Back to Top](#elitemining)

---

## Training Speech Recognition
<details>
<summary>Click to expand</summary>

1. Open VoiceAttack  
2. Go to **Help → Utilities → Recognition Training**  
3. Train in a quiet environment  
4. Backup your speech profile: [SpProfileMgr.zip](https://voiceattack.com/filesend.aspx?id=SpProfileMgr.zip)  

</details>

[Back to Top](#elitemining)

---

## In Development  
TBA  

[Back to Top](#elitemining)

---

## Contact  

### Community Support
Join our Discord server for real-time help, mining tips, and community discussions:  
[![Discord](https://img.shields.io/badge/EliteMining%20Community-Join%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/8fmpUpn5HJ)

### Other Resources
- **GitHub Discussions:** [EliteMining Forum](https://github.com/Viper-Dude/EliteMining/discussions/4)
- **Bug Reports:** [GitHub Issues](https://github.com/Viper-Dude/EliteMining/issues)

[Back to Top](#elitemining)

---

## License & Third-Party Notices  

**EliteMining** © 2025 CMDR ViperDude.  
Distributed under the [MIT License](LICENSE.md).  

This project bundles:  
- **ELITEVA** © 2023 Somfic – MIT License  

[Back to Top](#elitemining)

---

## Credits  
- [Somfic](https://docs.somfic.dev/projects/eliteva) – Creator of EliteVA  

[Back to Top](#elitemining)
