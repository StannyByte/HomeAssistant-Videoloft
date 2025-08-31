"use strict";

// Utility: shorthand for document.getElementById
const $ = (id) => document.getElementById(id);

const capitalizeFirstLetter = (string) =>
  string.charAt(0).toUpperCase() + string.slice(1);

/* ===============================
   TOAST NOTIFICATION SYSTEM
   =============================== */

class ToastManager {
  constructor() {
    this.container = null;
    this.init();
  }

  init() {
    // Create toast container if it doesn't exist
    this.container = document.getElementById('toast-container');
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.id = 'toast-container';
      this.container.className = 'toast-container';
      document.body.appendChild(this.container);
    }
  }

  show(message, type = 'info', duration = 5000) {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    const icon = this.getIcon(type);
    
    toast.innerHTML = `
      <span class="toast-icon">${icon}</span>
      <span class="toast-message">${message}</span>
      <button class="toast-close" aria-label="Close notification">
        <i class="fas fa-times"></i>
      </button>
    `;

    // Add close functionality
    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => this.remove(toast));

    // Add to container
    this.container.appendChild(toast);

    // Auto-remove after duration (except for loading toasts)
    if (type !== 'loading' && duration > 0) {
      setTimeout(() => this.remove(toast), duration);
    }

    return toast;
  }

  remove(toast) {
    if (!toast || !toast.parentNode) return;
    
    toast.classList.add('fade-out');
    setTimeout(() => {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, 300);
  }

  getIcon(type) {
    const icons = {
      success: '<i class="fas fa-check-circle"></i>',
      error: '<i class="fas fa-exclamation-circle"></i>',
      warning: '<i class="fas fa-exclamation-triangle"></i>',
      info: '<i class="fas fa-info-circle"></i>',
      loading: '<i class="fas fa-spinner spinning"></i>'
    };
    return icons[type] || icons.info;
  }

  success(message, duration = 4000) {
    return this.show(message, 'success', duration);
  }

  error(message, duration = 6000) {
    return this.show(message, 'error', duration);
  }

  warning(message, duration = 5000) {
    return this.show(message, 'warning', duration);
  }

  info(message, duration = 4000) {
    return this.show(message, 'info', duration);
  }

  loading(message) {
    return this.show(message, 'loading', 0); // No auto-remove
  }

  // Clear all toasts
  clear() {
    const toasts = this.container.querySelectorAll('.toast');
    toasts.forEach(toast => this.remove(toast));
  }
}

// Global toast manager instance
window.toastManager = new ToastManager();

// Convenience functions for global use
window.showToast = (message, type = 'info', duration) => {
  return window.toastManager.show(message, type, duration);
};

window.showSuccess = (message) => window.toastManager.success(message);
window.showError = (message) => window.toastManager.error(message);
window.showWarning = (message) => window.toastManager.warning(message);
window.showInfo = (message) => window.toastManager.info(message);
window.showLoading = (message) => window.toastManager.loading(message);

/* ===============================
   STATUS OVERLAY SYSTEM
   =============================== */

window.showStatus = (message) => {
  const overlay = document.getElementById('statusOverlay');
  const messageEl = document.getElementById('statusMessage');
  
  if (overlay && messageEl) {
    messageEl.textContent = message;
    overlay.style.display = 'flex';
  }
};

window.hideStatus = () => {
  const overlay = document.getElementById('statusOverlay');
  if (overlay) {
    overlay.style.display = 'none';
  }
};

/* ===============================
   ENHANCED STATUS MESSAGES
   =============================== */

window.updateStatusMessage = (element, message, type = 'ready', showIcon = true) => {
  if (!element) return;
  
  // Clear existing classes
  element.className = element.className.replace(/status-\w+/g, '');
  element.classList.add('status-message', `status-${type}`);
  
  const icon = showIcon ? `<span class="status-icon ${type === 'processing' ? 'spinning' : ''}">${getStatusIcon(type)}</span>` : '';
  element.innerHTML = `${icon}${message}`;
};

function getStatusIcon(type) {
  const icons = {
    ready: '<i class="fas fa-check-circle"></i>',
    processing: '<i class="fas fa-spinner"></i>',
    error: '<i class="fas fa-exclamation-circle"></i>',
    warning: '<i class="fas fa-exclamation-triangle"></i>',
    success: '<i class="fas fa-check-circle"></i>'
  };
  return icons[type] || icons.ready;
}