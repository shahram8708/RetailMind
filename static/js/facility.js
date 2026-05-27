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

    function showMessage(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type || 'info');
        }
    }

    function csrfToken() {
        if (typeof getCsrfToken === 'function') {
            return getCsrfToken();
        }
        const tokenMeta = document.querySelector('meta[name="csrf-token"]');
        return tokenMeta ? tokenMeta.content : '';
    }

    function scoreColor(score) {
        if (score >= 0.85) {
            return '#EF4444';
        }
        if (score >= 0.65) {
            return '#F97316';
        }
        if (score >= 0.40) {
            return '#F59E0B';
        }
        return '#10B981';
    }

    function initFloorFilter() {
        const buttons = document.querySelectorAll('.floor-filter-btn');
        const cards = document.querySelectorAll('.equipment-card');
        if (!buttons.length || !cards.length) {
            return;
        }

        buttons.forEach((button) => {
            button.addEventListener('click', function (event) {
                event.preventDefault();
                const floor = button.getAttribute('data-floor');

                buttons.forEach((btn) => {
                    btn.classList.remove('btn-primary');
                    btn.classList.add('btn-outline-primary');
                });
                button.classList.remove('btn-outline-primary');
                button.classList.add('btn-primary');

                cards.forEach((card) => {
                    const cardFloor = card.getAttribute('data-floor');
                    const visible = floor === 'all' || cardFloor === floor;
                    card.style.display = visible ? '' : 'none';
                });

                const url = new URL(window.location.href);
                if (floor === 'all') {
                    url.searchParams.delete('floor');
                } else {
                    url.searchParams.set('floor', floor);
                }
                window.history.replaceState({}, '', url.toString());
            });
        });
    }

    function initEquipmentTypeFilter() {
        const select = document.getElementById('equipment-type-filter');
        const cards = document.querySelectorAll('.equipment-card');
        if (!select || !cards.length) {
            return;
        }

        select.addEventListener('change', function () {
            const selectedType = String(select.value || '').toLowerCase();

            cards.forEach((card) => {
                const cardType = String(card.getAttribute('data-equipment-type') || '').toLowerCase();
                const visible = !selectedType || selectedType === cardType;
                card.style.display = visible ? '' : 'none';
            });

            const url = new URL(window.location.href);
            if (!selectedType) {
                url.searchParams.delete('equipment_type');
            } else {
                url.searchParams.set('equipment_type', selectedType);
            }
            window.history.replaceState({}, '', url.toString());
        });
    }

    function initStatusFilter() {
        const select = document.getElementById('status-filter');
        if (!select) {
            return;
        }

        select.addEventListener('change', function () {
            const url = new URL(window.location.href);
            const value = select.value || 'all';
            if (value === 'all') {
                url.searchParams.delete('status');
            } else {
                url.searchParams.set('status', value);
            }
            window.location.href = url.toString();
        });
    }

    async function initFpsGaugeChart() {
        const canvas = document.getElementById('fpsGaugeChart');
        if (!canvas || typeof fpsScore === 'undefined') {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const score = clamp(Number(fpsScore || 0), 0, 1);
        const color = scoreColor(score);

        new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: ['Score', 'Remaining'],
                datasets: [{
                    data: [score * 100, (1 - score) * 100],
                    backgroundColor: [color, '#E5E7EB'],
                    borderWidth: 0
                }]
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

    async function initTelemetryChart() {
        const canvas = document.getElementById('telemetryChart');
        if (!canvas || typeof telemetryData === 'undefined' || !telemetryData) {
            return;
        }

        const ready = await ensureChartReady();
        if (!ready) {
            return;
        }

        const labels = Array.isArray(telemetryData.timestamps) ? telemetryData.timestamps : [];
        const values = Array.isArray(telemetryData.values) ? telemetryData.values : [];
        const meanLine = Array.isArray(telemetryData.mean_line) ? telemetryData.mean_line : [];
        const upper = Array.isArray(telemetryData.upper_threshold) ? telemetryData.upper_threshold : [];
        const anomalyIndices = Array.isArray(telemetryData.anomaly_indices) ? telemetryData.anomaly_indices : [];

        if (!labels.length || !values.length) {
            return;
        }

        const anomalySeries = values.map(() => null);
        anomalyIndices.forEach((index) => {
            if (index >= 0 && index < anomalySeries.length) {
                anomalySeries[index] = values[index];
            }
        });

        new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: telemetryData.metric_name || 'Sensor',
                        data: values,
                        borderColor: '#1A6FE8',
                        pointRadius: 2,
                        borderWidth: 1.5,
                        tension: 0
                    },
                    {
                        label: `Mean (${Number(telemetryData.mu || 0).toFixed(2)})`,
                        data: meanLine,
                        borderColor: '#374151',
                        borderDash: [5, 5],
                        pointRadius: 0,
                        borderWidth: 1,
                        tension: 0
                    },
                    {
                        label: 'Upper Bound (+2.5 sigma)',
                        data: upper,
                        borderColor: 'rgba(239,68,68,0.5)',
                        borderDash: [3, 3],
                        pointRadius: 0,
                        borderWidth: 1,
                        tension: 0
                    },
                    {
                        label: 'Anomaly',
                        data: anomalySeries,
                        borderColor: '#EF4444',
                        pointRadius: 5,
                        pointBackgroundColor: '#EF4444',
                        showLine: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'nearest',
                    intersect: false
                },
                scales: {
                    x: {
                        ticks: {
                            callback: function (value, index) {
                                return index % 10 === 0 ? labels[index] : '';
                            }
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: telemetryData.metric_name || 'Metric'
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            afterBody: function (items) {
                                if (!items || !items.length) {
                                    return '';
                                }
                                const idx = items[0].dataIndex;
                                const isAnomaly = anomalyIndices.includes(idx);
                                if (!isAnomaly) {
                                    return '';
                                }
                                const mu = Number(telemetryData.mu || 0);
                                const sigma = Number(telemetryData.sigma || 0.001) || 0.001;
                                const z = (Number(values[idx] || 0) - mu) / sigma;
                                return `Z-score: ${z.toFixed(2)}`;
                            }
                        }
                    }
                }
            }
        });
    }

    function animateFactorBars() {
        const bars = document.querySelectorAll('.fps-factor-fill');
        if (!bars.length) {
            return;
        }

        bars.forEach((bar, index) => {
            const target = bar.getAttribute('data-width') || '0%';
            bar.style.width = '0%';
            window.setTimeout(() => {
                bar.style.width = target;
            }, 100 * (index + 1));
        });
    }

    function bindActionButtons() {
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

                fetchWithCSRF(`/api/actions/${actionId}/approve`, { method: 'POST' })
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Unable to approve action');
                        }
                        showMessage('Work order approved', 'success');
                        window.location.reload();
                    })
                    .catch(() => {
                        approveBtn.disabled = false;
                        if (rejectBtn) {
                            rejectBtn.disabled = false;
                        }
                        showMessage('Unable to approve action', 'error');
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

                fetchWithCSRF(`/api/actions/${actionId}/reject`, { method: 'POST' })
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Unable to reject action');
                        }
                        showMessage('Action rejected', 'warning');
                        window.location.reload();
                    })
                    .catch(() => {
                        rejectBtn.disabled = false;
                        if (approveBtn) {
                            approveBtn.disabled = false;
                        }
                        showMessage('Unable to reject action', 'error');
                    });
            });
        }
    }

    function appendWorkOrderRow(workOrderId, title, equipmentName, priority) {
        const table = document.getElementById('workOrdersTable');
        if (!table) {
            return;
        }

        const tbody = table.querySelector('tbody');
        if (!tbody) {
            return;
        }

        const row = document.createElement('tr');
        row.id = `wo-row-${workOrderId}`;
        row.innerHTML = `
            <td>#${workOrderId}</td>
            <td>${equipmentName || '-'}</td>
            <td><span class="priority-badge ${priority || 'medium'} badge">${(priority || 'medium').replace('_', ' ')}</span></td>
            <td>${title || 'Work order created'}</td>
            <td><span class="text-muted">Unassigned</span></td>
            <td>just now</td>
            <td><span class="badge bg-primary wo-status-badge">Open</span></td>
            <td><span class="text-muted">Refresh page for full controls</span></td>
        `;
        tbody.prepend(row);
    }

    function bindCreateWorkOrderModal() {
        const modalEl = document.getElementById('createWorkOrderModal');
        const form = document.getElementById('workOrderForm');
        const hiddenEquipment = document.getElementById('modal-equipment-id');
        const modalTitle = document.getElementById('workOrderModalTitle');

        if (!modalEl || !form || typeof bootstrap === 'undefined') {
            return;
        }

        if (modalEl.parentElement !== document.body) {
            document.body.appendChild(modalEl);
        }

        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        const endpoint = form.getAttribute('action') || '/facility/work-order/create';

        modalEl.addEventListener('shown.bs.modal', function () {
            const firstField = form.querySelector('input:not([type="hidden"]), textarea, select');
            if (firstField && typeof firstField.focus === 'function') {
                firstField.focus();
            }
        });

        modalEl.addEventListener('hidden.bs.modal', function () {
            form.reset();
            if (hiddenEquipment) {
                hiddenEquipment.value = '';
            }
            if (modalTitle) {
                modalTitle.textContent = 'Create Work Order';
            }
        });

        document.querySelectorAll('.btn-create-work-order').forEach((button) => {
            button.addEventListener('click', function () {
                const equipmentId = button.getAttribute('data-equipment-id') || '';
                const equipmentName = button.getAttribute('data-equipment-name') || 'Equipment';

                if (hiddenEquipment) {
                    hiddenEquipment.value = equipmentId;
                }
                if (modalTitle) {
                    modalTitle.textContent = `Create Work Order${equipmentName ? ` - ${equipmentName}` : ''}`;
                }
                modal.show();
            });
        });

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            const formData = new FormData(form);

            fetch(endpoint, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken()
                }
            })
                .then((response) => response.json().then((payload) => ({ response, payload })))
                .then(({ response, payload }) => {
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.error || 'Unable to create work order');
                    }

                    modal.hide();
                    showMessage(`Work order #${payload.work_order_id} created`, 'success');
                    appendWorkOrderRow(payload.work_order_id, payload.title, payload.equipment_name, payload.priority);
                })
                .catch(() => {
                    showMessage('Unable to create work order', 'error');
                });
        });
    }

    function bindQuickWorkOrderForm() {
        const form = document.getElementById('quickWorkOrderForm');
        if (!form) {
            return;
        }

        const endpoint = form.getAttribute('action') || '/facility/work-order/create';

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            const formData = new FormData(form);

            fetch(endpoint, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken()
                }
            })
                .then((response) => response.json().then((payload) => ({ response, payload })))
                .then(({ response, payload }) => {
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.error || 'Unable to create work order');
                    }

                    showMessage(`Work order #${payload.work_order_id} created`, 'success');
                    form.reset();
                })
                .catch(() => {
                    showMessage('Unable to create work order', 'error');
                });
        });
    }

    function bindCompleteWorkOrders() {
        document.querySelectorAll('.btn-complete-wo').forEach((button) => {
            button.addEventListener('click', function () {
                const workOrderId = button.getAttribute('data-wo-id');
                if (!workOrderId) {
                    return;
                }

                const row = document.getElementById(`wo-row-${workOrderId}`) || button.closest('tr');
                const inlineInput = row ? row.querySelector('.input-actual-cost') : null;
                let actualCost = '';

                if (inlineInput) {
                    actualCost = inlineInput.value || '';
                } else {
                    actualCost = window.prompt('Enter actual cost in INR (optional):', '') || '';
                }

                button.disabled = true;

                fetchWithCSRF(`/facility/work-order/${workOrderId}/complete`, {
                    method: 'POST',
                    body: JSON.stringify({ actual_cost_inr: actualCost })
                })
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Unable to complete work order');
                        }

                        if (row) {
                            const statusBadge = row.querySelector('.wo-status-badge');
                            if (statusBadge) {
                                statusBadge.textContent = 'Completed';
                                statusBadge.classList.remove('bg-primary', 'bg-info');
                                statusBadge.classList.add('bg-success');
                            }
                            row.classList.add('wo-status-completed');
                            row.querySelectorAll('button, select, input').forEach((el) => {
                                el.disabled = true;
                            });
                        }

                        showMessage('Work order completed.', 'success');
                    })
                    .catch(() => {
                        button.disabled = false;
                        showMessage('Unable to complete work order', 'error');
                    });
            });
        });
    }

    function bindAssignWorkOrders() {
        document.querySelectorAll('.select-assign-wo').forEach((select) => {
            select.addEventListener('focus', function () {
                select.setAttribute('data-prev-value', select.value || '');
            });

            select.addEventListener('change', function () {
                const workOrderId = select.getAttribute('data-wo-id');
                const userId = select.value;
                if (!workOrderId || !userId) {
                    return;
                }

                fetchWithCSRF(`/facility/work-order/${workOrderId}/assign`, {
                    method: 'POST',
                    body: JSON.stringify({ user_id: Number(userId) })
                })
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Unable to assign work order');
                        }

                        const row = document.getElementById(`wo-row-${workOrderId}`) || select.closest('tr');
                        if (row) {
                            const statusBadge = row.querySelector('.wo-status-badge');
                            if (statusBadge) {
                                statusBadge.textContent = 'In Progress';
                                statusBadge.classList.remove('bg-primary');
                                statusBadge.classList.add('bg-info');
                            }
                        }

                        showMessage('Work order assigned', 'success');
                    })
                    .catch(() => {
                        const previous = select.getAttribute('data-prev-value') || '';
                        select.value = previous;
                        showMessage('Unable to assign work order', 'error');
                    });
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initFloorFilter();
        initEquipmentTypeFilter();
        initStatusFilter();
        initFpsGaugeChart();
        initTelemetryChart();
        animateFactorBars();
        bindActionButtons();
        bindCreateWorkOrderModal();
        bindQuickWorkOrderForm();
        bindCompleteWorkOrders();
        bindAssignWorkOrders();
    });
})();
