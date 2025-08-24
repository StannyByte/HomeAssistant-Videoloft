"use strict";

(function () {
  class StreamManager {
    constructor(options = {}) {
      // Disabled: This StreamManager is replaced by HeaderStreamControl
      // Return early to prevent rendering the old banner/card
      console.debug('StreamManager: Disabled in favor of HeaderStreamControl');
      return;
      
      this.endpoint = "/api/videoloft/global_stream_state";
      this.pollIntervalMs = options.pollIntervalMs || 5000;
      this.container = document.querySelector(".camera-controls");
      this.timer = null;
      this.state = null;

      if (!this.container) {
        console.warn("StreamManager: .camera-controls container not found.");
        return;
      }

      this._renderSkeleton();
      this._bindEvents();
      this.refresh();
      this._startPolling();
    }

    _renderSkeleton() {
      const card = document.createElement("div");
      card.className = "card";
      card.style.marginBottom = "12px";
      card.innerHTML = `
        <div class="stream-control">
          <div class="stream-control-row" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <h3 style="margin:0;display:flex;align-items:center;gap:8px;">
              <i class="fas fa-satellite-dish"></i>
              Global Streaming
            </h3>
            <button id="vlToggleGlobalStreaming" class="btn btn-secondary btn-sm" aria-pressed="true">
              <i class="fas fa-power-off"></i>
              <span class="label">Loading...</span>
            </button>
            <button id="vlRefreshGlobalState" class="btn btn-sm" title="Refresh">
              <i class="fas fa-rotate"></i>
            </button>
          </div>
          <div class="stream-stats" style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;">
            <span class="chip" title="Active Videoloft streams">
              <i class="fas fa-video"></i>
              <span id="vlActiveStreams">0</span> Active Streams
            </span>
            <span class="chip" title="Total Videoloft cameras">
              <i class="fas fa-camera"></i>
              <span id="vlTotalCameras">0</span> Cameras
            </span>
          </div>
          <div id="vlGlobalNotice" class="notice" style="display:none;margin-top:10px;">
            <i class="fas fa-pause-circle"></i>
            Streaming is globally disabled. Live view is paused to save bandwidth.
          </div>
        </div>
      `;
      this.container.appendChild(card);

      // Cache elements
      this.toggleBtn = card.querySelector("#vlToggleGlobalStreaming");
      this.refreshBtn = card.querySelector("#vlRefreshGlobalState");
      this.activeStreamsEl = card.querySelector("#vlActiveStreams");
      this.totalCamerasEl = card.querySelector("#vlTotalCameras");
      this.noticeEl = card.querySelector("#vlGlobalNotice");
    }

    _bindEvents() {
      if (this.toggleBtn) {
        this.toggleBtn.addEventListener("click", async () => {
          if (!this.state) return;
          await this._setEnabled(!this.state.enabled);
        });
      }
      if (this.refreshBtn) {
        this.refreshBtn.addEventListener("click", () => this.refresh());
      }
    }

    _startPolling() {
      if (this.timer) clearInterval(this.timer);
      this.timer = setInterval(() => this.refresh(), this.pollIntervalMs);
    }

    async refresh() {
      try {
        this._setLoading(true);
        const res = await fetch(this.endpoint, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        this.state = data;
        this._updateUI();
      } catch (err) {
        console.error("StreamManager: failed to refresh state", err);
        if (window.showToast) window.showToast("Failed to load global streaming state", "error");
      } finally {
        this._setLoading(false);
      }
    }

    async _setEnabled(enabled) {
      try {
        this._setLoading(true);
        const res = await fetch(this.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled })
        });
        if (!res.ok) {
          const text = await res.text();
          throw new Error(text || `HTTP ${res.status}`);
        }
        const data = await res.json();
        this.state = data;
        this._updateUI();
        if (window.showToast) window.showToast(`Global streaming ${enabled ? "enabled" : "disabled"}.`, "success");
      } catch (err) {
        console.error("StreamManager: failed to set enabled", err);
        if (window.showToast) window.showToast(err.message || "Failed to update global streaming", "error");
      } finally {
        this._setLoading(false);
      }
    }

    _setLoading(loading) {
      if (this.toggleBtn) this.toggleBtn.disabled = !!loading;
      if (this.refreshBtn) this.refreshBtn.disabled = !!loading;
      if (this.toggleBtn) {
        const label = this.toggleBtn.querySelector(".label");
        if (label) {
          label.textContent = loading ? "Working..." : (this.state && this.state.enabled ? "Disable" : "Enable");
        }
      }
    }

    _updateUI() {
      if (!this.state) return;
      const enabled = !!this.state.enabled;

      if (this.toggleBtn) {
        this.toggleBtn.setAttribute("aria-pressed", String(enabled));
        this.toggleBtn.classList.toggle("btn-primary", !enabled);
        this.toggleBtn.classList.toggle("btn-secondary", enabled);
        const label = this.toggleBtn.querySelector(".label");
        if (label) label.textContent = enabled ? "Disable" : "Enable";
      }

      if (this.activeStreamsEl) this.activeStreamsEl.textContent = String(this.state.active_streams ?? 0);
      if (this.totalCamerasEl) this.totalCamerasEl.textContent = String(this.state.total_cameras ?? 0);

      if (this.noticeEl) this.noticeEl.style.display = enabled ? "none" : "block";
    }
  }

  window.StreamManager = StreamManager;
})();
