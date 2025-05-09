# HomeAssistant-Videoloft

[![HACS Badge](https://img.shields.io/badge/HACS-Default-blue.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/release/StannyByte/HomeAssistant-Videoloft.svg)](https://github.com/StannyByte/HomeAssistant-Videoloft/releases)

> **Seamlessly connect your Videoloft cameras to Home Assistant for live streaming, license plate recognition, and AI-powered event search!**

---

## 🚀 What is HomeAssistant-Videoloft?

**HomeAssistant-Videoloft** is a custom integration that brings your Videoloft cameras into Home Assistant, unlocking advanced automation and analytics:

- **Live HLS Streaming** – Watch your cameras in real time, right from Home Assistant.
- **License Plate Recognition (LPR) Automation** – Trigger automations when specific vehicles are detected.
- **AI-Powered Event Search** – Use Google Gemini to generate smart, searchable event descriptions.
---

<p align="left">
  <img src="https://github.com/user-attachments/assets/f22512e9-c72b-448c-b6ed-1a6a5aa89182" alt="Videoloft Live Stream" width="200">
  <img src="https://github.com/user-attachments/assets/c9e56adb-4491-4eef-abc9-4c7a45fe463c" alt="AI Search Interface" width="200">
  <img src="https://github.com/user-attachments/assets/a4912f1e-160f-4e88-b086-743d9dd56eed" alt="Dashboard Overview" width="200">
  <img src="https://github.com/user-attachments/assets/bda51a1c-84cd-482c-828d-87cb0d2e54be" alt="Event Analytics" width="186">
</p>

---

## ✨ Features

- **📺 Live Streaming:**  
  Smooth, reliable HLS streaming for all your Videoloft cameras.

- **🚗 License Plate Recognition (LPR):**  
  - Automated detection and matching of license plates, vehicle make/model/color.
  - Create automations for gates, lights, and more.
  - *Requires Videoloft LPR subscription.*

- **🔍 AI Search (Google Gemini):**  
  - Generate detailed, human-friendly event summaries using AI.
  - Search events with natural language (e.g., "person with red bag", "white van delivery").

- **⚡ Modern UI Panel:**  
  - Beautiful, responsive dashboard with tabs for Live, LPR, AI Search, and Analytics.
  - No YAML required — everything is managed via the Home Assistant UI.

- **📊 Dashboard Metrics (WIP):**  
  - Real-time camera status, uptime, and event history.
  - *(Coming soon!)*

---

## 🛠️ Installation

### HACS (Recommended)

1. In Home Assistant, go to **HACS > Integrations > + Explore & Add Repositories**.
2. Search for `HomeAssistant-Videoloft` or use:  
   `https://github.com/StannyByte/HomeAssistant-Videoloft`
3. Click **Install** and restart Home Assistant.

### Manual

1. Copy the `videoloft` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

---

## ⚙️ Setup & Configuration

1. Go to **Settings > Devices & Services** in Home Assistant.
2. Click **+ Add Integration** and search for **Videoloft**.
3. Enter your Videoloft credentials when prompted.
4. Done! Cameras and sensors will be auto-discovered.

> **No YAML needed!**  
> All configuration is handled via the Home Assistant UI.

---

## 🧠 How It Works

- **Camera Devices & Entities:**  
  Each Videoloft camera appears as a device/entity for live viewing and automations.

- **LPR Sensor:**  
  Detects license plates and vehicle attributes in real time.  
  Triggers automations when a match is found.

- **AI Search:**  
  Uses Google Gemini to analyze event thumbnails and generate searchable, natural-language descriptions.

- **Modern Dashboard:**  
  Access all features from a single, unified panel in Home Assistant.

---

## 🎬 Usage

- **Live Tab:**  
  View all camera streams in a responsive grid.

- **LPR Tab:**  
  - Add triggers for license plates, make/model/color.
  - See real-time logs and matched events.

- **AI Search Tab:**  
  - Save your Google Gemini API key.
  - Run AI-powered event analysis and search for events using keywords.

- **Dashboard Tab:**  
  - (WIP) See camera uptime, event counts, and more.

---

## 🔒 Privacy & Security

- Your Videoloft credentials and API keys are stored securely in Home Assistant.
- AI event analysis is opt-in and requires your own Google Gemini API key.

---

## 📝 License

MIT License.  
Copyright © [StannyByte](https://github.com/StannyByte)

---

## 🙏 Acknowledgements

- [Videoloft](https://videoloft.com) for their robust VMS cloud platform.
- [Home Assistant](https://www.home-assistant.io/) for the best open-source smart home platform.
- [Google Gemini](https://ai.google.dev/gemini-api/docs) for AI event analysis.

---

**Enjoy smarter, safer surveillance with Videoloft + Home Assistant!** 🚀
