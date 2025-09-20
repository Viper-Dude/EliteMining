# <img src="https://github.com/Viper-Dude/EliteMining/blob/main/images/logo_multi.ico" width="32" height="32"> EliteMining

**EliteMining** optimizes your mining efficiency with live prospecting analytics, automated announcements, and performance tracking as a standalone application. Optional VoiceAttack integration enables voice/hotkey mining sequences for complete hands-free operation.  

---

<details>
<summary>📑 Table of Contents</summary>

- [Usage Options](#-usage-options)  
- [Features](#-features)  
- [Requirements](#-requirements)  
- [Installation](#-installation)  
- [Configurator](#️-configurator)  
  - [EliteMining GUI](#-elitemining-gui)  
- [Getting Started](#-getting-started)  
- [Commands](#-commands)  
- [Mining Presets](#-mining-presets)  
- [Usage Tips](#-usage-tips)  
- [Known Limitations](#-known-limitations)  
- [Training Speech Recognition](#-training-speech-recognition)  
- [In Development](#-in-development)  
- [Contact](#-contact)  
- [License](#-license--third-party-notices)  
- [Credits](#-credits)  

</details>

---

## 🎯 Usage Options

### VoiceAttack Integration (Full Automation)  
Complete voice/hotkey-controlled mining with automated sequences and announcements.  

### Standalone Mode (Manual Control)  
The Configurator works independently for announcements, reports, and tracking. VoiceAttack is not required.  

[⬆️ Back to Top](#-elitemining)

---

## ✨ Features

### With VoiceAttack (Full Experience)  
- Voice/hotkey mining sequences  
- Automated collector & prospector deployment  
- Smart targeting & laser management  
- Real-time mining statistics  
- Cargo management automation  
- Custom commands & presets  
- Compatible with [EliteAPI by Somfic](https://docs.somfic.dev/projects/eliteva)  

### Standalone Features (No VoiceAttack Required)  
- Mining announcements & notifications  
- Session tracking & history  
- Ship configuration management  
- GUI for firegroups, timers, toggles, and announcements  

[⬆️ Back to Top](#-elitemining)

---

## 📦 Requirements
<details>
<summary>Click to expand</summary>

**Essential:**  
- **Elite Dangerous** (PC version)  

**For VoiceAttack Integration:**  
- **[EliteVA (API) by Somfic](https://docs.somfic.dev/projects/eliteva)** *(included in installer)*  
- **[VoiceAttack](https://voiceattack.com/)** – Paid version  
- **Microphone** for voice commands  

### 🔑 Keybind Requirement for EliteVA  
EliteVA requires the `Custom.binds` file:  

1. Open **Elite Dangerous → Options → Controls**  
2. Set preset to **Custom**  
3. Save — this creates/updates `Custom.binds`  

**Note:** VoiceAttack is optional. Configurator can run standalone.  

</details>

[⬆️ Back to Top](#-elitemining)

---

## 💾 Installation
<details>
<summary>Click to expand</summary>

- **Installer:** Run `EliteMiningSetup.exe` (includes VoiceAttack profile)  
- **Portable:** Extract `EliteMining_3.9.0-beta.zip`  

### Included Components  
The installer bundles the **EliteVA plugin**. No separate download required.  

### Manual Installation  
1. Download the latest `.zip` from [Releases](https://github.com/Viper-Dude/EliteMining/releases)  
2. Extract into your VoiceAttack app folder  
3. Open VoiceAttack → **Profile > Import Profile**  
4. Select **EliteMining-Profile.vap**  

</details>

[⬆️ Back to Top](#-elitemining)

---

## 🖥️ Configurator  

The **Configurator** lets you adjust firegroups, toggles, timers, and announcements via GUI. It can run standalone without VoiceAttack.  

### Launching  
- VoiceAttack: **"Open Configurator"**  
- Keyboard: **Right Ctrl + Right Shift + C**  
- Direct: `\EliteMining\Configurator\Configurator.exe`  

[⬆️ Back to Top](#-elitemining)

---

### 📸 EliteMining GUI  

#### Main Window (Dashboard) & Firegroups  
<img src="images/configurator-main.png" width="600"><br>  
*Configurator layout with firegroups & buttons.*  

#### Timers/Toggles Tab  
<img src="images/configurator-timers_toggles.png" width="600"><br>  
*Configure timers and toggles for automation.*  

---

### 🪓 Mining Session Tab  

#### Announcement Panel  
<img src="images/mining-announcement.png" width="600"><br>  
*Controls announcements, thresholds, and filters.*  

#### Mining Session  
<img src="images/mining-session.png" width="600"><br>  
*Tracks time, prospector reports, materials, and progress.*  

<img src="images/dashboard-graphs_yield_timeline_comparison.png" width="600"><br>  
*Yield comparisons across sessions.*  

<img src="images/dashboard-graphs_material_comparison.png" width="600"><br>  
*Material collection comparisons.*  

#### Reports 
<img src="images/mining-reports.png" width="600"><br>  
*Detailed mining statistics and summaries.*  

#### 🔖 Bookmarks  
<img src="https://github.com/Viper-Dude/EliteMining/blob/main/images/mining-session_bookmarks.png" width="600"><br>  
*Save, search, and manage mining spots.*  

#### 📊 Comprehensive Analytics  
<img src="https://github.com/Viper-Dude/EliteMining/blob/main/images/mining-session_statistic.png" width="600"><br>  
*Session statistics: yields, hit rates, and comparisons.*  

---

#### Interface Options Tab  
<img src="https://github.com/Viper-Dude/EliteMining/blob/main/images/configurator-options.png" width="600" height="400"><br>  
*UI and announcement preferences.*  

[⬆️ Back to Top](#-elitemining)

---

## 🚀 Getting Started
<details>
<summary>Click to expand</summary>

### Firegroup (FG) Setup  
| Component | FG | Fire Button | Notes |
|-----------|----|-------------|-------|
| Discovery Scanner | Preset/Command | Secondary | – |
| Surface Scanner | A | Primary | – |
| Mining Lasers | Preset/Command | Primary | – |
| Collector Limpet Controller | Preset/Command | Same as Mining Lasers | Must set manually |
| Pulse Wave Analyser | Preset/Command | Primary | – |
| SSDM | Preset/Command | Primary | – |
| Prospector Limpet Controller | Same as PWA | Secondary | Must set manually |

### Key / HOTAS Bindings  
| Action | Description |
|--------|-------------|
| Stop profiles command | Stops all running commands |
| Start Mining Sequence | Starts laser mining |
| Reset Mining Sequence | Stops/resets mining |
| Deploy Seismic Charge Launcher | Switch to launcher |
| Deploy Weapons | Switch to weapons |
| Start Scanning for Cores | Scanning sequence |
| Stop Scanning for Cores | Stops scanning |
| Clear and Jump | Clears mass lock & jumps |
| TrackIR Integration | Pause toggle = **F9** |

</details>

[⬆️ Back to Top](#-elitemining)

---

## 🎙️ Commands
<details>
<summary>Click to expand</summary>

### ✅ Status Checks  
| Spoken Command | Description |
|----------------|-------------|
| "Say firegroup for weapons" | Reports FG for weapons |
| "Say firegroup for mining lasers" | Reports FG for lasers |
| "Say firegroup for SSDM" | Reports FG for SSDMs |
| "Say firegroup for PWA" | Reports FG for PWA |
| "Say toggle for cargo scoop" | Reports toggle status |
| "Say timer for laser mining" | Reports active timer |

### 🔧 Firegroup & Parameter Commands  
| Spoken Command | Description |
|----------------|-------------|
| "Set firegroup for Discovery Scanner to [A–H]" | Assigns Discovery Scanner |
| "Set firegroup for mining lasers to [A–H]" | Assigns Mining Lasers |
| "Set firegroup for PWA to [A–H]" | Assigns PWA |
| "Set firegroup for Seismic Launcher to [A–H]" | Assigns Launcher |
| "Set firegroup for SSDM to [A–H]" | Assigns SSDM |
| "Set firegroup for weapons to [A–H]" | Assigns weapons |

### 🎮 Miscellaneous  
| Spoken Command | Description |
|----------------|-------------|
| "Landing Request" | Requests docking |
| "Enable/Disable Autohonk" | Toggles auto scan |

</details>

[⬆️ Back to Top](#-elitemining)

---

## ⚡ Mining Presets
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

[⬆️ Back to Top](#-elitemining)

---

## 💡 Usage Tips
- **Short press** → Starts command  
- **Long press** → Stops/resets command  
- Enable **"Shortcut is invoked when long-pressed"** in VoiceAttack  

[⬆️ Back to Top](#-elitemining)

---

## ⚠️ Known Limitations
- Only works with in-game keybinds (HOTAS setup manual)  
- Possible conflicts with HCS VoicePack  
- Works with EDCopilot  

[⬆️ Back to Top](#-elitemining)

---

## 🗣️ Training Speech Recognition
<details>
<summary>Click to expand</summary>

1. Open VoiceAttack  
2. Go to **Help → Utilities → Recognition Training**  
3. Train in a quiet environment  
4. Backup your speech profile: [SpProfileMgr.zip](https://voiceattack.com/filesend.aspx?id=SpProfileMgr.zip)  

</details>

[⬆️ Back to Top](#-elitemining)

---

## 🚧 In Development  
TBA  

[⬆️ Back to Top](#-elitemining)

---

## ❓ Contact  
For business/collab inquiries:  
[![Discord](https://img.shields.io/badge/Discord-7Ven__MP-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/users/394827769378242560)  

💬 Join the community: [EliteMining Forum](https://github.com/Viper-Dude/EliteMining/discussions/4)  

[⬆️ Back to Top](#-elitemining)

---

## 📜 License & Third-Party Notices  

**EliteMining** © 2025 CMDR ViperDude.  
Distributed under the [MIT License](LICENSE.md).  

This project bundles:  
- **ELITEVA** © 2023 Somfic – MIT License  

[⬆️ Back to Top](#-elitemining)

---

## 👏 Credits  
- [Somfic](https://docs.somfic.dev/projects/eliteva) – Creator of EliteVA  

[⬆️ Back to Top](#-elitemining)
