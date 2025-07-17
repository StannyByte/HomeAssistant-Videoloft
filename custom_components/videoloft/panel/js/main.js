"use strict";

(function () {
  /* ================================
   *         Global Functions
   * ================================ */
  window.openRecording = function (url) {
    window.open(url, "_blank");
  };

  window.downloadResults = function () {
    // Download functionality not implemented
  };

  window.deleteLPRTrigger = function (index) {
    if (window.lprManagerInstance) {
      window.lprManagerInstance.deleteTrigger(index);
    }
  };

  /* ================================
   *         Utility Functions
   * ================================ */
  function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <div style="display: flex; align-items: center; gap: 8px;">
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        <span>${message}</span>
      </div>
    `;

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'slideInToast 0.3s ease-out reverse';
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 3000);
  }

  function showStatus(message) {
    const overlay = document.getElementById('statusOverlay');
    const messageEl = document.getElementById('statusMessage');
    if (overlay && messageEl) {
      messageEl.textContent = message;
      overlay.style.display = 'flex';
    }
  }

  function hideStatus() {
    const overlay = document.getElementById('statusOverlay');
    if (overlay) {
      overlay.style.display = 'none';
    }
  }

  // Add to global scope
  window.showToast = showToast;
  window.showStatus = showStatus;
  window.hideStatus = hideStatus;

  /* ================================
   *        Initialization
   * ================================ */
  document.addEventListener("DOMContentLoaded", async () => {
    // Ensure UI utilities are available before initializing managers
    if (typeof window.toastManager === 'undefined') {
      console.log('Waiting for toast manager to initialize...');
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    // Initialize tabs & managers
    try {
      const tabs = new Tabs();
      window.lprManagerInstance = new LPRManager();
      window.aiManager = new AIManager(); // Store globally for access
      const headerScroll = new HeaderScroll();
    } catch (error) {
      console.error("Error initializing components:", error);
    }

    // Clear AI Data button functionality
    const clearBtn = document.getElementById('clearAIDataButton');
    if (clearBtn) {
      clearBtn.addEventListener('click', async function() {
        if (confirm('Are you sure you want to clear all AI search data? This will permanently remove all analyzed event descriptions and you will need to run analysis again.')) {
          // Disable button and show loading state
          const originalText = clearBtn.innerHTML;
          clearBtn.disabled = true;
          clearBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Clearing...';
          
          try {
            showStatus('Clearing AI data...');
            
            // Use AI Manager's clearAllAIData method if available, otherwise call API directly
            if (window.aiManager && typeof window.aiManager.clearAllAIData === 'function') {
              await window.aiManager.clearAllAIData();
            } else {
              // Fallback to direct API call
              const response = await fetch('/api/videoloft/clear_descriptions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
              });
              
              if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`Failed to clear AI data: ${errorText}`);
              }
              
              const result = await response.json();
              
              if (!result.success) {
                throw new Error(result.error || 'Unknown error occurred');
              }
              
              // Clear search results UI
              const results = document.getElementById('searchResults');
              if (results) {
                results.innerHTML = `
                  <div class="empty-state">
                    <div class="empty-state-icon">
                      <i class="fas fa-search"></i>
                    </div>
                    <div class="empty-state-title">Search Events</div>
                    <div class="empty-state-description">All AI data has been cleared. Run analysis again to search events.</div>
                  </div>
                `;
              }
              
              // Reset search form
              const searchQuery = document.getElementById('searchQuery');
              if (searchQuery) searchQuery.value = '';
              
              // Clear stored results in AI Manager if available
              if (window.aiManager) {
                window.aiManager.currentResults = [];
                window.aiManager.filteredResults = [];
                window.aiManager.currentPage = 0;
                window.aiManager.hideProcessingState('cleared');
              }
            }
            
            hideStatus();
            showToast('AI data cleared successfully. You will need to run analysis again to search events.', 'success');
            
          } catch (error) {
            console.error('Error clearing AI data:', error);
            hideStatus();
            showToast(error.message || 'Failed to clear AI data', 'error');
          } finally {
            // Restore button state
            clearBtn.disabled = false;
            clearBtn.innerHTML = originalText;
          }
        }
      });
    }

    // Fetch camera data with robust error handling
    const fetchCameraData = async (retryCount = 0) => {
      try {
        showStatus("Loading cameras...");
        const response = await fetch("/api/videoloft/cameras");
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: Failed to fetch cameras`);
        }
        const data = await response.json();
        
        // Preload thumbnails in background for faster display
        if (data.cameras && data.cameras.length > 0) {
          fetch("/api/videoloft/preload_thumbnails", { 
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
          }).catch(err => console.warn("Thumbnail preload failed:", err));
        }
        
        hideStatus();
        return data.cameras || [];
      } catch (error) {
        console.error("Error fetching camera data:", error);
        hideStatus();
        
        // Retry up to 3 times with increasing delay for temporary network issues
        if (retryCount < 3) {
          await new Promise(resolve => setTimeout(resolve, (retryCount + 1) * 1000));
          return fetchCameraData(retryCount + 1);
        }
        
        // Show user-friendly error after retries
        showToast("Unable to load cameras. Please check if the Videoloft integration is properly configured.", 'error');
        return [];
      }
    };

    const cameras = await fetchCameraData();

    // Display cameras or friendly error message
    const grid = document.querySelector(".camera-grid");
    if (grid) {
      if (cameras.length > 0) {
        try {
          new VideoloftPlayer(cameras);
          showToast(`Successfully loaded ${cameras.length} camera${cameras.length > 1 ? 's' : ''}`, 'success');
        } catch (error) {
          console.error("Error initializing video player:", error);
          grid.innerHTML = `
            <div class="error-message">
              <i class="fas fa-exclamation-triangle"></i>
              <h3>Video Player Error</h3>
              <p>Failed to initialize video player: ${error.message}</p>
            </div>`;
        }
      } else {
        grid.innerHTML = `
          <div class="error-message">
            <i class="fas fa-camera-slash"></i>
            <h3>No Cameras Found</h3>
            <p>No cameras are currently available. Please check your Videoloft account configuration.</p>
          </div>`;
      }
    }

    // Update camera selects in other forms
    if (cameras.length > 0) {
      const cameraSelects = document.querySelectorAll('#cameraSelect, #aiCameraSelect');
      cameraSelects.forEach(select => {
        if (select) {
          select.innerHTML = cameras.map(camera => 
            `<option value="${camera.uidd}">${camera.name}</option>`
          ).join('');
          
          // Add "All Cameras" option for AI select
          if (select.id === 'aiCameraSelect') {
            select.innerHTML = '<option value="">All Cameras</option>' + select.innerHTML;
          }
        }
      });
    }

  });
})();
