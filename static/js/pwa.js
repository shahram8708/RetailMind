(function () {
    const idb = window.RetailMindIDB || null;
    const state = {
        online: navigator.onLine,
        deferredInstall: null,
        swRegistration: null,
        vapidPublicKey: null,
        pwaConfig: null
    };

    const elements = {
        updateBanner: document.getElementById('pwa-update-banner'),
        updateNow: document.getElementById('pwa-update-now'),
        updateDismiss: document.getElementById('pwa-update-dismiss'),
        connectionBar: document.getElementById('pwa-connection-bar'),
        connectionText: document.getElementById('pwa-connection-text'),
        connectionSpinner: document.getElementById('pwa-connection-spinner'),
        installPrompt: document.getElementById('pwa-install-prompt'),
        installNow: document.getElementById('pwa-install-now'),
        installDismiss: document.getElementById('pwa-install-dismiss'),
        iosGuide: document.getElementById('pwa-ios-guide'),
        iosDismiss: document.getElementById('pwa-ios-dismiss'),
        firefoxTip: document.getElementById('pwa-firefox-tip'),
        firefoxDismiss: document.getElementById('pwa-firefox-dismiss'),
        pushBanner: document.getElementById('pwa-push-banner'),
        pushEnable: document.getElementById('pwa-push-enable'),
        pushDismiss: document.getElementById('pwa-push-dismiss'),
        pullIndicator: document.getElementById('pwa-pull-indicator')
    };

    function isStandalone() {
        return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    }

    function isIos() {
        return /iphone|ipad|ipod/i.test(navigator.userAgent);
    }

    function isFirefox() {
        return /firefox/i.test(navigator.userAgent);
    }

    function hasServiceWorkerSupport() {
        return 'serviceWorker' in navigator;
    }

    function hasPushSupport() {
        return 'PushManager' in window && 'Notification' in window;
    }

    function showElement(el) {
        if (el) {
            el.hidden = false;
        }
    }

    function hideElement(el) {
        if (el) {
            el.hidden = true;
        }
    }

    function setConnectionBar(text, mode, showSpinner) {
        if (!elements.connectionBar) {
            return;
        }

        elements.connectionText.textContent = text;
        elements.connectionBar.setAttribute('data-mode', mode || 'info');
        if (elements.connectionSpinner) {
            elements.connectionSpinner.hidden = !showSpinner;
        }
        showElement(elements.connectionBar);
    }

    function hideConnectionBar(delayMs) {
        if (!elements.connectionBar) {
            return;
        }
        window.setTimeout(() => hideElement(elements.connectionBar), delayMs || 0);
    }

    function registerServiceWorker() {
        if (!hasServiceWorkerSupport()) {
            return;
        }

        const isLocalhost = location.hostname === 'localhost' || location.hostname === '127.0.0.1';
        if (location.protocol !== 'https:' && !isLocalhost) {
            return;
        }

        navigator.serviceWorker.register('/sw.js', { scope: '/' }).then((registration) => {
            state.swRegistration = registration;

            if (registration.waiting) {
                showUpdateBanner(registration);
            }

            registration.addEventListener('updatefound', () => {
                const newWorker = registration.installing;
                if (!newWorker) {
                    return;
                }
                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        showUpdateBanner(registration);
                    }
                });
            });
        }).catch(() => {
            // Service worker registration failed.
        });

        navigator.serviceWorker.addEventListener('message', (event) => {
            const data = event.data || {};
            if (data.type === 'SYNC_COMPLETE') {
                setConnectionBar('All changes synchronized successfully.', 'online', false);
                hideConnectionBar(5000);
            }
            if (data.type === 'SYNC_FAILED') {
                setConnectionBar('Some changes failed to sync. Will retry.', 'offline', false);
            }
        });

        navigator.serviceWorker.addEventListener('controllerchange', () => {
            window.location.reload();
        });
    }

    function showUpdateBanner(registration) {
        if (!elements.updateBanner) {
            return;
        }

        const dismissed = sessionStorage.getItem('pwa_update_dismissed') === '1';
        if (dismissed) {
            return;
        }

        showElement(elements.updateBanner);
        if (elements.updateNow) {
            elements.updateNow.onclick = function () {
                if (registration.waiting) {
                    registration.waiting.postMessage({ type: 'SKIP_WAITING' });
                }
            };
        }
        if (elements.updateDismiss) {
            elements.updateDismiss.onclick = function () {
                sessionStorage.setItem('pwa_update_dismissed', '1');
                hideElement(elements.updateBanner);
            };
        }
    }

    function setupInstallPrompt() {
        window.addEventListener('beforeinstallprompt', (event) => {
            event.preventDefault();
            state.deferredInstall = event;
            maybeShowInstallPrompt();
        });

        if (elements.installNow) {
            elements.installNow.addEventListener('click', async () => {
                if (!state.deferredInstall) {
                    return;
                }
                state.deferredInstall.prompt();
                const choice = await state.deferredInstall.userChoice;
                if (choice && choice.outcome === 'accepted') {
                    if (typeof showToast === 'function') {
                        showToast('RetailMind has been installed.', 'success');
                    }
                }
                state.deferredInstall = null;
                hideElement(elements.installPrompt);
            });
        }

        if (elements.installDismiss) {
            elements.installDismiss.addEventListener('click', () => {
                const dismissUntil = Date.now() + (7 * 24 * 60 * 60 * 1000);
                localStorage.setItem('pwa_install_dismissed_until', String(dismissUntil));
                hideElement(elements.installPrompt);
            });
        }

        if (elements.iosDismiss) {
            elements.iosDismiss.addEventListener('click', () => hideElement(elements.iosGuide));
        }

        if (elements.firefoxDismiss) {
            elements.firefoxDismiss.addEventListener('click', () => hideElement(elements.firefoxTip));
        }

        window.addEventListener('appinstalled', () => {
            hideElement(elements.installPrompt);
        });

        maybeShowInstallPrompt();
    }

    function maybeShowInstallPrompt() {
        if (isStandalone()) {
            return;
        }

        const dismissUntil = Number(localStorage.getItem('pwa_install_dismissed_until') || 0);
        if (dismissUntil && Date.now() < dismissUntil) {
            return;
        }

        const pageViews = Number(sessionStorage.getItem('pwa_page_views') || 0) + 1;
        sessionStorage.setItem('pwa_page_views', String(pageViews));

        const showAfterDelay = () => {
            if (elements.installPrompt && state.deferredInstall) {
                showElement(elements.installPrompt);
            }
            if (isIos() && elements.iosGuide && !state.deferredInstall) {
                showElement(elements.iosGuide);
            }
            if (isFirefox() && elements.firefoxTip) {
                showElement(elements.firefoxTip);
            }
        };

        if (pageViews >= 3) {
            showAfterDelay();
        } else {
            window.setTimeout(showAfterDelay, 30000);
        }
    }

    async function fetchPwaConfig() {
        try {
            const response = await fetch('/api/pwa/config');
            if (!response.ok) {
                return null;
            }
            const data = await response.json();
            state.pwaConfig = data;
            state.vapidPublicKey = data.push_vapid_public_key || null;
            return data;
        } catch (_error) {
            return null;
        }
    }

    function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    async function setupPushNotifications() {
        if (!hasPushSupport() || !hasServiceWorkerSupport()) {
            return;
        }

        const config = state.pwaConfig || await fetchPwaConfig();
        if (!config || !config.features || !config.features.push_notifications) {
            return;
        }

        const hidePrompt = localStorage.getItem('push_prompt_dismissed') === '1';
        if (hidePrompt) {
            return;
        }

        if (!elements.pushBanner) {
            return;
        }

        if (Notification.permission === 'granted') {
            localStorage.setItem('push_subscribed', 'true');
            return;
        }

        const isDashboard = window.location.pathname.startsWith('/dashboard');
        if (!isDashboard) {
            return;
        }

        showElement(elements.pushBanner);

        if (elements.pushEnable) {
            elements.pushEnable.onclick = async function () {
                const permission = await Notification.requestPermission();
                if (permission !== 'granted') {
                    return;
                }

                const registration = await navigator.serviceWorker.ready;
                const key = state.vapidPublicKey;
                if (!key) {
                    return;
                }

                const subscription = await registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(key)
                });

                await fetch('/push/subscribe', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': typeof getCsrfToken === 'function' ? getCsrfToken() : ''
                    },
                    body: JSON.stringify(subscription)
                });

                localStorage.setItem('push_subscribed', 'true');
                hideElement(elements.pushBanner);
            };
        }

        if (elements.pushDismiss) {
            elements.pushDismiss.onclick = function () {
                localStorage.setItem('push_prompt_dismissed', '1');
                hideElement(elements.pushBanner);
            };
        }
    }

    function setupNetworkProbe() {
        const probe = async () => {
            const controller = new AbortController();
            const timeout = window.setTimeout(() => controller.abort(), 3000);
            try {
                const response = await fetch('/api/health-check', {
                    method: 'HEAD',
                    cache: 'no-store',
                    signal: controller.signal
                });
                state.online = response.ok;
            } catch (_error) {
                state.online = false;
            } finally {
                window.clearTimeout(timeout);
                updateConnectionState();
            }
        };

        probe();
        window.setInterval(probe, 30000);
    }

    function updateConnectionState() {
        if (state.online) {
            setConnectionBar('Connection restored. Syncing your changes...', 'online', true);
            triggerSync();
        } else {
            setConnectionBar('You are offline. RetailMind is working from cached data. Changes will sync when you reconnect.', 'offline', false);
        }
    }

    async function triggerSync() {
        if (state.swRegistration && 'sync' in state.swRegistration) {
            try {
                await state.swRegistration.sync.register('sync-pending-actions');
            } catch (_error) {
                await manualSync();
            }
        } else {
            await manualSync();
        }
    }

    async function manualSync() {
        if (!idb) {
            setConnectionBar('No offline storage available.', 'offline', false);
            return;
        }

        const items = await idb.getQueuedRequests('pending');
        if (!items.length) {
            setConnectionBar('All changes synchronized successfully.', 'online', false);
            hideConnectionBar(5000);
            return;
        }

        for (const item of items) {
            try {
                await idb.updateQueueItem(item.id, { status: 'syncing' });

                const response = await fetch(item.url, {
                    method: item.method,
                    headers: item.headers,
                    body: item.body
                });

                if (response.status >= 200 && response.status < 300) {
                    await idb.removeQueueItem(item.id);
                } else if (response.status >= 400 && response.status < 500) {
                    await idb.updateQueueItem(item.id, { status: 'failed' });
                } else {
                    const retry = (item.retry_count || 0) + 1;
                    await idb.updateQueueItem(item.id, { retry_count: retry, status: 'pending' });
                }
            } catch (_error) {
                const retry = (item.retry_count || 0) + 1;
                await idb.updateQueueItem(item.id, { retry_count: retry, status: 'pending' });
            }
        }

        setConnectionBar('All changes synchronized successfully.', 'online', false);
        hideConnectionBar(5000);
    }

    async function registerSyncTag(tag) {
        if (!state.swRegistration) {
            return;
        }
        if ('sync' in state.swRegistration) {
            try {
                await state.swRegistration.sync.register(tag);
            } catch (_error) {
                // Ignore if sync is not available.
            }
        }
    }

    function setupOfflineQueueBridge() {
        if (!window.RetailMindOffline) {
            window.RetailMindOffline = {};
        }

        window.RetailMindOffline.queueRequest = async function (request) {
            if (!idb) {
                return null;
            }
            const record = await idb.queueRequest(request);
            await registerSyncTag(request.sync_tag || 'sync-pending-actions');
            if (typeof showToast === 'function') {
                showToast('Changes saved offline. They will sync automatically.', 'info');
            }
            return record;
        };
    }

    function setupLogoutClear() {
        document.querySelectorAll('form[action*="/auth/logout"]').forEach((form) => {
            form.addEventListener('submit', async function () {
                if (idb) {
                    await idb.clearAll();
                }
                if (state.swRegistration) {
                    state.swRegistration.active.postMessage({ type: 'CLEAR_CACHES' });
                }
            });
        });
    }

    function cacheCurrentPage() {
        if (!idb) {
            return;
        }

        const path = window.location.pathname;
        const propertyId = Number(document.body.dataset.propertyId || 0) || null;

        if (path.startsWith('/dashboard')) {
            const kpi = {
                active_missions: Number(document.getElementById('kpi-active-missions')?.textContent || 0),
                inventory_alerts_today: Number(document.getElementById('kpi-inventory-alerts')?.textContent || 0),
                campaigns_this_week: Number(document.getElementById('kpi-campaigns-week')?.textContent || 0),
                open_work_orders: Number(document.getElementById('kpi-work-orders')?.textContent || 0)
            };
            idb.setOfflineUserSession({
                user_id: document.body.dataset.userId || null,
                user_name: document.body.dataset.userName || null,
                user_role: document.body.dataset.userRole || null,
                property_id: propertyId,
                property_name: document.body.dataset.propertyName || null,
                kpi_snapshot: kpi
            });

            const notifications = Array.from(document.querySelectorAll('.alert-feed-row')).map((row) => {
                return {
                    id: Number(row.getAttribute('data-notif-id') || 0),
                    title: row.querySelector('.fw-semibold')?.textContent || 'Alert',
                    message: row.querySelector('.text-muted.small')?.textContent || '',
                    is_read: row.getAttribute('data-is-read') === 'true',
                    created_at: Date.now()
                };
            });
            if (notifications.length) {
                idb.putNotifications(notifications);
            }
        }

        if (path.startsWith('/inventory')) {
            const rows = document.querySelectorAll('tr.sku-row');
            const items = Array.from(rows).map((row) => {
                const skuId = row.querySelector('td')?.textContent?.trim();
                const scoreText = row.querySelector('.srs-badge')?.textContent || '0';
                const score = Number(scoreText.replace('%', '')) / 100;
                return {
                    sku_id: skuId,
                    product_name: row.querySelector('.fw-semibold')?.textContent || '',
                    brand: row.querySelector('.text-muted.small')?.textContent || '',
                    srs_score: score,
                    property_id: propertyId
                };
            });
            if (items.length) {
                idb.putInventoryItems(items, propertyId);
            }
        }

        if (path.startsWith('/campaigns')) {
            const cards = document.querySelectorAll('.opportunity-card');
            const items = Array.from(cards).map((card) => {
                const id = Number(card.getAttribute('data-campaign-id') || 0);
                return {
                    campaign_id: id,
                    campaign_name: card.querySelector('.campaign-title')?.textContent || 'Campaign',
                    status: 'opportunity',
                    property_id: propertyId
                };
            });
            if (items.length) {
                idb.putCampaigns(items, propertyId);
            }
        }

        if (path.startsWith('/analytics') && typeof chartData !== 'undefined') {
            const range = new URL(window.location.href).searchParams.get('range') || '30d';
            idb.putAnalytics(range, { chart_data: chartData, roi_data: roiData || {} });
        }
    }

    async function hydrateOffline() {
        if (state.online || !idb) {
            return;
        }

        const path = window.location.pathname;
        const propertyId = Number(document.body.dataset.propertyId || 0) || null;

        if (path.startsWith('/inventory')) {
            const result = await idb.getInventoryItems(propertyId);
            const tableBody = document.querySelector('table tbody');
            if (result && result.items.length && tableBody) {
                tableBody.innerHTML = '';
                result.items.forEach((item) => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td><span class="monospace-small">${item.sku_id || ''}</span></td>
                        <td><div class="fw-semibold">${item.product_name || ''}</div><div class="small text-muted">${item.brand || ''}</div></td>
                        <td><span class="badge bg-light text-dark border">Offline</span></td>
                        <td><span class="srs-badge">${Math.round((item.srs_score || 0) * 100)}%</span></td>
                        <td class="text-muted">Cached</td>
                        <td class="text-muted">--</td>
                    `;
                    tableBody.appendChild(row);
                });
            }
        }

        if (path.startsWith('/campaigns')) {
            const result = await idb.getCampaigns(propertyId);
            if (result && result.items.length) {
                const holder = document.querySelector('.campaigns-page');
                if (holder) {
                    const note = document.createElement('div');
                    note.className = 'alert alert-warning mb-3';
                    note.textContent = 'Showing cached campaign data while offline.';
                    holder.prepend(note);
                }
            }
        }

        if (path.startsWith('/analytics')) {
            const range = new URL(window.location.href).searchParams.get('range') || '30d';
            const record = await idb.getAnalytics(range);
            if (record && typeof renderAllCharts === 'function') {
                await renderAllCharts(record.chart_data || {});
                if (record.roi_data && typeof updateRoiCards === 'function') {
                    updateRoiCards(record.roi_data);
                }
                const badge = document.createElement('div');
                badge.className = 'alert alert-warning';
                badge.textContent = 'Showing cached analytics data.';
                document.querySelector('.analytics-page')?.prepend(badge);
            }
        }

        if (path.startsWith('/shopper')) {
            const hero = document.querySelector('.shopper-hero');
            if (hero) {
                const banner = document.createElement('div');
                banner.className = 'alert alert-warning mt-3';
                banner.textContent = 'AI product search requires an internet connection. Cached promotions are shown below.';
                hero.appendChild(banner);
            }
        }
    }

    function setupPullToRefresh() {
        if (!elements.pullIndicator) {
            return;
        }

        const paths = ['/dashboard', '/inventory'];
        if (!paths.some((path) => window.location.pathname.startsWith(path))) {
            return;
        }

        let startY = null;
        let pulling = false;

        window.addEventListener('touchstart', (event) => {
            if (window.scrollY === 0) {
                startY = event.touches[0].clientY;
            }
        });

        window.addEventListener('touchmove', (event) => {
            if (startY === null) {
                return;
            }
            const currentY = event.touches[0].clientY;
            if (currentY - startY > 70 && !pulling) {
                pulling = true;
                showElement(elements.pullIndicator);
            }
        });

        window.addEventListener('touchend', () => {
            if (pulling) {
                window.location.reload();
            }
            startY = null;
            pulling = false;
            hideElement(elements.pullIndicator);
        });
    }

    async function init() {
        await fetchPwaConfig();
        registerServiceWorker();
        setupInstallPrompt();
        setupNetworkProbe();
        setupOfflineQueueBridge();
        setupPushNotifications();
        setupLogoutClear();
        setupPullToRefresh();
        cacheCurrentPage();
        hydrateOffline();

        if (state.swRegistration && state.vapidPublicKey) {
            state.swRegistration.active?.postMessage({
                type: 'PWA_CONFIG',
                vapidPublicKey: state.vapidPublicKey
            });
        }
    }

    document.addEventListener('DOMContentLoaded', init);
})();
