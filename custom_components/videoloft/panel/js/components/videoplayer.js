"use strict";

class VideoloftPlayer {
  constructor(cameras) {
    this.cameras = cameras;
    this.players = new Map();
    this.streamTimeouts = new Map();
    this.streamAttempts = new Map();
    this.streamStartTimes = new Map();
    this.STREAM_TIMEOUT = 12000;
    this.MAX_LOAD_RETRIES = 6;
    this.RETRY_DELAY = 1000;
    this.BUFFER_HEALTH_CHECK_INTERVAL = 5000;
    
    // Mobile detection for enhanced thumbnail handling
    this.isMobile = this.detectMobile();
    
    this.init();
  }
  
  detectMobile() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
           (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) ||
           window.innerWidth <= 768;
  }
  init() {
    this.loadCameraOrder();
    this.renderCameras();
    this.setGridColumns();
    this.setupDragAndDrop();
    this.startStreams();
    // Add debounced resize handler to prevent constant recalculation
    let resizeTimeout;
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimeout);
      resizeTimeout = setTimeout(() => {
        this.setGridColumns();
      }, 150);
    });
  }
  renderCameras() {
    const grid = document.querySelector(".camera-grid");
    if (!grid) return;
    
    const cameraCount = this.cameras.length;
    
    grid.innerHTML = this.cameras
      .map((camera, index) => {
        // Special handling for 3 cameras: make the 3rd camera span 2 columns
        const isThirdInGroup = cameraCount === 3 && index === 2;
        const spanClass = isThirdInGroup ? 'camera-card-span-2' : '';
        
        return `
        <div class="camera-card ${spanClass}" id="card-${camera.uidd}" data-uidd="${camera.uidd}" title="Drag to reorder cameras">
          <div class="video-container">
            <img id="thumb-${camera.uidd}" 
                 class="thumbnail" 
                 src="/api/videoloft/thumbnail/${camera.uidd}?t=${Date.now()}" 
                 alt="Loading thumbnail..." 
                 style="display: block;" />
            <div class="loading-spinner" id="spinner-${camera.uidd}" style="display: none;"></div>
            <video id="video-${camera.uidd}" 
                   playsinline 
                   muted 
                   preload="none"
                   poster="/api/videoloft/thumbnail/${camera.uidd}?t=${Date.now()}"
                   style="display: none; position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover;"></video>
            
            <div class="camera-header">
              <div class="camera-header-content">
                <span class="camera-name"><i class="fas fa-video"></i> ${camera.name}</span>
                <span class="camera-info">${camera.model} - ${camera.resolution}</span>
                <button class="fullscreen-button" aria-label="Toggle fullscreen">
                  <i class="fas fa-expand"></i>
                </button>
              </div>
            </div>
            <div class="error-message" id="error-${camera.uidd}"></div>
          </div>
        </div>
      `;
      })
      .join("");
    
    this.setupFullscreenHandlers();
    this.setupThumbnailRefresh();
    this.setupOverlayToggle();
  }

  setupThumbnailRefresh() {
    // Set up thumbnail refresh for all cameras
    this.cameras.forEach((camera) => {
      const thumbnail = document.getElementById(`thumb-${camera.uidd}`);
      if (thumbnail) {
        // Refresh thumbnail every 2 minutes
        setInterval(() => {
          this.refreshThumbnail(camera.uidd);
        }, 120000);
        
        // Handle thumbnail loading errors
        thumbnail.onerror = () => {
          console.warn(`Failed to load thumbnail for ${camera.name}, retrying...`);
          setTimeout(() => this.refreshThumbnail(camera.uidd), 5000);
        };
      }
    });
  }

  refreshThumbnail(uidd) {
    const thumbnail = document.getElementById(`thumb-${uidd}`);
    if (thumbnail) {
      // Add timestamp to bypass cache and get fresh thumbnail
      const currentSrc = thumbnail.src;
      const baseSrc = currentSrc.split('?')[0];
      thumbnail.src = `${baseSrc}?t=${Date.now()}`;
    }
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
  }    // Ultra-optimized Professional VMS grid layout system for maximum screen utilization
  setGridColumns() {
    const grid = document.querySelector(".camera-grid");
    if (!grid) return;
    
    const cameraCount = this.cameras.length;
    const screenWidth = window.innerWidth;
    const screenHeight = window.innerHeight;
    
    // Precise viewport calculations for maximum space utilization
    const navHeight = 60; // Navigation bar height
    const headerPadding = 20; // Top and bottom margins
    const availableHeight = screenHeight - navHeight - headerPadding;
    const availableWidth = screenWidth - 20; // Side margins (10px each)
    
    // Dynamic gap calculation for optimal spacing
    const baseGap = this.calculateOptimalGap(cameraCount);
    
    // Apply special class for single camera view
    if (cameraCount === 1) {
      grid.classList.add('single-camera');
      grid.style.gridTemplateColumns = '1fr';
      grid.style.gridTemplateRows = '1fr';
      grid.style.width = '100%';
      grid.style.height = `${availableHeight}px`;
      grid.style.gap = '0';
      grid.style.margin = '10px auto';
      return;
    } else {
      grid.classList.remove('single-camera');
    }
    
    // Mobile optimization with smart stacking
    if (screenWidth <= 768) {
      this.setupMobileLayout(grid, cameraCount, availableHeight);
      return;
    }
    
    // Calculate optimal layout with advanced algorithms
    const layout = this.calculateOptimalLayoutForScreen(cameraCount, availableWidth, availableHeight);
    const { columns, rows } = layout;
    
    // Precise space calculations
    const aspectRatio = 16/9;
    const horizontalGaps = Math.max(0, columns - 1);
    const verticalGaps = Math.max(0, rows - 1);
    
    const totalGapWidth = horizontalGaps * baseGap;
    const totalGapHeight = verticalGaps * baseGap;
    
    const netAvailableWidth = availableWidth - totalGapWidth;
    const netAvailableHeight = availableHeight - totalGapHeight;
    
    // Calculate optimal dimensions while maintaining aspect ratio
    const maxCellWidth = netAvailableWidth / columns;
    const maxCellHeight = netAvailableHeight / rows;
    
    // Choose the limiting dimension to maximize screen usage
    const cellWidthFromHeight = maxCellHeight * aspectRatio;
    const cellHeightFromWidth = maxCellWidth / aspectRatio;
    
    let finalCellWidth, finalCellHeight;
    
    if (cellWidthFromHeight <= maxCellWidth) {
      // Height is the limiting factor
      finalCellWidth = cellWidthFromHeight;
      finalCellHeight = maxCellHeight;
    } else {
      // Width is the limiting factor
      finalCellWidth = maxCellWidth;
      finalCellHeight = cellHeightFromWidth;
    }
    
    // Calculate final grid dimensions
    const gridWidth = (finalCellWidth * columns) + totalGapWidth;
    const gridHeight = (finalCellHeight * rows) + totalGapHeight;
    
    // Apply optimized styles for maximum space utilization
    grid.style.display = 'grid';
    grid.style.gridTemplateColumns = `repeat(${columns}, ${finalCellWidth}px)`;
    grid.style.gridTemplateRows = `repeat(${rows}, ${finalCellHeight}px)`;
    grid.style.gap = `${baseGap}px`;
    grid.style.width = `${Math.min(gridWidth, availableWidth)}px`;
    grid.style.height = `${gridHeight}px`;
    grid.style.margin = '10px auto';
    grid.style.justifyContent = 'center';
    grid.style.alignContent = 'center';
  }

  // Calculate optimal gap size based on camera count for professional appearance
  calculateOptimalGap(cameraCount) {
    if (cameraCount <= 2) return 16; // Larger gaps for few cameras
    if (cameraCount <= 4) return 12; // Medium gaps for small grids
    if (cameraCount <= 9) return 8;  // Smaller gaps for medium grids
    if (cameraCount <= 16) return 6; // Minimal gaps for larger grids
    return 4; // Very tight spacing for maximum cameras
  }

  // Mobile layout optimization
  setupMobileLayout(grid, cameraCount, availableHeight) {
    // Force a full width, vertical list layout for mobile
    grid.style.display = 'flex';
    grid.style.flexDirection = 'column';
    grid.style.width = '100%';
    grid.style.height = 'auto';
    grid.style.margin = '0';
    grid.style.padding = '0';
    grid.style.gap = '8px';
    
    // Clear any grid template properties
    grid.style.gridTemplateColumns = 'unset';
    grid.style.gridTemplateRows = 'unset';
    
    // Ensure proper overflow
    grid.style.overflow = 'visible';
    grid.style.maxHeight = 'none';
  }    calculateOptimalLayoutForScreen(cameraCount, screenWidth, screenHeight) {
    // Advanced VMS layout algorithm for professional surveillance monitoring
    // Optimized for maximum screen utilization while maintaining readability
    
    if (cameraCount === 1) return { columns: 1, rows: 1 };
    if (cameraCount === 2) {
      // For 2 cameras, prefer side-by-side on wider screens, stacked on narrow screens
      return screenWidth > screenHeight * 1.5 ? { columns: 2, rows: 1 } : { columns: 1, rows: 2 };
    }
    if (cameraCount === 3) {
      // Smart 3-camera layout: 2 on top, 1 centered below
      return { columns: 2, rows: 2 };
    }
    if (cameraCount === 4) return { columns: 2, rows: 2 };
    if (cameraCount === 5) return { columns: 3, rows: 2 };
    if (cameraCount === 6) return { columns: 3, rows: 2 };
    if (cameraCount <= 8) return { columns: 4, rows: 2 };
    if (cameraCount === 9) return { columns: 3, rows: 3 };
    if (cameraCount <= 12) return { columns: 4, rows: 3 };
    if (cameraCount <= 16) return { columns: 4, rows: 4 };
    if (cameraCount <= 20) return { columns: 5, rows: 4 };
    if (cameraCount <= 25) return { columns: 5, rows: 5 };
    
    // For 25+ cameras: Advanced algorithm for optimal layout
    const aspectRatio = 16/9;
    const screenAspectRatio = screenWidth / screenHeight;
    
    // Calculate theoretical optimal columns based on screen dimensions
    let optimalColumns = Math.sqrt(cameraCount * screenAspectRatio / aspectRatio);
    
    // Test different column configurations to find the best fit
    const testConfigs = [
      Math.floor(optimalColumns),
      Math.ceil(optimalColumns),
      Math.floor(optimalColumns) + 1,
      Math.max(1, Math.floor(optimalColumns) - 1)
    ].filter(cols => cols >= 1 && cols <= Math.min(8, cameraCount)); // Limit to reasonable column counts
    
    let bestConfig = { columns: 5, rows: Math.ceil(cameraCount / 5) };
    let bestEfficiency = 0;
    
    for (const cols of testConfigs) {
      const rows = Math.ceil(cameraCount / cols);
      const cellWidth = screenWidth / cols;
      const cellHeight = screenHeight / rows;
      const cellAspectRatio = cellWidth / cellHeight;
      
      // Calculate how well this configuration uses the screen
      const aspectRatioMatch = 1 - Math.abs(cellAspectRatio - aspectRatio) / aspectRatio;
      const spaceUtilization = (cameraCount / (cols * rows));
      const efficiency = aspectRatioMatch * 0.7 + spaceUtilization * 0.3;
      
      if (efficiency > bestEfficiency) {
        bestEfficiency = efficiency;
        bestConfig = { columns: cols, rows };
      }
    }
    
    return bestConfig;
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
    
    // Always show thumbnail until video is playing (especially important on mobile)
    if (thumbnail) {
      thumbnail.style.display = "block";
      thumbnail.style.opacity = "1";
      thumbnail.style.filter = "none";
      thumbnail.style.zIndex = "10";
    }
    
    // Ensure video is hidden until it's actually playing
    if (videoElement) {
      videoElement.style.display = "none";
      videoElement.style.zIndex = "15";
      
      // On mobile, add extra insurance against early video visibility
      if (this.isMobile) {
        videoElement.style.visibility = "hidden";
      }
    }
    
    if (errorElement) errorElement.style.display = "none";

    this.clearStreamTimeout(camera.uidd);
    this.setStreamTimeout(camera, videoElement, spinner, thumbnail, errorElement);
    this.streamStartTimes.set(camera.uidd, Date.now());
    const streamUrl = `/api/videoloft/stream/${camera.uidd}/index.m3u8`;

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        debug: false,
        // Network retry configuration
        manifestLoadingMaxRetry: 6,
        manifestLoadingRetryDelay: 1000,
        levelLoadingMaxRetry: 6,
        levelLoadingRetryDelay: 1000,
        fragLoadingMaxRetry: 8,
        fragLoadingRetryDelay: 1000,
        
        // Buffer management for surveillance cameras (2024 best practices)
        maxBufferLength: 20,              // Reduced for faster seeking in surveillance
        maxMaxBufferLength: 40,           // Maximum buffer for live streams
        maxBufferSize: 30 * 1000 * 1000,  // 30MB buffer limit
        maxBufferHole: 0.3,               // Allow small gaps in buffer
        backBufferLength: 10,             // Keep 10s back buffer (memory optimization)
        
        // Low-latency optimization for live surveillance
        liveSyncDurationCount: 1,         // Start playback after 1 segment (faster startup)
        liveMaxLatencyDurationCount: 8,   // Max 8 segments behind live edge
        liveDurationInfinity: true,       // Handle infinite live streams
        highBufferWatchdogPeriod: 1,      // Aggressive buffer monitoring
        nudgeOffset: 0.1,                 // Fine-tune playback position
        nudgeMaxRetry: 3,                 // Retry nudging 3 times
        
        // Performance optimizations
        maxLoadingDelay: 4,               // Max delay before fragment loading
        maxStarvationDelay: 4,            // Max starvation recovery delay
        startLevel: -1,                   // Auto-select start quality
        capLevelToPlayerSize: true,       // Optimize quality for player size
        
        // Error recovery
        fragLoadingTimeOut: 10000,        // 10s fragment timeout
        manifestLoadingTimeOut: 5000,     // 5s manifest timeout
        levelLoadingTimeOut: 5000,        // 5s level timeout
      });
      hls.loadSource(streamUrl);
      hls.attachMedia(videoElement);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        this.clearStreamTimeout(camera.uidd);
        
        // Start buffer health monitoring
        this.startBufferHealthMonitoring(camera.uidd, hls, videoElement);
        
        if (spinner) spinner.style.display = "none";
        
        // Set up proper thumbnail to video transition for mobile
        if (videoElement) {
          // Keep thumbnail visible until video actually starts playing
          videoElement.addEventListener('loadstart', () => {
            // Video is starting to load, but keep thumbnail visible
            console.log(`Video loadstart for ${camera.name}`);
          }, { once: true });
          
          videoElement.addEventListener('canplay', () => {
            // Video can start playing, but still keep thumbnail visible
            console.log(`Video canplay for ${camera.name}`);
          }, { once: true });
          
          // For mobile, use a more reliable method to detect when video content is actually playing
          if (this.isMobile) {
            let transitionComplete = false;
            
            // Listen for timeupdate to ensure video is actually progressing
            const handleTimeUpdate = () => {
              if (transitionComplete) return;
              
              if (videoElement.currentTime > 0 && videoElement.readyState >= 3) {
                transitionComplete = true;
                if (thumbnail) {
                  thumbnail.style.display = "none";
                }
                videoElement.classList.add('mobile-ready');
                videoElement.style.display = "block";
                videoElement.style.visibility = "visible";
                videoElement.removeEventListener('timeupdate', handleTimeUpdate);
                console.log(`Mobile video transition complete for ${camera.name}`);
              }
            };
            
            videoElement.addEventListener('timeupdate', handleTimeUpdate);
            
            // Fallback using playing event with delay
            videoElement.addEventListener('playing', () => {
              if (transitionComplete) return;
              
              console.log(`Video playing for ${camera.name}`);
              // Wait a bit longer on mobile to ensure video has actual frames
              setTimeout(() => {
                if (!transitionComplete && videoElement.readyState >= 3 && videoElement.currentTime > 0) {
                  transitionComplete = true;
                  if (thumbnail) {
                    thumbnail.style.display = "none";
                  }
                  videoElement.classList.add('mobile-ready');
                  videoElement.style.display = "block";
                  videoElement.style.visibility = "visible";
                  videoElement.removeEventListener('timeupdate', handleTimeUpdate);
                } else if (!transitionComplete) {
                  // Video isn't ready yet, wait a bit more
                  setTimeout(() => {
                    if (!transitionComplete) {
                      transitionComplete = true;
                      if (thumbnail) {
                        thumbnail.style.display = "none";
                      }
                      videoElement.classList.add('mobile-ready');
                      videoElement.style.display = "block";
                      videoElement.style.visibility = "visible";
                      videoElement.removeEventListener('timeupdate', handleTimeUpdate);
                    }
                  }, 500);
                }
              }, 300);
            }, { once: true });
          } else {
            // Desktop behavior - use the standard playing event
            videoElement.addEventListener('playing', () => {
              console.log(`Video playing for ${camera.name}`);
              if (thumbnail) {
                thumbnail.style.display = "none";
              }
              videoElement.style.display = "block";
            }, { once: true });
          }
          
          // Start video playback but don't show it yet
          videoElement.play().catch((error) => {
            console.error(`Playback error for ${camera.name}:`, error);
            this.handlePlaybackError(camera, videoElement, spinner, thumbnail, errorElement);
          });
        }
      });
      
      // Monitor buffer levels and quality switches
      hls.on(Hls.Events.BUFFER_APPENDED, () => {
        if (videoElement && !videoElement.paused) {
          const buffered = videoElement.buffered;
          if (buffered.length > 0) {
            const bufferEnd = buffered.end(buffered.length - 1);
            const currentTime = videoElement.currentTime;
            const bufferHealth = bufferEnd - currentTime;
            
            // Log buffer health for monitoring
            if (bufferHealth < 3) {
              console.warn(`Low buffer health for ${camera.name}: ${bufferHealth.toFixed(2)}s`);
            }
          }
        }
      });
      
      // Track quality switches for optimization
      hls.on(Hls.Events.LEVEL_SWITCHED, (event, data) => {
        // Quality switched to level ${data.level}
      });
      hls.on(Hls.Events.ERROR, (event, data) => {
        const { type, fatal, details } = data;
        console.error(`HLS error for ${camera.name}:`, { type, fatal, details, code: data.response?.code });
        
        if (fatal) {
          this.handleFatalError(hls, camera, videoElement, spinner, thumbnail, errorElement, type, retryCount);
        } else {
          // Handle non-fatal errors
          this.handleNonFatalError(hls, camera, data);
        }
      });
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
      
      // Set up proper thumbnail to video transition for mobile (native HLS)
      if (this.isMobile) {
        let transitionComplete = false;
        
        // Listen for timeupdate to ensure video is actually progressing
        const handleTimeUpdate = () => {
          if (transitionComplete) return;
          
          if (videoElement.currentTime > 0 && videoElement.readyState >= 3) {
            transitionComplete = true;
            if (thumbnail) {
              thumbnail.style.display = "none";
            }
            videoElement.classList.add('mobile-ready');
            videoElement.style.display = "block";
            videoElement.style.visibility = "visible";
            videoElement.removeEventListener('timeupdate', handleTimeUpdate);
            console.log(`Mobile native video transition complete for ${camera.name}`);
          }
        };
        
        videoElement.addEventListener('timeupdate', handleTimeUpdate);
        
        // Fallback using playing event with delay
        videoElement.addEventListener('playing', () => {
          if (transitionComplete) return;
          
          console.log(`Native video playing for ${camera.name}`);
          // Wait a bit longer on mobile to ensure video has actual frames
          setTimeout(() => {
            if (!transitionComplete && videoElement.readyState >= 3 && videoElement.currentTime > 0) {
              transitionComplete = true;
              if (thumbnail) {
                thumbnail.style.display = "none";
              }
              videoElement.classList.add('mobile-ready');
              videoElement.style.display = "block";
              videoElement.style.visibility = "visible";
              videoElement.removeEventListener('timeupdate', handleTimeUpdate);
            } else if (!transitionComplete) {
              // Video isn't ready yet, wait a bit more
              setTimeout(() => {
                if (!transitionComplete) {
                  transitionComplete = true;
                  if (thumbnail) {
                    thumbnail.style.display = "none";
                  }
                  videoElement.classList.add('mobile-ready');
                  videoElement.style.display = "block";
                  videoElement.style.visibility = "visible";
                  videoElement.removeEventListener('timeupdate', handleTimeUpdate);
                }
              }, 500);
            }
          }, 300);
        }, { once: true });
      } else {
        // Desktop behavior - use the standard playing event
        videoElement.addEventListener('playing', () => {
          console.log(`Native video playing for ${camera.name}`);
          if (thumbnail) {
            thumbnail.style.display = "none";
          }
          videoElement.style.display = "block";
        }, { once: true });
      }
      
      // Start video playback but don't show it yet
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
    this.clearStreamTimeout(uidd);
    this.stopBufferHealthMonitoring(uidd);
    const player = this.players.get(uidd);
    if (player) {
      if (player instanceof Hls) {
        try {
          player.destroy();
        } catch (e) {
          console.warn(`Error destroying HLS player for ${uidd}:`, e);
        }
      } else if (player.type === "native") {
        const element = player.element;
        try {
          element.pause();
          element.src = "";
          element.load();
        } catch (e) {
          console.warn(`Error cleaning up native player for ${uidd}:`, e);
        }
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
    const onlineEl = document.getElementById("onlineCameras"); // Assuming $ is not available if this becomes a module
    if (onlineEl) onlineEl.textContent = `${this.cameras.length} Cameras Online`;
  }

  handleNonFatalError(hls, camera, data) {
    const { details, response } = data;
    
    switch (details) {
      case Hls.ErrorDetails.FRAG_LOAD_TIMEOUT:
      case Hls.ErrorDetails.LEVEL_LOAD_TIMEOUT:
        console.warn(`Load timeout for ${camera.name}, will retry automatically`);
        break;
      case Hls.ErrorDetails.BUFFER_STALLED_ERROR:
        console.warn(`Buffer stalled for ${camera.name}, attempting recovery`);
        try {
          hls.trigger(Hls.Events.ERROR, {
            type: Hls.ErrorTypes.MEDIA_ERROR,
            details: Hls.ErrorDetails.BUFFER_SEEK_OVER_HOLE,
            fatal: false
          });
        } catch (e) {
          console.error(`Buffer recovery failed for ${camera.name}:`, e);
        }
        break;
      case Hls.ErrorDetails.FRAG_PARSING_ERROR:
        console.warn(`Fragment parsing error for ${camera.name}, may auto-recover`);
        break;
      default:
        // Non-fatal error handled internally
        break;
    }
  }

  startBufferHealthMonitoring(uidd, hls, videoElement) {
    // Clear any existing monitoring
    this.stopBufferHealthMonitoring(uidd);
    
    const monitoringInterval = setInterval(() => {
      if (!videoElement || videoElement.paused || hls.destroyed) {
        clearInterval(monitoringInterval);
        return;
      }
      
      try {
        const buffered = videoElement.buffered;
        const currentTime = videoElement.currentTime;
        const levels = hls.levels;
        
        if (buffered.length > 0 && levels.length > 0) {
          const bufferEnd = buffered.end(buffered.length - 1);
          const bufferHealth = bufferEnd - currentTime;
          const currentLevel = hls.currentLevel;
          
          // Adaptive quality adjustment based on buffer health
          if (bufferHealth < 2 && currentLevel > 0) {
            // Low buffer, consider dropping quality
            const newLevel = Math.max(0, currentLevel - 1);
            hls.nextLevel = newLevel;
          } else if (bufferHealth > 10 && currentLevel < levels.length - 1) {
            // High buffer, can increase quality
            const newLevel = Math.min(levels.length - 1, currentLevel + 1);
            hls.nextLevel = newLevel;
          }
        }
      } catch (e) {
        console.error(`Buffer monitoring error for ${uidd}:`, e);
      }
    }, this.BUFFER_HEALTH_CHECK_INTERVAL);
    
    // Store monitoring interval for cleanup
    this.streamTimeouts.set(`${uidd}_monitor`, monitoringInterval);
  }

  stopBufferHealthMonitoring(uidd) {
    const monitoringInterval = this.streamTimeouts.get(`${uidd}_monitor`);
    if (monitoringInterval) {
      clearInterval(monitoringInterval);
      this.streamTimeouts.delete(`${uidd}_monitor`);
    }
  }

  loadCameraOrder() {
    // Load saved camera order from localStorage
    const savedOrder = localStorage.getItem('videoloft_camera_order');
    if (savedOrder) {
      try {
        const orderArray = JSON.parse(savedOrder);
        // Reorder cameras array based on saved order
        const reorderedCameras = [];
        orderArray.forEach(uidd => {
          const camera = this.cameras.find(cam => cam.uidd === uidd);
          if (camera) {
            reorderedCameras.push(camera);
          }
        });
        // Add any new cameras that weren't in the saved order
        this.cameras.forEach(camera => {
          if (!orderArray.includes(camera.uidd)) {
            reorderedCameras.push(camera);
          }
        });
        this.cameras = reorderedCameras;
      } catch (e) {
        console.warn('Failed to load camera order:', e);
      }
    }
  }

  saveCameraOrder() {
    // Save current camera order to localStorage
    const order = this.cameras.map(camera => camera.uidd);
    localStorage.setItem('videoloft_camera_order', JSON.stringify(order));
  }

  setupDragAndDrop() {
    const grid = document.querySelector(".camera-grid");
    if (!grid || !window.Sortable) return;

    // Disable drag-and-drop on mobile devices
    if (window.innerWidth <= 768) {
      grid.classList.remove('sortable-enabled');
      return;
    }

    // Add sortable class for styling
    grid.classList.add('sortable-enabled');

    this.sortable = Sortable.create(grid, {
      animation: 200,
      ghostClass: 'sortable-ghost',
      chosenClass: 'sortable-chosen',
      dragClass: 'sortable-drag',
      forceFallback: true,
      fallbackClass: 'sortable-fallback',
      fallbackOnBody: true,
      swapThreshold: 0.8,
      onStart: (evt) => {
        // Pause all videos during drag
        this.pauseAllStreams();
        document.body.style.cursor = 'grabbing';
      },
      onEnd: (evt) => {
        document.body.style.cursor = '';
        
        // Update cameras array order
        const newOrder = Array.from(grid.children).map(card => {
          const uidd = card.id.replace('card-', '');
          return this.cameras.find(camera => camera.uidd === uidd);
        }).filter(Boolean);

        if (newOrder.length === this.cameras.length) {
          this.cameras = newOrder;
          this.saveCameraOrder();
          
          // Show success toast
          this.showToast('Camera layout saved successfully!');
          
          // Restart streams after reordering
          setTimeout(() => {
            this.startStreams();
          }, 500);
        }
      }
    });
  }

  pauseAllStreams() {
    // Pause all video streams
    this.players.forEach((player, uidd) => {
      const video = document.getElementById(`video-${uidd}`);
      if (video && !video.paused) {
        video.pause();
      }
    });
  }

  showToast(message, type = 'success') {
    // Remove existing toast if any
    const existingToast = document.querySelector('.toast-notification');
    if (existingToast) {
      existingToast.remove();
    }

    // Create new toast
    const toast = document.createElement('div');
    toast.className = `toast-notification ${type}`;
    toast.innerHTML = `
      <i class="fas fa-check-circle"></i>
      <span>${message}</span>
    `;

    document.body.appendChild(toast);

    // Show toast
    setTimeout(() => {
      toast.classList.add('show');
    }, 100);

    // Hide and remove toast after 3 seconds
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 3000);
  }

  setupOverlayToggle() {
    // Only enable tap-to-toggle on mobile
    if (window.innerWidth > 768) return;
    const cards = document.querySelectorAll('.camera-card');
    cards.forEach(card => {
      const header = card.querySelector('.camera-header');
      if (!header) return;
      let overlayVisible = false;
      card.addEventListener('click', (e) => {
        // Prevent toggling if fullscreen button is clicked
        if (e.target.closest('.fullscreen-button')) return;
        overlayVisible = !header.classList.contains('show-overlay');
        document.querySelectorAll('.camera-header.show-overlay').forEach(h => h.classList.remove('show-overlay'));
        if (overlayVisible) {
          header.classList.add('show-overlay');
        } else {
          header.classList.remove('show-overlay');
        }
        e.stopPropagation();
      });
      // Hide overlay if clicking outside any card
      document.body.addEventListener('click', (e) => {
        if (!card.contains(e.target)) {
          header.classList.remove('show-overlay');
        }
      });
    });
  }


}
