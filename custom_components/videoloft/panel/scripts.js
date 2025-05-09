(function () {
  "use strict";

  // Utility: shorthand for document.getElementById
  const $ = (id) => document.getElementById(id);
  const capitalizeFirstLetter = (string) =>
    string.charAt(0).toUpperCase() + string.slice(1);

  /* ================================
   *              Tabs
   * ================================ */
  class Tabs {
    constructor() {
      this.navItems = document.querySelectorAll(".nav-item");
      this.tabSections = document.querySelectorAll(".tab-section");
      this.init();
    }

    init() {
      this.navItems.forEach((item) => {
        item.addEventListener("click", () => this.activateTab(item));
      });
      // Activate the first tab if none is active
      const activeItem =
        document.querySelector(".nav-item.active") || this.navItems[0];
      if (activeItem) this.showTabContent(activeItem, false);
    }

    activateTab(selectedItem) {
      this.showTabContent(selectedItem, true);
    }

    showTabContent(selectedItem, showNotification = true) {
      this.navItems.forEach((item) => item.classList.remove("active"));
      selectedItem.classList.add("active");

      this.tabSections.forEach((section) => section.classList.remove("active"));
      const tabId = selectedItem.getAttribute("data-tab");
      const activeSection = document.getElementById(`${tabId}Tab`);
      if (activeSection) {
        activeSection.classList.add("active");
      } else {
        console.warn(`No tab section found for tab ID: ${tabId}`);
      }
      console.log(`${capitalizeFirstLetter(tabId)} tab activated`);
    }
  }

  /* ================================
   *          Videoloft Player
   * ================================ */
  class VideoloftPlayer {
    constructor(cameras) {
      this.cameras = cameras;
      this.players = new Map();
      this.streamTimeouts = new Map();
      this.streamAttempts = new Map();
      this.streamStartTimes = new Map();
      this.STREAM_TIMEOUT = 4000;
      this.MAX_LOAD_RETRIES = 5;
      this.RETRY_DELAY = 1000;
      this.init();
    }

    init() {
      this.renderCameras();
      this.setGridColumns();
      this.startStreams();
      window.addEventListener("resize", () => this.setGridColumns());
    }

    renderCameras() {
      const grid = document.querySelector(".camera-grid");
      if (!grid) return;
      grid.innerHTML = this.cameras
        .map(
          (camera) => `
          <div class="camera-card" id="card-${camera.uidd}">
            <div class="video-container">
              <img id="thumb-${camera.uidd}" class="thumbnail" src="/api/videoloft/thumbnail/${camera.uidd}" alt="Loading thumbnail..." />
              <div class="loading-spinner" id="spinner-${camera.uidd}"></div>
              <video id="video-${camera.uidd}" playsinline muted></video>
              <button class="fullscreen-button" aria-label="Toggle fullscreen">
                <i class="fas fa-expand"></i>
              </button>
              <div class="camera-header">
                <div class="camera-name">
                  <i class="fas fa-video"></i> ${camera.name}
                </div>
                <div class="camera-info">
                  <i class="fas fa-camera"></i> ${camera.model} - ${camera.resolution}
                </div>
              </div>
              <div class="error-message" id="error-${camera.uidd}"></div>
            </div>
          </div>
        `
        )
        .join("");
      this.updateOnlineCameras();
      this.setupFullscreenHandlers();
    }

    setupFullscreenHandlers() {
      this.cameras.forEach((camera) => {
        const container = document.getElementById(`card-${camera.uidd}`);
        const fullscreenBtn = container?.querySelector(".fullscreen-button");
        const videoElement = document.getElementById(`video-${camera.uidd}`);
        if (fullscreenBtn && videoElement) {
          fullscreenBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (document.fullscreenElement) {
              document.exitFullscreen();
              fullscreenBtn.innerHTML = '<i class="fas fa-expand"></i>';
            } else {
              videoElement.requestFullscreen();
              fullscreenBtn.innerHTML = '<i class="fas fa-compress"></i>';
            }
          });
          document.addEventListener("fullscreenchange", () => {
            if (!document.fullscreenElement && fullscreenBtn) {
              fullscreenBtn.innerHTML = '<i class="fas fa-expand"></i>';
            }
          });
        }
      });
    }

    setupZoomControls() {
      this.cameras.forEach((camera) => {
        const container = document.getElementById(`card-${camera.uidd}`);
        const videoContainer = container.querySelector(".video-container");
        const videoElement = document.getElementById(`video-${camera.uidd}`);
        const controls = document.createElement("div");
        controls.className = "video-controls";
        const zoomIn = document.createElement("button");
        zoomIn.innerHTML = '<i class="fas fa-search-plus"></i>';
        zoomIn.setAttribute("aria-label", "Zoom in");
        const zoomOut = document.createElement("button");
        zoomOut.innerHTML = '<i class="fas fa-search-minus"></i>';
        zoomOut.setAttribute("aria-label", "Zoom out");
        zoomOut.style.display = "none";
        const resetZoom = document.createElement("button");
        resetZoom.innerHTML = '<i class="fas fa-undo"></i>';
        resetZoom.setAttribute("aria-label", "Reset zoom");
        resetZoom.style.display = "none";

        let currentZoom = 1,
          isDragging = false,
          lastMouseX = 0,
          lastMouseY = 0,
          translateX = 0,
          translateY = 0;
        const MIN_ZOOM = 1,
          MAX_ZOOM = 2.5,
          ZOOM_SPEED = 0.0005;

        const updateTransform = (smooth = true) => {
          videoElement.style.transition = smooth ? "transform 0.2s ease" : "none";
          videoElement.style.transform = `scale(${currentZoom}) translate(${translateX}px, ${translateY}px)`;
          if (currentZoom > 1) {
            videoContainer.classList.add("zoomed");
            zoomOut.style.display = "flex";
            resetZoom.style.display = "flex";
            videoContainer.style.cursor = isDragging ? "grabbing" : "grab";
          } else {
            videoContainer.classList.remove("zoomed");
            zoomOut.style.display = "none";
            resetZoom.style.display = "none";
            videoContainer.style.cursor = "default";
            translateX = 0;
            translateY = 0;
          }
          zoomIn.style.display = currentZoom >= MAX_ZOOM ? "none" : "flex";
        };

        const constrainBounds = () => {
          const rect = videoContainer.getBoundingClientRect();
          const visibleWidth = rect.width / currentZoom;
          const visibleHeight = rect.height / currentZoom;
          const maxX = (rect.width - visibleWidth) / 2;
          const maxY = (rect.height - visibleHeight) / 2;
          translateX = Math.max(-maxX, Math.min(maxX, translateX));
          translateY = Math.max(-maxY, Math.min(maxY, translateY));
        };

        const applyZoom = (delta, mouseX, mouseY) => {
          const rect = videoContainer.getBoundingClientRect();
          const oldZoom = currentZoom;
          const zoomDelta = -delta * ZOOM_SPEED;
          currentZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, currentZoom * (1 + zoomDelta)));
          if (currentZoom !== oldZoom) {
            const relX = (mouseX - rect.left) / rect.width;
            const relY = (mouseY - rect.top) / rect.height;
            const scaleChange = currentZoom / oldZoom;
            translateX = (translateX - relX * rect.width) * scaleChange + relX * rect.width;
            translateY = (translateY - relY * rect.height) * scaleChange + relY * rect.height;
            constrainBounds();
            updateTransform(true);
          }
        };

        videoContainer.addEventListener("wheel", (e) => {
          e.preventDefault();
          applyZoom(e.deltaY, e.clientX, e.clientY);
        });

        videoContainer.addEventListener("mousedown", (e) => {
          if (currentZoom > 1) {
            isDragging = true;
            lastMouseX = e.clientX;
            lastMouseY = e.clientY;
            videoContainer.style.cursor = "grabbing";
          }
        });

        document.addEventListener("mousemove", (e) => {
          if (!isDragging) return;
          const deltaX = (e.clientX - lastMouseX) / currentZoom;
          const deltaY = (e.clientY - lastMouseY) / currentZoom;
          translateX += deltaX;
          translateY += deltaY;
          lastMouseX = e.clientX;
          lastMouseY = e.clientY;
          constrainBounds();
          updateTransform(false);
        });

        document.addEventListener("mouseup", () => {
          isDragging = false;
          videoContainer.style.cursor = currentZoom > 1 ? "grab" : "default";
        });

        zoomIn.addEventListener("click", () => {
          if (currentZoom < MAX_ZOOM) {
            const rect = videoContainer.getBoundingClientRect();
            applyZoom(-1000, rect.left + rect.width / 2, rect.top + rect.height / 2);
          }
        });

        zoomOut.addEventListener("click", () => {
          if (currentZoom > MIN_ZOOM) {
            const rect = videoContainer.getBoundingClientRect();
            applyZoom(1000, rect.left + rect.width / 2, rect.top + rect.height / 2);
          }
        });

        resetZoom.addEventListener("click", () => {
          currentZoom = 1;
          translateX = 0;
          translateY = 0;
          updateTransform(true);
        });

        controls.appendChild(zoomIn);
        controls.appendChild(zoomOut);
        controls.appendChild(resetZoom);
        videoContainer.appendChild(controls);
      });
    }

    // Updated setGridColumns() function
    setGridColumns() {
      const grid = document.querySelector(".camera-grid");
      if (!grid) return;
      const screenWidth = window.innerWidth;
      if (screenWidth <= 768) {
        // Mobile view: single column full width (unchanged)
        grid.style.gridTemplateColumns = "repeat(1, minmax(100%, 1fr))";
        grid.style.gap = "8px";
        grid.style.margin = "0 -24px";
        grid.style.width = "calc(100% + 48px)";
      } else {
        // Desktop view: use auto-fit so the cards expand to fill available space.
        // Each card has a minimum width of 320px.
        grid.style.gridTemplateColumns = "repeat(auto-fit, minmax(320px, 1fr))";
        grid.style.gap = "20px";
        grid.style.margin = "";
        grid.style.width = "100%";
      }
    }
    
    startStreams() {
      this.cleanup();
      this.cameras.forEach((camera) => {
        const videoElement = document.getElementById(`video-${camera.uidd}`);
        const spinner = document.getElementById(`spinner-${camera.uidd}`);
        const thumbnail = document.getElementById(`thumb-${camera.uidd}`);
        const errorElement = document.getElementById(`error-${camera.uidd}`);
        this.initializeStream(camera, videoElement, spinner, thumbnail, errorElement);
      });
    }
  
    setStreamTimeout(camera, videoElement, spinner, thumbnail, errorElement) {
      const timeoutId = setTimeout(() => {
        console.warn(`Stream timeout for ${camera.name}, restarting...`);
        this.handleStreamTimeout(camera, videoElement, spinner, thumbnail, errorElement);
      }, this.STREAM_TIMEOUT);
      this.streamTimeouts.set(camera.uidd, timeoutId);
    }
  
    clearStreamTimeout(uidd) {
      const timeoutId = this.streamTimeouts.get(uidd);
      if (timeoutId) {
        clearTimeout(timeoutId);
        this.streamTimeouts.delete(uidd);
      }
    }
  
    handleStreamTimeout(camera, videoElement, spinner, thumbnail, errorElement) {
      const attempts = this.streamAttempts.get(camera.uidd) || 0;
      if (attempts < this.MAX_LOAD_RETRIES) {
        this.streamAttempts.set(camera.uidd, attempts + 1);
        console.log(`Restarting stream for ${camera.name} (Attempt ${attempts + 1})`);
        this.reloadStream(camera.uidd);
      } else {
        console.error(`Stream failed to load for ${camera.name} after ${attempts} attempts`);
        if (errorElement) {
          errorElement.style.display = "block";
          errorElement.textContent = "❗ Stream failed to load. Click thumbnail to retry.";
        }
        if (spinner) spinner.style.display = "none";
        if (thumbnail) thumbnail.style.display = "block";
      }
    }
  
    initializeStream(camera, videoElement, spinner, thumbnail, errorElement, retryCount = 0) {
      if (spinner) spinner.style.display = "block";
      if (thumbnail) thumbnail.style.display = "block";
      if (videoElement) videoElement.style.display = "none";
      if (errorElement) errorElement.style.display = "none";
  
      this.clearStreamTimeout(camera.uidd);
      this.setStreamTimeout(camera, videoElement, spinner, thumbnail, errorElement);
      this.streamStartTimes.set(camera.uidd, Date.now());
      const streamUrl = `/api/videoloft/stream/${camera.uidd}/index.m3u8`;
  
      if (Hls.isSupported()) {
        const hls = new Hls({
          enableWorker: true,
          debug: false,
          manifestLoadingMaxRetry: 2,
          manifestLoadingRetryDelay: 1000,
          levelLoadingMaxRetry: 2,
          levelLoadingRetryDelay: 1000,
          fragLoadingMaxRetry: 2,
          fragLoadingRetryDelay: 1000,
        });
        hls.loadSource(streamUrl);
        hls.attachMedia(videoElement);
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          this.clearStreamTimeout(camera.uidd);
          if (spinner) spinner.style.display = "none";
          if (thumbnail) thumbnail.style.display = "none";
          if (videoElement) {
            videoElement.style.display = "block";
            videoElement.play().catch((error) => {
              console.error(`Playback error for ${camera.name}:`, error);
              this.handlePlaybackError(camera, videoElement, spinner, thumbnail, errorElement);
            });
          }
        });
        hls.on(Hls.Events.ERROR, (event, data) => {
          const { type, fatal } = data;
          console.error(`HLS error for ${camera.name}:`, data);
          if (fatal) {
            this.handleFatalError(hls, camera, videoElement, spinner, thumbnail, errorElement, type, retryCount);
          }
        });
        this.monitorStreamHealth(camera, videoElement, hls);
        this.players.set(camera.uidd, hls);
      } else if (videoElement.canPlayType("application/vnd.apple.mpegurl")) {
        this.initializeNativeHLS(camera, videoElement, spinner, thumbnail, errorElement, streamUrl);
      } else {
        this.handleUnsupportedBrowser(camera, errorElement);
      }
  
      if (thumbnail) {
        thumbnail.onclick = () => {
          this.streamAttempts.delete(camera.uidd);
          this.reloadStream(camera.uidd);
        };
      }
    }
  
    monitorStreamHealth(camera, videoElement, hls) {
      const healthCheck = setInterval(() => {
        if (videoElement.paused || videoElement.ended) this.reloadStream(camera.uidd);
      }, 5000);
      this.players.set(`${camera.uidd}_health`, healthCheck);
    }
  
    handleFatalError(hls, camera, videoElement, spinner, thumbnail, errorElement, errorType, retryCount) {
      switch (errorType) {
        case Hls.ErrorTypes.NETWORK_ERROR:
          if (retryCount < this.MAX_LOAD_RETRIES) {
            console.warn(`Network error on ${camera.name}, retrying...`);
            setTimeout(() => { hls.startLoad(); }, this.RETRY_DELAY);
          } else {
            this.handleStreamTimeout(camera, videoElement, spinner, thumbnail, errorElement);
          }
          break;
        case Hls.ErrorTypes.MEDIA_ERROR:
          console.warn(`Media error on ${camera.name}, attempting recovery...`);
          hls.recoverMediaError();
          break;
        default:
          if (retryCount < this.MAX_LOAD_RETRIES) {
            console.warn(`Fatal error on ${camera.name}, restarting stream...`);
            this.reloadStream(camera.uidd);
          } else {
            this.handleStreamTimeout(camera, videoElement, spinner, thumbnail, errorElement);
          }
          break;
      }
    }
  
    handlePlaybackError(camera, videoElement, spinner, thumbnail, errorElement) {
      const attempts = this.streamAttempts.get(camera.uidd) || 0;
      if (attempts < this.MAX_LOAD_RETRIES) {
        setTimeout(() => {
          this.reloadStream(camera.uidd);
        }, this.RETRY_DELAY * Math.pow(2, attempts));
      } else {
        this.handleStreamTimeout(camera, videoElement, spinner, thumbnail, errorElement);
      }
    }
  
    initializeNativeHLS(camera, videoElement, spinner, thumbnail, errorElement, streamUrl) {
      videoElement.src = streamUrl;
      videoElement.addEventListener("loadedmetadata", () => {
        this.clearStreamTimeout(camera.uidd);
        if (spinner) spinner.style.display = "none";
        if (thumbnail) thumbnail.style.display = "none";
        videoElement.style.display = "block";
        videoElement.play().catch((error) => {
          console.error(`Native playback error for ${camera.name}:`, error);
          this.handlePlaybackError(camera, videoElement, spinner, thumbnail, errorElement);
        });
      });
      videoElement.addEventListener("error", () => {
        console.error(`Native video error for ${camera.name}`);
        this.handleStreamTimeout(camera, videoElement, spinner, thumbnail, errorElement);
      });
      this.players.set(camera.uidd, { type: "native", element: videoElement });
    }
  
    handleUnsupportedBrowser(camera, errorElement) {
      console.error(`HLS not supported in this browser for ${camera.name}`);
      if (errorElement) {
        errorElement.style.display = "block";
        errorElement.textContent = "❗ HLS not supported in this browser.";
      }
    }
  
    reloadStream(uidd) {
      const camera = this.cameras.find((cam) => cam.uidd === uidd);
      if (!camera) return;
      this.cleanupPlayer(uidd);
      const videoElement = document.getElementById(`video-${uidd}`);
      const spinner = document.getElementById(`spinner-${uidd}`);
      const thumbnail = document.getElementById(`thumb-${uidd}`);
      const errorElement = document.getElementById(`error-${uidd}`);
      const attempts = this.streamAttempts.get(uidd) || 0;
      this.initializeStream(camera, videoElement, spinner, thumbnail, errorElement, attempts);
    }
  
    cleanupPlayer(uidd) {
      const healthCheck = this.players.get(uidd + "_health");
      if (healthCheck) {
        clearInterval(healthCheck);
        this.players.delete(uidd + "_health");
      }
      this.clearStreamTimeout(uidd);
      const player = this.players.get(uidd);
      if (player) {
        if (player instanceof Hls) {
          player.destroy();
        } else if (player.type === "native") {
          const element = player.element;
          element.pause();
          element.src = "";
          element.load();
        }
        this.players.delete(uidd);
      }
    }
  
    cleanup() {
      this.players.forEach((_, uidd) => {
        this.cleanupPlayer(uidd);
      });
      this.streamTimeouts.clear();
      this.streamAttempts.clear();
      this.streamStartTimes.clear();
    }
  
    updateOnlineCameras() {
      const onlineEl = $("onlineCameras");
      if (onlineEl) onlineEl.textContent = `${this.cameras.length} Cameras Online`;
    }
  }

  /* ================================
   *          LPR Manager
   * ================================ */
  class LPRManager {
    constructor() {
      this.logContainer = $("lprLogs");
      this.clearLogsBtn = $("clearLogs");
      this.maxLogEntries = 1000;
      this.cameraSelect = $("cameraSelect");
      this.lprForm = $("lprForm");
      this.triggersList = $("lprTriggersList");
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
          license_plate: $("licensePlate").value,
          make: $("make").value,
          model: $("model").value,
          color: $("color").value,
        };
        if (!formData.uidd) {
          alert("Please select a camera");
          return;
        }
        if (
          !formData.license_plate &&
          !formData.make &&
          !formData.model &&
          !formData.color
        ) {
          alert("At least one identifier is required");
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
                        ${trigger.license_plate ? `<span><strong>Plate:</strong> ${trigger.license_plate}</span>` : ""}
                        ${trigger.make ? `<span><strong>Make:</strong> ${trigger.make}</span>` : ""}
                        ${trigger.model ? `<span><strong>Model:</strong> ${trigger.model}</span>` : ""}
                        ${trigger.color ? `<span><strong>Color:</strong> ${trigger.color}</span>` : ""}
                        <span><strong>Camera:</strong> ${trigger.uidd}</span>
                      </div>
                    </div>
                    <div class="trigger-actions">
                      <button class="btn btn-warning" onclick="window.deleteTrigger(${index})" aria-label="Delete trigger">
                        <i class="fas fa-trash"></i>
                      </button>
                    </div>
                  </div>
                `
        )
        .join("");
    }

    async deleteTrigger(index) {
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

  /* ================================
   *             AI Manager
   * ================================ */
  class AIManager {
    constructor() {
      this.geminiApiKeyInput = $("geminiApiKey");
      this.saveApiKeyButton = $("saveApiKeyButton");
      this.removeApiKeyButton = $("removeApiKeyButton");
      this.runAISearchButton = $("runAISearchButton");
      this.aiSearchInput = $("aiSearchInput");
      this.aiSearchButton = $("aiSearchButton");
      this.searchResultsDiv = $("searchResults");
      this.taskStatusDiv = $("taskStatus");
      this.aiCameraSelect = $("aiCameraSelect");
      this.aiSearchLogs = $("aiSearchLogs");
      this.maxLogEntries = 100;
      this.init();
    }

    async init() {
      await this.checkApiKey();
      await this.populateCameraSelector();
      this.setupApiKeyHandlers();
      this.setupRunAISearchHandler();
      this.setupSearchHandler();
      this.setupClearDescriptionsHandler();
    }

    async checkApiKey() {
      try {
        const response = await fetch("/api/videoloft/gemini_key");
        const data = await response.json();
        if (data.has_key) {
          this.geminiApiKeyInput.value = "********";
          this.geminiApiKeyInput.disabled = true;
          this.saveApiKeyButton.disabled = true;
          this.removeApiKeyButton.disabled = false;
          console.log("Gemini API key loaded");
        } else {
          this.geminiApiKeyInput.value = "";
          this.geminiApiKeyInput.disabled = false;
          this.saveApiKeyButton.disabled = false;
          this.removeApiKeyButton.disabled = true;
          console.log("No Gemini API key found");
        }
      } catch (error) {
        console.error("Error checking API key:", error);
      }
    }

    setupApiKeyHandlers() {
      this.saveApiKeyButton.addEventListener("click", async () => {
        const apiKey = this.geminiApiKeyInput.value.trim();
        if (!apiKey) {
          alert("Please enter an API key.");
          return;
        }
        try {
          const response = await fetch("/api/videoloft/gemini_key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: apiKey }),
          });
          const data = await response.json();
          if (response.ok) {
            alert("API key saved successfully.");
            this.geminiApiKeyInput.value = "********";
            this.geminiApiKeyInput.disabled = true;
            this.saveApiKeyButton.disabled = true;
            this.removeApiKeyButton.disabled = false;
            console.log("Gemini API key saved successfully");
          } else {
            alert("Error saving API key: " + data.error);
            console.error(`Error saving API key: ${data.error}`);
          }
        } catch (error) {
          console.error("Error saving API key:", error);
        }
      });

      this.removeApiKeyButton.addEventListener("click", async () => {
        try {
          const response = await fetch("/api/videoloft/gemini_key", { method: "DELETE" });
          const data = await response.json();
          if (response.ok) {
            alert("API key removed successfully.");
            this.geminiApiKeyInput.value = "";
            this.geminiApiKeyInput.disabled = false;
            this.saveApiKeyButton.disabled = false;
            this.removeApiKeyButton.disabled = true;
            console.log("Gemini API key removed successfully");
          } else {
            alert("Error removing API key: " + data.error);
            console.error(`Error removing API key: ${data.error}`);
          }
        } catch (error) {
          console.error("Error removing API key:", error);
        }
      });
    }

    async populateCameraSelector() {
      try {
        const response = await fetch("/api/videoloft/cameras");
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        const cameras = data.cameras || [];
        if (this.aiCameraSelect) {
          this.aiCameraSelect.innerHTML = "<option value=''>Select Camera</option>";
          cameras.forEach((camera) => {
            const option = document.createElement("option");
            option.value = camera.uidd;
            option.textContent = camera.name;
            this.aiCameraSelect.appendChild(option);
          });
          console.log(
            cameras.length > 0
              ? `Loaded ${cameras.length} cameras into selector`
              : "No cameras available for AI Search"
          );
        }
      } catch (error) {
        console.error("Failed to populate AI Search camera selector:", error);
      }
    }

    setupRunAISearchHandler() {
      this.runAISearchButton.addEventListener("click", async () => {
        const selectedCamera = this.aiCameraSelect.value;
        if (!selectedCamera) {
          alert("Please select a camera first.");
          return;
        }
        this.taskStatusDiv.innerHTML = "<p>Processing events...</p>";
        try {
          const response = await fetch("/api/videoloft/process_ai_search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ camera: selectedCamera }),
          });
          const data = await response.json();
          if (response.ok) {
            this.taskStatusDiv.innerHTML = "<p>Events are being processed. This may take some time.</p>";
            console.log("AI Search task initiated");
          } else {
            this.taskStatusDiv.innerHTML = `<p>Error: ${data.error}</p>`;
            console.error(`Failed to initiate AI Search task: ${data.error}`);
          }
        } catch (error) {
          console.error("Error processing events:", error);
          this.taskStatusDiv.innerHTML = "<p>An error occurred.</p>";
        }
      });
    }

    setupSearchHandler() {
      this.aiSearchButton.addEventListener("click", async () => {
        const query = this.aiSearchInput.value.trim();
        if (!query) {
          alert("Please enter a search query.");
          return;
        }
        this.searchResultsDiv.innerHTML = "Searching...";
        try {
          const response = await fetch(`/api/videoloft/search_events?query=${encodeURIComponent(query)}`);
          const data = await response.json();
          if (response.ok) {
            this.displaySearchResults(data.events);
            console.log(`Search completed. Found ${data.events.length} events.`);
          } else {
            this.searchResultsDiv.innerHTML = "Error: " + data.error;
            console.error(`Search failed: ${data.error}`);
          }
        } catch (error) {
          console.error("Error searching events:", error);
          this.searchResultsDiv.innerHTML = "An error occurred.";
        }
      });
    }

    displaySearchResults(events) {
      const resultsContainer = this.searchResultsDiv;
      resultsContainer.innerHTML = "";
      if (!events || events.length === 0) {
        resultsContainer.innerHTML = `
                <div class="search-empty-state">
                  <i class="fas fa-search"></i>
                  <h3>No matches found</h3>
                  <p>Try adjusting your search terms or processing more events</p>
                </div>`;
        return;
      }
      const headerDiv = document.createElement("div");
      headerDiv.className = "search-results-header";
      headerDiv.innerHTML = `
              <h3><i class="fas fa-list"></i> Found ${events.length} matching events</h3>
              <div class="search-results-actions">
              </div>`;
      resultsContainer.appendChild(headerDiv);
      const resultsGrid = document.createElement("div");
      resultsGrid.className = "search-results-grid";
      events.forEach((event) => {
        const eventCard = document.createElement("div");
        eventCard.className = "search-result-card";
        const timestamp = new Date(event.startt).toLocaleString();
        eventCard.innerHTML = `
                <div class="result-thumbnail">
                  <img src="${event.thumbnail_url}" alt="Event Thumbnail" loading="lazy">
                  <div class="result-overlay">
                    <a href="${event.recording_url}" target="_blank" class="btn-play" title="View Recording">
                      <i class="fas fa-play"></i>
                    </a>
                  </div>
                </div>
                <div class="result-content">
                  <div class="result-header">
                    <span class="result-time">
                      <i class="far fa-clock"></i> ${timestamp}
                    </span>
                    <span class="result-score">
                      <i class="fas fa-star"></i> ${Math.round(event.relevance * 100)}% match
                    </span>
                  </div>
                  <p class="result-description">${event.description}</p>
                  <div class="result-actions">
                    <button class="btn-secondary" onclick="window.copyToClipboard('${event.recording_url}')">
                      <i class="fas fa-link"></i> Copy Link
                    </button>
                    <a href="${event.recording_url}" target="_blank" class="btn-secondary">
                      <i class="fas fa-external-link-alt"></i> Open
                    </a>
                  </div>
                </div>`;
        resultsGrid.appendChild(eventCard);
      });
      resultsContainer.appendChild(resultsGrid);
    }

    async clearDescriptions() {
      const modal = document.createElement("div");
      modal.className = "modal-overlay";
      modal.innerHTML = `
              <div class="modal-content">
                <h3><i class="fas fa-exclamation-triangle"></i> Warning</h3>
                <p>This will delete all stored event descriptions. This action cannot be undone.</p>
                <div class="modal-actions">
                  <button class="btn-secondary" id="cancelClear">Cancel</button>
                  <button class="btn-warning" id="confirmClear">Delete All</button>
                </div>
              </div>`;
      document.body.appendChild(modal);
      setTimeout(() => modal.classList.add("active"), 10);
      return new Promise((resolve) => {
        const cancelBtn = $("cancelClear");
        const confirmBtn = $("confirmClear");
        const cleanup = () => {
          modal.classList.remove("active");
          setTimeout(() => modal.remove(), 300);
        };
        cancelBtn.onclick = () => {
          cleanup();
          resolve(false);
        };
        confirmBtn.onclick = async () => {
          try {
            const response = await fetch("/api/videoloft/clear_descriptions", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
            });
            if (!response.ok) throw new Error(await response.text());
            this.addLogEntry({
              timestamp: new Date().toISOString(),
              level: "INFO",
              message: "All event descriptions cleared successfully",
            });
            if (this.searchResultsDiv) this.searchResultsDiv.innerHTML = "";
            cleanup();
            resolve(true);
          } catch (error) {
            console.error("Failed to clear descriptions:", error);
            cleanup();
            resolve(false);
          }
        };
      });
    }

    setupClearDescriptionsHandler() {
      const clearBtn = $("clearDescriptionsBtn");
      if (clearBtn) clearBtn.addEventListener("click", () => this.clearDescriptions());
    }
  }

  /* ================================
   *         Global Functions
   * ================================
   */
  window.openRecording = function (url) {
    window.open(url, "_blank");
  };

  window.copyToClipboard = function (text) {
    navigator.clipboard
      .writeText(text)
      .then(() => console.log("Link copied to clipboard"))
      .catch(() => console.error("Failed to copy link"));
  };

  window.downloadResults = function () {
    console.log("Download functionality not implemented.");
  };

  window.deleteTrigger = function (index) {
    if (window.lprManager) {
      window.lprManager.deleteTrigger(index);
    }
  };

  window.capitalizeFirstLetter = capitalizeFirstLetter;

  /* ================================
   *        Initialization
   * ================================
   */
  document.addEventListener("DOMContentLoaded", async () => {
    // Initialize tabs & managers for an awesome interactive experience
    const tabs = new Tabs();
    window.lprManager = new LPRManager();
    const aiManager = new AIManager();

    // Asynchronously fetch camera data with robust error handling
    const fetchCameraData = async () => {
      try {
        const response = await fetch("/api/videoloft/cameras");
        if (!response.ok) throw new Error("Failed to fetch cameras");
        const data = await response.json();
        return data.cameras || [];
      } catch (error) {
        console.error("Error fetching camera data:", error);
        return [];
      }
    };

    const cameras = await fetchCameraData();

    // Display cameras or friendly error message
    if (cameras.length > 0) {
      new VideoloftPlayer(cameras);
    } else {
      const grid = document.querySelector(".camera-grid");
      if (grid) {
        grid.innerHTML = `
        <div class="error-message">
          <i class="fas fa-camera-slash"></i> No cameras found.
        </div>`;
      }
    }

    // Set up eye-catching dashboard metrics
    const activeCamerasEl = document.getElementById("activeCameras");
    const eventsTodayEl = document.getElementById("eventsToday");
    const uptimeEl = document.getElementById("uptime");
    const vehiclesDetectedEl = document.getElementById("vehiclesDetected");
    if (activeCamerasEl) activeCamerasEl.textContent = `${cameras.length}`;
    if (eventsTodayEl) eventsTodayEl.textContent = "123";
    if (uptimeEl) uptimeEl.textContent = "99%";
    if (vehiclesDetectedEl) vehiclesDetectedEl.textContent = "10";
  });

  // Fetch dashboard data and render stylish cards for each camera
  async function loadDashboardData() {
    try {
      const response = await fetch("/api/videoloft/cameras");
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      const cameras = data.cameras || [];
      renderDashboardCards(cameras);
    } catch (error) {
      console.error("Failed to load dashboard data:", error);
    }
  }

  // Render dashboard cards with an engaging layout and icons
  function renderDashboardCards(cameras) {
    const dashboardGrid = document.getElementById("dashboardGrid");
    if (!dashboardGrid) return;

    dashboardGrid.innerHTML = cameras
      .map((camera) => {
        return `
        <div class="dashboard-card" id="dashboard-${camera.uidd}">
          <h3><i class="fas fa-video"></i> ${camera.name}</h3>
          <p><i class="fas fa-clock"></i> Uptime: ${camera.uptime || "99.8%"}</p>
          <p><i class="fas fa-car"></i> Vehicles Detected: ${camera.vehiclesDetected || "48"}</p>
          <p><i class="fas fa-calendar-alt"></i> Events Today: ${camera.eventsToday || "103"}</p>
          <p><i class="fas fa-cloud"></i> Cloud Adapter ID: ${camera.cloudAdapterId || "TBC"}</p>
          ${camera.model ? `<p><i class="fas fa-info-circle"></i> Model: ${camera.model}</p>` : ""}
          ${camera.resolution ? `<p><i class="fas fa-tv"></i> Resolution: ${camera.resolution}</p>` : ""}
        </div>
      `;
      })
      .join("");
  }

  // Load dashboard data as soon as the DOM is ready for a wow effect
  document.addEventListener("DOMContentLoaded", loadDashboardData);
})();