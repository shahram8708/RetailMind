(function () {
    function showMessage(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type || 'info');
        }
    }

    function bindLogRows() {
        const rows = document.querySelectorAll('.log-row.expandable');
        if (!rows.length || typeof bootstrap === 'undefined') {
            return;
        }

        rows.forEach((row) => {
            row.addEventListener('click', function () {
                const target = row.getAttribute('data-bs-target');
                if (!target) {
                    return;
                }

                const panel = document.querySelector(target);
                if (!panel) {
                    return;
                }

                const collapse = bootstrap.Collapse.getOrCreateInstance(panel, { toggle: false });
                const isOpen = panel.classList.contains('show');

                if (isOpen) {
                    collapse.hide();
                    row.classList.remove('expanded');
                } else {
                    collapse.show();
                    row.classList.add('expanded');
                    row.classList.add('viewed');
                }
            });
        });
    }

    function badgeClassForValue(value) {
        if (value < 0.60) {
            return 'lenient';
        }
        if (value <= 0.75) {
            return 'balanced';
        }
        return 'strict';
    }

    function bindThresholdSliders() {
        const sliders = document.querySelectorAll('.threshold-slider');
        if (!sliders.length) {
            return;
        }

        sliders.forEach((slider) => {
            const badge = document.querySelector(`[data-badge-for="${slider.id}"]`);
            if (!badge) {
                return;
            }

            const updateBadge = function () {
                const value = Number(slider.value || 0);
                badge.textContent = value.toFixed(2);
                badge.classList.remove('lenient', 'balanced', 'strict');
                badge.classList.add(badgeClassForValue(value));
            };

            slider.addEventListener('input', updateBadge);
            updateBadge();
        });
    }

    function bindAutoApprovalWarnings() {
        const toggles = document.querySelectorAll('.auto-approval-toggle');
        if (!toggles.length) {
            return;
        }

        toggles.forEach((toggle) => {
            const container = toggle.closest('.mission-toggle-item');
            const warning = container ? container.querySelector('.auto-approval-warning') : null;
            if (!warning) {
                return;
            }

            const sync = function () {
                warning.classList.toggle('visible', toggle.checked);
            };

            toggle.addEventListener('change', sync);
            sync();
        });
    }

    function bindTestAlertButton() {
        const button = document.getElementById('testAlertBtn');
        if (!button || typeof fetchWithCSRF !== 'function') {
            return;
        }

        button.addEventListener('click', function () {
            const original = button.innerHTML;
            button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Sending...';

            fetchWithCSRF('/agent/settings/test-alert', {
                method: 'POST'
            })
                .then((response) => response.json().then((payload) => ({ response, payload })))
                .then(({ response, payload }) => {
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.error || 'Failed to send test alert');
                    }
                    showMessage('Test alert sent! Check your notifications.', 'success');
                })
                .catch(() => {
                    showMessage('Unable to send test alert', 'error');
                })
                .finally(() => {
                    button.disabled = false;
                    button.innerHTML = original;
                });
        });
    }

    function bindResetButton() {
        const button = document.getElementById('resetSettingsBtn');
        if (!button || typeof fetchWithCSRF !== 'function') {
            return;
        }

        button.addEventListener('click', function () {
            const confirmed = window.confirm('Reset all settings to defaults? This cannot be undone.');
            if (!confirmed) {
                return;
            }

            button.disabled = true;

            fetchWithCSRF('/agent/settings/reset', {
                method: 'POST'
            })
                .then((response) => response.json().then((payload) => ({ response, payload })))
                .then(({ response, payload }) => {
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.error || 'Unable to reset settings');
                    }
                    window.location.reload();
                })
                .catch(() => {
                    button.disabled = false;
                    showMessage('Unable to reset settings', 'error');
                });
        });
    }

    function bindLogScoreSlider() {
        const slider = document.getElementById('scoreMinSlider');
        const valueLabel = document.getElementById('scoreMinValue');
        if (!slider || !valueLabel) {
            return;
        }

        slider.addEventListener('input', function () {
            valueLabel.textContent = Number(slider.value || 0).toFixed(2);
        });
    }

    function initTooltips() {
        if (typeof bootstrap === 'undefined') {
            return;
        }

        const tooltipTriggers = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltipTriggers.forEach((el) => {
            bootstrap.Tooltip.getOrCreateInstance(el);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        bindLogRows();
        bindThresholdSliders();
        bindAutoApprovalWarnings();
        bindTestAlertButton();
        bindResetButton();
        bindLogScoreSlider();
        initTooltips();
    });
})();
