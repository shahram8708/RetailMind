(function () {
    function notify(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type || 'info');
        }
    }

    function setLoading(isLoading) {
        const overlay = document.getElementById('shopperSearchLoading');
        if (!overlay) {
            return;
        }
        overlay.classList.toggle('active', Boolean(isLoading));
    }

    async function runShopperSearch(rawQuery) {
        const query = (rawQuery || '').trim();
        const input = document.getElementById('shopperSearchInput');

        if (!query) {
            if (input) {
                input.classList.add('error');
                window.setTimeout(() => input.classList.remove('error'), 1200);
            }
            return;
        }

        if (typeof SHOPPER_API_URL === 'undefined' || typeof PROPERTY_ID === 'undefined') {
            notify('Search configuration is unavailable on this page.', 'error');
            return;
        }

        setLoading(true);

        try {
            const response = await fetch(SHOPPER_API_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    query: query,
                    property_id: PROPERTY_ID
                })
            });

            const payload = await response.json();

            if (!response.ok || !payload.success) {
                throw new Error(payload.error || 'Search failed');
            }

            if (payload.query_id && payload.redirect_url) {
                window.location.href = payload.redirect_url;
                return;
            }

            throw new Error('No result redirect returned');
        } catch (_error) {
            setLoading(false);
            notify('Search failed. Please try again.', 'error');
        }
    }

    function bindShopperSearchPage() {
        const input = document.getElementById('shopperSearchInput');
        const form = document.getElementById('shopperSearchForm');

        if (!input || !form) {
            return;
        }

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            runShopperSearch(input.value);
        });

        input.addEventListener('input', function () {
            input.classList.remove('error');
        });

        document.querySelectorAll('.category-btn').forEach((button) => {
            button.addEventListener('click', function () {
                const category = button.getAttribute('data-category') || '';
                input.value = category;
                runShopperSearch(category);
            });
        });

        document.querySelectorAll('.promotion-card').forEach((card) => {
            card.addEventListener('click', function () {
                const tenantName = card.getAttribute('data-tenant-name') || '';
                input.value = tenantName;
                runShopperSearch(tenantName);
            });
        });

        document.querySelectorAll('.recent-search-tag').forEach((tag) => {
            tag.addEventListener('click', function () {
                const query = (tag.textContent || '').replace('🔍', '').trim();
                input.value = query;
                runShopperSearch(query);
            });
        });

        const clearRecentBtn = document.getElementById('clearRecentSearchesBtn');
        if (clearRecentBtn) {
            clearRecentBtn.addEventListener('click', async function () {
                try {
                    if (typeof CLEAR_RECENT_SEARCHES_URL !== 'undefined') {
                        await fetch(CLEAR_RECENT_SEARCHES_URL, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            }
                        });
                    }
                } catch (_error) {
                    // Ignore clear failures and still update UI.
                }

                const section = document.getElementById('recentSearchesSection');
                if (section) {
                    section.remove();
                }
            });
        }
    }

    function parseNavSteps(navText) {
        return String(navText || '')
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0)
            .map((line) => line.replace(/^\d+\.\s*/, ''));
    }

    function setModalFloor(floorValue) {
        document.querySelectorAll('#modalFloorIndicator .floor-pill').forEach((pill) => {
            const isActive = String(pill.getAttribute('data-floor')) === String(floorValue);
            pill.classList.toggle('active', isActive);
        });
    }

    function highlightPinBySku(skuId) {
        document.querySelectorAll('.floor-pin').forEach((pin) => {
            const isActive = pin.getAttribute('data-sku-id') === String(skuId);
            pin.classList.toggle('active', isActive);
        });
    }

    function applyFloorFilter(floorValue) {
        document.querySelectorAll('.floor-pin').forEach((pin) => {
            const match = String(pin.getAttribute('data-floor')) === String(floorValue);
            pin.classList.toggle('hidden', !match);
        });
    }

    function bindResultsPage() {
        const navModalElement = document.getElementById('navModal');
        const directionsButtons = document.querySelectorAll('.btn-get-directions');
        const copyButtons = document.querySelectorAll('.btn-copy-directions');
        const resultCards = document.querySelectorAll('.result-card');

        if (directionsButtons.length === 0 && copyButtons.length === 0 && resultCards.length === 0) {
            return;
        }

        let navModal = null;
        if (navModalElement && typeof bootstrap !== 'undefined') {
            navModal = new bootstrap.Modal(navModalElement);
        }

        directionsButtons.forEach((button) => {
            button.addEventListener('click', function () {
                const tenantName = button.getAttribute('data-tenant-name') || 'Store';
                const floor = button.getAttribute('data-floor') || '0';
                const zone = button.getAttribute('data-zone') || '';
                const unit = button.getAttribute('data-unit') || '';
                const skuId = button.getAttribute('data-sku-id') || '';
                const navText = button.getAttribute('data-nav-instructions') || '';

                const storeNameEl = document.getElementById('modalStoreName');
                const metaEl = document.getElementById('modalStoreMeta');
                const stepsEl = document.getElementById('modalNavSteps');

                if (storeNameEl) {
                    storeNameEl.textContent = tenantName;
                }
                if (metaEl) {
                    metaEl.textContent = `Zone ${zone} · ${String(floor) === '0' ? 'Ground Floor' : `Floor ${floor}`} · Unit ${unit}`;
                }
                if (stepsEl) {
                    stepsEl.innerHTML = '';
                    const steps = parseNavSteps(navText);
                    if (!steps.length) {
                        const li = document.createElement('li');
                        li.textContent = 'Directions are temporarily unavailable. Please ask the information desk.';
                        stepsEl.appendChild(li);
                    } else {
                        steps.forEach((step) => {
                            const li = document.createElement('li');
                            li.textContent = step;
                            stepsEl.appendChild(li);
                        });
                    }
                }

                setModalFloor(floor);
                highlightPinBySku(skuId);

                if (typeof queryId !== 'undefined' && typeof logClickUrl !== 'undefined') {
                    fetch(logClickUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            query_id: queryId,
                            sku_id: skuId
                        })
                    }).catch(() => {
                        // Silent logging failure.
                    });
                }

                if (navModal) {
                    navModal.show();
                }
            });
        });

        copyButtons.forEach((button) => {
            button.addEventListener('click', async function () {
                const navText = button.getAttribute('data-nav-instructions') || '';
                try {
                    await navigator.clipboard.writeText(navText);
                    const oldText = button.textContent;
                    button.textContent = 'Copied! ✓';
                    window.setTimeout(() => {
                        button.textContent = oldText;
                    }, 2000);
                } catch (_error) {
                    notify('Unable to copy directions.', 'error');
                }
            });
        });

        resultCards.forEach((card) => {
            card.addEventListener('mouseenter', function () {
                const skuId = card.getAttribute('data-sku-id');
                if (skuId) {
                    highlightPinBySku(skuId);
                }
            });
        });

        document.querySelectorAll('.floor-selector-tabs [data-floor]').forEach((button) => {
            button.addEventListener('click', function () {
                const floorValue = button.getAttribute('data-floor');
                document.querySelectorAll('.floor-selector-tabs [data-floor]').forEach((tab) => {
                    tab.classList.toggle('active', tab === button);
                });
                applyFloorFilter(floorValue);
            });
        });

        if (typeof searchResults !== 'undefined' && Array.isArray(searchResults) && searchResults.length) {
            const initialFloor = searchResults[0].tenant_floor;
            document.querySelectorAll('.floor-selector-tabs [data-floor]').forEach((tab) => {
                tab.classList.toggle('active', String(tab.getAttribute('data-floor')) === String(initialFloor));
            });
            applyFloorFilter(initialFloor);
            highlightPinBySku(searchResults[0].sku_id);
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        bindShopperSearchPage();
        bindResultsPage();
    });
})();
