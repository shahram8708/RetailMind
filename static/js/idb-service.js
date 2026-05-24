(function () {
    const DB_NAME = 'RetailMindOfflineDB';
    const DB_VERSION = 1;

    const TTL = {
        inventory: 15 * 60 * 1000,
        analytics: 60 * 60 * 1000,
        notifications: 5 * 60 * 1000
    };

    const memoryStore = {
        offline_queue: [],
        cached_inventory: {},
        cached_campaigns: {},
        cached_notifications: {},
        cached_analytics: {},
        cached_agent_actions: {},
        pending_approvals: {},
        offline_user_session: {}
    };

    function supportsIdb() {
        return typeof indexedDB !== 'undefined';
    }

    function openDb() {
        if (!supportsIdb()) {
            return Promise.resolve(null);
        }

        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onupgradeneeded = function (event) {
                const db = event.target.result;

                if (!db.objectStoreNames.contains('offline_queue')) {
                    const store = db.createObjectStore('offline_queue', { keyPath: 'id', autoIncrement: true });
                    store.createIndex('status', 'status', { unique: false });
                    store.createIndex('timestamp', 'timestamp', { unique: false });
                }

                if (!db.objectStoreNames.contains('cached_inventory')) {
                    const store = db.createObjectStore('cached_inventory', { keyPath: 'sku_id' });
                    store.createIndex('property_id', 'property_id', { unique: false });
                    store.createIndex('srs_score', 'srs_score', { unique: false });
                }

                if (!db.objectStoreNames.contains('cached_campaigns')) {
                    const store = db.createObjectStore('cached_campaigns', { keyPath: 'campaign_id' });
                    store.createIndex('status', 'status', { unique: false });
                    store.createIndex('property_id', 'property_id', { unique: false });
                }

                if (!db.objectStoreNames.contains('cached_notifications')) {
                    const store = db.createObjectStore('cached_notifications', { keyPath: 'id' });
                    store.createIndex('is_read', 'is_read', { unique: false });
                    store.createIndex('created_at', 'created_at', { unique: false });
                }

                if (!db.objectStoreNames.contains('cached_analytics')) {
                    const store = db.createObjectStore('cached_analytics', { keyPath: 'range_key' });
                    store.createIndex('last_updated', 'last_updated', { unique: false });
                }

                if (!db.objectStoreNames.contains('cached_agent_actions')) {
                    const store = db.createObjectStore('cached_agent_actions', { keyPath: 'id' });
                    store.createIndex('status', 'status', { unique: false });
                    store.createIndex('mission_type', 'mission_type', { unique: false });
                }

                if (!db.objectStoreNames.contains('pending_approvals')) {
                    const store = db.createObjectStore('pending_approvals', { keyPath: 'id', autoIncrement: true });
                    store.createIndex('synced', 'synced', { unique: false });
                }

                if (!db.objectStoreNames.contains('offline_user_session')) {
                    db.createObjectStore('offline_user_session', { keyPath: 'key' });
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

    const dbPromise = openDb();

    function withStore(storeName, mode, callback) {
        if (!supportsIdb()) {
            return Promise.resolve(callback(null));
        }

        return dbPromise.then((db) => {
            return new Promise((resolve, reject) => {
                const tx = db.transaction(storeName, mode);
                const store = tx.objectStore(storeName);
                let result;

                tx.oncomplete = function () {
                    resolve(result);
                };
                tx.onerror = function () {
                    reject(tx.error || new Error('IndexedDB transaction failed'));
                };

                result = callback(store);
            });
        });
    }

    function now() {
        return Date.now();
    }

    async function queueRequest(request) {
        const record = {
            url: request.url,
            method: request.method || 'POST',
            headers: request.headers || {},
            body: request.body || null,
            timestamp: now(),
            retry_count: 0,
            max_retries: request.max_retries || 5,
            sync_tag: request.sync_tag || 'sync-pending-actions',
            status: 'pending'
        };

        if (!supportsIdb()) {
            record.id = memoryStore.offline_queue.length + 1;
            memoryStore.offline_queue.push(record);
            return record;
        }

        return withStore('offline_queue', 'readwrite', (store) => store.add(record));
    }

    async function getQueuedRequests(status) {
        if (!supportsIdb()) {
            if (!status) {
                return memoryStore.offline_queue.slice();
            }
            return memoryStore.offline_queue.filter((item) => item.status === status);
        }

        return withStore('offline_queue', 'readonly', (store) => {
            return new Promise((resolve, reject) => {
                const items = [];
                const request = status ? store.index('status').openCursor(status) : store.openCursor();
                request.onsuccess = function (event) {
                    const cursor = event.target.result;
                    if (cursor) {
                        items.push(cursor.value);
                        cursor.continue();
                    } else {
                        resolve(items);
                    }
                };
                request.onerror = function () {
                    reject(request.error || new Error('Queue cursor failed'));
                };
            });
        });
    }

    async function updateQueueItem(id, updates) {
        if (!supportsIdb()) {
            const idx = memoryStore.offline_queue.findIndex((item) => item.id === id);
            if (idx >= 0) {
                memoryStore.offline_queue[idx] = { ...memoryStore.offline_queue[idx], ...updates };
            }
            return true;
        }

        return withStore('offline_queue', 'readwrite', (store) => {
            return new Promise((resolve, reject) => {
                const getReq = store.get(id);
                getReq.onsuccess = function () {
                    const record = getReq.result;
                    if (!record) {
                        resolve(false);
                        return;
                    }
                    const updated = { ...record, ...updates };
                    const putReq = store.put(updated);
                    putReq.onsuccess = () => resolve(true);
                    putReq.onerror = () => reject(putReq.error || new Error('Queue update failed'));
                };
                getReq.onerror = function () {
                    reject(getReq.error || new Error('Queue get failed'));
                };
            });
        });
    }

    async function removeQueueItem(id) {
        if (!supportsIdb()) {
            memoryStore.offline_queue = memoryStore.offline_queue.filter((item) => item.id !== id);
            return true;
        }

        return withStore('offline_queue', 'readwrite', (store) => store.delete(id));
    }

    async function putInventoryItems(items, propertyId) {
        if (!Array.isArray(items)) {
            return;
        }

        const stamp = now();
        if (!supportsIdb()) {
            items.forEach((item) => {
                memoryStore.cached_inventory[item.sku_id] = { ...item, property_id: propertyId, last_updated: stamp };
            });
            return;
        }

        return withStore('cached_inventory', 'readwrite', (store) => {
            items.forEach((item) => {
                store.put({ ...item, property_id: propertyId, last_updated: stamp });
            });
        });
    }

    async function getInventoryItems(propertyId) {
        const stamp = now();
        if (!supportsIdb()) {
            const items = Object.values(memoryStore.cached_inventory).filter((item) => {
                return propertyId ? item.property_id === propertyId : true;
            });
            const stale = items.some((item) => stamp - (item.last_updated || 0) > TTL.inventory);
            return { items, stale };
        }

        return withStore('cached_inventory', 'readonly', (store) => {
            return new Promise((resolve, reject) => {
                const items = [];
                const source = propertyId ? store.index('property_id') : store;
                const request = propertyId ? source.openCursor(propertyId) : source.openCursor();
                request.onsuccess = function (event) {
                    const cursor = event.target.result;
                    if (cursor) {
                        items.push(cursor.value);
                        cursor.continue();
                    } else {
                        const stale = items.some((item) => stamp - (item.last_updated || 0) > TTL.inventory);
                        resolve({ items, stale });
                    }
                };
                request.onerror = function () {
                    reject(request.error || new Error('Inventory cursor failed'));
                };
            });
        });
    }

    async function putCampaigns(items, propertyId) {
        if (!Array.isArray(items)) {
            return;
        }

        const stamp = now();
        if (!supportsIdb()) {
            items.forEach((item) => {
                memoryStore.cached_campaigns[item.campaign_id || item.id] = { ...item, property_id: propertyId, last_updated: stamp };
            });
            return;
        }

        return withStore('cached_campaigns', 'readwrite', (store) => {
            items.forEach((item) => {
                const key = item.campaign_id || item.id;
                if (!key) {
                    return;
                }
                store.put({ ...item, campaign_id: key, property_id: propertyId, last_updated: stamp });
            });
        });
    }

    async function getCampaigns(propertyId) {
        const stamp = now();
        if (!supportsIdb()) {
            const items = Object.values(memoryStore.cached_campaigns).filter((item) => {
                return propertyId ? item.property_id === propertyId : true;
            });
            const stale = items.some((item) => stamp - (item.last_updated || 0) > TTL.inventory);
            return { items, stale };
        }

        return withStore('cached_campaigns', 'readonly', (store) => {
            return new Promise((resolve, reject) => {
                const items = [];
                const source = propertyId ? store.index('property_id') : store;
                const request = propertyId ? source.openCursor(propertyId) : source.openCursor();
                request.onsuccess = function (event) {
                    const cursor = event.target.result;
                    if (cursor) {
                        items.push(cursor.value);
                        cursor.continue();
                    } else {
                        const stale = items.some((item) => stamp - (item.last_updated || 0) > TTL.inventory);
                        resolve({ items, stale });
                    }
                };
                request.onerror = function () {
                    reject(request.error || new Error('Campaign cursor failed'));
                };
            });
        });
    }

    async function putNotifications(items) {
        if (!Array.isArray(items)) {
            return;
        }

        const stamp = now();
        if (!supportsIdb()) {
            items.forEach((item) => {
                memoryStore.cached_notifications[item.id] = { ...item, last_updated: stamp };
            });
            return;
        }

        return withStore('cached_notifications', 'readwrite', (store) => {
            items.forEach((item) => {
                store.put({ ...item, last_updated: stamp });
            });
        });
    }

    async function getNotifications() {
        const stamp = now();
        if (!supportsIdb()) {
            const items = Object.values(memoryStore.cached_notifications);
            const sorted = items.sort((a, b) => (b.created_at || 0) - (a.created_at || 0)).slice(0, 50);
            const stale = sorted.some((item) => stamp - (item.last_updated || 0) > TTL.notifications);
            return { items: sorted, stale };
        }

        return withStore('cached_notifications', 'readonly', (store) => {
            return new Promise((resolve, reject) => {
                const items = [];
                const request = store.openCursor();
                request.onsuccess = function (event) {
                    const cursor = event.target.result;
                    if (cursor) {
                        items.push(cursor.value);
                        cursor.continue();
                    } else {
                        items.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
                        const trimmed = items.slice(0, 50);
                        const stale = trimmed.some((item) => stamp - (item.last_updated || 0) > TTL.notifications);
                        resolve({ items: trimmed, stale });
                    }
                };
                request.onerror = function () {
                    reject(request.error || new Error('Notifications cursor failed'));
                };
            });
        });
    }

    async function putAnalytics(rangeKey, payload) {
        if (!rangeKey || !payload) {
            return;
        }

        const record = {
            range_key: rangeKey,
            chart_data: payload.chart_data || payload.chartData || payload,
            roi_data: payload.roi_data || payload.roiData || {},
            last_updated: now()
        };

        if (!supportsIdb()) {
            memoryStore.cached_analytics[rangeKey] = record;
            return;
        }

        return withStore('cached_analytics', 'readwrite', (store) => store.put(record));
    }

    async function getAnalytics(rangeKey) {
        if (!rangeKey) {
            return null;
        }

        if (!supportsIdb()) {
            const record = memoryStore.cached_analytics[rangeKey];
            if (!record) {
                return null;
            }
            const stale = now() - (record.last_updated || 0) > TTL.analytics;
            return { ...record, stale };
        }

        return withStore('cached_analytics', 'readonly', (store) => {
            return new Promise((resolve, reject) => {
                const request = store.get(rangeKey);
                request.onsuccess = function () {
                    const record = request.result;
                    if (!record) {
                        resolve(null);
                        return;
                    }
                    const stale = now() - (record.last_updated || 0) > TTL.analytics;
                    resolve({ ...record, stale });
                };
                request.onerror = function () {
                    reject(request.error || new Error('Analytics get failed'));
                };
            });
        });
    }

    async function putAgentActions(items) {
        if (!Array.isArray(items)) {
            return;
        }

        const stamp = now();
        if (!supportsIdb()) {
            items.forEach((item) => {
                memoryStore.cached_agent_actions[item.id] = { ...item, last_updated: stamp };
            });
            return;
        }

        return withStore('cached_agent_actions', 'readwrite', (store) => {
            items.forEach((item) => {
                store.put({ ...item, last_updated: stamp });
            });
        });
    }

    async function getAgentActions() {
        if (!supportsIdb()) {
            return Object.values(memoryStore.cached_agent_actions).slice(0, 100);
        }

        return withStore('cached_agent_actions', 'readonly', (store) => {
            return new Promise((resolve, reject) => {
                const items = [];
                const request = store.openCursor();
                request.onsuccess = function (event) {
                    const cursor = event.target.result;
                    if (cursor) {
                        items.push(cursor.value);
                        cursor.continue();
                    } else {
                        items.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
                        resolve(items.slice(0, 100));
                    }
                };
                request.onerror = function () {
                    reject(request.error || new Error('Agent actions cursor failed'));
                };
            });
        });
    }

    async function addPendingApproval(actionId, decision) {
        const record = {
            action_id: actionId,
            decision: decision,
            timestamp: now(),
            synced: false
        };

        if (!supportsIdb()) {
            const id = Object.keys(memoryStore.pending_approvals).length + 1;
            memoryStore.pending_approvals[id] = { ...record, id };
            return id;
        }

        return withStore('pending_approvals', 'readwrite', (store) => store.add(record));
    }

    async function getPendingApprovals() {
        if (!supportsIdb()) {
            return Object.values(memoryStore.pending_approvals).filter((item) => !item.synced);
        }

        return withStore('pending_approvals', 'readonly', (store) => {
            return new Promise((resolve, reject) => {
                const items = [];
                const request = store.index('synced').openCursor(false);
                request.onsuccess = function (event) {
                    const cursor = event.target.result;
                    if (cursor) {
                        items.push(cursor.value);
                        cursor.continue();
                    } else {
                        resolve(items);
                    }
                };
                request.onerror = function () {
                    reject(request.error || new Error('Pending approvals cursor failed'));
                };
            });
        });
    }

    async function setOfflineUserSession(data) {
        const record = {
            key: 'current_session',
            ...data,
            last_login: data.last_login || now()
        };

        if (!supportsIdb()) {
            memoryStore.offline_user_session.current_session = record;
            return;
        }

        return withStore('offline_user_session', 'readwrite', (store) => store.put(record));
    }

    async function clearAll() {
        if (!supportsIdb()) {
            Object.keys(memoryStore).forEach((key) => {
                if (Array.isArray(memoryStore[key])) {
                    memoryStore[key] = [];
                } else {
                    memoryStore[key] = {};
                }
            });
            return;
        }

        const db = await dbPromise;
        if (!db) {
            return;
        }

        const stores = Array.from(db.objectStoreNames);
        await Promise.all(
            stores.map((storeName) => withStore(storeName, 'readwrite', (store) => store.clear()))
        );
    }

    window.RetailMindIDB = {
        queueRequest,
        getQueuedRequests,
        updateQueueItem,
        removeQueueItem,
        putInventoryItems,
        getInventoryItems,
        putCampaigns,
        getCampaigns,
        putNotifications,
        getNotifications,
        putAnalytics,
        getAnalytics,
        putAgentActions,
        getAgentActions,
        addPendingApproval,
        getPendingApprovals,
        setOfflineUserSession,
        clearAll
    };
})();
