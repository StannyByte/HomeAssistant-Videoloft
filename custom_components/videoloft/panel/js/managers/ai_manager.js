/**
 * AI Manager - Handles AI Search functionality
 * Manages API key configuration, search operations, and results display
 */

class AIManager {
  constructor() {
    this.apiKey = null;
    this.hasServerKey = false;
    this.searchInProgress = false;
    this.cancelController = null;
    this.currentResults = [];
    this.filteredResults = [];
    this.currentPage = 0;
    this.resultsPerPage = 9; // show 3x3 per page for a tidy grid
    this.currentSortBy = 'relevance';
    this.currentFilters = {
      camera: 'all',
      timeOfDay: 'all',
      searchText: '' // quick keyword filter on description
    };
    
    this.init();
  }

  init() {
    console.log('AIManager: Initializing...');
    
    // Check server-stored API key
    this.checkServerKey();
    
    // Bind event listeners
    this.bindEvents();
    
    // Set default date range (last 24 hours)
    this.setDefaultDateRange();
    // Restore previous UI state
    this.loadUIState();
    
    console.log('AIManager: Initialization complete');
  }

  bindEvents() {
    // API Key management
    const saveApiKeyBtn = document.getElementById('saveApiKeyButton');
    const removeApiKeyBtn = document.getElementById('removeApiKeyButton');
    const apiKeyInput = document.getElementById('geminiApiKey');
    
    if (saveApiKeyBtn) {
      saveApiKeyBtn.addEventListener('click', () => this.saveApiKey());
    }
    
    if (removeApiKeyBtn) {
      removeApiKeyBtn.addEventListener('click', () => this.removeApiKey());
    }
    
    if (apiKeyInput) {
      apiKeyInput.addEventListener('input', () => this.updateApiKeyButtons());
    }
    
    // Date input event listeners
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    const cameraSelect = document.getElementById('aiCameraSelect');
    const searchInput = document.getElementById('searchQuery');
    
    if (startDateInput) {
      startDateInput.addEventListener('change', () => { this.handleStartDateChange(); this.saveUIState(); });
    }
    
    if (endDateInput) {
      // Allow user to change end date
      endDateInput.addEventListener('change', () => { this.handleEndDateChange(); this.saveUIState(); });
    }
    if (cameraSelect) {
      cameraSelect.addEventListener('change', () => this.saveUIState());
    }
    if (searchInput) {
      searchInput.addEventListener('input', () => this.saveUIState());
    }
    
    // Search form
    const searchForm = document.getElementById('aiSearchForm');
    if (searchForm) {
      searchForm.addEventListener('submit', (e) => this.handleSearchSubmit(e));
    }
    // Reuse the earlier searchInput reference to avoid redeclaration errors
    const searchButton = searchForm ? searchForm.querySelector('button[type="submit"]') : null;
    if (searchInput && searchButton) {
      const updateSearchButton = () => {
        const hasQuery = !!searchInput.value.trim();
        searchButton.disabled = !hasQuery;
      };
      searchInput.addEventListener('input', updateSearchButton);
      updateSearchButton();
    }
    
    // Run Analysis button
    const runAnalysisBtn = document.getElementById('runAnalysisButton');
    if (runAnalysisBtn) {
      runAnalysisBtn.addEventListener('click', () => this.handleRunAnalysis());
    }
    
    // Clear AI Data button
    const clearDataBtn = document.getElementById('clearAIDataButton');
    if (clearDataBtn) {
      clearDataBtn.addEventListener('click', () => this.handleClearData());
    }
    
    // Cancel processing
    const cancelBtn = document.getElementById('cancelProcessing');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => this.cancelSearch());
    }

    // Keyboard navigation for search results and quick focus (Ctrl/Cmd+K)
    document.addEventListener('keydown', (e) => this.handleKeyboardNavigation(e));
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const qi = document.getElementById('searchQuery');
        if (qi) qi.focus();
      }
      if (e.key === 'Escape') {
        // Clear quick filter if active, close sort dropdowns
        let changed = false;
        if (this.currentFilters.searchText) {
          this.currentFilters.searchText = '';
          changed = true;
        }
        document.querySelectorAll('.sort-options').forEach(d => d.style.display = 'none');
        if (changed) {
          this.applyFiltersAndSort();
          this.saveUIState();
          this.announce('Cleared filters');
        }
      }
    });
  }

  async checkServerKey() {
    try {
      const resp = await fetch('/api/videoloft/gemini_key');
      const data = await resp.json();
      this.hasServerKey = !!data.has_key;
      this.updateApiKeyButtons();
    } catch (error) {
      console.warn('Failed to check server key:', error);
    }
  }

  async saveApiKey() {
    const input = document.getElementById('geminiApiKey');
    if (!input || !input.value.trim()) {
      if (window.showError) {
        window.showError('Please enter an API key');
      }
      return;
    }

    const apiKey = input.value.trim();
    try {
      const resp = await fetch('/api/videoloft/gemini_key', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey })
      });
      if (!resp.ok) throw new Error('Failed to store key');
      this.hasServerKey = true;
      this.apiKey = null;
      input.value = '';
      input.type = 'password';
      this.updateApiKeyButtons();
      window.showSuccess('API key stored on server');
      this.announce('API key stored on server');
    } catch (error) {
      console.error('Failed to save key:', error);
      window.showError('Failed to save API key');
    }
  }

  removeApiKey() {
    fetch('/api/videoloft/gemini_key', { method: 'DELETE' })
      .then((resp) => {
        if (!resp.ok) throw new Error('Failed to remove key');
        this.hasServerKey = false;
        const input = document.getElementById('geminiApiKey');
        if (input) input.value = '';
        this.updateApiKeyButtons();
        window.showSuccess('Server API key removed');
        this.announce('Server API key removed');
      })
      .catch((error) => {
        console.error('Failed to remove key:', error);
        window.showError('Failed to remove API key');
      });
  }

  updateApiKeyButtons() {
    const saveBtn = document.getElementById('saveApiKeyButton');
    const removeBtn = document.getElementById('removeApiKeyButton');
    const input = document.getElementById('geminiApiKey');
    const status = document.getElementById('serverKeyStatus');
    
    if (this.hasServerKey) {
      if (status) status.textContent = 'Key stored on server';
      if (saveBtn) saveBtn.style.display = 'none';
      if (removeBtn) removeBtn.style.display = 'inline-flex';
      if (input) input.placeholder = 'Key stored on server';
    } else if (input && input.value.trim()) {
      if (status) status.textContent = '';
      if (saveBtn) saveBtn.style.display = 'inline-flex';
      if (removeBtn) removeBtn.style.display = 'none';
    } else {
      if (status) status.textContent = '';
      if (saveBtn) saveBtn.style.display = 'inline-flex';
      if (removeBtn) removeBtn.style.display = 'none';
    }
  }

  setDefaultDateRange() {
    const now = new Date();
    // Set start date to 7 days ago to give a reasonable analysis window
    const weekAgo = new Date(now - 7 * 24 * 60 * 60 * 1000);
    
    const startInput = document.getElementById('startDate');
    const endInput = document.getElementById('endDate');
    
    if (startInput) {
      startInput.value = this.formatDateOnly(weekAgo);
      startInput.max = this.formatDateOnly(now);
      startInput.addEventListener('change', () => this.saveUIState());
    }
    
    if (endInput) {
      // Set default end date to today, but allow user to change it
      endInput.value = this.formatDateOnly(now);
      endInput.max = this.formatDateOnly(now);
      endInput.addEventListener('change', () => this.saveUIState());
    }
  }

  formatDateOnly(date) {
    // Format date as YYYY-MM-DD for date input
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  handleStartDateChange() {
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    const today = new Date();
    
    if (!startDateInput || !endDateInput) return;
    
    const selectedStartDate = new Date(startDateInput.value);
    const selectedEndDate = new Date(endDateInput.value);
    
    // Validate start date is not in the future
    if (selectedStartDate > today) {
      window.showWarning('Start date cannot be in the future');
      startDateInput.value = this.formatDateOnly(new Date(today - 7 * 24 * 60 * 60 * 1000)); // Reset to 7 days ago
      return;
    }
    
    // Validate date range - start date should be before end date
    if (selectedStartDate >= selectedEndDate) {
      window.showWarning('Start date must be before end date');
      startDateInput.value = this.formatDateOnly(new Date(selectedEndDate - 24 * 60 * 60 * 1000)); // Set to day before end date
    }
  }

  handleEndDateChange() {
    const startDateInput = document.getElementById('startDate');
    const endDateInput = document.getElementById('endDate');
    const today = new Date();
    
    if (!startDateInput || !endDateInput) return;
    
    const selectedStartDate = new Date(startDateInput.value);
    const selectedEndDate = new Date(endDateInput.value);
    
    // Validate end date is not in the future
    if (selectedEndDate > today) {
      window.showWarning('End date cannot be in the future');
      endDateInput.value = this.formatDateOnly(today);
      return;
    }
    
    // Validate date range - end date should be after start date
    if (selectedEndDate <= selectedStartDate) {
      window.showWarning('End date must be after start date');
      endDateInput.value = this.formatDateOnly(new Date(selectedStartDate.getTime() + 24 * 60 * 60 * 1000)); // Set to day after start date
    }
  }

  // handlePresetClick method removed - no longer needed since we removed date selectors

  async handleRunAnalysis() {
    console.log('AIManager: handleRunAnalysis called');
    
    if (this.searchInProgress) {
      window.showWarning('Analysis already in progress');
      return;
    }
    // Allow either a server-stored key or a locally-entered key
    await this.checkServerKey();
    if (!this.hasServerKey && !this.apiKey) {
      console.error('AIManager: No API key configured');
      window.showError('Please configure your Gemini API key first');
      return;
    }
    
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    const cameraSelect = document.getElementById('aiCameraSelect').value;
    
    console.log('AIManager: Analysis parameters:', { startDate, endDate, camera: cameraSelect });
    
    if (!startDate || !endDate) {
      console.error('AIManager: Missing date parameters');
      window.showError('Please select both start and end dates');
      return;
    }
    
    // Validate date range (start date should be before end date)
    const startDateObj = new Date(startDate);
    const endDateObj = new Date(endDate);
    const today = new Date();
    
    if (startDateObj >= endDateObj) {
      console.error('AIManager: Invalid date range');
      window.showError('Start date must be before end date');
      return;
    }
    
    if (startDateObj > today) {
      console.error('AIManager: Start date in future');
      window.showError('Start date cannot be in the future');
      return;
    }
    
    await this.performAnalysis({
      startDate,
      endDate,
      camera: cameraSelect
    });
  }

  async handleClearData() {
    console.log('AIManager: handleClearData called');
    
    if (this.searchInProgress) {
      window.showWarning('Cannot clear data while processing');
      return;
    }
    
    if (!confirm('Are you sure you want to clear all AI analysis data? This action cannot be undone.')) {
      return;
    }
    
    try {
      await this.clearAllAIData();
      window.showSuccess('AI analysis data cleared successfully');
    } catch (error) {
      console.error('Failed to clear AI data:', error);
      window.showError('Failed to clear AI data: ' + error.message);
    }
  }

  async handleSearchSubmit(event) {
    event.preventDefault();
    console.log('AIManager: handleSearchSubmit called');
    
    if (this.searchInProgress) {
      window.showWarning('Search already in progress');
      return;
    }
    
    await this.checkServerKey();
    if (!this.hasServerKey) {
      window.showError('Please configure your Gemini API key first');
      return;
    }
    
    const searchQuery = document.getElementById('searchQuery').value.trim();
    console.log('AIManager: Search query:', searchQuery);
    
    if (!searchQuery) {
      console.error('AIManager: Empty search query');
      window.showError('Please enter a search query');
      return;
    }
    
    await this.performSearch({ query: searchQuery });
  }

  async performAnalysis(params) {
    this.searchInProgress = true;
    this.cancelController = new AbortController();
    
    // Update UI with enhanced feedback
    this.showProcessingState('Starting analysis...');
    this.clearResults();
    
    try {
      console.log('Sending analysis request:', { url: '/api/videoloft/ai_analysis', params });

      const response = await fetch('/api/videoloft/ai_analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: this.cancelController.signal
      });
      
      console.log('Analysis response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Analysis response error:', errorText);
        
        let errorMessage = `HTTP ${response.status}`;
        try {
          const errorData = JSON.parse(errorText);
          errorMessage = errorData.error || errorMessage;
        } catch (e) {
          errorMessage = errorText || errorMessage;
        }
        
        throw new Error(`Analysis failed: ${errorMessage}`);
      }
      
      const result = await response.json();
      console.log('Analysis result:', result);
      this.announce('Analysis started');
      window.showSuccess('Analysis started — you can track progress above');
      
    } catch (error) {
      if (error.name === 'AbortError') {
        window.showInfo('Analysis cancelled by user');
      } else {
        console.error('Analysis error details:', {
          name: error.name,
          message: error.message,
          stack: error.stack
        });
        
        // More descriptive error messages
        let userMessage = error.message;
        if (error.message.includes('404')) {
          userMessage = 'Analysis endpoint not found. Please check your integration configuration.';
        } else if (error.message.includes('500')) {
          userMessage = 'Server error during analysis. Check Home Assistant logs for details.';
        } else if (error.message.includes('Failed to fetch')) {
          userMessage = 'Network error. Check your connection and try again.';
        }
        
        window.showError(userMessage);
      }
    } finally {
      this.searchInProgress = false;
      this.cancelController = null;
      this.hideProcessingState();
    }
  }

  async performSearch(params) {
    if (!this.validateSearchState()) return;
    
    this.searchInProgress = true;
    this.cancelController = new AbortController();
    
    // Update UI with search feedback and loading state
    this.showProcessingState('Searching events...');
    this.showLoadingState();
    
    try {
      console.log('Sending search request:', { url: '/api/videoloft/ai_search', params });

      const response = await fetch('/api/videoloft/ai_search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
        signal: this.cancelController.signal
      });
      
      console.log('Search response status:', response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error('Search response error:', errorText);
        
        let errorMessage = `HTTP ${response.status}`;
        try {
          const errorData = JSON.parse(errorText);
          errorMessage = errorData.error || errorMessage;
        } catch (e) {
          errorMessage = errorText || errorMessage;
        }
        
        throw new Error(`Search failed: ${errorMessage}`);
      }
      
      const result = await response.json();
      console.log('Search result:', result);
      this.announce(`${(result.total_count || (result.events ? result.events.length : 0))} results found`);
      
      // Check if no analysis has been run yet
      if (!result.success && result.error === 'no_analysis') {
        this.showNoAnalysisMessage(result.message);
        return;
      }
      
      this.displayResults(result, params.query);
      
    } catch (error) {
      if (error.name === 'AbortError') {
        window.showInfo('Search cancelled by user');
        this.clearResults();
      } else {
        console.error('Search error details:', {
          name: error.name,
          message: error.message,
          stack: error.stack
        });
        
        // More descriptive error messages
        let userMessage = error.message;
        if (error.message.includes('404')) {
          userMessage = 'Search endpoint not found. Please check your integration configuration.';
        } else if (error.message.includes('500')) {
          userMessage = 'Server error during search. Check Home Assistant logs for details.';
        } else if (error.message.includes('Failed to fetch')) {
          userMessage = 'Network error. Check your connection and try again.';
        }
        
        window.showError(userMessage);
        this.showSearchError(userMessage);
      }
    } finally {
      this.searchInProgress = false;
      this.cancelController = null;
      this.hideProcessingState();
    }
  }

  validateSearchState() {
    // Add any validation logic for search state
    return true;
  }

  cancelSearch() {
    if (this.cancelController) {
      this.cancelController.abort();
    }
  }

  showProcessingState(message = 'Processing...') {
    const statusElement = document.getElementById('aiProcessingStatus');
    const progressContainer = document.getElementById('processingProgress');
    const cancelBtn = document.getElementById('cancelProcessing');
    
    if (statusElement) {
      const statusText = statusElement.querySelector('.status-text');
      if (statusText) {
        statusText.textContent = message;
        statusText.style.color = 'var(--turquoise)';
        statusText.style.fontWeight = '500';
      }
    }
    
    if (progressContainer) {
      progressContainer.style.display = 'block';
    }
    
    if (cancelBtn) {
      cancelBtn.style.display = 'inline-flex';
    }
    
    // Reset progress
    this.updateProgress(0, 0, 0, 0);

    // Disable interactive controls during processing
    ['saveApiKeyButton','removeApiKeyButton','runAnalysisButton','clearAIDataButton','searchQuery','startDate','endDate','aiCameraSelect']
      .forEach(id => { const el = document.getElementById(id); if (el) el.disabled = true; });
    const searchForm = document.getElementById('aiSearchForm');
    const searchBtn = searchForm ? searchForm.querySelector('button[type="submit"]') : null;
    if (searchBtn) searchBtn.disabled = true;
    this.announce(message);
  }

  hideProcessingState(status = 'ready') {
    const statusElement = document.getElementById('aiProcessingStatus');
    const progressContainer = document.getElementById('processingProgress');
    const cancelBtn = document.getElementById('cancelProcessing');
    
    if (statusElement) {
      const statusText = statusElement.querySelector('.status-text');
      if (statusText) {
        if (status === 'cleared') {
          statusText.textContent = 'Analysis cleared';
          statusText.style.color = 'var(--text-muted)';
        } else {
          statusText.textContent = 'Ready to process';
          statusText.style.color = 'var(--text-secondary)';
        }
        statusText.style.fontWeight = 'normal';
      }
    }
    
    if (progressContainer) {
      progressContainer.style.display = 'none';
    }
    
    if (cancelBtn) {
      cancelBtn.style.display = 'none';
    }

    // Re-enable controls
    ['saveApiKeyButton','removeApiKeyButton','runAnalysisButton','clearAIDataButton','searchQuery','startDate','endDate','aiCameraSelect']
      .forEach(id => { const el = document.getElementById(id); if (el) el.disabled = false; });
    const searchForm = document.getElementById('aiSearchForm');
    const searchBtn = searchForm ? searchForm.querySelector('button[type="submit"]') : null;
    if (searchBtn) searchBtn.disabled = false;
    this.announce('Ready');
  }

  updateProgress(processed, total, tokens, percent) {
    const processedEl = document.getElementById('processedEvents');
    const totalEl = document.getElementById('totalEvents');
    const tokensEl = document.getElementById('usedTokens');
    const percentEl = document.getElementById('progressPercent');
    const fillEl = document.getElementById('progressFill');
    
    if (processedEl) processedEl.textContent = processed;
    if (totalEl) totalEl.textContent = total;
    if (tokensEl) tokensEl.textContent = tokens.toLocaleString();
    if (percentEl) percentEl.textContent = `${percent}%`;
    if (fillEl) fillEl.style.width = `${percent}%`;
  }

  clearResults(message = null) {
    const resultsContainer = document.getElementById('searchResults');
    if (resultsContainer) {
      const displayMessage = message || "Enter your search criteria and click \"Search\" to find matching events";
      resultsContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">
            <i class="fas fa-search"></i>
          </div>
          <div class="empty-state-title">Search Events</div>
          <div class="empty-state-description">${displayMessage}</div>
        </div>
      `;
    }
    
    // Clear internal state
    this.currentResults = [];
    this.filteredResults = [];
    this.currentPage = 0;
    
    // Update status box to reflect cleared state
    this.hideProcessingState('cleared');
  }

  async clearAllAIData() {
    /**
     * Clear all AI analysis data from both frontend and backend
     */
    try {
      // Call backend API to clear stored descriptions
      const response = await fetch('/api/videoloft/clear_descriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Backend clear failed: ${errorText}`);
      }
      
      const result = await response.json();
      
      if (!result.success) {
        throw new Error(result.error || 'Backend clear failed');
      }
      
      // Clear frontend state
      this.clearResults("All AI data has been cleared. Run analysis again to search events.");
      
      // Reset search form
      const searchQuery = document.getElementById('searchQuery');
      if (searchQuery) searchQuery.value = '';
      
      return { success: true };
      
    } catch (error) {
      console.error('Error clearing AI data:', error);
      throw error;
    }
  }

  showSearchError(errorMessage) {
    const resultsContainer = document.getElementById('searchResults');
    if (resultsContainer) {
      resultsContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">
            <i class="fas fa-exclamation-triangle"></i>
          </div>
          <div class="empty-state-title">Search Failed</div>
          <div class="empty-state-description">${errorMessage}</div>
        </div>
      `;
    }
  }

  showNoAnalysisMessage(message) {
    const resultsContainer = document.getElementById('searchResults');
    if (!resultsContainer) return;
    
    resultsContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">
          <i class="fas fa-brain fa-3x"></i>
        </div>
        <div class="empty-state-title">AI Analysis Required</div>
        <div class="empty-state-description">
          ${message}
        </div>
        <div class="empty-state-actions" style="margin-top: 20px;">
          <button type="button" id="runAnalysisFromSearch" class="btn btn-primary" onclick="document.getElementById('runAnalysisButton')?.click(); this.closest('.empty-state')?.remove();">
            <i class="fas fa-play"></i> Run Analysis Now
          </button>
        </div>
      </div>
    `;
    
    // Also show a warning toast
    window.showWarning('Please run AI analysis first to process your footage');
  }

  displayResults(results, searchQuery = '') {
   const resultsContainer = document.getElementById('searchResults');
   if (!resultsContainer) return;
   
   if (!results || !results.events || results.events.length === 0) {
     this.showEmptyState(resultsContainer, searchQuery);
     return;
   }

   // Store results for filtering and sorting
   this.currentResults = results.events;
   this.filteredResults = [...results.events];
   this.currentPage = 0;
   
   // Process and display results
   this.applyFiltersAndSort();
   
   // Show success toast with count
   const count = results.events.length;
   window.showSuccess(`Found ${count} matching event${count !== 1 ? 's' : ''} for "${searchQuery}"`);
   // Focus the first result for better keyboard flow
   setTimeout(() => {
     const firstCard = document.querySelector('.search-result-card');
     if (firstCard) firstCard.focus();
   }, 0);
  }

  // Persist non-sensitive UI state across sessions
  loadUIState() {
    try {
      const state = JSON.parse(localStorage.getItem('videoloft_ui_state') || '{}');
      const startInput = document.getElementById('startDate');
      const endInput = document.getElementById('endDate');
      const camSelect = document.getElementById('aiCameraSelect');
      const queryInput = document.getElementById('searchQuery');
      if (state.startDate && startInput) startInput.value = state.startDate;
      if (state.endDate && endInput) endInput.value = state.endDate;
      if (state.camera && camSelect) camSelect.value = state.camera;
      if (state.query && queryInput) queryInput.value = state.query;
      if (state.searchText) this.currentFilters.searchText = state.searchText;
      if (state.sortBy) this.currentSortBy = state.sortBy;
  } catch (_) {}
  }

  saveUIState() {
    try {
      const startInput = document.getElementById('startDate');
      const endInput = document.getElementById('endDate');
      const camSelect = document.getElementById('aiCameraSelect');
      const queryInput = document.getElementById('searchQuery');
      const state = {
        startDate: startInput ? startInput.value : undefined,
        endDate: endInput ? endInput.value : undefined,
        camera: camSelect ? camSelect.value : undefined,
        query: queryInput ? queryInput.value : undefined,
        searchText: this.currentFilters.searchText,
        sortBy: this.currentSortBy,
      };
      localStorage.setItem('videoloft_ui_state', JSON.stringify(state));
    } catch (_) {}
  }

 showEmptyState(container, searchQuery) {
   container.innerHTML = `
     <div class="search-empty-state">
       <div class="empty-state-icon">
         <i class="fas fa-search-minus"></i>
       </div>
       <h3>No Results Found</h3>
       <p>
         No events found matching "${searchQuery}". Try adjusting your search terms or check if events have been analyzed for this time period.
       </p>
       <div class="empty-state-actions">
         <button type="button" class="btn btn-secondary" onclick="document.getElementById('searchQuery').focus();">
           <i class="fas fa-edit"></i> Refine Search
         </button>
       </div>
     </div>
   `;
 }

 createResultsHeader(totalCount, filteredCount) {
   const quick = [
     { label: 'All', icon: 'list', value: '' },
     { label: 'People', icon: 'user', value: 'person' },
     { label: 'Vehicles', icon: 'car', value: 'car' },
     { label: 'Animals', icon: 'paw', value: 'dog' }
   ];
   const activeQuick = this.currentFilters.searchText || '';
   const filterChips = [
     this.currentFilters.camera !== 'all' ? `<span class="chip" data-chip="camera">${this.currentFilters.camera}<button class="chip-close" aria-label="Clear camera" data-clear="camera">×</button></span>` : '',
     activeQuick ? `<span class="chip" data-chip="quick">${activeQuick}<button class="chip-close" aria-label="Clear filter" data-clear="quick">×</button></span>` : ''
   ].filter(Boolean).join('');
   const chipsHtml = filterChips ? `<div class="active-chips">${filterChips}</div>` : '';

   return `
     <div class="search-results-header">
       <div class="search-results-title">
         <h3>
           <i class="fas fa-video"></i>
           Search Results
         </h3>
         <div class="search-results-count">
           Showing ${filteredCount} of ${totalCount} results
         </div>
       </div>
       ${chipsHtml}
       <div class="search-controls">
         <div class="search-filters">
           ${quick.map(q => `
             <button class="filter-btn ${activeQuick === q.value ? 'active' : ''}" data-filter="searchText" data-value="${q.value}">
               <i class="fas fa-${q.icon}"></i> ${q.label}
             </button>
           `).join('')}
         </div>
         <div class="sort-dropdown">
           <button class="sort-btn" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'block' ? 'none' : 'block'">
             <i class="fas fa-sort"></i>
             Sort: ${this.getSortDisplayName()}
             <i class="fas fa-chevron-down"></i>
           </button>
           <div class="sort-options" style="display: none; position: absolute; top: 100%; left: 0; background: var(--ha-bg-elevated); border: 1px solid var(--border-primary); border-radius: var(--radius-md); min-width: 160px; z-index: 10;">
             <button class="sort-option ${this.currentSortBy === 'relevance' ? 'active' : ''}" data-sort="relevance">Relevance</button>
             <button class="sort-option ${this.currentSortBy === 'newest' ? 'active' : ''}" data-sort="newest">Newest First</button>
             <button class="sort-option ${this.currentSortBy === 'oldest' ? 'active' : ''}" data-sort="oldest">Oldest First</button>
           </div>
         </div>
       </div>
     </div>
   `;
 }

 renderResults() {
   const resultsContainer = document.getElementById('searchResults');
   if (!resultsContainer) return;

   const startIndex = this.currentPage * this.resultsPerPage;
   const endIndex = startIndex + this.resultsPerPage;
   const pageResults = this.filteredResults.slice(startIndex, endIndex);
   const hasMoreResults = endIndex < this.filteredResults.length;

   const headerHtml = this.createResultsHeader(this.currentResults.length, this.filteredResults.length);
   
   const cardsHtml = pageResults.map(event => this.createResultCard(event)).join('');
   
   const loadMoreHtml = hasMoreResults ? `
     <div class="load-more-container">
       <button class="btn-load-more" onclick="window.aiManager.loadMoreResults()">
         <i class="fas fa-plus"></i>
         Load More Results
       </button>
     </div>
   ` : '';

   resultsContainer.innerHTML = `
     ${headerHtml}
     <div class="search-results-grid">
       ${cardsHtml}
     </div>
     ${loadMoreHtml}
   `;

   // Bind event listeners for filters and sorting
   this.bindFilterAndSortEvents();
 }

 createResultCard(event) {
   const thumbnailUrl = event.thumbnail || 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZjFmMWYxIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCwgc2Fucy1zZXJpZiIgZm9udC1zaXplPSIxOCIgZmlsbD0iIzk5OTk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPk5vIFRodW1ibmFpbDwvdGV4dD48L3N2Zz4=';
   const videoUrl = event.url || '#';
   const cameraName = event.camera_name || 'Unknown Camera';
   const timestamp = this.formatDateTime(event.timestamp);

   // Clean up description - remove generic AI prefixes and introductory text
   let description = event.description || 'No description available';
   description = description
     .replace(/^(Here's a description of the CCTV image:\s*|The image shows:\s*|In this image,?\s*|This image depicts\s*|The CCTV footage shows\s*)/i, '')
     .replace(/^(I can see\s*|Looking at this image,?\s*|In the footage,?\s*|The video shows\s*|This surveillance image\s*)/i, '')
     .replace(/^(Comprehensive, factual description:\s*|Analyzing this CCTV footage image:\s*|Forensic analysis reveals:\s*)/i, '')
     .replace(/^(Detailed observation:\s*|In this security footage:\s*)/i, '')
     .trim();
   
   if (!description || description.length < 10) {
     description = 'Event detected - click to view video';
   }

   return `
     <div class="search-result-card" onclick="window.open('${videoUrl}', '_blank')" role="button" tabindex="0"
          onkeydown="if(event.key==='Enter'||event.key===' '){window.open('${videoUrl}', '_blank')}"
          aria-label="Play video from ${cameraName} at ${timestamp}">
       <div class="result-thumbnail">
         <img src="${thumbnailUrl}" alt="Video thumbnail from ${cameraName}" loading="lazy" 
              onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'" />
         <div class="thumbnail-placeholder" style="display: none; width: 100%; height: 100%; background: var(--ha-bg-secondary); align-items: center; justify-content: center; color: var(--text-muted);">
           <i class="fas fa-video" style="font-size: 2rem; opacity: 0.5;"></i>
         </div>
         <div class="result-overlay">
           <div class="btn-play" aria-hidden="true">
             <i class="fas fa-play"></i>
           </div>
         </div>
       </div>
       <div class="result-content">
         <div class="result-header">
           <div class="result-camera" title="Filter by this camera">
             <i class="fas fa-video"></i>
             <button class="link-btn" onclick="event.stopPropagation(); window.aiManager.applyFilter('camera', '${cameraName.replace(/'/g, "\\'")}')">${cameraName}</button>
           </div>
           <div class="result-time">
             <i class="fas fa-clock"></i>
             ${timestamp}
           </div>
         </div>
         <div class="result-description">
           ${description}
         </div>
         <div class="result-actions">
           <button class="btn btn-primary btn-lg" onclick="event.stopPropagation(); window.open('${videoUrl}', '_blank')">
             <i class="fas fa-external-link-alt"></i> Play in Videoloft
           </button>
         </div>
       </div>
     </div>
   `;
 }

 bindFilterAndSortEvents() {
   // Filter button events (use closest to handle icon clicks)
   document.querySelectorAll('.filter-btn').forEach(btn => {
     btn.addEventListener('click', (e) => {
       const target = e.target.closest('.filter-btn');
       if (!target) return;
       const filterType = target.getAttribute('data-filter');
       const filterValue = target.getAttribute('data-value');
       this.applyFilter(filterType, filterValue);
     });
   });

   // Active chip clear events
   document.querySelectorAll('.chip-close').forEach(btn => {
     btn.addEventListener('click', (e) => {
       const clearType = e.currentTarget.getAttribute('data-clear');
       if (clearType === 'camera') this.currentFilters.camera = 'all';
       if (clearType === 'quick') this.currentFilters.searchText = '';
       this.currentPage = 0;
       this.applyFiltersAndSort();
       this.saveUIState();
       e.stopPropagation();
     });
   });

   // Sort option events
   document.querySelectorAll('.sort-option').forEach(btn => {
     btn.addEventListener('click', (e) => {
       const sortBy = e.target.getAttribute('data-sort');
       this.applySorting(sortBy);
       e.target.closest('.sort-options').style.display = 'none';
     });
   });

   // Close sort dropdown when clicking outside
   document.addEventListener('click', (e) => {
     if (!e.target.closest('.sort-dropdown')) {
       document.querySelectorAll('.sort-options').forEach(dropdown => {
         dropdown.style.display = 'none';
       });
     }
   });
 }

  applyFilter(filterType, filterValue) {
    if (filterType === 'searchText') {
      this.currentFilters.searchText = (filterValue || '').toLowerCase();
    } else if (filterType === 'camera') {
      this.currentFilters.camera = filterValue || 'all';
    } else if (filterType === 'all') {
      this.currentFilters = { camera: 'all', timeOfDay: 'all', searchText: '' };
    } else {
      this.currentFilters[filterType] = filterValue;
    }
    this.currentPage = 0; // Reset to first page
    this.applyFiltersAndSort();
    this.saveUIState();
  }

  applySorting(sortBy) {
    this.currentSortBy = sortBy;
    this.currentPage = 0; // Reset to first page
    this.applyFiltersAndSort();
    this.saveUIState();
  }

 applyFiltersAndSort() {
   // Apply filters
   const quick = (this.currentFilters.searchText || '').trim();
   this.filteredResults = this.currentResults.filter(event => {
     // Camera filter
     if (this.currentFilters.camera !== 'all' && event.camera_name !== this.currentFilters.camera) {
       return false;
     }
     // Quick keyword filter on description
     if (quick) {
       const d = (event.description || '').toString().toLowerCase();
       if (!d.includes(quick)) return false;
     }
     return true;
   });

   // Apply sorting
   this.filteredResults.sort((a, b) => {
     switch (this.currentSortBy) {
       case 'relevance':
         return new Date(b.timestamp) - new Date(a.timestamp); // Default to newest first for relevance
       case 'newest':
         return new Date(b.timestamp) - new Date(a.timestamp);
       case 'oldest':
         return new Date(a.timestamp) - new Date(b.timestamp);
       default:
         return 0;
     }
   });

   this.renderResults();
 }

 loadMoreResults() {
   this.currentPage++;
   this.renderResults();
 }

 getSortDisplayName() {
   const sortNames = {
     'relevance': 'Relevance',
     'newest': 'Newest First',
     'oldest': 'Oldest First'
   };
   return sortNames[this.currentSortBy] || 'Relevance';
 }

  showLoadingState() {
   const resultsContainer = document.getElementById('searchResults');
   if (!resultsContainer) return;

   const skeletonCards = Array(6).fill().map(() => `
     <div class="skeleton-card">
       <div class="skeleton-thumbnail"></div>
       <div class="skeleton-content">
         <div class="skeleton-line medium"></div>
         <div class="skeleton-line short"></div>
         <div class="skeleton-line"></div>
         <div class="skeleton-line medium"></div>
       </div>
     </div>
   `).join('');

   resultsContainer.innerHTML = `
     <div class="search-results-header">
       <div class="search-results-title">
         <h3><i class="fas fa-video"></i> Searching...</h3>
       </div>
     </div>
     <div class="search-results-skeleton">
       ${skeletonCards}
     </div>
   `;
 }

 handleKeyboardNavigation(event) {
   // Only handle navigation when search results are visible
   const resultsGrid = document.querySelector('.search-results-grid');
   if (!resultsGrid || !document.activeElement) return;

   const cards = Array.from(resultsGrid.querySelectorAll('.search-result-card'));
   const currentIndex = cards.findIndex(card => card === document.activeElement);

   switch (event.key) {
     case 'ArrowDown':
       event.preventDefault();
       if (currentIndex < cards.length - 1) {
         cards[currentIndex + 1].focus();
       }
       break;
     case 'ArrowUp':
       event.preventDefault();
       if (currentIndex > 0) {
         cards[currentIndex - 1].focus();
       }
       break;
     case 'ArrowRight':
       event.preventDefault();
       // Move to next card in grid row
       const nextCard = cards[currentIndex + 1];
       if (nextCard) nextCard.focus();
       break;
     case 'ArrowLeft':
       event.preventDefault();
       // Move to previous card in grid row
       const prevCard = cards[currentIndex - 1];
       if (prevCard) prevCard.focus();
       break;
   }
 }

  formatDateTime(timestamp) {
    if (!timestamp) return 'Unknown';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    // Show relative time for recent events
    if (diffMins < 60) {
      return diffMins <= 1 ? 'Just now' : `${diffMins} minutes ago`;
    } else if (diffHours < 24) {
      return diffHours === 1 ? '1 hour ago' : `${diffHours} hours ago`;
    } else if (diffDays < 7) {
      return diffDays === 1 ? '1 day ago' : `${diffDays} days ago`;
    } else {
      // Show formatted date for older events
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    }
  }

  // Accessibility: announce status for screen readers
  announce(message) {
    const sr = document.getElementById('srStatus');
    if (sr) sr.textContent = message;
  }

}

// Make it globally available
window.AIManager = AIManager;
window.aiManager = null; // Will be set when initialized
