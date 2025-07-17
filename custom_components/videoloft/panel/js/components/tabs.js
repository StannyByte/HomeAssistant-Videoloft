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
  }
} 