/**
 * Magic UI × Daylight Liquid Glass Interactive Engine
 * - Magic Card Proximity Border Mask & Inner Spotlight (--mouse-x, --mouse-y, --spotlight-opacity)
 * - Magic Dock Proximity Magnification (--dock-scale on .navbar-custom .nav-link)
 * - Magic Number Ticker (smooth count-up animation on count badges)
 * - Liquid Click Ripple Wave on Buttons & Nav Pills
 */
(function () {
    'use strict';

    const GLASS_SELECTOR = '.card-custom, .navbar-custom, .login-card, .participant-card, .timer-cockpit, .attendance-card';
    const DOCK_ITEM_SELECTOR = '.navbar-custom .nav-link';
    const RIPPLE_SELECTOR = '.btn-custom, .navbar-custom .nav-link';
    const TICKER_BADGE_IDS = [
        'devicesCountBadge',
        'channelsCountBadge',
        'usersCountBadge',
        'modelsCountBadge',
        'meetingsCountBadge'
    ];

    let rafId = null;
    let lastEvent = null;

    function updateInteractiveEffects() {
        rafId = null;
        if (!lastEvent) return;

        const clientX = lastEvent.clientX;
        const clientY = lastEvent.clientY;

        // 1. Magic Card Proximity Border Mask & Inner Spotlight
        const surfaces = document.querySelectorAll(GLASS_SELECTOR);
        for (let i = 0; i < surfaces.length; i++) {
            const el = surfaces[i];
            const rect = el.getBoundingClientRect();

            const isNear =
                clientX >= rect.left - 160 &&
                clientX <= rect.right + 160 &&
                clientY >= rect.top - 160 &&
                clientY <= rect.bottom + 160;

            if (isNear) {
                const x = clientX - rect.left;
                const y = clientY - rect.top;
                el.style.setProperty('--mouse-x', `${x}px`);
                el.style.setProperty('--mouse-y', `${y}px`);
                el.style.setProperty('--spotlight-opacity', '1');
            } else {
                el.style.setProperty('--spotlight-opacity', '0');
            }
        }

        // 2. Magic UI Dock Magnification on Desktop Nav Links
        if (window.innerWidth >= 992) {
            const nav = document.querySelector('.navbar-custom');
            const dockItems = document.querySelectorAll(DOCK_ITEM_SELECTOR);
            if (nav && dockItems.length > 0) {
                const navRect = nav.getBoundingClientRect();
                const inNavZone =
                    clientY >= navRect.top - 40 &&
                    clientY <= navRect.bottom + 40 &&
                    clientX >= navRect.left - 40 &&
                    clientX <= navRect.right + 40;

                for (let j = 0; j < dockItems.length; j++) {
                    const item = dockItems[j];
                    if (!inNavZone) {
                        item.style.setProperty('--dock-scale', '1');
                        continue;
                    }
                    const itemRect = item.getBoundingClientRect();
                    const itemCenterX = itemRect.left + itemRect.width / 2;
                    const itemCenterY = itemRect.top + itemRect.height / 2;
                    const dist = Math.hypot(clientX - itemCenterX, clientY - itemCenterY);
                    const maxDist = 140;

                    if (dist < maxDist) {
                        // Gaussian-like smooth magnification up to 1.11x
                        const ratio = 1 - dist / maxDist;
                        const scale = 1 + 0.11 * (ratio * ratio);
                        item.style.setProperty('--dock-scale', scale.toFixed(3));
                    } else {
                        item.style.setProperty('--dock-scale', '1');
                    }
                }
            }
        }
    }

    document.addEventListener('pointermove', function (e) {
        lastEvent = e;
        if (!rafId) {
            rafId = window.requestAnimationFrame(updateInteractiveEffects);
        }
    }, { passive: true });

    document.addEventListener('pointerleave', function () {
        const surfaces = document.querySelectorAll(GLASS_SELECTOR);
        for (let i = 0; i < surfaces.length; i++) {
            surfaces[i].style.setProperty('--spotlight-opacity', '0');
        }
        const dockItems = document.querySelectorAll(DOCK_ITEM_SELECTOR);
        for (let j = 0; j < dockItems.length; j++) {
            dockItems[j].style.setProperty('--dock-scale', '1');
        }
    }, { passive: true });

    // 3. Liquid Click Ripple Effect
    document.addEventListener('pointerdown', function (e) {
        const btn = e.target && e.target.closest ? e.target.closest(RIPPLE_SELECTOR) : null;
        if (!btn || btn.disabled) return;

        const rect = btn.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        const ripple = document.createElement('span');
        ripple.className = 'liquid-click-ripple';
        ripple.style.width = `${size}px`;
        ripple.style.height = `${size}px`;
        ripple.style.left = `${e.clientX - rect.left - size / 2}px`;
        ripple.style.top = `${e.clientY - rect.top - size / 2}px`;

        btn.appendChild(ripple);
        setTimeout(function () {
            ripple.remove();
        }, 680);
    }, { passive: true });

    // 4. Magic UI Number Ticker for Count Badges
    function initNumberTickers() {
        TICKER_BADGE_IDS.forEach(function (id) {
            const badge = document.getElementById(id);
            if (!badge) return;

            let isAnimating = false;
            let lastTargetText = badge.textContent;

            const observer = new MutationObserver(function () {
                if (isAnimating) return;
                const fullText = badge.textContent || '';
                if (fullText === lastTargetText) return;
                lastTargetText = fullText;

                // Match leading integer (e.g. "12 อุปกรณ์" or "2/5 ติดตั้งแล้ว")
                const match = fullText.match(/^(\d+)(.*)$/);
                if (!match) return;

                const targetNum = parseInt(match[1], 10);
                const suffix = match[2];
                if (isNaN(targetNum) || targetNum <= 0) return;

                isAnimating = true;
                const duration = 520;
                const startTime = performance.now();

                function tick(now) {
                    const elapsed = now - startTime;
                    const progress = Math.min(1, elapsed / duration);
                    // Ease-out cubic
                    const eased = 1 - Math.pow(1 - progress, 3);
                    const currentNum = Math.round(targetNum * eased);
                    badge.textContent = `${currentNum}${suffix}`;

                    if (progress < 1) {
                        window.requestAnimationFrame(tick);
                    } else {
                        badge.textContent = fullText;
                        isAnimating = false;
                    }
                }

                window.requestAnimationFrame(tick);
            });

            observer.observe(badge, { childList: true, characterData: true, subtree: true });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initNumberTickers);
    } else {
        initNumberTickers();
    }
})();
