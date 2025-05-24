"use strict";

class HeaderScroll {
  constructor() {
    this.header = document.querySelector('.header');
    this.lastScrollTop = 0;
    this.scrollThreshold = 10; // Minimum scroll distance before toggle
    this.init();
  }

  init() {
    if (!this.header) return;

    window.addEventListener('scroll', () => {
      this.handleScroll();
    }, { passive: true });

    // Initialize header visibility
    this.handleScroll();
  }

  handleScroll() {
    const currentScrollTop = window.scrollY || document.documentElement.scrollTop;
    
    // Determine scroll direction and toggle header visibility
    if (currentScrollTop > this.lastScrollTop && currentScrollTop > this.scrollThreshold) {
      // Scrolling DOWN beyond threshold - hide header
      this.header.classList.add('header-hidden');
    } else if (currentScrollTop < this.lastScrollTop || currentScrollTop <= this.scrollThreshold) {
      // Scrolling UP or at the top - show header
      this.header.classList.remove('header-hidden');
    }
    
    this.lastScrollTop = currentScrollTop;
  }
} 