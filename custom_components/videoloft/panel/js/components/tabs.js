"use strict";

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
    const otherTabsWrapper = document.getElementById("other-tabs-wrapper");

    if (otherTabsWrapper) {
      if (tabId === 'live') {
        otherTabsWrapper.style.display = 'none';
      } else {
        otherTabsWrapper.style.display = 'block'; // Or 'flex' depending on its original display type
      }
    }

    if (activeSection) {
      activeSection.classList.add("active");
    } else {
      console.warn(`No tab section found for tab ID: ${tabId}`);
    }
    // Log which tab is activated (using a utility function if available)
    // Ensure capitalizeFirstLetter is defined or imported if this file is a module
    // For now, assuming it's globally available or will be handled by module system
    if (typeof capitalizeFirstLetter === 'function') {
        console.log(`${capitalizeFirstLetter(tabId)} tab activated`);
    } else {
        console.log(`${tabId.charAt(0).toUpperCase() + tabId.slice(1)} tab activated`);
    }
  }
} 