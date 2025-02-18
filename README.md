# HomeAssistant-Videoloft



[![HACS Badge](https://img.shields.io/badge/HACS-Default-blue.svg)](https://hacs.xyz)  

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)  

[![GitHub release](https://img.shields.io/github/release/StannyByte/HomeAssistant-Videoloft.svg)](https://github.com/StannyByte/HomeAssistant-Videoloft/releases)



A custom integration for Home Assistant that seamlessly connects to Videoloft cameras. This integration enables real‑time live streaming, license plate recognition automation, and AI Search directly from Home Assistant.



## Overview



HomeAssistant‑Videoloft connects your Videoloft cameras to Home Assistant by automatically adding each camera as a device and corresponding entity. In addition, the integration provides a dedicated LPR sensor that updates when a license plate is detected—allowing you to create automations (for example, to control gates, lights, or other devices) based on specific plate events.



## Features



- **Live Streaming:**  

  Supports HLS live streaming.

  

- **License Plate Recognition (LPR):**  

  Automatically processes camera events to detect and match license plates, enabling automations triggered by plate detections(Must have Videoloft LPR).



- **AI Search:**  

  Leverages OpenAI’s GPT‑4 model to analyze events and generate detailed, searchable descriptions of captured events.



- **Config Flow:**  

  Configure the integration easily via the Home Assistant UI—no YAML configuration required.



- **Dashboard Metrics:**  

  Displays real-time camera status, uptime, and event history directly on your Home Assistant dashboards (WIP).



## Installation



### Manual Installation



1. Copy the `videoloft` folder into the `custom_components` directory of your Home Assistant configuration.

2. Restart Home Assistant.



### HACS (Home Assistant Community Store)



1. In HACS, go to **Integrations** > **+ Explore & Add Repositories**.

2. Search for `HomeAssistant-Videoloft` or add it via the URL: `https://github.com/StannyByte/HomeAssistant-Videoloft`.

3. Install the integration and restart Home Assistant.



## Configuration



Once installed, configure the integration via the Home Assistant UI:



1. Go to **Configuration** > **Devices & Services**.

2. Click **+ Add Integration**.

3. Search for **Videoloft** and follow the on‑screen instructions (enter your Videoloft credentials, etc.).



No YAML configuration is necessary.



## How It Works



- **Camera Devices & Entities:**  

  Each Videoloft camera is automatically added as a device with an associated entity. This makes it easy to view live streams and access camera-specific information directly within Home Assistant.



- **LPR Sensor:**  

  The integration creates a dedicated LPR sensor that updates on license plate detection. Use this sensor to trigger automations—such as opening gates or controlling other devices—when a specific license plate is detected.



- **AI Search:**  

  The AI Search functionality leverages OpenAI’s GPT‑4 model to analyze camera events. It generates detailed, searchable descriptions that help you quickly find events in your history.



## Usage



After configuration, you will be able to:

- **View Live Streams:** Monitor your cameras in real‑time under the **Live** tab.

- **Set Up LPR Triggers:** Use the **LPR** tab to configure triggers and create automations based on detected license plates.

- **Run AI Search:** Initiate AI Search tasks via the **AI Search** tab.

- **Monitor Dashboard Metrics:** Access comprehensive metrics (e.g., camera status, uptime, and event history) under the **Dashboard** tab.
