(function () {
    async function ensureChartReady() {
        if (typeof Chart !== 'undefined') {
            return true;
        }
        if (typeof ensureChartJs === 'function') {
            try {
                await ensureChartJs();
            } catch (_error) {
                return false;
            }
        }
        return typeof Chart !== 'undefined';
    }
    const zoneColors = {
        A: '#1A6FE8',
        B: '#0D9488',
        C: '#F97316',
        D: '#06B6D4',
        E: '#10B981'
    };

    const chartRefs = {};

    function showMessage(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type || 'info');
        }
    }

    function hasData(arrayLike) {
        return Array.isArray(arrayLike) && arrayLike.length > 0;
    }

    function toggleEmptyState(id, show) {
        const el = document.getElementById(id);
        if (!el) {
            return;
        }
        el.classList.toggle('d-none', !show);
    }

    function destroyChart(key) {
        if (chartRefs[key]) {
            chartRefs[key].destroy();
            chartRefs[key] = null;
        }
    }

    async function createFootTrafficChart(data) {
        const canvas = document.getElementById('footTrafficChart');
        if (!canvas) {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const dates = data && Array.isArray(data.dates) ? data.dates : [];
        const zones = data && data.zones ? data.zones : {};

        toggleEmptyState('footTrafficEmpty', !dates.length);
        destroyChart('footTrafficChart');

        chartRefs.footTrafficChart = new Chart(canvas, {
            type: 'line',
            data: {
                labels: dates,
                datasets: ['A', 'B', 'C', 'D', 'E'].map((zone) => ({
                    label: `Zone ${zone}`,
                    data: Array.isArray(zones[zone]) ? zones[zone] : [],
                    borderColor: zoneColors[zone],
                    backgroundColor: 'transparent',
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 2
                }))
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top' }
                },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: 'Visitor Count' } }
                }
            }
        });
    }

    async function createInventoryRiskChart(data) {
        const canvas = document.getElementById('inventoryRiskChart');
        if (!canvas) {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const dates = data && Array.isArray(data.dates) ? data.dates : [];
        const values = data && Array.isArray(data.alerts_per_day) ? data.alerts_per_day : [];

        toggleEmptyState('inventoryRiskEmpty', !dates.length);
        destroyChart('inventoryRiskChart');

        chartRefs.inventoryRiskChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: dates,
                datasets: [{
                    label: 'Inventory Risk Alerts',
                    data: values,
                    backgroundColor: '#F97316'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, ticks: { precision: 0 } }
                }
            }
        });
    }

    async function createCampaignPerfChart(data) {
        const canvas = document.getElementById('campaignPerfChart');
        if (!canvas) {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const names = data && Array.isArray(data.campaign_names) ? data.campaign_names : [];
        const impressions = data && Array.isArray(data.impressions) ? data.impressions : [];
        const conversions = data && Array.isArray(data.conversions) ? data.conversions : [];

        toggleEmptyState('campaignPerfEmpty', !names.length);
        destroyChart('campaignPerfChart');

        chartRefs.campaignPerfChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels: names.map((name) => name.length > 24 ? `${name.slice(0, 24)}...` : name),
                datasets: [
                    {
                        label: 'Impressions',
                        data: impressions,
                        backgroundColor: '#1A6FE8'
                    },
                    {
                        label: 'Conversions',
                        data: conversions,
                        backgroundColor: '#10B981'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, ticks: { precision: 0 } }
                }
            }
        });
    }

    async function createFacilityAnomalyChart(data) {
        const canvas = document.getElementById('facilityAnomalyChart');
        if (!canvas) {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const dates = data && Array.isArray(data.dates) ? data.dates : [];
        const values = data && Array.isArray(data.anomaly_events) ? data.anomaly_events : [];

        toggleEmptyState('facilityAnomalyEmpty', !dates.length);
        destroyChart('facilityAnomalyChart');

        chartRefs.facilityAnomalyChart = new Chart(canvas, {
            type: 'line',
            data: {
                labels: dates,
                datasets: [{
                    label: 'Anomaly Events',
                    data: values,
                    borderColor: '#F97316',
                    backgroundColor: 'rgba(249,115,22,0.15)',
                    fill: 'origin',
                    tension: 0.35,
                    borderWidth: 2,
                    pointRadius: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, ticks: { precision: 0 } }
                }
            }
        });
    }

    async function createActionPieChart(data) {
        const canvas = document.getElementById('agentActionPieChart');
        if (!canvas) {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const labels = data && Array.isArray(data.labels) ? data.labels : [];
        const counts = data && Array.isArray(data.counts) ? data.counts : [];
        const colors = data && Array.isArray(data.colors) ? data.colors : ['#1A6FE8', '#0D9488', '#F97316', '#06B6D4'];

        toggleEmptyState('agentActionEmpty', !labels.length);
        destroyChart('agentActionPieChart');

        chartRefs.agentActionPieChart = new Chart(canvas, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: counts,
                    backgroundColor: colors
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right'
                    }
                }
            }
        });
    }

    function formatInr(value) {
        const number = Number(value || 0);
        return number.toLocaleString('en-IN', { maximumFractionDigits: 0 });
    }

    function updateRoiCards(data) {
        if (!data) {
            return;
        }

        const mappings = {
            stockout_prevention_revenue: `\u20B9${formatInr(data.stockout_prevention_revenue)}`,
            stockout_actions_count: `${Number(data.stockout_actions_count || 0)} restock actions approved`,
            stockout_trend_pct: `${Number(data.stockout_trend_pct || 0) >= 0 ? '+' : ''}${Math.trunc(Number(data.stockout_trend_pct || 0))}% vs previous period`,
            campaign_revenue: `\u20B9${formatInr(data.campaign_revenue)}`,
            campaigns_count: `${Number(data.campaigns_count || 0)} campaigns activated`,
            campaign_trend_pct: `${Number(data.campaign_trend_pct || 0) >= 0 ? '+' : ''}${Math.trunc(Number(data.campaign_trend_pct || 0))}% vs previous period`,
            maintenance_cost_saved: `\u20B9${formatInr(data.maintenance_cost_saved)}`,
            work_orders_completed: `${Number(data.work_orders_completed || 0)} work orders completed`,
            maintenance_trend_pct: `${Number(data.maintenance_trend_pct || 0) >= 0 ? '+' : ''}${Math.trunc(Number(data.maintenance_trend_pct || 0))}% vs previous period`,
            total_roi: `\u20B9${formatInr(data.total_roi)}`,
            total_roi_trend_pct: `${Number(data.total_roi_trend_pct || 0) >= 0 ? '+' : ''}${Math.trunc(Number(data.total_roi_trend_pct || 0))}% vs previous period`
        };

        Object.keys(mappings).forEach((key) => {
            const element = document.querySelector(`[data-roi-key="${key}"]`);
            if (element) {
                element.textContent = mappings[key];
            }
        });

        ['stockout_trend_pct', 'campaign_trend_pct', 'maintenance_trend_pct', 'total_roi_trend_pct'].forEach((key) => {
            const element = document.querySelector(`[data-roi-key="${key}"]`);
            if (!element) {
                return;
            }
            const value = Number(data[key] || 0);
            element.classList.remove('positive', 'negative');
            element.classList.add(value >= 0 ? 'positive' : 'negative');
        });
    }

    async function renderAllCharts(data) {
        await createFootTrafficChart(data.foot_traffic || {});
        await createInventoryRiskChart(data.inventory_trend || {});
        await createCampaignPerfChart(data.campaign_trend || {});
        await createFacilityAnomalyChart(data.facility_trend || {});
        await createActionPieChart(data.action_distribution || {});
    }

    function ensureLoadingOverlay() {
        let overlay = document.getElementById('analyticsLoadingOverlay');
        if (overlay) {
            return overlay;
        }

        overlay = document.createElement('div');
        overlay.id = 'analyticsLoadingOverlay';
        overlay.style.position = 'fixed';
        overlay.style.inset = '0';
        overlay.style.background = 'rgba(255,255,255,0.65)';
        overlay.style.display = 'none';
        overlay.style.alignItems = 'center';
        overlay.style.justifyContent = 'center';
        overlay.style.zIndex = '3000';
        overlay.innerHTML = '<div class="spinner-border text-primary" role="status"></div>';
        document.body.appendChild(overlay);
        return overlay;
    }

    function fetchAnalyticsData(rangeStr, startDate, endDate) {
        const overlay = ensureLoadingOverlay();
        const url = new URL('/api/analytics/data', window.location.origin);
        url.searchParams.set('range', rangeStr || '30d');

        if (rangeStr === 'custom') {
            if (startDate) {
                url.searchParams.set('start', startDate);
            }
            if (endDate) {
                url.searchParams.set('end', endDate);
            }
        }

        overlay.style.display = 'flex';

        fetch(url.toString())
            .then((response) => response.json().then((payload) => ({ response, payload })))
            .then(({ response, payload }) => {
                if (!response.ok || !payload.success) {
                    throw new Error(payload.error || 'Unable to fetch analytics data');
                }

                const data = payload.data || {};
                renderAllCharts(data);
                updateRoiCards(data.roi_data || {});

                const pageUrl = new URL(window.location.href);
                pageUrl.searchParams.set('range', rangeStr);
                if (rangeStr === 'custom') {
                    pageUrl.searchParams.set('start', startDate || '');
                    pageUrl.searchParams.set('end', endDate || '');
                } else {
                    pageUrl.searchParams.delete('start');
                    pageUrl.searchParams.delete('end');
                }
                window.history.replaceState({}, '', pageUrl.toString());
            })
            .catch(() => {
                showMessage('Unable to refresh analytics data', 'error');
            })
            .finally(() => {
                overlay.style.display = 'none';
            });
    }

    function bindRangePills() {
        const pills = document.querySelectorAll('.range-pill[data-range]');
        const customRow = document.getElementById('customDateRow');
        if (!pills.length) {
            return;
        }

        pills.forEach((pill) => {
            pill.addEventListener('click', function (event) {
                const range = pill.getAttribute('data-range');

                if (range === 'custom') {
                    if (customRow) {
                        customRow.classList.add('d-flex');
                    }
                    return;
                }

                event.preventDefault();
                const url = new URL(window.location.href);
                url.searchParams.set('range', range);
                url.searchParams.delete('start');
                url.searchParams.delete('end');
                window.location.href = url.toString();
            });
        });
    }

    function bindCustomRangeApply() {
        const button = document.getElementById('applyCustomRange');
        const startInput = document.getElementById('customStartDate');
        const endInput = document.getElementById('customEndDate');

        if (!button || !startInput || !endInput) {
            return;
        }

        button.addEventListener('click', function () {
            const startDate = startInput.value;
            const endDate = endInput.value;
            if (!startDate || !endDate) {
                showMessage('Select both start and end dates', 'warning');
                return;
            }

            const url = new URL(window.location.href);
            url.searchParams.set('range', 'custom');
            url.searchParams.set('start', startDate);
            url.searchParams.set('end', endDate);
            window.location.href = url.toString();
        });
    }

    function sortTableByColumn(table, columnIndex, isAscending) {
        const tbody = table.querySelector('tbody');
        if (!tbody) {
            return;
        }

        const rows = Array.from(tbody.querySelectorAll('tr'));

        rows.sort((rowA, rowB) => {
            const cellA = rowA.children[columnIndex];
            const cellB = rowB.children[columnIndex];

            const valA = cellA ? String(cellA.getAttribute('data-value') || cellA.textContent).trim() : '';
            const valB = cellB ? String(cellB.getAttribute('data-value') || cellB.textContent).trim() : '';

            const numA = Number(valA.replace(/[^0-9.-]/g, ''));
            const numB = Number(valB.replace(/[^0-9.-]/g, ''));

            const bothNumeric = !Number.isNaN(numA) && !Number.isNaN(numB) && valA !== '' && valB !== '';
            if (bothNumeric) {
                return isAscending ? numA - numB : numB - numA;
            }

            return isAscending ? valA.localeCompare(valB) : valB.localeCompare(valA);
        });

        rows.forEach((row) => tbody.appendChild(row));
    }

    function bindTenantTableSorting() {
        const table = document.getElementById('tenantPerformanceTable');
        if (!table) {
            return;
        }

        const headers = table.querySelectorAll('.sortable-header');
        const currentState = { index: -1, ascending: true };

        headers.forEach((header) => {
            header.addEventListener('click', function () {
                const thList = Array.from(header.parentElement.children);
                const index = thList.indexOf(header);
                if (index < 0) {
                    return;
                }

                if (currentState.index === index) {
                    currentState.ascending = !currentState.ascending;
                } else {
                    currentState.index = index;
                    currentState.ascending = true;
                }

                headers.forEach((h) => {
                    h.textContent = h.textContent.replace(/\s[▲▼]$/, '');
                });

                header.textContent = `${header.textContent.replace(/\s[▲▼]$/, '')} ${currentState.ascending ? '▲' : '▼'}`;
                sortTableByColumn(table, index, currentState.ascending);
            });
        });
    }

    function exportTableCSV() {
        const table = document.getElementById('tenantPerformanceTable');
        if (!table) {
            showMessage('No tenant table available to export', 'warning');
            return;
        }

        const rows = table.querySelectorAll('tr');
        const csvLines = [];

        rows.forEach((row) => {
            const cells = row.querySelectorAll('th, td');
            const values = Array.from(cells).map((cell) => {
                const text = (cell.textContent || '').replace(/\s+/g, ' ').trim();
                return `"${text.replace(/"/g, '""')}"`;
            });
            csvLines.push(values.join(','));
        });

        const blob = new Blob([csvLines.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const dateStamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        link.href = URL.createObjectURL(blob);
        link.download = `RetailMind_TenantPerformance_${dateStamp}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    }

    function bindCsvExportButtons() {
        const tableButton = document.getElementById('exportTableCSV');
        if (tableButton) {
            tableButton.addEventListener('click', exportTableCSV);
        }

        const topButton = document.getElementById('exportAnalyticsCSV');
        if (topButton) {
            topButton.addEventListener('click', exportTableCSV);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (typeof chartData === 'object' && chartData) {
            renderAllCharts(chartData);
        }

        bindRangePills();
        bindCustomRangeApply();
        bindTenantTableSorting();
        bindCsvExportButtons();
    });
})();
