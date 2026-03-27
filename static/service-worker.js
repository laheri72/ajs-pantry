const CACHE_NAME = 'ajs-pantry-v2';
const STATIC_ASSETS = [
    '/',
    '/static/style.css',
    '/static/theme-dark.css',
    '/static/script.js',
    '/offline',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js'
];

// Routes that should never be cached (auth-related or sensitive)
const NEVER_CACHE = [
    '/login',
    '/staff-login',
    '/logout',
    '/change-password',
    '/api/'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('push', (event) => {
    let data = {};
    if (event.data) {
        data = event.data.json();
    }

    const title = data.title || 'Maskan Breakfast Notification';
    const options = {
        body: data.body || 'You have a new update.',
        icon: data.icon || '/static/icons/icon-192.png',
        badge: '/static/icons/icon-192.png',
        data: {
            url: data.url || '/dashboard'
        }
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const urlToOpen = event.notification.data.url;

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
            // Check if there is already a window/tab open with the target URL
            for (let i = 0; i < windowClients.length; i++) {
                const client = windowClients[i];
                if (client.url === urlToOpen && 'focus' in client) {
                    return client.focus();
                }
            }
            // If not, open a new window/tab
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET requests or requests to never-cache routes
    if (event.request.method !== 'GET' || NEVER_CACHE.some(route => url.pathname.startsWith(route))) {
        return;
    }

    // Handle same-origin navigation/API and external assets separately
    const isStaticAsset = url.pathname.startsWith('/static/') || url.origin !== self.location.origin;

    if (isStaticAsset) {
        // Static assets (CSS, JS, Images, Fonts) - Cache-first
        event.respondWith(
            caches.match(event.request).then((response) => {
                return response || fetch(event.request).then((fetchResponse) => {
                    // Only cache successful responses
                    if (fetchResponse.status === 200) {
                        const responseToCache = fetchResponse.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, responseToCache);
                        });
                    }
                    return fetchResponse;
                });
            }).catch(() => {
                // If static asset not found and offline, return offline page for navigation if it's one of them
                if (event.request.mode === 'navigate') {
                    return caches.match('/offline');
                }
            })
        );
    } else {
        // Navigation and API - Network-first
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    // Cache only successful HTML responses
                    if (response.status === 200 && response.headers.get('content-type')?.includes('text/html')) {
                        const responseClone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, responseClone);
                        });
                    }
                    return response;
                })
                .catch(() => {
                    return caches.match(event.request).then((response) => {
                        return response || caches.match('/offline');
                    });
                })
        );
    }
});
