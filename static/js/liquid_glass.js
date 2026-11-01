/**
 * Daylight Liquid Glass Interactive Engine
 * - Real-time Cursor Specular Refraction (--mouse-x, --mouse-y, --spotlight-opacity)
 * - Liquid Click Ripple Wave on Buttons & Nav Pills
 */
(function () {
    'use strict';

    const GLASS_SELECTOR = '.card-custom, .navbar-custom, .login-card, .participant-card, .timer-cockpit, .attendance-card';
    const RIPPLE_SELECTOR = '.btn-custom, .navbar-custom .nav-link';

    let rafId = null;
    let lastEvent = null;

    function updateSpecularPosition() {
        rafId = null;
        if (!lastEvent) return;

        const target = lastEvent.target;
        if (!target || typeof target.closest !== 'function') return;

        const surfaces = document.querySelectorAll(GLASS_SELECTOR);
        const clientX = lastEvent.clientX;
        const clientY = lastEvent.clientY;

        for (let i = 0; i < surfaces.length; i++) {
            const el = surfaces[i];
            const rect = el.getBoundingClientRect();

            // Check if pointer is near or inside the element
            const isNear =
                clientX >= rect.left - 120 &&
                clientX <= rect.right + 120 &&
                clientY >= rect.top - 120 &&
                clientY <= rect.bottom + 120;

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
    }

    document.addEventListener('pointermove', function (e) {
        lastEvent = e;
        if (!rafId) {
            rafId = window.requestAnimationFrame(updateSpecularPosition);
        }
    }, { passive: true });

    document.addEventListener('pointerleave', function () {
        const surfaces = document.querySelectorAll(GLASS_SELECTOR);
        for (let i = 0; i < surfaces.length; i++) {
            surfaces[i].style.setProperty('--spotlight-opacity', '0');
        }
    }, { passive: true });

    // Liquid Click Ripple Effect
    document.addEventListener('pointerdown', function (e) {
        const btn = e.target.closest ? e.target.closest(RIPPLE_SELECTOR) : null;
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
})();

