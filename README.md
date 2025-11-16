<a name="top"></a>

# <img src="https://github.com/Viper-Dude/EliteMining/blob/main/app/Images/logo_multi.ico" width="32" height="32"> EliteMining
[![Discord](https://img.shields.io/badge/Discord%20Community-Join%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5dsF3UshRR)

**EliteMining** optimizes your mining efficiency with live analytics, automated announcements, performance tracking, and a comprehensive hotspot finder with 61,000+ mining locations as a standalone application. Optional VoiceAttack integration enables voice/hotkey mining sequences for complete hands-free operation.

---

<details>
<summary>Table of Contents</summary>

- [Features and Usage Options](#features-and-usage-options)
- [Requirements](#requirements)
- [Installation](#installation)
- [EliteMining App](#elitemining-app)
- [Hotspot Finder](#hotspot-finder)
- [Commodity Market](#commodity-market)
- [Distance Calculator](#distance-calculator)
- [Getting Started](#getting-started)
- [Commands](#commands)
- [Mining Presets](#mining-presets)
- [Usage Tips](#usage-tips)
- [Known Limitations](#known-limitations)
- [Training Speech Recognition](#training-speech-recognition)
- [In Development](#in-development)
- [FAQ](#faq)
- [Contact](#contact)
- [License](#license--third-party-notices)
- [Credits](#credits)

</details>

---

## Features and Usage Options

### Standalone (Without VoiceAttack)
Full-featured mining companion with GUI controls:
- Real-time mining statistics  
- Automated cargo monitoring  
- Mining announcements & notifications  
- **Engineering materials tracking** – Monitor raw materials by grade
- **Auto-start mining session** – Automatically begins tracking when you fire your first prospector limpet
- **Cargo full notification** – Prompts you to end session when cargo hold is 100% full and idle for 1 minute
- Session tracking & history  
- Ship configuration management  
- GUI for firegroups, timers, toggles, and announcements  
- **Detailed HTML Reports** – Generate detailed reports with charts, screenshots, and analytics tooltips  
- **Hotspot Finder** – Search 61,000+ mining hotspots by minerals, ring type, and distance with detailed location data  
- **Commodity Market** – Find the best sell prices for your mined commodities with real-time market data and distance calculations  
- **Backup & Restore** – Save and restore full setup including settings, bookmarks, and reports

### With VoiceAttack Integration (Optional)
All standalone features **plus** voice/hotkey automation:
- Voice/hotkey mining sequences  
- Automated collector & prospector deployment  
- Smart targeting & laser management  
- Custom commands & presets
- Ship presets
- Includes [EliteAPI by Somfic](https://docs.somfic.dev/projects/eliteva) (bundled with installer)  

[Back to Top](#top)

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

[Back to Top](#top)

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

[Back to Top](#top)

---

## EliteMining App  

The **EliteMining App** provides a comprehensive GUI for configuring mining automation, tracking sessions, and managing all settings. It can run standalone without VoiceAttack.

### Start EliteMining  
- EliteMining Desktop icon or direct: `\EliteMining\Configurator\EliteMining.exe`

### Firegroups & Fire Buttons

Configure Elite Dangerous firegroups (A-H) and fire buttons (Primary/Secondary) for automated mining sequences:

<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/configurator-main.png" width="600"><br>  
*Firegroups configuration for mining tools and fire button assignments.*

**Available Tools:**
- **Mining Lasers/MVR** – Automated laser mining with configurable duration
- **Discovery Scanner** – System honk on FSD arrival  
- **Prospector Limpet** – Launch and auto-target asteroids
- **Pulse Wave Analyser** – Core asteroid scanning
- **Seismic Charge Launcher** – Fissure targeting for core mining
- **Weapons** – Defense firegroup configuration
- **Sub-surface Displacement Missile** – Deposit extraction

### Timers & Toggles

Control mining sequence timing and automated behaviors:

<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/configurator-timers_toggles.png" width="600"><br>  
*Timers and toggles for mining automation sequences.*

**Timers:** Configure duration for laser periods, pauses, and delays (1-50 seconds range)

**Toggles:**
- **Auto Honk** – Scan system automatically on FSD arrival
- **Cargo Scoop** – Auto-retract when mining completes
- **Headtracker Docking Control** – Toggle headtracker (F9) for docking
- **Laser Mining Extra** – Second laser period with cooldown pause
- **Night Vision** – Auto-enable when starting mining
- **FSD Jump Sequence** – Auto-chain jumps with system map toggle
- **Power Settings** – Max engines during mining, balance when complete
- **Prospector Sequence** – Auto-target prospector after launch
- **Pulse Wave Analyser** – Auto-switch to PWA firegroup after mining
- **Target** – Deselect prospector when mining completes

💡 **Tip:** Use "Stop all profile commands" in VoiceAttack to interrupt any active sequence.

[Back to Top](#top)

---

## Hotspot Finder

The Hotspot Finder provides access to a comprehensive database of 61,000+ confirmed mining hotspots with detailed location data, minerals information, and intelligent filtering capabilities.

### Key Features
- **Search Planetary Rings** – Find optimal mining rings (Ice, Metal Rich, Rocky, Metallic)
- **Filter by Minerals** – Search for specific minerals (Painite, Platinum, Low Temperature Diamonds, etc.)
- **Min Hotspots Filter** – Filter results to show only rings with X or more hotspots (1-20 range, available when specific mineral selected)
- **Auto-Search** – Automatically searches for hotspots when jumping to new systems and auto-refreshes results when scanning rings (remembers preference across restarts)
- **Pre-loaded Database** – 61,000+ hotspots with minerals types, ring densities
- **Auto-Import & Tracking** – Automatically imports hotspots from journal files and tracks new discoveries
- **Distance-Based Results** – Filter by jump range (up to 500 LY) to find nearby opportunities
- **Ring Composition Details** – View ring density and distance from arrival (LS) with comma-separated formatting
- **Smart Sorting** – Results ranked by distance, hotspot overlaps, and ring density

Automatically imports hotspots from your Elite Dangerous journal files and continuously tracks newly discovered locations.

<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/ring_finder.png" width="600"><br>  
*Hotspot Finder showing search results with minerals filters and distance calculations.*

[Back to Top](#top)

---

## Commodity Market

The Commodity Market helps you find the best sell prices for your mined commodities using real-time market data from the Ardent API, with automatic distance calculations to help you maximize profits.

### Key Features
- **Two Search Modes:**
  - **Near System** – Find top 30 stations within 500 LY, filtered by distance
  - **Galaxy-Wide** – Find top 30 best prices anywhere in the galaxy with calculated distances
- **Buy/Sell Toggle:**
  - **Sell Mode** – Find stations buying your commodities (best sell prices)
  - **Buy Mode** – Find stations selling commodities you want to purchase (lowest buy prices)
- **Real-Time Market Data** – Live commodity prices updated from active commanders
- **Smart Filtering:**
  - Station type (Orbital/Surface/Fleet Carrier/MegaShip)
  - Landing pad size (Large pads only option)
  - Exclude Fleet Carriers
- **Distance Calculations** – Automatically calculates jump distance from your reference system
- **Data Freshness** – Shows when prices were last updated (minutes/hours/days ago)
- **Sortable Results** – Click column headers to sort by location, type, distance, demand, or price
- **Threaded Updates** – Results appear instantly with distances calculated in background for smooth performance
- **External Links** – Right-click any search result to:
  - Open station in Inara (station search)
  - Open system in EDSM (system page with all stations)
  - Copy system name to clipboard

Perfect for planning your mining runs and finding the most profitable stations to sell your haul.

<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/commidity_marked.png" width="600"><br>  
*Commodity Market showing search results with filters and distance calculations.*

[Back to Top](#top)

---

## Distance Calculator

Calculate distances between any two systems using real-time EDSM data. Perfect for planning long-distance trips, tracking your home base, or finding your fleet carrier.

### Key Features
- **System Distance Calculator** – Calculate precise jump distances between any two star systems
- **Home System Tracking** – Save your home system and see distance from your current location in real-time
- **Fleet Carrier Tracking** – Auto-detect your fleet carrier location from journals or set manually
- **Coordinates & Sol Distance** – View galactic coordinates and distance to Sol for all systems
- **Live Updates** – Distances to Home and Fleet Carrier update automatically when you jump systems
- **Session Memory** – Remembers your last calculated systems and settings between app restarts
- **Quick Actions:**
  - "Use Current" button fills with your current system instantly
  - "Home" and "FC" buttons quickly fill destination field
  - Press Enter to calculate without clicking

<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/distance_calc.png" width="600"><br>  
*Distance Calculator showing system distances with Home and Fleet Carrier tracking.*

[Back to Top](#top)

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

> **⚠️ Important for Automated Firegroup Switching:**  
> For the mining sequence automation to work correctly, **ALL firegroups (A through H) must be populated** in Elite Dangerous, even if you don't actively use them. Not populated firegroups will prevent automatic switching.
> 
> <img src="Screenshot/fg_all.png" width="600"><br>
> *Example: All 8 firegroups configured (A-H). Unused groups can have any weapon assigned.*

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

[Back to Top](#top)

---

### EliteMining GUI  
<details open>
<summary>Click to expand</summary>

### Mining Session Tab  

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

#### Discord Integration
*Manually share mining session reports to Discord channels.*  

Share completed mining session summaries to Discord channels via webhook integration. Configure your Discord webhook URL in settings, then manually share individual session reports with custom comments. Reports include materials found, yields, performance metrics, and session duration. 

#### 📊 Mining Cards
Generate shareable PNG cards from your mining sessions.

<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/mining_cards.png" width="300"><br>

**Features:**
- Session stats, performance metrics, and commodity breakdown
- Add your CMDR name and optional notes
- Right-click any session in Reports → "Mining Card"

Cards saved to: `app/Reports/Mining Session/Cards/`

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

#### Announcement Panel  
<img src="Screenshot/mining-announcement.png" width="600"><br>  
*Controls announcements, thresholds, and filters.*  

<img src="Screenshot/txt_overlay.png" width="600"><br>  
*Text overlay showing real-time mining announcements in-game.*

<img src="Screenshot/txt_overlay_enhanced.png" width="600"><br>  
*Enhanced overlay with improved readability and detailed mining statistics.*

</details>

[Back to Top](#top)

---

### Backup & Restore 
- Easily save and restore your complete EliteMining setup including settings, bookmarks, and reports. Create timestamped backups before updates or quickly restore previous configurations with one click.  

<img src="https://github.com/Viper-Dude/EliteMining/blob/main/Screenshot/backup.png" width="350"><br>  

[Back to Top](#top)

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

[Back to Top](#top)

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

[Back to Top](#top)

---

## Usage Tips
- **Short press** → Starts command  
- **Long press** → Stops/resets command  
- Enable **"Shortcut is invoked when long-pressed"** in VoiceAttack  

[Back to Top](#top)

---

## Known Limitations
- **Only works with in-game keybinds (HOTAS setup manual)**
- **There may be conflicts with HCS VoicePack commands, but these can be easily adjusted manually in the EliteMining Profile within VoiceAttack.**
- **Works with EDCopilot**

> **Note:** VoiceAttack startup warnings about EliteVA plugin bindings are normal due to recent Elite Dangerous changes and can be safely ignored - they don't impact EliteMining voice commands.

[Back to Top](#top)

---

## Training Speech Recognition
<details>
<summary>Click to expand</summary>

1. Open VoiceAttack  
2. Go to **Help → Utilities → Recognition Training**  
3. Train in a quiet environment  
4. Backup your speech profile: [SpProfileMgr.zip](https://voiceattack.com/filesend.aspx?id=SpProfileMgr.zip)  

</details>

[Back to Top](#top)

---

## In Development  
TBA  

[Back to Top](#top)

---

## Contact  

### Community Support
Join our Discord server for real-time help, mining tips, and community discussions:  
[![Discord](https://img.shields.io/badge/EliteMining%20Community-Join%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5dsF3UshRR)

### Other Resources
- **GitHub Discussions:** [EliteMining Forum](https://github.com/Viper-Dude/EliteMining/discussions/4)
- **Bug Reports:** [GitHub Issues](https://github.com/Viper-Dude/EliteMining/issues)

[Back to Top](#top)

---

## License & Third-Party Notices  

**EliteMining** © 2024-2025 CMDR ViperDude (Viper-Dude).  
Licensed under the [GNU General Public License v3.0](LICENSE).  

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

**Third-Party Components:**  
- **ELITEVA** © 2023 Somfic – MIT License  

For complete license terms, see the [LICENSE](LICENSE) file in the repository.  

[Back to Top](#top)

---

## Credits  
- [Somfic](https://docs.somfic.dev/projects/eliteva) – Creator of EliteVA  
- [Iain Collins](https://github.com/iaincollins/ardent-api) – Developer of Ardent API for Elite Dangerous market data  
- [EDCD/EDDN](https://github.com/EDCD/EDDN) – Elite Dangerous Data Network for real-time game data  
- **gOOvER | CMDR Shyvin** – For continued support and contributions to this project

[Back to Top](#top)

---

## FAQ

For detailed answers to common questions, see our [FAQ page](FAQ.md).

[Back to Top](#top)
