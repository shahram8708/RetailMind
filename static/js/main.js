function showToast(message, type = 'success', duration = 5000) {
    let container = document.querySelector('.toast-container');

    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    window.setTimeout(() => {
        toast.style.animation = 'toastFadeOut 0.25s ease forwards';
        window.setTimeout(() => {
            toast.remove();
        }, 250);
    }, duration);
}

let chartJsPromise = null;

function ensureChartJs() {
    if (typeof Chart !== 'undefined') {
        return Promise.resolve(true);
    }

    if (chartJsPromise) {
        return chartJsPromise;
    }

    chartJsPromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js';
        script.async = true;
        script.onload = () => resolve(true);
        script.onerror = () => reject(new Error('Chart.js failed to load'));
        document.head.appendChild(script);
    });

    return chartJsPromise;
}

function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

async function fetchWithCSRF(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken(),
        ...(options.headers || {})
    };

    if (!navigator.onLine && window.RetailMindOffline && typeof window.RetailMindOffline.queueRequest === 'function' && method !== 'GET') {
        await window.RetailMindOffline.queueRequest({
            url,
            method,
            headers,
            body: options.body || null
        });

        return new Response(
            JSON.stringify({ success: true, queued: true }),
            { status: 202, headers: { 'Content-Type': 'application/json' } }
        );
    }

    return fetch(url, {
        ...options,
        headers
    });
}

function applyTheme(value) {
    const root = document.documentElement;
    const resolved = value === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
        : value;

    root.setAttribute('data-theme', resolved);
}

function initThemeToggle() {
    const buttons = document.querySelectorAll('[data-theme-value]');
    if (!buttons.length) {
        return;
    }

    const stored = localStorage.getItem('theme') || 'system';
    applyTheme(stored);

    buttons.forEach((button) => {
        button.addEventListener('click', function () {
            const value = button.getAttribute('data-theme-value');
            if (!value) {
                return;
            }
            localStorage.setItem('theme', value);
            applyTheme(value);
        });
    });

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
        const current = localStorage.getItem('theme') || 'system';
        if (current === 'system') {
            applyTheme('system');
        }
    });
}

function pollNotificationCount() {
    if (!document.getElementById('notif-count-badge')) {
        return;
    }

    fetch('/api/notifications/unread')
        .then((response) => response.json())
        .then((data) => {
            const badge = document.getElementById('notif-count-badge');
            const count = Number((data && data.count !== undefined ? data.count : data?.data?.count) || 0);

            if (count > 0) {
                badge.textContent = String(count);
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }
        })
        .catch(() => {
            // Silent failure for non-authenticated pages or unavailable endpoints.
        });
}

function checkPasswordStrength(password) {
    const checks = {
        length: password.length >= 8,
        upper: /[A-Z]/.test(password),
        lower: /[a-z]/.test(password),
        digit: /\d/.test(password),
        special: /[^A-Za-z0-9]/.test(password)
    };

    let score = 0;
    const passed = [checks.length, checks.upper, checks.lower, checks.digit, checks.special].filter(Boolean).length;

    if (!checks.length) {
        score = 0;
    } else if (passed <= 2) {
        score = 1;
    } else if (passed === 3) {
        score = 2;
    } else if (passed === 4) {
        score = 3;
    } else {
        score = 4;
    }

    const strengthBar = document.getElementById('password-strength-bar');
    if (strengthBar) {
        const dots = strengthBar.querySelectorAll('.strength-dot');
        dots.forEach((dot, idx) => {
            dot.classList.remove('active-1', 'active-2', 'active-3', 'active-4');
            if (idx < score) {
                dot.classList.add(`active-${score}`);
            }
        });
    }

    return score;
}

document.addEventListener('DOMContentLoaded', function () {
    const currentPath = window.location.pathname;

    document.querySelectorAll('.nav-link').forEach((link) => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });

    if (document.getElementById('notif-count-badge')) {
        pollNotificationCount();
        window.setInterval(pollNotificationCount, 60000);
    }

    initThemeToggle();

    const passwordInputs = document.querySelectorAll('input[type="password"]');
    passwordInputs.forEach((input) => {
        if (input.id && input.id.toLowerCase().includes('password') && !input.id.toLowerCase().includes('confirm')) {
            input.addEventListener('input', () => {
                checkPasswordStrength(input.value || '');
            });
        }
    });
});

window.setTimeout(() => {
    document.querySelectorAll('.alert.auto-dismiss').forEach((element) => {
        element.style.opacity = '0';
        element.style.transition = 'opacity 0.5s';
        window.setTimeout(() => element.remove(), 500);
    });
}, 6000);

window.ensureChartJs = ensureChartJs;
