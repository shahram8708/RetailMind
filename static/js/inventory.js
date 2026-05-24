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
    function clamp(value, low, high) {
        return Math.min(high, Math.max(low, value));
    }

    function getScoreColor(score) {
        if (score >= 0.85) {
            return '#EF4444';
        }
        if (score >= 0.70) {
            return '#F97316';
        }
        if (score >= 0.50) {
            return '#F59E0B';
        }
        return '#10B981';
    }

    function getCsrfFetch(url, method) {
        if (typeof fetchWithCSRF === 'function') {
            return fetchWithCSRF(url, { method: method || 'POST' });
        }
        return fetch(url, { method: method || 'POST' });
    }

    function showMessage(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type || 'info');
        }
    }

    function setAgentCardResolved(html) {
        const card = document.querySelector('.agent-recommendation-card');
        if (!card) {
            return;
        }
        card.innerHTML = html;
    }

    async function initSrsGauge() {
        const canvas = document.getElementById('srsGaugeChart');
        if (!canvas || typeof srsScore === 'undefined') {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const safeScore = clamp(Number(srsScore || 0), 0, 1);
        const scoreColor = getScoreColor(safeScore);

        new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: ['Risk', 'Remaining'],
                datasets: [
                    {
                        data: [safeScore * 100, (1 - safeScore) * 100],
                        backgroundColor: [scoreColor, '#E5E7EB'],
                        borderWidth: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '80%',
                circumference: 180,
                rotation: -90,
                plugins: {
                    legend: { display: false },
                    tooltip: { enabled: false }
                }
            }
        });
    }

    async function initVelocityChart() {
        const canvas = document.getElementById('velocityChart');
        if (!canvas || typeof velocityChartData === 'undefined') {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const labels = Array.isArray(velocityChartData.timestamps) ? velocityChartData.timestamps : [];
        const values = Array.isArray(velocityChartData.units_sold) ? velocityChartData.units_sold : [];

        const context = canvas.getContext('2d');
        const gradient = context.createLinearGradient(0, 0, 0, 200);
        gradient.addColorStop(0, 'rgba(26, 111, 232, 0.22)');
        gradient.addColorStop(1, 'rgba(26, 111, 232, 0.00)');

        new Chart(context, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        data: values,
                        borderColor: '#1A6FE8',
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 3,
                        pointHoverRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { precision: 0 }
                    },
                    x: {
                        ticks: { maxTicksLimit: 8 }
                    }
                }
            }
        });

        const allZero = values.length > 0 && values.every((value) => Number(value) === 0);
        if (allZero) {
            const wrap = canvas.parentElement;
            if (wrap) {
                const empty = document.createElement('div');
                empty.className = 'text-muted small mt-2';
                empty.textContent = 'No sales recorded in the last 48 hours.';
                wrap.appendChild(empty);
            }
        }
    }

    async function initStockHistoryChart() {
        const canvas = document.getElementById('stockHistoryChart');
        if (!canvas || typeof stockHistoryData === 'undefined') {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const labels = Array.isArray(stockHistoryData.dates) ? stockHistoryData.dates : [];
        const stockLevels = Array.isArray(stockHistoryData.stock_levels) ? stockHistoryData.stock_levels : [];
        const thresholdValue = typeof reorderThreshold !== 'undefined'
            ? Number(reorderThreshold || 0)
            : Number(stockHistoryData.reorder_threshold || 0);

        if (!labels.length) {
            const wrap = canvas.parentElement;
            if (wrap) {
                const empty = document.createElement('div');
                empty.className = 'text-muted small mt-2';
                empty.textContent = 'No stock history available.';
                wrap.appendChild(empty);
            }
            return;
        }

        new Chart(canvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        type: 'bar',
                        label: 'Stock Level',
                        data: stockLevels,
                        backgroundColor: 'rgba(26, 111, 232, 0.7)',
                        borderColor: '#1A6FE8',
                        borderWidth: 1
                    },
                    {
                        type: 'line',
                        label: 'Reorder Threshold',
                        data: labels.map(() => thresholdValue),
                        borderColor: '#EF4444',
                        borderDash: [6, 5],
                        borderWidth: 2,
                        pointRadius: 0,
                        fill: false,
                        tension: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: true }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Units'
                        }
                    }
                }
            }
        });
    }

    function bindDetailActionButtons() {
        const approveBtn = document.getElementById('approveActionBtn');
        const rejectBtn = document.getElementById('rejectActionBtn');

        if (approveBtn) {
            approveBtn.addEventListener('click', function () {
                const actionId = approveBtn.getAttribute('data-action-id');
                if (!actionId) {
                    return;
                }

                approveBtn.disabled = true;
                if (rejectBtn) {
                    rejectBtn.disabled = true;
                }

                getCsrfFetch(`/inventory/approve/${actionId}`, 'POST')
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Unable to approve');
                        }

                        setAgentCardResolved(
                            `<div class="p-3 text-success fw-semibold">` +
                            `\u2705 Restock Approved - Action ID ${actionId}. Supplier notification sent.` +
                            `</div>`
                        );
                        showMessage('Restock approved successfully', 'success');
                    })
                    .catch(() => {
                        approveBtn.disabled = false;
                        if (rejectBtn) {
                            rejectBtn.disabled = false;
                        }
                        showMessage('Unable to approve restock right now', 'error');
                    });
            });
        }

        if (rejectBtn) {
            rejectBtn.addEventListener('click', function () {
                const actionId = rejectBtn.getAttribute('data-action-id');
                if (!actionId) {
                    return;
                }

                rejectBtn.disabled = true;
                if (approveBtn) {
                    approveBtn.disabled = true;
                }

                getCsrfFetch(`/inventory/reject/${actionId}`, 'POST')
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Unable to reject');
                        }

                        setAgentCardResolved(
                            '<div class="p-3 text-secondary fw-semibold">\u2717 Action rejected</div>'
                        );
                        showMessage('Action rejected', 'warning');
                    })
                    .catch(() => {
                        rejectBtn.disabled = false;
                        if (approveBtn) {
                            approveBtn.disabled = false;
                        }
                        showMessage('Unable to reject action right now', 'error');
                    });
            });
        }
    }

    function debounce(fn, delayMs) {
        let timer = null;
        return function () {
            const context = this;
            const args = arguments;
            window.clearTimeout(timer);
            timer = window.setTimeout(() => fn.apply(context, args), delayMs);
        };
    }

    function bindLiveSearch() {
        const input = document.getElementById('inventorySearchInput');
        if (!input) {
            return;
        }

        const rows = Array.from(document.querySelectorAll('.sku-row'));
        const visibleCountEl = document.getElementById('visibleSkuCount');

        const runSearch = debounce(function () {
            const term = String(input.value || '').trim().toLowerCase();
            let visibleCount = 0;

            rows.forEach((row) => {
                const product = String(row.getAttribute('data-product') || '').toLowerCase();
                const sku = String(row.getAttribute('data-sku') || '').toLowerCase();
                const brand = String(row.getAttribute('data-brand') || '').toLowerCase();
                const shouldShow = !term || product.includes(term) || sku.includes(term) || brand.includes(term);

                row.style.display = shouldShow ? '' : 'none';
                if (shouldShow) {
                    visibleCount += 1;
                }
            });

            if (visibleCountEl) {
                visibleCountEl.textContent = String(visibleCount);
            }
        }, 300);

        input.addEventListener('input', runSearch);
    }

    function animateCountUps() {
        const elements = document.querySelectorAll('.count-up-number');
        if (!elements.length) {
            return;
        }

        elements.forEach((element) => {
            const target = Number(element.getAttribute('data-target') || 0);
            const duration = 1000;
            const start = performance.now();

            function frame(timestamp) {
                const progress = Math.min(1, (timestamp - start) / duration);
                const value = Math.round(target * progress);
                element.textContent = String(value);
                if (progress < 1) {
                    requestAnimationFrame(frame);
                }
            }

            requestAnimationFrame(frame);
        });
    }

    function bindListActionButtons() {
        document.querySelectorAll('.btn-approve-list').forEach((button) => {
            button.addEventListener('click', function () {
                const actionId = button.getAttribute('data-action-id');
                if (!actionId) {
                    return;
                }
                button.disabled = true;

                getCsrfFetch(`/inventory/approve/${actionId}`, 'POST')
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Unable to approve');
                        }

                        const holder = button.closest('.action-cell');
                        if (holder) {
                            holder.innerHTML = '<span class="badge bg-success-subtle text-success">Approved</span>';
                        } else {
                            button.remove();
                        }
                        showMessage('Restock approved successfully', 'success');
                    })
                    .catch(() => {
                        button.disabled = false;
                        showMessage('Unable to approve restock right now', 'error');
                    });
            });
        });

        document.querySelectorAll('.btn-reject-list').forEach((button) => {
            button.addEventListener('click', function () {
                const actionId = button.getAttribute('data-action-id');
                if (!actionId) {
                    return;
                }
                button.disabled = true;

                getCsrfFetch(`/inventory/reject/${actionId}`, 'POST')
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Unable to reject');
                        }

                        const holder = button.closest('.action-cell');
                        if (holder) {
                            holder.innerHTML = '<span class="badge bg-secondary-subtle text-secondary">Rejected</span>';
                        } else {
                            button.remove();
                        }
                        showMessage('Restock request rejected', 'warning');
                    })
                    .catch(() => {
                        button.disabled = false;
                        showMessage('Unable to reject action right now', 'error');
                    });
            });
        });
    }

    function bindRunAnalysisButton() {
        const button = document.getElementById('runInventoryNowBtn');
        if (!button) {
            return;
        }

        button.addEventListener('click', function (event) {
            event.preventDefault();
            getCsrfFetch('/api/agent/run-now/inventory', 'POST')
                .then((response) => response.json().then((payload) => ({ response, payload })))
                .then(({ response, payload }) => {
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.error || 'Unable to trigger mission');
                    }
                    showMessage(payload.message || 'Inventory mission started', 'info');
                })
                .catch(() => {
                    showMessage('Inventory run trigger is coming soon', 'info');
                });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initSrsGauge();
        initVelocityChart();
        initStockHistoryChart();
        bindDetailActionButtons();
        bindLiveSearch();
        animateCountUps();
        bindListActionButtons();
        bindRunAnalysisButton();
    });
})();
