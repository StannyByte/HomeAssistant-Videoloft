"use strict";

class LPRManager {
  constructor() {
    this.logContainer = document.getElementById("lprLogs"); // Use $ if available and preferred
    this.clearLogsBtn = document.getElementById("clearLogs");
    this.maxLogEntries = 1000;
    this.cameraSelect = document.getElementById("cameraSelect");
    this.lprForm = document.getElementById("lprForm");
    this.triggersList = document.getElementById("lprTriggersList");
    this.init();
  }

  async init() {
    await this.populateCameraSelector();
    await this.loadTriggers();
    this.setupWebSocket();
    this.setupClearLogsHandler();
    this.setupFormHandler();
    this.addLogEntry({
      timestamp: new Date().toISOString(),
      level: "INFO",
      message: "LPR log viewer initialized",
    });
  }

  async populateCameraSelector() {
    try {
      const response = await fetch("/api/videoloft/cameras");
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      const cameras = data.cameras || [];
      if (this.cameraSelect) {
        this.cameraSelect.innerHTML = "<option value=''>Select Camera</option>";
        cameras.forEach((camera) => {
          const option = document.createElement("option");
          option.value = camera.uidd;
          option.textContent = camera.name;
          this.cameraSelect.appendChild(option);
        });
        console.log(
          cameras.length > 0
            ? `Loaded ${cameras.length} cameras into selector`
            : "No cameras available for LPR triggers"
        );
      }
    } catch (error) {
      console.error("Failed to populate camera selector:", error);
      this.addLogEntry({
        timestamp: new Date().toISOString(),
        level: "ERROR",
        message: `Failed to populate camera selector: ${error.message}`,
      });
    }
  }

  setupWebSocket() {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/api/videoloft/ws/lpr_logs`;
    const connect = () => {
      console.log("Attempting WebSocket connection to:", wsUrl);
      this.ws = new WebSocket(wsUrl);
      this.ws.onopen = () => {
        console.log("WebSocket connected");
        this.addLogEntry({
          timestamp: new Date().toISOString(),
          level: "INFO",
          message: "WebSocket connected - Log streaming active",
        });
      };
      this.ws.onmessage = (event) => {
        try {
          const log = JSON.parse(event.data);
          console.log("Received log:", log);
          this.addLogEntry(log);
        } catch (error) {
          console.error("Error processing log:", error);
        }
      };
      this.ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        this.addLogEntry({
          timestamp: new Date().toISOString(),
          level: "ERROR",
          message: "WebSocket error occurred",
        });
      };
      this.ws.onclose = () => {
        console.log("WebSocket closed, attempting to reconnect...");
        this.addLogEntry({
          timestamp: new Date().toISOString(),
          level: "WARNING",
          message: "WebSocket disconnected - Attempting to reconnect...",
        });
        setTimeout(connect, 5000);
      };
    };
    connect();
  }
  setupFormHandler() {
    if (!this.lprForm) return;
    this.lprForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const formData = {
        uidd: this.cameraSelect.value,
        license_plate: document.getElementById("licensePlate").value, // Use $ if available
      };
      if (!formData.uidd) {
        alert("Please select a camera");
        return;
      }
      if (!formData.license_plate) {
        alert("License plate number is required");
        return;
      }
      try {
        const response = await fetch("/api/videoloft/lpr_triggers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(formData),
        });
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.error || "Failed to add trigger");
        }
        await this.loadTriggers();
        this.addLogEntry({
          timestamp: new Date().toISOString(),
          level: "INFO",
          message: "New LPR trigger created",
        });
        this.lprForm.reset();
      } catch (error) {
        console.error("Error adding LPR trigger:", error);
        this.addLogEntry({
          timestamp: new Date().toISOString(),
          level: "ERROR",
          message: `Failed to add trigger: ${error.message}`,
        });
      }
    });
  }

  async loadTriggers() {
    try {
      const response = await fetch("/api/videoloft/lpr_triggers");
      if (!response.ok) throw new Error("Failed to fetch triggers");
      const data = await response.json();
      this.displayTriggers(data.triggers || []);
    } catch (error) {
      console.error("Error loading triggers:", error);
      this.addLogEntry({
        timestamp: new Date().toISOString(),
        level: "ERROR",
        message: `Failed to load triggers: ${error.message}`,
      });
    }
  }
  displayTriggers(triggers) {
    if (!this.triggersList) return;
    this.triggersList.innerHTML = triggers
      .map(
        (trigger, index) => `
                <div class="trigger-item">
                  <div class="trigger-info">
                    <div class="trigger-details">
                      <span><strong>Plate:</strong> ${trigger.license_plate}</span>
                      <span><strong>Camera:</strong> ${trigger.uidd}</span>
                    </div>
                  </div>
                  <div class="trigger-actions">
                    <button class="btn btn-warning" onclick="window.deleteLPRTrigger(${index})" aria-label="Delete trigger">
                      <i class="fas fa-trash"></i>
                    </button>
                  </div>
                </div>
              `
      )
      .join("");
  }

  async deleteTrigger(index) { // Renamed to avoid conflict if globally exposed
    if (!confirm("Are you sure you want to delete this trigger?")) return;
    try {
      const response = await fetch("/api/videoloft/lpr_triggers", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index }),
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to delete trigger");
      }
      await this.loadTriggers();
      this.addLogEntry({
        timestamp: new Date().toISOString(),
        level: "INFO",
        message: `Trigger ${index} deleted successfully`,
      });
    } catch (error) {
      console.error("Error deleting trigger:", error);
      this.addLogEntry({
        timestamp: new Date().toISOString(),
        level: "ERROR",
        message: `Error deleting trigger: ${error.message}`,
      });
    }
  }

  setupClearLogsHandler() {
    if (this.clearLogsBtn) {
      this.clearLogsBtn.addEventListener("click", () => {
        if (this.logContainer) this.logContainer.innerHTML = "";
        this.addLogEntry({
          timestamp: new Date().toISOString(),
          level: "INFO",
          message: "Logs cleared by user",
        });
      });
    }
  }

  addLogEntry(log) {
    if (!this.logContainer) return;
    const entry = document.createElement("div");
    entry.className = `log-entry ${log.level.toLowerCase()}`;
    entry.textContent = `${log.timestamp} - ${log.level} - ${log.message}`;
    this.logContainer.appendChild(entry);
    while (this.logContainer.children.length > this.maxLogEntries) {
      this.logContainer.removeChild(this.logContainer.firstChild);
    }
    this.logContainer.scrollTop = this.logContainer.scrollHeight;
  }
} 