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

// Profile Picture Management
function uploadProfilePicture(input) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            document.getElementById('profilePicture').src = e.target.result;
            // Store in localStorage for demo purposes
            localStorage.setItem('profilePicture', e.target.result);
            showNotification('Profile picture updated!', 'success');
        };
        reader.readAsDataURL(input.files[0]);
    }
}

// Floor Filtering for Admin
function filterByFloor() {
    const selectedFloor = document.getElementById('floorFilter').value;
    const rows = document.querySelectorAll('.user-row');
    
    rows.forEach(row => {
        const userFloor = row.getAttribute('data-floor');
        if (!selectedFloor || userFloor === selectedFloor) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

// Cooking Reminder Notifications
function setupCookingReminders() {
    if ('Notification' in window && Notification.permission === 'granted') {
        // Check for upcoming cooking assignments
        const today = new Date();
        const reminderDate = new Date(today.getTime() + (2 * 24 * 60 * 60 * 1000));
        
        // This would check against actual menu data
        console.log('Checking for cooking reminders...');
    }
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
    const printEl = document.getElementById('printableReport');
    if (!printEl) return;

    const w = window.open('', '_blank', 'width=900,height=650');
    if (!w) return;

    w.document.open();
    w.document.write(`
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Expense Report</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body class="p-4">
            ${printEl.innerHTML}
        </body>
        </html>
    `);
    w.document.close();

    w.focus();
    w.print();
    w.close();
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

// Profile picture handling
function handleProfilePicUpload(event) {
    const file = event.target.files[0];
    if (file) {
        if (file.size > 5 * 1024 * 1024) { // 5MB limit
            showNotification('File size must be less than 5MB', 'error');
            return;
        }
        
        const reader = new FileReader();
        reader.onload = function(e) {
            const profileImg = document.querySelector('.profile-pic');
            const profileIcon = document.querySelector('.profile-avatar-large i');
            
            if (profileImg) {
                profileImg.src = e.target.result;
            } else if (profileIcon) {
                profileIcon.style.display = 'none';
                const newImg = document.createElement('img');
                newImg.src = e.target.result;
                newImg.alt = 'Profile Picture';
                newImg.className = 'profile-pic';
                newImg.style.cssText = 'width: 100px; height: 100px; border-radius: 50%; object-fit: cover;';
                profileIcon.parentNode.appendChild(newImg);
            }
            
            // Store in localStorage (in real app, would upload to server)
            localStorage.setItem('userProfilePic', e.target.result);
            showNotification('Profile picture updated successfully!', 'success');
        };
        reader.readAsDataURL(file);
    }
}

// Admin edit user functionality
function editUser(userId, username, email, role, floor) {
    const modal = new bootstrap.Modal(document.getElementById('editUserModal'));
    const form = document.getElementById('editUserForm');
    
    // Set form action to the edit user route
    form.action = `/admin/edit_user/${userId}`;
    
    // Populate form fields
    document.getElementById('editUserId').value = userId;
    document.getElementById('editUsername').value = username;
    document.getElementById('editEmail').value = email;
    document.getElementById('editRole').value = role;
    document.getElementById('editFloor').value = floor;
    
    modal.show();
}

// Floor filtering for admin
function filterByFloor() {
    const selectedFloor = document.getElementById('floorFilter').value;
    const rows = document.querySelectorAll('#usersTable tbody tr');
    
    rows.forEach(row => {
        const floorCell = row.querySelector('td:nth-child(3)'); // Floor column
        if (!selectedFloor || floorCell.textContent.trim() === selectedFloor) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

// Cooking reminder notifications
function initializeCookingAlerts() {
    console.log('Cooking alerts initialized');
    
    // Check for upcoming cooking tasks every 30 seconds
    setInterval(checkCookingReminders, 30000);
    
    // Check immediately on load
    checkCookingReminders();
}

function checkCookingReminders() {
    const now = new Date();
    const today = now.toISOString().split('T')[0];
    const currentTime = now.getHours() * 60 + now.getMinutes(); // Minutes since midnight
    
    // Check for menus and tea tasks due soon (within 30 minutes)
    const upcomingTasks = JSON.parse(localStorage.getItem('upcomingTasks') || '[]');
    
    upcomingTasks.forEach(task => {
        if (task.date === today) {
            const taskTime = parseTime(task.time || '08:00'); // Default breakfast time
            const timeDiff = taskTime - currentTime;
            
            if (timeDiff > 0 && timeDiff <= 30) { // Within 30 minutes
                showCookingNotification(task);
            }
        }
    });
}

function parseTime(timeString) {
    const [hours, minutes] = timeString.split(':').map(Number);
    return hours * 60 + minutes;
}

function showCookingNotification(task) {
    const notificationId = `cooking-${task.id}-${task.date}`;
    
    // Avoid duplicate notifications
    if (localStorage.getItem(notificationId)) {
        return;
    }
    
    const message = `🍳 Reminder: "${task.title}" is scheduled soon!`;
    showNotification(message, 'warning', 8000);
    
    // Push notification if supported
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Cooking Reminder', {
            body: message,
            icon: '/static/icon-192x192.png',
            tag: notificationId
        });
    }
    
    // Mark as notified
    localStorage.setItem(notificationId, 'true');
}

// Expose global functions
window.toggleTheme = toggleTheme;
window.refreshData = refreshData;
window.downloadApp = downloadApp;
window.returnToLastPage = returnToLastPage;
window.exportData = exportData;
window.printExpenseReport = printExpenseReport;
window.showNotification = showNotification;
window.handleProfilePicUpload = handleProfilePicUpload;
window.editUser = editUser;
window.filterByFloor = filterByFloor;
window.initializeCookingAlerts = initializeCookingAlerts;
