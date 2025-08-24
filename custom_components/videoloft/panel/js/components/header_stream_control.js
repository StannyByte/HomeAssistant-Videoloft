"use strict";

/**
 * Header Stream Control - Clean stream toggle button in the header
 * Replaces complex WebSocket tracking with simple user-controlled streaming
 */
(function () {
  class HeaderStreamControl {
    constructor() {
      console.log("HeaderStreamControl: Initializing...");
      this.endpoint = "/api/videoloft/global_stream_state";
      this.button = document.getElementById("globalStreamToggle");
      this.icon = document.getElementById("streamToggleIcon");
      this.text = document.getElementById("streamToggleText");
      this.isLoading = false;
      this.currentState = null;

      if (!this.button) {
        console.warn("HeaderStreamControl: Button not found - DOM elements missing");
        return;
      }
      
      console.log("HeaderStreamControl: Button found, initializing...");
      this.init();
    }

    init() {
      console.log("HeaderStreamControl: Setting up event listeners...");
      // Bind click event
      this.button.addEventListener("click", () => {
        console.log("HeaderStreamControl: Button clicked!");
        this.handleToggle();
      });

      // Initial state load
      console.log("HeaderStreamControl: Loading initial state...");
      this.refreshState();

      // Periodic state refresh (less frequent than old implementation)
      setInterval(() => this.refreshState(), 10000); // 10 seconds
    }

    async handleToggle() {
      console.log("HeaderStreamControl: handleToggle called, current state:", this.currentState, "isLoading:", this.isLoading);
      if (this.isLoading || !this.currentState) {
        console.log("HeaderStreamControl: Skipping toggle - loading or no state");
        return;
      }

      const newEnabled = !this.currentState.enabled;
      console.log("HeaderStreamControl: Toggling to:", newEnabled);
      
      try {
        this.setLoading(true);
        
        console.log("HeaderStreamControl: Making API call to", this.endpoint);
        const response = await fetch(this.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: newEnabled })
        });

        console.log("HeaderStreamControl: API response status:", response.status);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        console.log("HeaderStreamControl: API response data:", data);
        this.currentState = data;
        this.updateUI();

        // Show feedback to user
        this.showFeedback(newEnabled ? "Streams enabled" : "Streams paused");
        
        // Refresh video player if on live tab to show immediate effect
        if (window.videoPlayer && document.querySelector('.nav-item[data-tab="live"]').classList.contains('active')) {
          setTimeout(() => {
            if (newEnabled) {
              window.videoPlayer.startStreams();
            } else {
              window.videoPlayer.pauseAllStreams();
            }
          }, 500);
        }

      } catch (error) {
        console.error("HeaderStreamControl: Failed to toggle stream state:", error);
        this.showFeedback("Failed to toggle streams", "error");
      } finally {
        this.setLoading(false);
      }
    }

    async refreshState() {
      if (this.isLoading) return;

      try {
        console.log("HeaderStreamControl: Refreshing state from", this.endpoint);
        const response = await fetch(this.endpoint, { cache: "no-store" });
        console.log("HeaderStreamControl: Refresh response status:", response.status);
        if (!response.ok) {
          console.warn("HeaderStreamControl: Failed to refresh state, HTTP", response.status);
          return;
        }

        const data = await response.json();
        console.log("HeaderStreamControl: Refresh response data:", data);
        this.currentState = data;
        this.updateUI();
      } catch (error) {
        console.debug("HeaderStreamControl: Failed to refresh stream state:", error);
      }
    }

    setLoading(loading) {
      this.isLoading = loading;
      this.button.disabled = loading;
      
      if (loading) {
        this.icon.className = "fas fa-spinner fa-spin";
        if (this.text) this.text.textContent = "...";
      } else {
        this.updateUI();
      }
    }

    updateUI() {
      if (!this.currentState) return;

      const enabled = this.currentState.enabled;
      
      // Update button state classes
      this.button.classList.toggle("active", enabled);
      this.button.classList.toggle("disabled", !enabled);
      
      // Update icon
      this.icon.className = enabled ? "fas fa-video" : "fas fa-video-slash";
      
      // Update text
      if (this.text) {
        this.text.textContent = enabled ? "Streams" : "Paused";
      }
      
      // Update tooltip
      this.button.title = enabled ? "Streams Active - Click to pause" : "Streams Paused - Click to enable";
      
      // Update aria-label
      this.button.setAttribute("aria-label", 
        enabled ? "Pause all camera streams" : "Enable all camera streams"
      );
    }

    showFeedback(message, type = "success") {
      // Try to use existing toast system if available
      if (window.showToast) {
        window.showToast(message, type);
        return;
      }

      // Fallback: simple console feedback
      console.log(`Stream Control: ${message}`);
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === "loading") {
    console.log("HeaderStreamControl: DOM loading, waiting for DOMContentLoaded...");
    document.addEventListener("DOMContentLoaded", () => {
      console.log("HeaderStreamControl: DOMContentLoaded fired, initializing...");
      window.headerStreamControl = new HeaderStreamControl();
    });
  } else {
    console.log("HeaderStreamControl: DOM already ready, initializing immediately...");
    window.headerStreamControl = new HeaderStreamControl();
  }
})();