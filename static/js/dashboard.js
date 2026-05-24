(function () {
    const API_ENDPOINTS = {
        agentStatus: '/api/agent/status',
        kpiSummary: '/api/kpi/summary',
        footTrafficCurrent: '/api/foot-traffic/current'
    };

    const POLLING_INTERVALS = {
        agentStatus: 30000,
        kpi: 30000,
        heatmap: 60000
    };

    const HEATMAP_COLORS = {
        veryLow: '#DBEAFE',
        low: '#93C5FD',
        medium: '#FDE68A',
        high: '#FB923C',
        veryHigh: '#DC2626'
    };

    const pollingHandles = [];
    let previousMissionStatuses = null;
    let todayTrafficChart = null;

    function toHourLabel(hour) {
        const suffix = hour < 12 ? 'AM' : 'PM';
        const normalized = hour % 12;
        const display = normalized === 0 ? 12 : normalized;
        return `${display}${suffix}`;
    }

    function getHeatmapColor(count, maxValue) {
        const safeMax = maxValue > 0 ? maxValue : 1;
        const ratio = count / safeMax;

        if (ratio <= 0.2) {
            return HEATMAP_COLORS.veryLow;
        }
        if (ratio <= 0.4) {
            return HEATMAP_COLORS.low;
        }
        if (ratio <= 0.6) {
            return HEATMAP_COLORS.medium;
        }
        if (ratio <= 0.8) {
            return HEATMAP_COLORS.high;
        }
        return HEATMAP_COLORS.veryHigh;
    }

    async function fetchJson(url) {
        const response = await fetch(url);
        const data = await response.json();
        return { response, data };
    }

    function updateMissionCard(mission, missionData) {
        const card = document.querySelector(`.mission-card[data-mission="${mission}"]`);
        if (!card) {
            return;
        }

        const statusBadge = card.querySelector('.mission-status-badge');
        const statusDot = card.querySelector('.status-dot');
        const statusText = card.querySelector('.status-text');
        const lastAction = card.querySelector('.mission-last-action');
        const description = card.querySelector('.mission-last-description');

        if (statusBadge) {
            statusBadge.classList.remove('running', 'paused', 'error');
            statusBadge.classList.add(missionData.status);
        }

        if (statusDot) {
            statusDot.classList.remove('running', 'paused', 'error');
            statusDot.classList.add(missionData.status);
            statusDot.style.transition = 'background-color 0.4s ease';
        }

        if (statusText) {
            const statusLabel = missionData.status.charAt(0).toUpperCase() + missionData.status.slice(1);
            statusText.textContent = statusLabel;
        }

        if (lastAction) {
            lastAction.textContent = `Last action: ${missionData.last_action}`;
        }

        if (description) {
            description.textContent = missionData.last_action_description || 'No recent activity';
        }
    }

    async function fetchAgentStatus() {
        const missionCards = document.querySelectorAll('.mission-card[data-mission]');
        if (!missionCards.length) {
            return;
        }

        try {
            const { response, data } = await fetchJson(API_ENDPOINTS.agentStatus);
            if (!response.ok || !data.success || !data.data) {
                return;
            }

            const nextStatuses = {};
            ['inventory', 'campaign', 'facility', 'shopper'].forEach((mission) => {
                if (data.data[mission]) {
                    updateMissionCard(mission, data.data[mission]);
                    nextStatuses[mission] = data.data[mission].status;
                }
            });

            if (previousMissionStatuses) {
                const changed = Object.keys(nextStatuses).some((mission) => previousMissionStatuses[mission] !== nextStatuses[mission]);
                if (changed && typeof showToast === 'function') {
                    showToast('Agent status updated', 'info');
                }
            }

            previousMissionStatuses = nextStatuses;
        } catch (_error) {
            // Silent fail to keep dashboard resilient.
        }
    }

    async function fetchKPIs() {
        const activeMissionsEl = document.getElementById('kpi-active-missions');
        if (!activeMissionsEl) {
            return;
        }

        try {
            const { response, data } = await fetchJson(API_ENDPOINTS.kpiSummary);
            if (!response.ok || !data.success || !data.data) {
                return;
            }

            const summary = data.data;

            const activeEl = document.getElementById('kpi-active-missions');
            const inventoryEl = document.getElementById('kpi-inventory-alerts');
            const campaignsEl = document.getElementById('kpi-campaigns-week');
            const workOrdersEl = document.getElementById('kpi-work-orders');

            if (activeEl) {
                activeEl.textContent = String(summary.active_missions ?? 0);
            }
            if (inventoryEl) {
                inventoryEl.textContent = String(summary.inventory_alerts_today ?? 0);
            }
            if (campaignsEl) {
                campaignsEl.textContent = String(summary.campaigns_this_week ?? 0);
            }
            if (workOrdersEl) {
                workOrdersEl.textContent = String(summary.open_work_orders ?? 0);
            }
        } catch (_error) {
            // Silent fail to keep dashboard resilient.
        }
    }

    function updateZoneVisual(zone, count, maxValue) {
        const rect = document.getElementById(`zone-${zone}`);
        const countLabel = document.getElementById(`zone-${zone}-count`);

        if (rect) {
            rect.setAttribute('fill', getHeatmapColor(count, maxValue));
            const title = rect.querySelector('title');
            if (title) {
                title.textContent = `Zone ${zone}: ${count} visitors`;
            }
        }

        if (countLabel) {
            countLabel.textContent = String(count);
        }
    }

    async function updateHeatmap() {
        if (!document.getElementById('zone-A')) {
            return;
        }

        try {
            const { response, data } = await fetchJson(API_ENDPOINTS.footTrafficCurrent);
            if (!response.ok) {
                return;
            }

            const traffic = (data && data.data) ? data.data : data;
            if (!traffic || typeof traffic !== 'object') {
                return;
            }

            const zones = ['A', 'B', 'C', 'D', 'E'];
            const values = zones.map((zone) => Number(traffic[zone] || 0));
            const maxValue = Math.max(...values, 1);

            zones.forEach((zone) => {
                const count = Number(traffic[zone] || 0);
                updateZoneVisual(zone, count, maxValue);
            });
        } catch (_error) {
            // Silent fail to keep dashboard resilient.
        }
    }

    async function initializeChart() {
        const chartCanvas = document.getElementById('todayTrafficChart');
        if (!chartCanvas) {
            return;
        }

        if (typeof ensureChartJs === 'function') {
            try {
                await ensureChartJs();
            } catch (_error) {
                return;
            }
        }

        if (typeof Chart === 'undefined') {
            return;
        }

        const chartContext = chartCanvas.getContext('2d');
        if (!chartContext) {
            return;
        }

        const gradient = chartContext.createLinearGradient(0, 0, 0, 220);
        gradient.addColorStop(0, 'rgba(26,111,232,0.15)');
        gradient.addColorStop(1, 'rgba(26,111,232,0)');

        const source = (typeof todayHourlyTraffic === 'object' && todayHourlyTraffic) ? todayHourlyTraffic : { hours: [], counts: [] };
        const hours = Array.isArray(source.hours) ? source.hours : [];
        const counts = Array.isArray(source.counts) ? source.counts : [];

        todayTrafficChart = new Chart(chartContext, {
            type: 'line',
            data: {
                labels: hours.map((hour) => toHourLabel(hour)),
                datasets: [{
                    data: counts,
                    borderColor: '#1A6FE8',
                    backgroundColor: gradient,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 2,
                    pointBackgroundColor: '#1A6FE8',
                    pointHoverRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        },
                        ticks: {
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 8
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: '#E5E7EB'
                        },
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });
    }

    function updatePendingActionsCount() {
        const badge = document.getElementById('pending-actions-count');
        if (!badge) {
            return;
        }

        const rows = document.querySelectorAll('[id^="pending-action-"]');
        badge.textContent = String(rows.length);
    }

    function handleActionResolution(button, actionType) {
        const actionId = button.getAttribute('data-action-id');
        if (!actionId || typeof fetchWithCSRF !== 'function') {
            return;
        }

        const row = button.closest('tr');
        const rowButtons = row ? row.querySelectorAll('.btn-approve, .btn-reject') : [];
        rowButtons.forEach((btn) => {
            btn.setAttribute('disabled', 'disabled');
        });

        const endpoint = actionType === 'approve'
            ? `/api/actions/${actionId}/approve`
            : `/api/actions/${actionId}/reject`;

        fetchWithCSRF(endpoint, { method: 'POST' })
            .then((response) => response.json().then((payload) => ({ status: response.status, payload })))
            .then(({ status, payload }) => {
                if (status >= 200 && status < 300 && payload.success) {
                    if (row) {
                        row.classList.add('row-fade-out');
                        window.setTimeout(() => {
                            row.remove();
                            updatePendingActionsCount();
                        }, 400);
                    }

                    if (typeof showToast === 'function') {
                        showToast(actionType === 'approve' ? 'Action approved \u2713' : 'Action rejected', actionType === 'approve' ? 'success' : 'warning');
                    }
                } else {
                    throw new Error(payload.error || 'Request failed');
                }
            })
            .catch(() => {
                if (typeof showToast === 'function') {
                    showToast('Failed to process action. Please try again.', 'error');
                }
                rowButtons.forEach((btn) => {
                    btn.removeAttribute('disabled');
                });
            });
    }

    function bindApproveRejectButtons() {
        document.querySelectorAll('.btn-approve').forEach((button) => {
            button.addEventListener('click', function () {
                handleActionResolution(button, 'approve');
            });
        });

        document.querySelectorAll('.btn-reject').forEach((button) => {
            button.addEventListener('click', function () {
                handleActionResolution(button, 'reject');
            });
        });
    }

    function updateNavNotificationBadge(nextCount) {
        const badge = document.getElementById('notif-count-badge');
        if (!badge) {
            return;
        }

        const safeCount = Math.max(0, Number(nextCount || 0));
        if (safeCount > 0) {
            badge.textContent = String(safeCount);
            badge.style.display = 'flex';
        } else {
            badge.textContent = '0';
            badge.style.display = 'none';
        }
    }

    function decrementNavNotificationBadge() {
        const badge = document.getElementById('notif-count-badge');
        if (!badge) {
            return;
        }

        const current = Number(badge.textContent || 0);
        updateNavNotificationBadge(current - 1);
    }

    function markNotificationRowRead(row) {
        if (!row) {
            return;
        }

        row.classList.remove('unread');
        row.classList.add('read');
        row.setAttribute('data-is-read', 'true');
    }

    function markSingleNotificationRead(notifId, row) {
        if (!notifId || typeof fetchWithCSRF !== 'function') {
            return Promise.resolve(false);
        }

        return fetchWithCSRF(`/notifications/${notifId}/read`, { method: 'POST' })
            .then((response) => response.json().then((payload) => ({ status: response.status, payload })))
            .then(({ status, payload }) => {
                if (status >= 200 && status < 300 && payload.success) {
                    if (row) {
                        markNotificationRowRead(row);
                    }
                    decrementNavNotificationBadge();
                    return true;
                }
                return false;
            })
            .catch(() => false);
    }

    function bindAlertFeedRows() {
        document.querySelectorAll('.alert-feed-row[data-notif-id]').forEach((row) => {
            row.addEventListener('click', function (event) {
                if (event.target.closest('a')) {
                    return;
                }

                const notifId = row.getAttribute('data-notif-id');
                const isRead = row.getAttribute('data-is-read') === 'true';
                const actionUrl = row.getAttribute('data-action-url');

                const navigate = function () {
                    if (actionUrl && actionUrl !== '#') {
                        window.location.href = actionUrl;
                    }
                };

                if (!isRead) {
                    markSingleNotificationRead(notifId, row).then(() => navigate());
                } else {
                    navigate();
                }
            });
        });
    }

    function bindNotificationTitleLinks() {
        document.querySelectorAll('.notif-title-link[data-notif-id]').forEach((link) => {
            link.addEventListener('click', function (event) {
                const notifId = link.getAttribute('data-notif-id');
                const row = link.closest('.notif-row');
                const href = link.getAttribute('href');
                const isRead = row && row.getAttribute('data-is-read') === 'true';

                if (!notifId || isRead) {
                    return;
                }

                event.preventDefault();
                markSingleNotificationRead(notifId, row).then(() => {
                    if (href && href !== '#') {
                        window.location.href = href;
                    }
                });
            });
        });
    }

    function updateUnreadCountLabel() {
        const unreadLabel = document.getElementById('notification-unread-count');
        if (!unreadLabel) {
            return;
        }

        const unreadRows = document.querySelectorAll('.notif-row.unread, .alert-feed-row.unread').length;
        unreadLabel.textContent = `${unreadRows} unread notifications`;
    }

    function bindMarkAllReadButton() {
        const button = document.getElementById('mark-all-read-btn');
        if (!button || typeof fetchWithCSRF !== 'function') {
            return;
        }

        button.addEventListener('click', function () {
            fetchWithCSRF('/notifications/read-all', { method: 'POST' })
                .then((response) => response.json().then((payload) => ({ status: response.status, payload })))
                .then(({ status, payload }) => {
                    if (status >= 200 && status < 300 && payload.success) {
                        document.querySelectorAll('.alert-feed-row.unread, .notif-row.unread').forEach((row) => {
                            markNotificationRowRead(row);
                        });
                        updateNavNotificationBadge(0);
                        updateUnreadCountLabel();
                        if (typeof showToast === 'function') {
                            showToast('All notifications marked as read', 'success');
                        }
                    } else {
                        throw new Error(payload.error || 'Failed');
                    }
                })
                .catch(() => {
                    if (typeof showToast === 'function') {
                        showToast('Unable to mark notifications as read.', 'error');
                    }
                });
        });
    }

    function bindNotificationDeleteButtons() {
        document.querySelectorAll('.notif-delete-btn').forEach((button) => {
            button.addEventListener('click', function (event) {
                event.preventDefault();
                const notifId = button.getAttribute('data-notif-id');
                if (!notifId || typeof fetchWithCSRF !== 'function') {
                    return;
                }

                fetchWithCSRF(`/notifications/${notifId}/delete`, { method: 'POST' })
                    .then((response) => response.json().then((payload) => ({ status: response.status, payload })))
                    .then(({ status, payload }) => {
                        if (status >= 200 && status < 300 && payload.success) {
                            const row = button.closest('.notif-row');
                            if (row) {
                                row.remove();
                            }
                            updateUnreadCountLabel();
                            if (typeof showToast === 'function') {
                                showToast('Notification deleted', 'success');
                            }
                        } else {
                            throw new Error(payload.error || 'Failed');
                        }
                    })
                    .catch(() => {
                        if (typeof showToast === 'function') {
                            showToast('Failed to delete notification', 'error');
                        }
                    });
            });
        });
    }

    function applyFilter(filterValue, rowSelector, typeAttrName) {
        const rows = document.querySelectorAll(rowSelector);
        rows.forEach((row) => {
            const type = row.getAttribute(typeAttrName) || '';
            const visible = filterValue === 'all' || filterValue === type;
            row.style.display = visible ? '' : 'none';
        });
    }

    function bindAlertFilterTabs() {
        document.querySelectorAll('.alert-filter-tab').forEach((button) => {
            button.addEventListener('click', function () {
                const filterValue = button.getAttribute('data-filter') || 'all';
                document.querySelectorAll('.alert-filter-tab').forEach((tab) => tab.classList.remove('active'));
                button.classList.add('active');
                applyFilter(filterValue, '.alert-feed-row[data-type]', 'data-type');
            });
        });
    }

    function bindNotificationFilterTabs() {
        document.querySelectorAll('.notif-filter-tab').forEach((tab) => {
            tab.addEventListener('click', function (event) {
                const filterValue = tab.getAttribute('data-filter') || 'all';
                document.querySelectorAll('.notif-filter-tab').forEach((item) => item.classList.remove('active'));
                tab.classList.add('active');
                applyFilter(filterValue, '.notif-row[data-type]', 'data-type');
            });
        });
    }

    function bindRefreshButton() {
        const refreshBtn = document.getElementById('dashboard-refresh-btn');
        if (!refreshBtn) {
            return;
        }

        refreshBtn.addEventListener('click', function () {
            window.location.reload();
        });
    }

    function startDashboardPolling() {
        const hasDashboardElements = Boolean(document.querySelector('.mission-card[data-mission]'));
        if (!hasDashboardElements) {
            return;
        }

        fetchAgentStatus();
        fetchKPIs();
        updateHeatmap();

        pollingHandles.push(window.setInterval(fetchAgentStatus, POLLING_INTERVALS.agentStatus));
        pollingHandles.push(window.setInterval(fetchKPIs, POLLING_INTERVALS.kpi));
        pollingHandles.push(window.setInterval(updateHeatmap, POLLING_INTERVALS.heatmap));

        window.addEventListener('beforeunload', function () {
            pollingHandles.forEach((id) => window.clearInterval(id));
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initializeChart();
        bindRefreshButton();
        bindApproveRejectButtons();
        bindAlertFeedRows();
        bindAlertFilterTabs();
        bindNotificationTitleLinks();
        bindNotificationDeleteButtons();
        bindMarkAllReadButton();
        bindNotificationFilterTabs();
        startDashboardPolling();
    });
})();
