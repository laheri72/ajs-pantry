// Maskan Breakfast Management - Custom JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    // Load theme preference
    loadTheme();
    
    // Initialize form validation
    initializeFormValidation();
    
    // Initialize offline functionality
    initializeOfflineSupport();
    
    // Initialize notifications
    initializeNotifications();
    
    // Initialize tooltips
    initializeTooltips();
    
    // Save last page for return navigation
    saveCurrentPage();
}

// Theme Management
function loadTheme() {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-theme');
        const themeIcon = document.getElementById('themeIcon');
        if (themeIcon) {
            themeIcon.className = 'fas fa-sun';
        }
    }
}

function toggleTheme() {
    const body = document.body;
    const themeIcon = document.getElementById('themeIcon');
    
    if (body.classList.contains('dark-theme')) {
        body.classList.remove('dark-theme');
        if (themeIcon) themeIcon.className = 'fas fa-moon';
        localStorage.setItem('theme', 'light');
        showNotification('Light theme activated', 'success');
    } else {
        body.classList.add('dark-theme');
        if (themeIcon) themeIcon.className = 'fas fa-sun';
        localStorage.setItem('theme', 'dark');
        showNotification('Dark theme activated', 'success');
    }
}

// Form Validation
function initializeFormValidation() {
    // Real-time email validation
    const emailInputs = document.querySelectorAll('input[type="email"]');
    emailInputs.forEach(input => {
        input.addEventListener('blur', validateEmail);
        input.addEventListener('input', debounce(validateEmailRealTime, 300));
    });
    
    // Password confirmation validation
    const passwordInputs = document.querySelectorAll('input[name="confirm_password"]');
    passwordInputs.forEach(input => {
        input.addEventListener('input', validatePasswordMatch);
    });
    
    // Form submission validation
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', validateFormOnSubmit);
    });
}

function validateEmail(event) {
    const email = event.target.value;
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    
    if (email && !emailRegex.test(email)) {
        showFieldError(event.target, 'Please enter a valid email address');
        return false;
    } else {
        clearFieldError(event.target);
        return true;
    }
}

function validateEmailRealTime(event) {
    const email = event.target.value;
    if (email.length > 3) {
        validateEmail(event);
    }
}

function validatePasswordMatch(event) {
    const confirmPassword = event.target.value;
    const password = document.querySelector('input[name="password"]').value;
    
    if (confirmPassword && password !== confirmPassword) {
        showFieldError(event.target, 'Passwords do not match');
        return false;
    } else {
        clearFieldError(event.target);
        return true;
    }
}

function validateFormOnSubmit(event) {
    const form = event.target;
    let isValid = true;
    
    // Validate all required fields
    const requiredFields = form.querySelectorAll('[required]');
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            showFieldError(field, 'This field is required');
            isValid = false;
        }
    });
    
    // Validate email fields
    const emailFields = form.querySelectorAll('input[type="email"]');
    emailFields.forEach(field => {
        if (!validateEmail({target: field})) {
            isValid = false;
        }
    });
    
    // Validate password confirmation
    const confirmPasswordField = form.querySelector('input[name="confirm_password"]');
    if (confirmPasswordField && !validatePasswordMatch({target: confirmPasswordField})) {
        isValid = false;
    }
    
    if (!isValid) {
        event.preventDefault();
        showNotification('Please correct the errors in the form', 'error');
    }
}

function showFieldError(field, message) {
    clearFieldError(field);
    field.classList.add('is-invalid');
    
    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback';
    errorDiv.textContent = message;
    
    field.parentNode.appendChild(errorDiv);
}

function clearFieldError(field) {
    field.classList.remove('is-invalid');
    const errorDiv = field.parentNode.querySelector('.invalid-feedback');
    if (errorDiv) {
        errorDiv.remove();
    }
}

// Offline Support
function initializeOfflineSupport() {
    // Check online status
    window.addEventListener('online', handleOnlineStatus);
    window.addEventListener('offline', handleOfflineStatus);
    
    // Initialize service worker for offline functionality
    if ('serviceWorker' in navigator) {
        registerServiceWorker();
    }
    
    // Initialize IndexedDB for offline storage
    initializeOfflineStorage();
}

function handleOnlineStatus() {
    showNotification('Connection restored', 'success');
    syncOfflineData();
    updateOnlineIndicator(true);
}

function handleOfflineStatus() {
    showNotification('Working offline', 'warning');
    updateOnlineIndicator(false);
}

function updateOnlineIndicator(isOnline) {
    // Add visual indicator for online/offline status
    let indicator = document.getElementById('onlineIndicator');
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'onlineIndicator';
        indicator.style.cssText = `
            position: fixed;
            top: 80px;
            right: 20px;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 0.8rem;
            z-index: 1050;
            transition: all 0.3s ease;
        `;
        document.body.appendChild(indicator);
    }
    
    if (isOnline) {
        indicator.style.background = '#4CAF50';
        indicator.style.color = 'white';
        indicator.textContent = 'Online';
        setTimeout(() => indicator.style.display = 'none', 3000);
    } else {
        indicator.style.background = '#FF9800';
        indicator.style.color = 'white';
        indicator.textContent = 'Offline';
        indicator.style.display = 'block';
    }
}

function registerServiceWorker() {
    navigator.serviceWorker.register('/static/sw.js')
        .then(registration => {
            console.log('Service Worker registered successfully');
        })
        .catch(error => {
            console.log('Service Worker registration failed');
        });
}

function initializeOfflineStorage() {
    // Initialize IndexedDB for offline data storage
    const request = indexedDB.open('MaskanBreakfastDB', 1);
    
    request.onerror = function(event) {
        console.log('Database error:', event.target.error);
    };
    
    request.onsuccess = function(event) {
        window.db = event.target.result;
        console.log('Offline database initialized');
    };
    
    request.onupgradeneeded = function(event) {
        const db = event.target.result;
        
        // Create object stores for offline data
        if (!db.objectStoreNames.contains('syncQueue')) {
            const syncStore = db.createObjectStore('syncQueue', { keyPath: 'id', autoIncrement: true });
            syncStore.createIndex('timestamp', 'timestamp', { unique: false });
        }
        
        if (!db.objectStoreNames.contains('offlineData')) {
            const dataStore = db.createObjectStore('offlineData', { keyPath: 'key' });
        }
    };
}

function syncOfflineData() {
    if (!window.db) return;
    
    const transaction = window.db.transaction(['syncQueue'], 'readonly');
    const store = transaction.objectStore('syncQueue');
    
    store.getAll().onsuccess = function(event) {
        const queuedItems = event.target.result;
        
        queuedItems.forEach(item => {
            // Process queued offline changes
            processOfflineItem(item);
        });
    };
}

function processOfflineItem(item) {
    // Process individual offline items
    console.log('Processing offline item:', item);
    // Implementation would depend on specific data types
}

// Notifications
function initializeNotifications() {
    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
    
    // Setup cooking alert notifications
    setupCookingAlerts();
}

function setupCookingAlerts() {
    // Check for cooking assignments 2 days in advance
    if ('serviceWorker' in navigator && 'Notification' in window) {
        // This would be handled by the service worker
        console.log('Cooking alerts initialized');
    }
}

function showNotification(message, type = 'info') {
    // Create custom notification toast
    const toast = document.createElement('div');
    toast.className = `alert alert-${type === 'error' ? 'danger' : type} toast-notification`;
    toast.style.cssText = `
        position: fixed;
        top: 90px;
        right: 20px;
        z-index: 1060;
        min-width: 300px;
        animation: slideInRight 0.3s ease;
    `;
    
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
    `;
    
    document.body.appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.animation = 'slideOutRight 0.3s ease';
            setTimeout(() => toast.remove(), 300);
        }
    }, 5000);
    
    // Browser notification for important alerts
    if (type === 'warning' || type === 'error') {
        showBrowserNotification(message);
    }
}

function showBrowserNotification(message) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Maskan Breakfast Management', {
            body: message,
            icon: '/static/icon-192.png'
        });
    }
}

// Tooltips
function initializeTooltips() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Navigation
function saveCurrentPage() {
    localStorage.setItem('lastPage', window.location.pathname);
}

function returnToLastPage() {
    const lastPage = localStorage.getItem('lastPage');
    if (lastPage && lastPage !== window.location.pathname) {
        window.location.href = lastPage;
    }
}

// Utility Functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function refreshData() {
    showNotification('Refreshing data...', 'info');
    setTimeout(() => {
        location.reload();
    }, 500);
}

function downloadApp() {
    // Create downloadable HTML file
    showNotification('Preparing app download...', 'info');
    
    // This would create a static HTML version of the app
    setTimeout(() => {
        showNotification('Download feature will be available soon!', 'warning');
    }, 1000);
}

// Data Management
function exportData(format = 'json') {
    const data = {
        timestamp: new Date().toISOString(),
        version: '1.0',
        // Add relevant data export logic here
    };
    
    const dataStr = JSON.stringify(data, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    
    const link = document.createElement('a');
    link.href = URL.createObjectURL(dataBlob);
    link.download = `maskan-data-${new Date().toISOString().split('T')[0]}.json`;
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showNotification('Data exported successfully', 'success');
}

// Search and Filter
function setupSearch() {
    const searchInputs = document.querySelectorAll('.search-input');
    searchInputs.forEach(input => {
        input.addEventListener('input', debounce(function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const targetSelector = e.target.getAttribute('data-target');
            const items = document.querySelectorAll(targetSelector);
            
            items.forEach(item => {
                const text = item.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    item.style.display = '';
                } else {
                    item.style.display = 'none';
                }
            });
        }, 300));
    });
}

// Calendar Functions
function generateCalendarEvents(menus, teaTasks) {
    const events = [];
    
    if (menus) {
        menus.forEach(menu => {
            events.push({
                date: menu.date,
                title: menu.title,
                type: 'menu',
                class: 'bg-teal'
            });
        });
    }
    
    if (teaTasks) {
        teaTasks.forEach(task => {
            events.push({
                date: task.date,
                title: task.title,
                type: 'tea',
                class: 'bg-warning'
            });
        });
    }
    
    return events;
}

// Print Functions
function printExpenseReport() {
    const printContent = document.getElementById('printableReport');
    if (printContent) {
        const originalContent = document.body.innerHTML;
        document.body.innerHTML = printContent.innerHTML;
        window.print();
        document.body.innerHTML = originalContent;
        location.reload();
    }
}

// Error Handling
window.addEventListener('error', function(event) {
    console.error('Application error:', event.error);
    showNotification('An unexpected error occurred. Please refresh the page.', 'error');
});

window.addEventListener('unhandledrejection', function(event) {
    console.error('Unhandled promise rejection:', event.reason);
    showNotification('A network error occurred. Please check your connection.', 'error');
});

// Performance Monitoring
function logPerformance() {
    if ('performance' in window) {
        const loadTime = performance.now();
        console.log(`Page loaded in ${loadTime.toFixed(2)}ms`);
        
        // Log to analytics if needed
        if (loadTime > 3000) {
            console.warn('Slow page load detected');
        }
    }
}

// Initialize performance monitoring
window.addEventListener('load', logPerformance);

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    
    @keyframes slideOutRight {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
    
    .toast-notification {
        animation: slideInRight 0.3s ease;
    }
`;
document.head.appendChild(style);

// Expose global functions
window.toggleTheme = toggleTheme;
window.refreshData = refreshData;
window.downloadApp = downloadApp;
window.returnToLastPage = returnToLastPage;
window.exportData = exportData;
window.printExpenseReport = printExpenseReport;
window.showNotification = showNotification;
