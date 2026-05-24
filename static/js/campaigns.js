(function () {
    function showMessage(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type || 'info');
        }
    }

    function postWithCsrf(url) {
        if (typeof fetchWithCSRF === 'function') {
            return fetchWithCSRF(url, { method: 'POST' });
        }
        return fetch(url, { method: 'POST' });
    }

    async function initCampaignPerformanceChart() {
        const canvas = document.getElementById('campaignPerfChart');
        if (!canvas || typeof campaignPerfData === 'undefined') {
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

        const labels = Array.isArray(campaignPerfData.hours) ? campaignPerfData.hours : [];
        const metrics = campaignPerfData.metrics || {};
        const impressions = Array.isArray(metrics.impressions_per_hour) ? metrics.impressions_per_hour : [];
        const clicks = Array.isArray(metrics.clicks_per_hour) ? metrics.clicks_per_hour : [];

        new Chart(canvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Impressions',
                        data: impressions,
                        borderColor: '#1A6FE8',
                        backgroundColor: 'rgba(26, 111, 232, 0.15)',
                        yAxisID: 'y1',
                        tension: 0.4,
                        fill: false,
                        pointRadius: 3
                    },
                    {
                        label: 'Clicks',
                        data: clicks,
                        borderColor: '#F97316',
                        backgroundColor: 'rgba(249, 115, 22, 0.15)',
                        yAxisID: 'y2',
                        tension: 0.4,
                        fill: false,
                        pointRadius: 3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y1: {
                        type: 'linear',
                        position: 'left',
                        beginAtZero: true,
                        ticks: { precision: 0 }
                    },
                    y2: {
                        type: 'linear',
                        position: 'right',
                        beginAtZero: true,
                        grid: { drawOnChartArea: false },
                        ticks: { precision: 0 }
                    }
                }
            }
        });
    }

    function animateCosBars() {
        const bars = Array.from(document.querySelectorAll('.cos-factor-fill'));
        if (!bars.length) {
            return;
        }

        bars.forEach((bar, index) => {
            const targetWidth = bar.getAttribute('data-width') || '0%';
            bar.style.width = '0%';
            window.setTimeout(() => {
                bar.style.width = targetWidth;
            }, index * 100);
        });
    }

    function updateActiveCount(delta) {
        const counter = document.getElementById('activeCampaignCount');
        if (!counter) {
            return;
        }
        const current = Number(counter.textContent || 0);
        counter.textContent = String(Math.max(0, current + delta));
    }

    function bindActivateButtons() {
        document.querySelectorAll('.btn-activate-campaign').forEach((button) => {
            button.addEventListener('click', function () {
                const campaignId = button.getAttribute('data-campaign-id');
                if (!campaignId) {
                    return;
                }

                button.disabled = true;
                const originalHtml = button.innerHTML;
                button.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';

                postWithCsrf(`/campaigns/activate/${campaignId}`)
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Activation failed');
                        }

                        const card = button.closest('.opportunity-card');
                        if (card) {
                            card.style.transition = 'opacity 0.3s ease';
                            card.style.opacity = '0';
                            window.setTimeout(() => {
                                card.remove();
                            }, 320);
                        }

                        updateActiveCount(1);
                        showMessage('\u2705 Campaign activated! Check Active Campaigns panel.', 'success');
                    })
                    .catch(() => {
                        button.disabled = false;
                        button.innerHTML = originalHtml;
                        showMessage('Unable to activate campaign right now', 'error');
                    });
            });
        });
    }

    function bindDismissButtons() {
        document.querySelectorAll('.btn-dismiss-campaign').forEach((button) => {
            button.addEventListener('click', function () {
                const campaignId = button.getAttribute('data-campaign-id');
                if (!campaignId) {
                    return;
                }

                if (!window.confirm('Dismiss this campaign opportunity?')) {
                    return;
                }

                button.disabled = true;
                postWithCsrf(`/campaigns/pause/${campaignId}`)
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Dismiss failed');
                        }

                        const card = button.closest('.opportunity-card');
                        if (card) {
                            card.style.transition = 'opacity 0.3s ease';
                            card.style.opacity = '0';
                            window.setTimeout(() => {
                                card.remove();
                            }, 320);
                        }

                        showMessage('Campaign dismissed', 'warning');
                    })
                    .catch(() => {
                        button.disabled = false;
                        showMessage('Unable to dismiss campaign', 'error');
                    });
            });
        });
    }

    function bindGenerateButton() {
        const button = document.getElementById('generateOpportunitiesBtn');
        if (!button) {
            return;
        }

        button.addEventListener('click', function () {
            const original = button.innerHTML;
            button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Analyzing...';

            postWithCsrf('/campaigns/generate')
                .then((response) => response.json().then((payload) => ({ response, payload })))
                .then(({ response, payload }) => {
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.error || 'Unable to run analysis');
                    }

                    showMessage('Analysis complete. New opportunities loading...', 'info');
                    window.setTimeout(() => {
                        window.location.reload();
                    }, 2000);
                })
                .catch(() => {
                    button.disabled = false;
                    button.innerHTML = original;
                    showMessage('Unable to generate opportunities right now', 'error');
                });
        });
    }

    function bindDetailToggleButtons() {
        document.querySelectorAll('.btn-toggle-campaign-status').forEach((button) => {
            button.addEventListener('click', function () {
                const campaignId = button.getAttribute('data-campaign-id');
                const targetStatus = button.getAttribute('data-target-status');
                if (!campaignId || !targetStatus) {
                    return;
                }

                const endpoint = targetStatus === 'active'
                    ? `/campaigns/activate/${campaignId}`
                    : `/campaigns/pause/${campaignId}`;

                button.disabled = true;
                postWithCsrf(endpoint)
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Unable to update status');
                        }
                        showMessage(payload.message || 'Campaign status updated', 'success');
                        window.setTimeout(() => window.location.reload(), 600);
                    })
                    .catch(() => {
                        button.disabled = false;
                        showMessage('Unable to update campaign status', 'error');
                    });
            });
        });
    }

    function bindEditCampaignModal() {
        const modalElement = document.getElementById('editCampaignModal');
        const form = document.getElementById('editCampaignForm');
        if (!modalElement || !form || typeof bootstrap === 'undefined') {
            return;
        }

        const modal = new bootstrap.Modal(modalElement);

        document.querySelectorAll('.btn-edit-campaign').forEach((button) => {
            button.addEventListener('click', function () {
                const campaignId = button.getAttribute('data-campaign-id');
                const campaignName = button.getAttribute('data-campaign-name') || '';
                const campaignCopy = button.getAttribute('data-campaign-copy') || '';
                const audience = button.getAttribute('data-target-audience') || '';
                const channel = button.getAttribute('data-channel') || 'in_app';

                const idField = form.querySelector('input[name="campaign_id"]');
                const nameField = form.querySelector('input[name="campaign_name"]');
                const copyField = form.querySelector('textarea[name="campaign_copy"]');
                const audienceField = form.querySelector('textarea[name="target_audience_description"]');
                const channelField = form.querySelector('select[name="channel"]');

                if (idField) {
                    idField.value = campaignId;
                }
                if (nameField) {
                    nameField.value = campaignName;
                }
                if (copyField) {
                    copyField.value = campaignCopy;
                }
                if (audienceField) {
                    audienceField.value = audience;
                }
                if (channelField) {
                    channelField.value = channel;
                }

                modal.show();
            });
        });

        form.addEventListener('submit', function (event) {
            event.preventDefault();

            const idField = form.querySelector('input[name="campaign_id"]');
            if (!idField || !idField.value) {
                return;
            }

            const campaignId = idField.value;
            const formData = new FormData(form);

            fetch(`/campaigns/${campaignId}/edit`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': (typeof getCsrfToken === 'function' ? getCsrfToken() : '')
                }
            })
                .then((response) => response.json().then((payload) => ({ response, payload })))
                .then(({ response, payload }) => {
                    if (!response.ok || !payload.success) {
                        throw new Error(payload.error || 'Unable to save campaign');
                    }

                    modal.hide();

                    const card = document.querySelector(`.opportunity-card[data-campaign-id="${campaignId}"]`);
                    if (card) {
                        const title = card.querySelector('.campaign-title');
                        const copy = card.querySelector('.campaign-copy-preview');
                        if (title) {
                            title.textContent = payload.campaign_name || title.textContent;
                        }
                        if (copy) {
                            copy.textContent = payload.campaign_copy || copy.textContent;
                        }
                    }

                    showMessage('Campaign updated successfully', 'success');
                })
                .catch(() => {
                    showMessage('Unable to save campaign changes', 'error');
                });
        });
    }

    function bindHistorySort() {
        const headers = document.querySelectorAll('th[data-sort]');
        if (!headers.length) {
            return;
        }

        headers.forEach((header) => {
            header.addEventListener('click', function () {
                const table = header.closest('table');
                const body = table ? table.querySelector('tbody') : null;
                if (!body) {
                    return;
                }

                const key = header.getAttribute('data-sort');
                const rows = Array.from(body.querySelectorAll('tr'));
                const currentDirection = header.getAttribute('data-direction') === 'asc' ? 'desc' : 'asc';
                header.setAttribute('data-direction', currentDirection);

                rows.sort((a, b) => {
                    const aCell = a.querySelector(`[data-key="${key}"]`);
                    const bCell = b.querySelector(`[data-key="${key}"]`);
                    const aText = (aCell ? aCell.getAttribute('data-sort-value') || aCell.textContent : '').trim();
                    const bText = (bCell ? bCell.getAttribute('data-sort-value') || bCell.textContent : '').trim();

                    const aNum = Number(aText.replace(/[^0-9.]/g, ''));
                    const bNum = Number(bText.replace(/[^0-9.]/g, ''));
                    const bothNumeric = !Number.isNaN(aNum) && !Number.isNaN(bNum) && aText !== '' && bText !== '';

                    if (bothNumeric) {
                        return currentDirection === 'asc' ? aNum - bNum : bNum - aNum;
                    }

                    return currentDirection === 'asc'
                        ? aText.localeCompare(bText)
                        : bText.localeCompare(aText);
                });

                rows.forEach((row) => body.appendChild(row));
            });
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initCampaignPerformanceChart();
        animateCosBars();
        bindActivateButtons();
        bindDismissButtons();
        bindGenerateButton();
        bindDetailToggleButtons();
        bindEditCampaignModal();
        bindHistorySort();
    });
})();
