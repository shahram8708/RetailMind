let CACHE_VERSION = '1.0.0';
let vapidPublicKey = null;

const CACHE_NAMES = {
    static: () => `retailmind-static-${CACHE_VERSION}`,
    html: () => `retailmind-html-${CACHE_VERSION}`,
    api: () => `retailmind-api-${CACHE_VERSION}`,
    images: () => `retailmind-images-${CACHE_VERSION}`,
    cdn: () => `retailmind-cdn-${CACHE_VERSION}`
};

const OFFLINE_URL = '/offline';
const OFFLINE_IMAGE = '/static/img/offline-placeholder.svg';

const PRECACHE_ASSETS = [
    '/manifest.json',
    '/offline',
    '/dashboard',
    '/inventory',
    '/shopper',
    '/campaigns',
    '/static/css/main.css',
    '/static/css/dashboard.css',
    '/static/css/auth.css',
    '/static/css/inventory.css',
    '/static/css/campaigns.css',
    '/static/css/facility.css',
    '/static/css/analytics.css',
    '/static/css/shopper.css',
    '/static/css/superadmin.css',
    '/static/js/main.js',
    '/static/js/dashboard.js',
    '/static/js/inventory.js',
    '/static/js/campaigns.js',
    '/static/js/facility.js',
    '/static/js/analytics.js',
    '/static/js/agent.js',
    '/static/js/shopper.js',
    '/static/js/settings.js',
    '/static/js/superadmin.js',
    '/static/js/pwa.js',
    '/static/js/idb-service.js',
    '/static/img/offline-placeholder.svg',
    '/static/icons/icon-72.png',
    '/static/icons/icon-96.png',
    '/static/icons/icon-128.png',
    '/static/icons/icon-144.png',
    '/static/icons/icon-152.png',
    '/static/icons/icon-180.png',
    '/static/icons/icon-192.png',
    '/static/icons/icon-256.png',
    '/static/icons/icon-384.png',
    '/static/icons/icon-512.png',
    '/static/icons/icon-maskable-512.png',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css',
    'https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js',
    'https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js'
];

const CACHE_LIMITS = {
    static: 80,
    html: 40,
    api: 60,
    images: 60,
    cdn: 30
};

const API_TTL = {
    default: 5 * 60 * 1000,
    inventory: 15 * 60 * 1000,
    analytics: 60 * 60 * 1000,
    dashboard: 2 * 60 * 1000
};

const inFlightRequests = new Map();

self.addEventListener('message', (event) => {
    const data = event.data || {};
    if (data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    if (data.type === 'PWA_CONFIG') {
        if (data.vapidPublicKey) {
            vapidPublicKey = data.vapidPublicKey;
        }
    }
    if (data.type === 'CLEAR_CACHES') {
        event.waitUntil(clearAllCaches());
    }
});

self.addEventListener('install', (event) => {
    event.waitUntil((async () => {
        try {
            const response = await fetch('/api/pwa/config', { cache: 'no-store' });
            if (response.ok) {
                const config = await response.json();
                if (config.cache_version) {
                    CACHE_VERSION = config.cache_version;
                }
            }
        } catch (_error) {
            // Ignore config fetch errors.
        }

        const cache = await caches.open(CACHE_NAMES.static());
        await precacheAssets(cache, PRECACHE_ASSETS);
    })());
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        await clearOldCaches();
        await self.clients.claim();
    })());
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);

    if (request.method !== 'GET') {
        event.respondWith(handleNonGetRequest(event));
        return;
    }

    if (url.origin !== self.location.origin && isCdnRequest(url)) {
        event.respondWith(cacheFirst(request, CACHE_NAMES.cdn(), CACHE_LIMITS.cdn, 7 * 24 * 60 * 60 * 1000));
        return;
    }

    if (isAuthOrPayment(url)) {
        event.respondWith(networkOnly(request));
        return;
    }

    if (isApiRequest(url)) {
        event.respondWith(networkFirst(request, CACHE_NAMES.api(), getApiTtl(url)));
        return;
    }

    if (isImageRequest(request)) {
        event.respondWith(cacheFirst(request, CACHE_NAMES.images(), CACHE_LIMITS.images, null, OFFLINE_IMAGE));
        return;
    }

    if (isHtmlRequest(request)) {
        if (isStaleOkRoute(url)) {
            event.respondWith(staleWhileRevalidate(request, CACHE_NAMES.html(), CACHE_LIMITS.html));
            return;
        }
        event.respondWith(networkFirst(request, CACHE_NAMES.html(), 5000, OFFLINE_URL));
        return;
    }

    if (isStaticAsset(url)) {
        event.respondWith(cacheFirst(request, CACHE_NAMES.static(), CACHE_LIMITS.static));
        return;
    }

    event.respondWith(networkOnly(request));
});

self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-pending-actions') {
        event.waitUntil(processOfflineQueue('sync-pending-actions'));
    }
    if (event.tag === 'sync-pending-approvals') {
        event.waitUntil(processOfflineQueue('sync-pending-approvals'));
    }
    if (event.tag === 'sync-notification-reads') {
        event.waitUntil(processOfflineQueue('sync-notification-reads'));
    }
});

self.addEventListener('push', (event) => {
    const data = event.data ? event.data.json() : {};
    const title = data.title || 'RetailMind';
    const options = {
        body: data.body || 'You have a new notification.',
        icon: data.icon || '/static/icons/icon-192.png',
        badge: data.badge || '/static/icons/icon-72.png',
        tag: data.tag || 'retailmind',
        data: data.data || {},
        actions: data.actions || [],
        vibrate: data.vibrate || [150, 100, 150],
        requireInteraction: Boolean(data.requireInteraction)
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const targetUrl = event.notification.data?.url || '/dashboard';

    event.waitUntil((async () => {
        const allClients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const client of allClients) {
            if ('focus' in client) {
                client.navigate(targetUrl);
                return client.focus();
            }
        }
        if (self.clients.openWindow) {
            return self.clients.openWindow(targetUrl);
        }
        return null;
    })());
});

self.addEventListener('notificationclose', (event) => {
    event.waitUntil(fetch('/push/notification-close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag: event.notification.tag })
    }).catch(() => null));
});

self.addEventListener('pushsubscriptionchange', (event) => {
    event.waitUntil((async () => {
        if (!vapidPublicKey) {
            return;
        }
        const subscription = await self.registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
        });
        await fetch('/push/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(subscription)
        });
    })());
});

async function handleNonGetRequest(event) {
    try {
        const response = await fetch(event.request.clone());
        return response;
    } catch (_error) {
        const queueRecord = await queueRequest(event.request.clone());
        if (queueRecord && queueRecord.sync_tag) {
            try {
                await self.registration.sync.register(queueRecord.sync_tag);
            } catch (_syncError) {
                // Ignore if sync is not available.
            }
        }

        return new Response(JSON.stringify({ success: true, queued: true }), {
            status: 202,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

async function networkFirst(request, cacheName, timeoutMs, fallbackUrl) {
    const cache = await caches.open(cacheName);
    const key = `${request.method}:${request.url}`;

    if (inFlightRequests.has(key)) {
        return inFlightRequests.get(key);
    }

    const fetchPromise = (async () => {
        try {
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), timeoutMs || 5000);
            const response = await fetch(request, { signal: controller.signal });
            clearTimeout(timeout);

            if (response && response.ok) {
                if (cacheName === CACHE_NAMES.api()) {
                    try {
                        const cloned = response.clone();
                        const jsonBody = await cloned.json();
                        const sanitized = new Response(JSON.stringify(jsonBody), {
                            headers: { 'Content-Type': 'application/json', 'X-Cache-Time': String(Date.now()) }
                        });
                        await cache.put(request, sanitized.clone());
                    } catch (_error) {
                        // Skip caching non-JSON responses.
                    }
                } else {
                    await cache.put(request, response.clone());
                }
            }
            return response;
        } catch (_error) {
            const cached = await cache.match(request);
            if (cached) {
                return cached;
            }
            if (fallbackUrl) {
                return caches.match(fallbackUrl);
            }
            return new Response('Offline', { status: 503, statusText: 'Offline' });
        } finally {
            inFlightRequests.delete(key);
        }
    })();

    inFlightRequests.set(key, fetchPromise);
    return fetchPromise;
}

async function networkOnly(request) {
    try {
        return await fetch(request);
    } catch (_error) {
        const cached = await caches.match(request);
        if (cached) {
            return cached;
        }
        return new Response('Offline', { status: 503, statusText: 'Offline' });
    }
}

async function staleWhileRevalidate(request, cacheName, maxEntries) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request);

    const fetchPromise = fetch(request).then((response) => {
        if (response && response.ok) {
            cache.put(request, response.clone());
            limitCacheEntries(cacheName, maxEntries);
        }
        return response;
    }).catch(() => null);

    return cached || fetchPromise;
}

async function cacheFirst(request, cacheName, maxEntries, maxAgeMs, fallbackUrl) {
    const cache = await caches.open(cacheName);
    const cached = await cache.match(request);

    if (cached) {
        if (maxAgeMs) {
            const cachedTime = cached.headers.get('X-Cache-Time');
            if (cachedTime && (Date.now() - Number(cachedTime)) > maxAgeMs) {
                cache.delete(request);
            } else {
                return cached;
            }
        } else {
            return cached;
        }
    }

    try {
        const response = await fetch(request);
        if (response && response.ok) {
            const stored = maxAgeMs
                ? new Response(response.clone().body, {
                    headers: { ...Object.fromEntries(response.headers.entries()), 'X-Cache-Time': String(Date.now()) }
                })
                : response.clone();

            cache.put(request, stored);
            limitCacheEntries(cacheName, maxEntries);
        }
        return response;
    } catch (_error) {
        if (fallbackUrl) {
            return caches.match(fallbackUrl);
        }
        return cached || new Response('Offline', { status: 503, statusText: 'Offline' });
    }
}

function isApiRequest(url) {
    return url.pathname.startsWith('/api/');
}

function isStaticAsset(url) {
    return url.pathname.startsWith('/static/');
}

function isImageRequest(request) {
    return request.destination === 'image';
}

function isHtmlRequest(request) {
    return request.mode === 'navigate' || (request.headers.get('accept') || '').includes('text/html');
}

function isAuthOrPayment(url) {
    return url.pathname.startsWith('/auth') || url.pathname.startsWith('/api/payment') || url.pathname.startsWith('/api/billing');
}

function isStaleOkRoute(url) {
    return ['/features', '/pricing', '/about', '/analytics'].some((path) => url.pathname.startsWith(path));
}

function isCdnRequest(url) {
    return url.hostname.includes('cdn.jsdelivr.net');
}

function getApiTtl(url) {
    if (url.pathname.startsWith('/api/inventory')) {
        return API_TTL.inventory;
    }
    if (url.pathname.startsWith('/api/analytics')) {
        return API_TTL.analytics;
    }
    if (url.pathname.startsWith('/api/kpi')) {
        return API_TTL.dashboard;
    }
    return API_TTL.default;
}

async function clearOldCaches() {
    const cacheNames = await caches.keys();
    await Promise.all(
        cacheNames
            .filter((name) => !Object.values(CACHE_NAMES).some((builder) => name === builder()))
            .map((name) => caches.delete(name))
    );
}

async function clearAllCaches() {
    const cacheNames = await caches.keys();
    await Promise.all(cacheNames.map((name) => caches.delete(name)));
}

async function precacheAssets(cache, assets) {
    for (const asset of assets) {
        try {
            const response = await fetch(asset, { cache: 'no-cache' });
            if (response.ok || response.type === 'opaque') {
                await cache.put(asset, response.clone());
            }
        } catch (_error) {
            // Skip missing or blocked assets so install can still complete.
        }
    }
}

async function limitCacheEntries(cacheName, maxEntries) {
    if (!maxEntries) {
        return;
    }
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    if (keys.length <= maxEntries) {
        return;
    }
    const excess = keys.length - maxEntries;
    for (let i = 0; i < excess; i += 1) {
        await cache.delete(keys[i]);
    }
}

async function queueRequest(request) {
    const bodyText = await request.clone().text();
    const headers = {};
    request.headers.forEach((value, key) => {
        headers[key] = value;
    });

    const url = request.url;
    let syncTag = 'sync-pending-actions';
    if (url.includes('/api/actions/') && (url.includes('/approve') || url.includes('/reject'))) {
        syncTag = 'sync-pending-approvals';
    }
    if (url.includes('/notifications/') && url.includes('/read')) {
        syncTag = 'sync-notification-reads';
    }

    const record = {
        url,
        method: request.method,
        headers,
        body: bodyText,
        timestamp: Date.now(),
        retry_count: 0,
        max_retries: 5,
        sync_tag: syncTag,
        status: 'pending'
    };

    const db = await openDb();
    const tx = db.transaction('offline_queue', 'readwrite');
    const store = tx.objectStore('offline_queue');
    await store.add(record);
    return record;
}

async function processOfflineQueue(tag) {
    const db = await openDb();
    const tx = db.transaction('offline_queue', 'readwrite');
    const store = tx.objectStore('offline_queue');

    const items = await new Promise((resolve, reject) => {
        const queue = [];
        const index = store.index('status');
        const request = index.openCursor('pending');
        request.onsuccess = function (event) {
            const cursor = event.target.result;
            if (cursor) {
                if (!tag || cursor.value.sync_tag === tag) {
                    queue.push(cursor.value);
                }
                cursor.continue();
            } else {
                resolve(queue);
            }
        };
        request.onerror = function () {
            reject(request.error || new Error('Queue read failed'));
        };
    });

    for (const item of items) {
        try {
            const response = await fetch(item.url, {
                method: item.method,
                headers: item.headers,
                body: item.body
            });

            if (response.status >= 200 && response.status < 300) {
                store.delete(item.id);
            } else if (response.status >= 400 && response.status < 500) {
                store.put({ ...item, status: 'failed' });
            } else {
                const retry = (item.retry_count || 0) + 1;
                store.put({ ...item, retry_count: retry, status: retry >= item.max_retries ? 'failed' : 'pending' });
            }
        } catch (_error) {
            const retry = (item.retry_count || 0) + 1;
            store.put({ ...item, retry_count: retry, status: retry >= item.max_retries ? 'failed' : 'pending' });
        }
    }

    notifyClients('SYNC_COMPLETE');
}

function notifyClients(type) {
    self.clients.matchAll({ includeUncontrolled: true, type: 'window' }).then((clients) => {
        clients.forEach((client) => client.postMessage({ type }));
    });
}

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = self.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

function openDb() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('RetailMindOfflineDB', 1);
        request.onupgradeneeded = function (event) {
            const db = event.target.result;
            if (!db.objectStoreNames.contains('offline_queue')) {
                const store = db.createObjectStore('offline_queue', { keyPath: 'id', autoIncrement: true });
                store.createIndex('status', 'status', { unique: false });
                store.createIndex('timestamp', 'timestamp', { unique: false });
            }
        };
        request.onsuccess = function (event) {
            resolve(event.target.result);
        };
        request.onerror = function () {
            reject(request.error || new Error('IndexedDB open failed'));
        };
    });
}
