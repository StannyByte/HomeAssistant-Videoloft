"use strict";

class AIManager {
  constructor() {
    this.geminiApiKeyInput = document.getElementById("geminiApiKey"); // Use $ if available
    this.saveApiKeyButton = document.getElementById("saveApiKeyButton");
    this.removeApiKeyButton = document.getElementById("removeApiKeyButton");
    this.runAISearchButton = document.getElementById("runAISearchButton");
    this.aiSearchInput = document.getElementById("aiSearchInput");
    this.aiSearchButton = document.getElementById("aiSearchButton");
    this.searchResultsDiv = document.getElementById("searchResults");
    this.taskStatusDiv = document.getElementById("taskStatus");
    this.aiCameraSelect = document.getElementById("aiCameraSelect");
    this.aiSearchLogs = document.getElementById("aiSearchLogs"); // Ensure this element exists if used
    this.maxLogEntries = 100; // If aiSearchLogs is used for logging
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
                  <a href="${event.recording_url}" target="_blank" class="btn btn-primary btn-full-width">
                    <i class="fas fa-external-link-alt"></i> Play event in Videoloft
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
      const cancelBtn = document.getElementById("cancelClear"); // Use $ if available
      const confirmBtn = document.getElementById("confirmClear"); // Use $ if available
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
          // Add log entry if a logging mechanism is implemented for AIManager
          // Example: this.addLogEntry({ timestamp: new Date().toISOString(), level: "INFO", message: "All event descriptions cleared successfully" });
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
    const clearBtn = document.getElementById("clearDescriptionsBtn"); // Use $ if available
    if (clearBtn) clearBtn.addEventListener("click", () => this.clearDescriptions());
  }
} 