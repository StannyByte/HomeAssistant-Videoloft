"use strict";

class Tabs {
  constructor() {
    this.navItems = document.querySelectorAll(".nav-item");
    this.tabSections = document.querySelectorAll(".tab-section");
    this.handleHashChange = this.handleHashChange.bind(this);
    this.init();
  }

  init() {
    // Clicking a nav item updates the URL hash; hashchange handler drives UI
    this.navItems.forEach((item) => {
      item.addEventListener("click", () => {
        const tabId = item.getAttribute("data-tab");
        if (!tabId) return;
        if (location.hash !== `#${tabId}`) {
          location.hash = `#${tabId}`;
        } else {
          // If hash already matches (e.g., user re-clicks), still ensure UI is synced
          this.showTabContent(item, false);
        }
      });
    });

    // Respond to URL hash changes (back/forward navigation supported)
    window.addEventListener('hashchange', this.handleHashChange, { passive: true });

    // Initial activation based on URL hash or default to first tab
    if (location.hash) {
      this.handleHashChange();
    } else {
      const initial = document.querySelector(".nav-item.active") || this.navItems[0];
      if (initial) {
        const tabId = initial.getAttribute("data-tab");
        if (tabId) {
          // Set the hash to support back/forward from the start
          location.hash = `#${tabId}`;
        } else {
          this.showTabContent(initial, false);
        }
      }
    }
  }

  activateTab(selectedItem) {
    this.showTabContent(selectedItem, true);
  }

  showTabContent(selectedItem, showNotification = true) {
    // Remove active class from all nav items and sections
    this.navItems.forEach((item) => item.classList.remove("active"));
    selectedItem.classList.add("active");

    this.tabSections.forEach((section) => section.classList.remove("active"));
    
    // Activate the target tab section
    const tabId = selectedItem.getAttribute("data-tab");
    const activeSection = document.getElementById(`${tabId}Tab`);

    if (activeSection) {
      activeSection.classList.add("active");
    } else {
      console.warn(`No tab section found for tab ID: ${tabId}`);
    }

    // Optional: update document title suffix for clarity
    try {
      const baseTitle = document.title.replace(/\s*[-|•]\s*.*$/, '');
      const label = selectedItem.querySelector('.nav-text')?.textContent?.trim() || tabId;
      document.title = `${baseTitle} — ${label}`;
    } catch (_) {}
  }

  handleHashChange() {
    const hash = (location.hash || '').replace('#', '');
    if (!hash) return;
    const target = Array.from(this.navItems).find((i) => i.getAttribute('data-tab') === hash);
    if (target) {
      this.showTabContent(target, false);
    } else {
      // Fallback: activate first tab if hash is unknown
      const first = this.navItems[0];
      if (first) this.showTabContent(first, false);
    }
  }
}
