# HomeAssistant-Videoloft

<p align="center">
  <a href="https://hacs.xyz" target="_blank"><img src="https://img.shields.io/badge/HACS-Default-blue.svg?style=for-the-badge" alt="HACS Badge"></a>
  <a href="https://github.com/StannyByte/HomeAssistant-Videoloft/releases" target="_blank"><img src="https://img.shields.io/github/v/release/StannyByte/HomeAssistant-Videoloft?style=for-the-badge" alt="GitHub release"></a>
  <a href="https://github.com/StannyByte/HomeAssistant-Videoloft/commits/main" target="_blank"><img src="https://img.shields.io/github/last-commit/StannyByte/HomeAssistant-Videoloft?style=for-the-badge" alt="GitHub last commit"></a>
  <a href="LICENSE" target="_blank"><img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge" alt="License: MIT"></a>
</p>

> **Seamlessly connect your Videoloft cameras to Home Assistant for live streaming, license plate alerts with snapshots and AI-powered event search!**

---

## 🚀 What is HomeAssistant-Videoloft?

**HomeAssistant-Videoloft** is a custom integration that brings your Videoloft cameras into Home Assistant. It provides native Home Assistant camera entities for streaming and snapshots, LPR sensors for automation, and a sophisticated custom panel for an enhanced user experience.

Unlock advanced capabilities:
- **Live HLS Streaming** Watch your cameras in real-time directly within Home Assistant.
- **License Plate Recognition (LPR) Automation:** Receive LPR events and trigger automations based on detected license plates.
- **AI-Powered Event Search:** Utilize Google Gemini to analyze event thumbnails and generate smart, searchable natural language descriptions.

---

### Gallery
<p align="left">
  <img src="https://github.com/user-attachments/assets/f22512e9-c72b-448c-b6ed-1a6a5aa89182" alt="Videoloft Live Stream Tab" width="200">
  <img src="https://github.com/user-attachments/assets/538da131-b861-40c5-b419-d7ab263a8e48" alt="LPR Tab with Real-time Logs" width="200">
  <img src="https://github.com/user-attachments/assets/ecbd2327-b5c6-4c10-9e36-55cdeec6bd48" alt="LPR Trigger Management" width="200">
  <img src="https://github.com/user-attachments/assets/078d8154-e5cd-4dcb-b458-7924bdcca679" alt="LPR Detection Logs" width="200">
  <img src="https://github.com/user-attachments/assets/b1fda041-ff29-480c-bc31-d3d08db55be1" alt="AI Event Search Tab" width="200">
  <img src="https://github.com/user-attachments/assets/9872d370-1425-4cba-9bc1-0f7b7e3b66c4" alt="Gemini API Key Setup in Panel" width="200">
  <img src="https://github.com/user-attachments/assets/ddbc0544-a423-45da-89d2-8ae2f6bf7cb9" alt="Home Assistant Notification with Snapshot" width="200">
  <img src="https://github.com/user-attachments/assets/b5465559-612e-475a-8108-07dde45342fb" alt="Notification Automation Example (YAML)" width="200" height="417">
</p>

---

## ✨ Features

- **📺 Advanced Live Streaming:**
  - Smooth and reliable streaming for all your Videoloft cameras.
  - Interactive player with fullscreen toggle, pan, and zoom controls

- **🚗 License Plate Recognition (LPR):**.
  - LPR sensor entities in Home Assistant for triggering automations (e.g., open gates, turn on lights).
  - Dedicated LPR tab in the panel for managing triggers and viewing live detection logs.
  - *Requires Videoloft LPR subscription.*

- **🔍 AI-Powered Event Search (Google Gemini):**
  - Leverage Google Gemini to analyze event thumbnails and generate detailed, human-friendly summaries.
  - Search past events using natural language queries (e.g., "person with red bag near door").
  - Securely manage your Gemini API key within the panel.
  - *Requires your own Google Gemini API key.*

- **⚡ Modern UI Panel:**
  - A beautiful, responsive dashboard accessible directly from the Home Assistant sidebar.
  - Tabbed interface for easy navigation:
    - **Live:** View all camera streams in a dynamic grid.
    - **LPR:** Manage LPR triggers and monitor real-time detections.
    - **AI Search:** Configure Gemini and perform event searches.

- **🔧 Easy Configuration:**
  - Simple setup via the Home Assistant UI (no YAML required for integration setup).
  - Automatic discovery of cameras and LPR capabilities.

---

## 📋 Prerequisites

- Home Assistant (latest stable version recommended).
- A Videoloft account with connected cameras.
- For LPR features: An active Videoloft LPR subscription.
- For AI Search features: Your own Google Gemini API key.

---

## 🛠️ Installation

### HACS (Recommended)

1.  Ensure HACS is installed.
2.  In Home Assistant, go to **HACS > Integrations > Click the 3 dots in the top right > Custom Repositories**.
3.  Enter `https://github.com/StannyByte/HomeAssistant-Videoloft` as the repository URL, select `Integration` as the category, and click **Add**.
4.  The `HomeAssistant-Videoloft` integration will now appear. Click **Install** and follow the prompts.
5.  Restart Home Assistant.

### Manual Installation

1.  Download the latest release from the [Releases page](https://github.com/StannyByte/HomeAssistant-Videoloft/releases).
2.  Copy the `videoloft` folder from the downloaded archive into your Home Assistant `custom_components` directory.
3.  Restart Home Assistant.

---

## ⚙️ Setup & Configuration

1.  After installation and restarting Home Assistant, go to **Settings > Devices & Services**.
2.  Click the **+ Add Integration** button in the bottom right.
3.  Search for **Videoloft** and select it.
4.  Enter your Videoloft username and password when prompted.
5.  The integration will automatically discover your cameras and associated LPR sensors.
6.  Access the custom panel by clicking on **Videoloft Cams** in the Home Assistant sidebar.

> **No YAML needed for integration setup!**
> All core integration configuration is handled via the Home Assistant UI. Panel-specific settings (like the Gemini API key) are managed within the panel itself.

---

## 🧠 How It Works

- **Core Integration:**
  - **Camera Entities:** Creates standard Home Assistant `camera` entities. These provide HLS stream sources (`stream_source`) for live viewing and snapshot capabilities (`async_camera_image`).
  - **LPR Sensor Entities:** If LPR is enabled on your Videoloft account, `sensor` entities are created to report the latest LPR event data, enabling powerful automations.
  - **API Communication:** Securely communicates with the Videoloft API to fetch camera lists, stream URLs, and LPR data.

- **Custom Panel (`Videoloft Cams`):**
  - **Rich UI:** Provides an advanced user interface for interacting with your cameras and features.
  - **HLS Player:** Utilizes HLS.js for robust video streaming with custom controls.
  - **LPR Management:** Connects via WebSocket to stream LPR logs in real-time and manage LPR triggers.
  - **AI Search Interface:** Facilitates interaction with the Google Gemini API for event analysis and search.

---

## 🎬 Usage Examples

### Viewing Live Streams
- Navigate to the **Videoloft Cams** panel from the sidebar. The **Live** tab will display all your camera streams.
- Alternatively, add individual camera entities to your Home Assistant dashboards for standard viewing.

### Creating LPR Automations
- Go to **Settings > Automations & Scenes** in Home Assistant.
- Create a new automation, using the **State** of an LPR sensor (e.g., `sensor.videoloft_lpr_matched_event`) as a trigger.
- Example: If the state of `sensor.videoloft_lpr_matched_event` changes, turn on the driveway light.

### Using AI Search
1.  In the **Videoloft Cams** panel, go to the **AI Search** tab.
2.  Enter and save your Google Gemini API key.
3.  Select a camera and run the task.
4.  Type your natural language query (e.g., "person wearing a blue jacket") and click search.

---

## 🙏 Acknowledgements

- [Videoloft](https://videoloft.com) for their excellent cloud VMS platform and API.
- The [Home Assistant Community](https://community.home-assistant.io/) for continuous inspiration and support.
- [Google Gemini](https://ai.google.dev/gemini-api/docs) for the powerful AI capabilities.
