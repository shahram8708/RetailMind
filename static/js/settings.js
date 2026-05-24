(function () {
    function notify(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type || 'info');
        }
    }

    function roleLabel(roleValue) {
        const map = {
            store_manager: 'Store Manager',
            marketing_manager: 'Marketing Manager',
            facility_manager: 'Facility Manager'
        };
        return map[roleValue] || roleValue;
    }

    function roleBadgeClass(roleValue) {
        return `role-${roleValue}`;
    }

    function bindTeamRoleChanges() {
        const selects = document.querySelectorAll('.select-change-role');
        if (!selects.length || typeof fetchWithCSRF !== 'function') {
            return;
        }

        selects.forEach((select) => {
            select.addEventListener('focus', function () {
                select.dataset.originalValue = select.value;
            });

            select.addEventListener('change', function () {
                const userId = select.getAttribute('data-user-id');
                const userName = select.getAttribute('data-user-name') || 'this member';
                const newRole = select.value;
                const original = select.dataset.originalValue || select.value;

                if (!userId) {
                    return;
                }

                const confirmed = window.confirm(`Change ${userName}'s role to ${roleLabel(newRole)}?`);
                if (!confirmed) {
                    select.value = original;
                    return;
                }

                fetchWithCSRF(`/settings/team/change-role/${userId}`, {
                    method: 'POST',
                    body: JSON.stringify({ role: newRole })
                })
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Role update failed');
                        }

                        const badge = document.getElementById(`role-badge-${userId}`);
                        if (badge) {
                            badge.textContent = roleLabel(newRole);
                            badge.className = `badge role-badge ${roleBadgeClass(newRole)}`;
                        }

                        notify(`Role updated for ${userName}`, 'success');
                        select.dataset.originalValue = newRole;
                    })
                    .catch((error) => {
                        select.value = original;
                        notify(error.message || 'Unable to update role', 'error');
                    });
            });
        });
    }

    function bindTeamDeactivate() {
        const buttons = document.querySelectorAll('.btn-deactivate-member');
        if (!buttons.length || typeof fetchWithCSRF !== 'function') {
            return;
        }

        buttons.forEach((button) => {
            button.addEventListener('click', function () {
                const userId = button.getAttribute('data-user-id');
                const userName = button.getAttribute('data-user-name') || 'this member';

                if (!userId) {
                    return;
                }

                const confirmed = window.confirm(`Deactivate ${userName}? They will lose access to RetailMind.`);
                if (!confirmed) {
                    return;
                }

                fetchWithCSRF(`/settings/team/remove/${userId}`, {
                    method: 'POST'
                })
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        if (!response.ok || !payload.success) {
                            throw new Error(payload.error || 'Deactivation failed');
                        }

                        const row = document.getElementById(`member-row-${userId}`);
                        if (row) {
                            row.style.opacity = '0.55';
                            row.classList.add('table-secondary');
                        }

                        const statusBadge = document.getElementById(`status-badge-${userId}`);
                        if (statusBadge) {
                            statusBadge.textContent = 'Deactivated';
                            statusBadge.className = 'badge text-bg-secondary';
                        }

                        button.disabled = true;
                        button.textContent = 'Deactivated';

                        notify(payload.message || `${userName} deactivated`, 'success');
                    })
                    .catch((error) => {
                        notify(error.message || 'Unable to deactivate member', 'error');
                    });
            });
        });
    }

    async function createOrder(planName, billingCycle, propertyId) {
        if (typeof PAYMENT_CREATE_ORDER_URL === 'undefined') {
            throw new Error('Payment create order endpoint is not configured.');
        }

        const response = await fetchWithCSRF(PAYMENT_CREATE_ORDER_URL, {
            method: 'POST',
            body: JSON.stringify({
                plan_name: planName,
                billing_cycle: billingCycle,
                property_id: propertyId
            })
        });

        const payload = await response.json();
        if (!response.ok || !payload.success) {
            throw new Error(payload.error || 'Unable to create order.');
        }

        return payload;
    }

    async function verifyPayment(paymentId, orderId, signature, planName, billingCycle, propertyId) {
        if (typeof PAYMENT_VERIFY_URL === 'undefined') {
            throw new Error('Payment verify endpoint is not configured.');
        }

        const response = await fetchWithCSRF(PAYMENT_VERIFY_URL, {
            method: 'POST',
            body: JSON.stringify({
                razorpay_payment_id: paymentId,
                razorpay_order_id: orderId,
                razorpay_signature: signature,
                plan_name: planName,
                billing_cycle: billingCycle,
                property_id: propertyId
            })
        });

        const payload = await response.json();
        if (!response.ok || !payload.success) {
            throw new Error(payload.error || 'Payment verification failed.');
        }

        return payload;
    }

    async function initiatePayment(planName, billingCycle, doneCallback) {
        if (typeof RAZORPAY_ENABLED === 'undefined' || !RAZORPAY_ENABLED) {
            notify('Payment gateway not configured.', 'error');
            if (typeof doneCallback === 'function') {
                doneCallback();
            }
            return;
        }

        const propertyId = typeof BILLING_PROPERTY_ID === 'undefined' ? null : BILLING_PROPERTY_ID;

        if (typeof Razorpay === 'undefined') {
            notify('Razorpay SDK failed to load.', 'error');
            if (typeof doneCallback === 'function') {
                doneCallback();
            }
            return;
        }

        try {
            const orderData = await createOrder(planName, billingCycle, propertyId);

            const options = {
                key: orderData.key_id,
                amount: orderData.amount_paise,
                currency: 'INR',
                name: 'RetailMind',
                description: `${orderData.plan_display_name} Subscription`,
                order_id: orderData.order_id,
                handler: async function (response) {
                    try {
                        await verifyPayment(
                            response.razorpay_payment_id,
                            response.razorpay_order_id,
                            response.razorpay_signature,
                            planName,
                            billingCycle,
                            propertyId
                        );

                        notify(`Payment successful! Your ${planName} plan is now active.`, 'success');
                        window.setTimeout(() => {
                            window.location.reload();
                        }, 2000);
                    } catch (error) {
                        notify(error.message || 'Payment verification failed. Contact support.', 'error');
                        if (typeof doneCallback === 'function') {
                            doneCallback();
                        }
                    }
                },
                prefill: {
                    name: typeof CURRENT_USER_NAME === 'undefined' ? '' : CURRENT_USER_NAME,
                    email: typeof CURRENT_USER_EMAIL === 'undefined' ? '' : CURRENT_USER_EMAIL,
                    contact: typeof CURRENT_USER_PHONE === 'undefined' ? '' : CURRENT_USER_PHONE
                },
                theme: {
                    color: '#1A6FE8'
                },
                modal: {
                    ondismiss: function () {
                        notify('Payment cancelled.', 'info');
                        if (typeof doneCallback === 'function') {
                            doneCallback();
                        }
                    }
                }
            };

            const rzp = new Razorpay(options);
            rzp.open();
        } catch (error) {
            notify(error.message || 'Unable to initiate payment.', 'error');
            if (typeof doneCallback === 'function') {
                doneCallback();
            }
        }
    }

    function bindBillingActions() {
        const upgradeButtons = document.querySelectorAll('.btn-upgrade-plan');

        upgradeButtons.forEach((button) => {
            button.addEventListener('click', function () {
                const planName = button.getAttribute('data-plan-name');
                const billingCycle = button.getAttribute('data-billing-cycle') || 'monthly';
                const originalText = button.textContent;

                upgradeButtons.forEach((btn) => {
                    btn.disabled = true;
                });

                button.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Processing';

                initiatePayment(planName, billingCycle, function () {
                    upgradeButtons.forEach((btn) => {
                        btn.disabled = false;
                    });
                    button.textContent = originalText;
                });
            });
        });

        const updateBillingBtn = document.getElementById('updateBillingMethodBtn');
        if (updateBillingBtn) {
            updateBillingBtn.addEventListener('click', function () {
                notify('Update billing method is coming soon.', 'info');
            });
        }

        const cancelBtn = document.getElementById('cancelSubscriptionBtn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', function () {
                const confirmed = window.confirm('Are you sure you want to cancel your subscription?');
                if (!confirmed) {
                    return;
                }
                notify('Cancellation workflow will be added in the next release.', 'info');
            });
        }

        const contactSalesBtn = document.getElementById('contactSalesBtn');
        if (contactSalesBtn) {
            contactSalesBtn.addEventListener('click', function () {
                window.location.href = 'mailto:sales@retailmind.ai';
            });
        }
    }

    function updateIntegrationStatus(type, success) {
        const dot = document.getElementById(`status-dot-${type}`);
        if (!dot) {
            return;
        }

        dot.classList.remove('connected', 'simulator', 'not_connected');
        dot.classList.add(success ? 'connected' : 'not_connected');
    }

    function bindIntegrationTests() {
        const buttons = document.querySelectorAll('.btn-test-integration');
        if (!buttons.length || typeof fetchWithCSRF !== 'function') {
            return;
        }

        buttons.forEach((button) => {
            button.addEventListener('click', function () {
                const integrationType = button.getAttribute('data-integration-type');
                const endpoint = button.getAttribute('data-test-url');
                const resultLabel = document.getElementById(`test-result-${integrationType}`);
                const original = button.innerHTML;

                if (!endpoint) {
                    return;
                }

                button.disabled = true;
                button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Testing';

                fetchWithCSRF(endpoint, { method: 'POST' })
                    .then((response) => response.json().then((payload) => ({ response, payload })))
                    .then(({ response, payload }) => {
                        const ok = response.ok && payload.success;
                        if (resultLabel) {
                            resultLabel.textContent = payload.message || (ok ? 'Connection successful.' : 'Connection failed.');
                            resultLabel.className = `small ms-2 test-result ${ok ? 'text-success' : 'text-danger'}`;
                        }
                        updateIntegrationStatus(integrationType, ok);
                        notify(payload.message || (ok ? 'Connection successful.' : 'Connection failed.'), ok ? 'success' : 'error');
                    })
                    .catch(() => {
                        if (resultLabel) {
                            resultLabel.textContent = 'Connection test failed.';
                            resultLabel.className = 'small ms-2 test-result text-danger';
                        }
                        updateIntegrationStatus(integrationType, false);
                        notify('Connection test failed.', 'error');
                    })
                    .finally(() => {
                        window.setTimeout(() => {
                            button.disabled = false;
                            button.innerHTML = original;
                        }, 3000);
                    });
            });
        });
    }

    function passwordStrength(password) {
        let score = 0;
        if (password.length >= 8) score += 1;
        if (/[A-Z]/.test(password)) score += 1;
        if (/[a-z]/.test(password)) score += 1;
        if (/\d/.test(password)) score += 1;
        if (/[^A-Za-z0-9]/.test(password)) score += 1;
        return score;
    }

    function bindPasswordStrength() {
        const input = document.getElementById('new-password-input');
        const progress = document.getElementById('password-strength-progress');
        const text = document.getElementById('password-strength-text');
        if (!input || !progress || !text) {
            return;
        }

        const labels = ['Very weak', 'Weak', 'Fair', 'Good', 'Strong'];
        const colors = ['#EF4444', '#F97316', '#F59E0B', '#1A6FE8', '#10B981'];

        input.addEventListener('input', function () {
            const score = passwordStrength(input.value || '');
            const percent = (score / 5) * 100;
            progress.style.width = `${percent}%`;
            progress.style.backgroundColor = colors[Math.max(score - 1, 0)] || '#E5E7EB';
            text.textContent = input.value ? labels[Math.max(score - 1, 0)] : 'Enter a new password';
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        bindTeamRoleChanges();
        bindTeamDeactivate();
        bindBillingActions();
        bindIntegrationTests();
        bindPasswordStrength();
    });
})();
