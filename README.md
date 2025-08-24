# HomeAssistant-Videoloft

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=StannyByte&repository=HomeAssistant-Videoloft&category=integration"><img src="https://img.shields.io/badge/HACS-Install-41BDF5.svg?style=for-the-badge" alt="Install via HACS"></a>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Default-blue.svg?style=for-the-badge" alt="HACS"></a>
  <a href="https://github.com/StannyByte/HomeAssistant-Videoloft/releases"><img src="https://img.shields.io/github/v/release/StannyByte/HomeAssistant-Videoloft?style=for-the-badge" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge" alt="License"></a>
</p>

**Videoloft cameras in Home Assistant with live streaming, LPR automation, and AI-powered event search.**

---

## Features

- **📺 Live HLS streaming** with interactive controls
- **🚗 License Plate Recognition** sensors for automation (requires Videoloft LPR subscription)
- **🔍 AI Event Search** using Google Gemini (requires API key)
- **⚡ Custom sidebar panel** with tabbed interface
- **🔧 UI-based setup** - no YAML configuration required

## Screenshots

<p align="left">
  <img src="https://github.com/user-attachments/assets/f22512e9-c72b-448c-b6ed-1a6a5aa89182" alt="Live Streams" width="250">
  <img src="https://github.com/user-attachments/assets/ddbc0544-a423-45da-89d2-8ae2f6bf7cb9" alt="Home Assistant Notification with Snapshot" width="250">
</p>

## Installation

### One-Click Install (Recommended)
[![Install via HACS](https://img.shields.io/badge/HACS-Install-41BDF5.svg?style=for-the-badge)](https://my.home-assistant.io/redirect/hacs_repository/?owner=StannyByte&repository=HomeAssistant-Videoloft&category=integration)

Click the badge above to install directly via HACS.

### Manual HACS Install
1. Go to **HACS > Integrations > ⋮ > Custom Repositories**
2. Add `https://github.com/StannyByte/HomeAssistant-Videoloft` as Integration
3. Install **HomeAssistant-Videoloft**
4. Restart Home Assistant

### Manual File Install
1. Download [latest release](https://github.com/StannyByte/HomeAssistant-Videoloft/releases)
2. Copy `videoloft` folder to `custom_components/`
3. Restart Home Assistant

## Setup

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **Videoloft** and configure with your credentials
3. Access **Videoloft Cams** panel from sidebar

## Usage

- **Live Streaming:** View all cameras in the Live tab
- **LPR Automation:** Create automations using `sensor.videoloft_lpr_matched_event`
- **AI Search:** Configure Gemini API key in AI Search tab, then search events with natural language

## Requirements

- Home Assistant (latest stable)
- Videoloft account with cameras
- For LPR: Videoloft LPR subscription
- For AI Search: Google Gemini API key

## Support

[Issues](https://github.com/StannyByte/HomeAssistant-Videoloft/issues) • [Releases](https://github.com/StannyByte/HomeAssistant-Videoloft/releases)
