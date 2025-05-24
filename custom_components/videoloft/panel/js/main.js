"use strict";

// Assuming ui.js, tabs.js, videoplayer.js, header_scroll.js, lpr_manager.js, ai_manager.js are loaded before this script
// or will be handled by a module bundler.

(function () {
  /* ================================
   *         Global Functions
   * ================================ */
  window.openRecording = function (url) {
    window.open(url, "_blank");
  };

  window.downloadResults = function () {
    console.log("Download functionality not implemented.");
  };

  // Renamed to avoid conflict with LPRManager internal method if it were global
  window.deleteLPRTrigger = function (index) {
    if (window.lprManagerInstance) { // Check if instance exists
      window.lprManagerInstance.deleteTrigger(index);
    }
  };

  /* ================================
   *        Initialization
   * ================================ */
  document.addEventListener("DOMContentLoaded", async () => {
    // Initialize tabs & managers for an awesome interactive experience
    const tabs = new Tabs();
    window.lprManagerInstance = new LPRManager(); // Store instance for global access
    const aiManager = new AIManager();
    const headerScroll = new HeaderScroll(); // Initialize header scroll behavior

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

    // Add event listeners for copy code buttons
    document.querySelectorAll('.copy-code-button').forEach(button => {
      button.addEventListener('click', () => {
        const targetId = button.getAttribute('data-target');
        const codeElement = document.getElementById(targetId);
        if (codeElement) {
          navigator.clipboard.writeText(codeElement.textContent.trim())
            .then(() => {
              console.log('Code copied to clipboard!');
              const originalHTML = button.innerHTML; // Save original content
              button.textContent = 'Copied!';
              setTimeout(() => { button.innerHTML = originalHTML; }, 2000); // Restore original content
            })
            .catch(err => {
              console.error('Failed to copy code: ', err);
              const originalHTML = button.innerHTML; // Save original content
              button.textContent = 'Failed to copy!';
              setTimeout(() => { button.innerHTML = originalHTML; }, 2000); // Restore original content
            });
        } else {
          console.error('Code element not found for copying.', targetId);
        }
      });
    });
  });
})(); 