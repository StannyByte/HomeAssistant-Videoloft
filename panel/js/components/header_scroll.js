"use strict";

class HeaderScroll {
  constructor() {
    this.header = document.querySelector('.header');
    this.scrollContainer = document.querySelector('.videoloft-panel') || window;
    console.log('[HeaderScroll] Initialized. Header found:', !!this.header, 'Container:', this.scrollContainer);
    this.lastScrollTop = 0;
    this.scrollThreshold = 10; // Minimum scroll distance before toggle
    this.isMobile = window.innerWidth <= 768;
    this.init();
  }

  init() {
    if (!this.header) return;

    this.scrollContainer.addEventListener('scroll', () => {
      this.handleScroll();
    }, { passive: true });

    // Listen for window resize to update mobile state
    window.addEventListener('resize', () => {
      this.isMobile = window.innerWidth <= 768;
    }, { passive: true });

    // Initialize header visibility
    this.handleScroll();
  }

  handleScroll() {
    const currentScrollTop = (this.scrollContainer === window
      ? (window.scrollY || document.documentElement.scrollTop)
      : this.scrollContainer.scrollTop) || 0;
    console.log('[HeaderScroll] Scroll event. isMobile:', this.isMobile, 'currentScrollTop:', currentScrollTop, 'lastScrollTop:', this.lastScrollTop);

    if (this.isMobile) {
      // Mobile behavior: show when scrolling up or at top, hide when scrolling down
      if (currentScrollTop > this.lastScrollTop && currentScrollTop > this.scrollThreshold) {
        // Scrolling DOWN beyond threshold - hide header
        this.header.classList.add('header-hidden');
        console.log('[HeaderScroll] Hiding header (mobile)');
      } else if (currentScrollTop < this.lastScrollTop || currentScrollTop <= this.scrollThreshold) {
        // Scrolling UP or at the top - show header
        this.header.classList.remove('header-hidden');
        console.log('[HeaderScroll] Showing header (mobile)');
      }
    } else {
      // Desktop behavior: show when scrolling up or at top, hide when scrolling down
      if (currentScrollTop > this.lastScrollTop && currentScrollTop > this.scrollThreshold) {
        this.header.classList.add('header-hidden');
        console.log('[HeaderScroll] Hiding header (desktop)');
      } else if (currentScrollTop < this.lastScrollTop || currentScrollTop <= this.scrollThreshold) {
        this.header.classList.remove('header-hidden');
        console.log('[HeaderScroll] Showing header (desktop)');
      }
    }

    this.lastScrollTop = currentScrollTop;
  }
}
