(function () {
    function getCsrfToken() {
        const tokenElement = document.querySelector('meta[name="csrf-token"]');
        return tokenElement ? tokenElement.content : '';
    }

    function notify(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type || 'success');
            return;
        }
        window.alert(message);
    }

    function requestJson(url, method, payload) {
        return fetch(url, {
            method: method || 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: payload ? JSON.stringify(payload) : undefined
        }).then((response) => response.json().then((data) => ({ response, data })));
    }

    function tierBadgeClass(tier) {
        if (tier === 'enterprise') {
            return 'badge-tier-enterprise';
        }
        if (tier === 'professional') {
            return 'badge-tier-professional';
        }
        return 'badge-tier-starter';
    }

    function roleBadgeClass(role) {
        if (role === 'superadmin') {
            return 'text-bg-dark';
        }
        if (role === 'mall_admin') {
            return 'text-bg-primary';
        }
        if (role === 'store_manager') {
            return 'text-bg-info';
        }
        if (role === 'marketing_manager') {
            return 'text-bg-warning';
        }
        if (role === 'facility_manager') {
            return 'text-bg-secondary';
        }
        return 'text-bg-light text-dark';
    }

    function demoStatusBadgeClass(status) {
        if (status === 'new') {
            return 'text-bg-primary';
        }
        if (status === 'contacted') {
            return 'text-bg-warning';
        }
        if (status === 'qualified') {
            return 'text-bg-info';
        }
        return 'text-bg-secondary';
    }

    function markUpdated(element) {
        if (!element) {
            return;
        }

        let indicator = element.parentElement ? element.parentElement.querySelector('.sa-updated-indicator') : null;
        if (!indicator) {
            indicator = document.createElement('span');
            indicator.className = 'sa-updated-indicator';
            indicator.textContent = 'Updated just now';
            if (element.parentElement) {
                element.parentElement.appendChild(indicator);
            }
        }

        indicator.style.opacity = '1';
        window.setTimeout(function () {
            indicator.style.opacity = '0';
        }, 3000);
    }

    function updateTextIfChanged(element, value) {
        if (!element) {
            return;
        }
        const nextText = String(value);
        if (element.textContent.trim() !== nextText) {
            element.textContent = nextText;
            markUpdated(element);
        }
    }

    function refreshPlatformStats() {
        const totalPropertiesEl = document.getElementById('sa-total-properties');
        if (!totalPropertiesEl) {
            return;
        }

        fetch('/api/admin/platform-stats')
            .then((response) => response.json())
            .then((payload) => {
                if (!payload || !payload.success) {
                    return;
                }

                const data = payload.data || payload;

                updateTextIfChanged(totalPropertiesEl, data.total_properties || totalPropertiesEl.textContent.trim());
                updateTextIfChanged(document.getElementById('sa-total-users'), data.total_users || document.getElementById('sa-total-users')?.textContent.trim());
                updateTextIfChanged(document.getElementById('sa-agent-actions-today'), data.agent_actions_today || 0);
                updateTextIfChanged(document.getElementById('sa-pending-agent-actions'), data.pending_all || 0);
            })
            .catch(function () {
                // Keep dashboard resilient on transient API failures.
            });
    }

    function bindPlatformStatsAutoRefresh() {
        if (!document.getElementById('sa-total-properties')) {
            return;
        }

        window.setInterval(refreshPlatformStats, 60000);
    }

    function bindChangeTierModal() {
        const modalElement = document.getElementById('changeTierModal');
        const tierSelect = document.getElementById('tierSelect');
        const propertyIdInput = document.getElementById('changeTierPropertyId');
        const currentTierLabel = document.getElementById('currentTierLabel');
        const form = document.getElementById('changeTierForm');

        if (!modalElement || !tierSelect || !propertyIdInput || !form || typeof bootstrap === 'undefined') {
            return;
        }

        const modal = bootstrap.Modal.getOrCreateInstance(modalElement);

        document.querySelectorAll('.btn-change-tier').forEach((button) => {
            button.addEventListener('click', function () {
                const propertyId = button.getAttribute('data-property-id');
                const currentTier = (button.getAttribute('data-current-tier') || 'starter').toLowerCase();

                propertyIdInput.value = propertyId || '';
                tierSelect.value = currentTier;
                if (currentTierLabel) {
                    currentTierLabel.textContent = currentTier.charAt(0).toUpperCase() + currentTier.slice(1);
                }

                modal.show();
            });
        });

        form.addEventListener('submit', function (event) {
            event.preventDefault();

            const propertyId = propertyIdInput.value;
            const newTier = tierSelect.value;
            if (!propertyId || !newTier) {
                return;
            }

            requestJson(`/superadmin/properties/${propertyId}/change-tier`, 'POST', { tier: newTier })
                .then(({ response, data }) => {
                    if (!response.ok || !data.success) {
                        throw new Error(data.message || 'Tier change failed.');
                    }

                    const badge = document.getElementById(`tier-badge-${propertyId}`);
                    if (badge) {
                        badge.textContent = newTier.charAt(0).toUpperCase() + newTier.slice(1);
                        badge.className = `badge ${tierBadgeClass(newTier)}`;
                    }

                    document.querySelectorAll(`.btn-change-tier[data-property-id="${propertyId}"]`).forEach((button) => {
                        button.setAttribute('data-current-tier', newTier);
                    });

                    modal.hide();
                    notify(`Tier updated to ${newTier}`, 'success');
                })
                .catch((error) => {
                    notify(error.message || 'Unable to update tier.', 'error');
                });
        });
    }

    function bindSuspendProperty() {
        document.querySelectorAll('.btn-suspend-property').forEach((button) => {
            button.addEventListener('click', function () {
                const propertyId = button.getAttribute('data-property-id');
                if (!propertyId) {
                    return;
                }

                if (!window.confirm('Suspend this property? All users will be deactivated.')) {
                    return;
                }

                requestJson(`/superadmin/properties/${propertyId}/suspend`, 'POST')
                    .then(({ response, data }) => {
                        if (!response.ok || !data.success) {
                            throw new Error(data.message || 'Unable to suspend property.');
                        }

                        const row = document.getElementById(`property-row-${propertyId}`);
                        if (row) {
                            row.classList.add('sa-row-muted');
                            const existing = row.querySelector('.sa-suspended-badge');
                            if (!existing) {
                                const badge = document.createElement('span');
                                badge.className = 'badge text-bg-secondary sa-suspended-badge';
                                badge.textContent = 'Suspended';
                                const actionCell = row.querySelector('td:last-child');
                                if (actionCell) {
                                    actionCell.appendChild(document.createElement('br'));
                                    actionCell.appendChild(badge);
                                }
                            }
                        }

                        notify(data.message || 'Property suspended.', 'warning');
                    })
                    .catch((error) => {
                        notify(error.message || 'Unable to suspend property.', 'error');
                    });
            });
        });
    }

    function bindUserVerification() {
        document.querySelectorAll('.btn-verify-user').forEach((button) => {
            button.addEventListener('click', function () {
                const userId = button.getAttribute('data-user-id');
                if (!userId) {
                    return;
                }

                requestJson(`/superadmin/users/${userId}/verify`, 'POST')
                    .then(({ response, data }) => {
                        if (!response.ok || !data.success) {
                            throw new Error(data.message || 'Unable to verify user.');
                        }

                        const indicator = document.getElementById(`verified-indicator-${userId}`);
                        if (indicator) {
                            indicator.className = 'badge text-bg-success';
                            indicator.innerHTML = '&#10003; Verified';
                        }
                        button.remove();
                        notify(data.message || 'User verified.', 'success');
                    })
                    .catch((error) => {
                        notify(error.message || 'Unable to verify user.', 'error');
                    });
            });
        });
    }

    function bindUserActiveToggle() {
        document.querySelectorAll('.btn-toggle-active-user').forEach((button) => {
            button.addEventListener('click', function () {
                const userId = button.getAttribute('data-user-id');
                if (!userId) {
                    return;
                }

                requestJson(`/superadmin/users/${userId}/deactivate`, 'POST')
                    .then(({ response, data }) => {
                        if (!response.ok || !data.success) {
                            throw new Error(data.message || 'Unable to update user status.');
                        }

                        const isActive = Boolean(data.is_active);
                        const badge = document.getElementById(`active-badge-${userId}`);
                        if (badge) {
                            badge.className = `badge ${isActive ? 'text-bg-success' : 'text-bg-secondary'}`;
                            badge.textContent = isActive ? 'Active' : 'Inactive';
                        }

                        const row = document.getElementById(`user-row-${userId}`);
                        if (row) {
                            row.classList.toggle('sa-row-muted', !isActive);
                        }

                        button.classList.toggle('btn-danger', isActive);
                        button.classList.toggle('btn-success', !isActive);
                        button.textContent = isActive ? 'Deactivate' : 'Reactivate';

                        notify(data.message || 'User status updated.', 'success');
                    })
                    .catch((error) => {
                        notify(error.message || 'Unable to update user status.', 'error');
                    });
            });
        });
    }

    function bindUserRoleChange() {
        document.querySelectorAll('.select-change-role-sa').forEach((select) => {
            select.addEventListener('change', function () {
                const userId = select.getAttribute('data-user-id');
                const role = select.value;
                if (!userId || !role) {
                    return;
                }

                requestJson(`/superadmin/users/${userId}/change-role`, 'POST', { role })
                    .then(({ response, data }) => {
                        if (!response.ok || !data.success) {
                            throw new Error(data.message || 'Unable to change role.');
                        }

                        const badge = document.getElementById(`role-badge-${userId}`);
                        if (badge) {
                            badge.className = `badge ${roleBadgeClass(role)}`;
                            badge.textContent = role.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                        }

                        notify('User role updated.', 'success');
                    })
                    .catch((error) => {
                        notify(error.message || 'Unable to update role.', 'error');
                    });
            });
        });
    }

    function bindUserDelete() {
        document.querySelectorAll('.btn-delete-user').forEach((button) => {
            button.addEventListener('click', function () {
                const userId = button.getAttribute('data-user-id');
                if (!userId) {
                    return;
                }

                if (!window.confirm('Delete this user? This cannot be undone.')) {
                    return;
                }

                requestJson(`/superadmin/users/${userId}/delete`, 'POST')
                    .then(({ response, data }) => {
                        if (!response.ok || !data.success) {
                            throw new Error(data.message || 'Unable to delete user.');
                        }

                        const row = document.getElementById(`user-row-${userId}`);
                        if (row) {
                            row.style.transition = 'opacity 0.25s ease';
                            row.style.opacity = '0';
                            window.setTimeout(function () {
                                row.remove();
                            }, 250);
                        }

                        notify(data.message || 'User deleted.', 'success');
                    })
                    .catch((error) => {
                        notify(error.message || 'Unable to delete user.', 'error');
                    });
            });
        });
    }

    function updateDemoStatus(reqId, status) {
        return requestJson(`/superadmin/demo-requests/${reqId}/update`, 'POST', { status })
            .then(({ response, data }) => {
                if (!response.ok || !data.success) {
                    throw new Error(data.message || 'Unable to update demo request.');
                }

                const badge = document.getElementById(`demo-status-badge-${reqId}`);
                if (badge) {
                    badge.className = `badge ${demoStatusBadgeClass(status)}`;
                    badge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
                }

                const select = document.querySelector(`.select-demo-status[data-req-id="${reqId}"]`);
                if (select) {
                    select.value = status;
                }

                notify('Demo request updated.', 'success');
                return true;
            });
    }

    function bindDemoRequestUpdates() {
        document.querySelectorAll('.select-demo-status').forEach((select) => {
            select.addEventListener('change', function () {
                const reqId = select.getAttribute('data-req-id');
                const status = select.value;
                if (!reqId || !status) {
                    return;
                }

                updateDemoStatus(reqId, status).catch((error) => {
                    notify(error.message || 'Unable to update demo request.', 'error');
                });
            });
        });

        document.querySelectorAll('.btn-demo-quick-status').forEach((button) => {
            button.addEventListener('click', function () {
                const reqId = button.getAttribute('data-req-id');
                const status = button.getAttribute('data-status');
                if (!reqId || !status) {
                    return;
                }

                updateDemoStatus(reqId, status).catch((error) => {
                    notify(error.message || 'Unable to update demo request.', 'error');
                });
            });
        });
    }

    function bindBillingActions() {
        document.querySelectorAll('.btn-extend-trial').forEach((button) => {
            button.addEventListener('click', function () {
                const propertyId = button.getAttribute('data-property-id');
                if (!propertyId) {
                    return;
                }

                requestJson(`/superadmin/billing/extend-trial/${propertyId}`, 'POST')
                    .then(({ response, data }) => {
                        if (!response.ok || !data.success) {
                            throw new Error(data.message || 'Unable to extend trial.');
                        }
                        notify(data.message || 'Trial extended.', 'success');
                    })
                    .catch((error) => {
                        notify(error.message || 'Unable to extend trial.', 'error');
                    });
            });
        });

        document.querySelectorAll('.select-billing-tier').forEach((select) => {
            select.addEventListener('change', function () {
                const propertyId = select.getAttribute('data-property-id');
                const tier = select.value;
                if (!propertyId || !tier) {
                    return;
                }

                requestJson(`/superadmin/billing/change-tier/${propertyId}`, 'POST', { tier })
                    .then(({ response, data }) => {
                        if (!response.ok || !data.success) {
                            throw new Error(data.message || 'Unable to change plan tier.');
                        }
                        notify(data.message || `Plan updated to ${tier}.`, 'success');
                    })
                    .catch((error) => {
                        notify(error.message || 'Unable to change plan tier.', 'error');
                    });
            });
        });
    }

    function bindTenantToggle() {
        document.querySelectorAll('.btn-toggle-tenant').forEach((button) => {
            button.addEventListener('click', function () {
                const tenantId = button.getAttribute('data-tenant-id');
                if (!tenantId) {
                    return;
                }

                requestJson(`/superadmin/tenants/${tenantId}/toggle-active`, 'POST')
                    .then(({ response, data }) => {
                        if (!response.ok || !data.success) {
                            throw new Error(data.message || 'Unable to update tenant status.');
                        }

                        const isActive = Boolean(data.is_active);
                        const badge = document.getElementById(`tenant-active-badge-${tenantId}`);
                        if (badge) {
                            badge.className = `badge ${isActive ? 'text-bg-success' : 'text-bg-secondary'}`;
                            badge.textContent = isActive ? 'Active' : 'Inactive';
                        }

                        const row = document.getElementById(`tenant-row-${tenantId}`);
                        if (row) {
                            row.classList.toggle('sa-row-muted', !isActive);
                        }

                        button.classList.toggle('btn-danger', isActive);
                        button.classList.toggle('btn-success', !isActive);
                        button.textContent = isActive ? 'Deactivate' : 'Reactivate';

                        notify(data.message || 'Tenant status updated.', 'success');
                    })
                    .catch((error) => {
                        notify(error.message || 'Unable to update tenant status.', 'error');
                    });
            });
        });
    }

    function initRevenueCharts() {
        if (typeof Chart === 'undefined') {
            return;
        }

        const monthCanvas = document.getElementById('revenueByMonthChart');
        if (monthCanvas && Array.isArray(window.revenueByMonth)) {
            const labels = window.revenueByMonth.map((item) => item.month);
            const values = window.revenueByMonth.map((item) => Number(item.total_inr || 0));

            new Chart(monthCanvas, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [
                        {
                            label: 'Revenue (INR)',
                            data: values,
                            backgroundColor: '#7C3AED',
                            borderColor: '#7C3AED',
                            borderWidth: 1
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: function (value) {
                                    return `₹${value}`;
                                }
                            }
                        }
                    }
                }
            });
        }

        const tierCanvas = document.getElementById('revenueByTierChart');
        if (tierCanvas && Array.isArray(window.revenueByTier)) {
            const labels = window.revenueByTier.map((item) => (item.plan || 'starter').toUpperCase());
            const values = window.revenueByTier.map((item) => Number(item.total_inr || 0));

            new Chart(tierCanvas, {
                type: 'pie',
                data: {
                    labels,
                    datasets: [
                        {
                            data: values,
                            backgroundColor: ['#1E1B4B', '#7C3AED', '#D1D5DB']
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false
                }
            });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        bindPlatformStatsAutoRefresh();
        bindChangeTierModal();
        bindSuspendProperty();
        bindUserVerification();
        bindUserActiveToggle();
        bindUserRoleChange();
        bindUserDelete();
        bindDemoRequestUpdates();
        bindBillingActions();
        bindTenantToggle();
        initRevenueCharts();
    });
})();
