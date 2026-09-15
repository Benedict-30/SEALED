// ==========================================
// Theme Color Picker
// Handles any .theme-picker block: preset swatches,
// native color input, editable hex field, copy button,
// and a live preview card driven by CSS variables.
// ==========================================
(function() {
    'use strict';

    function normalizeHex(hex) {
        hex = (hex || '').trim();
        if (hex.charAt(0) !== '#') hex = '#' + hex;
        if (!/^#([0-9a-fA-F]{6})$/.test(hex)) return null;
        return hex.toLowerCase();
    }

    function hexToRgb(hex) {
        const h = normalizeHex(hex);
        if (!h) return null;
        return {
            r: parseInt(h.slice(1, 3), 16),
            g: parseInt(h.slice(3, 5), 16),
            b: parseInt(h.slice(5, 7), 16)
        };
    }

    // Mix `hex` toward a target channel value (255 = white, 0 = black)
    function mix(hex, target, ratio) {
        const rgb = hexToRgb(hex);
        if (!rgb) return hex;
        const m = (c) => Math.round(c + (target - c) * ratio);
        return '#' + [m(rgb.r), m(rgb.g), m(rgb.b)]
            .map(c => c.toString(16).padStart(2, '0'))
            .join('');
    }

    function isLight(hex) {
        const rgb = hexToRgb(hex);
        if (!rgb) return false;
        return (0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b) > 150;
    }

    document.querySelectorAll('.theme-picker').forEach(picker => {
        const hidden =
            picker.querySelector('input[name="theme_color"]') ||
            (picker.dataset.form
                ? document.querySelector('#' + picker.dataset.form + ' input[name="theme_color"]')
                : null);
        if (!hidden) return;

        const swatches = picker.querySelectorAll('.color-swatch');
        const colorInput = picker.querySelector('.color-input');
        const hexInput = picker.querySelector('.color-hex-input');
        const copyBtn = picker.querySelector('.color-copy-btn');
        const copyIcon = copyBtn ? copyBtn.querySelector('i') : null;
        const preview = picker.querySelector('.theme-preview');

        function apply(color, swatchEl) {
            const hex = normalizeHex(color) || normalizeHex(hidden.value) || '#059669';
            hidden.value = hex;
            if (hexInput) {
                hexInput.value = hex.toUpperCase();
                hexInput.classList.remove('invalid');
            }
            if (colorInput) colorInput.value = hex;
            swatches.forEach(s => s.classList.remove('selected'));
            if (swatchEl) swatchEl.classList.add('selected');
            if (preview) {
                preview.style.setProperty('--tp-primary', hex);
                preview.style.setProperty('--tp-primary-dark', mix(hex, 0, 0.35));
                preview.style.setProperty('--tp-primary-light', mix(hex, 255, 0.55));
                preview.style.setProperty('--tp-primary-bg', mix(hex, 255, 0.9));
                preview.style.setProperty('--tp-check', isLight(hex) ? '#1C1917' : '#FFFFFF');
            }
            picker.dispatchEvent(new CustomEvent('themechange', { detail: { hex: hex } }));
        }

        swatches.forEach(swatch => {
            swatch.addEventListener('click', function() {
                apply(this.dataset.color, this);
            });
        });

        if (colorInput) {
            colorInput.addEventListener('input', function() {
                apply(this.value, null);
            });
        }

        if (hexInput) {
            hexInput.addEventListener('input', function() {
                const hex = normalizeHex(this.value);
                if (hex) {
                    apply(hex, null);
                } else {
                    this.classList.add('invalid');
                }
            });
            hexInput.addEventListener('blur', function() {
                const hex = normalizeHex(this.value);
                this.value = hex ? hex.toUpperCase() : (hidden.value || '').toUpperCase();
                this.classList.remove('invalid');
            });
            hexInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') this.blur();
            });
        }

        if (copyBtn) {
            copyBtn.addEventListener('click', function() {
                if (navigator.clipboard) navigator.clipboard.writeText(hidden.value);
                if (copyIcon) copyIcon.className = 'fa-solid fa-check';
                copyBtn.classList.add('copied');
                setTimeout(function() {
                    if (copyIcon) copyIcon.className = 'fa-regular fa-copy';
                    copyBtn.classList.remove('copied');
                }, 1500);
            });
        }

        // Init with saved value
        const saved = (hidden.value || '').trim();
        const normalized = normalizeHex(saved);
        if (normalized) {
            const match = Array.prototype.find.call(
                swatches,
                s => s.dataset.color && s.dataset.color.toLowerCase() === normalized
            );
            apply(normalized, match || null);
        }
    });

    // ══════════════════════════════════════════════════════
    // Detailed live preview panel (left side of the form)
    // ══════════════════════════════════════════════════════
    function applyLivePreview(el, hex) {
        el.style.setProperty('--lp-primary', hex);
        el.style.setProperty('--lp-primary-dark', mix(hex, 0, 0.35));
        el.style.setProperty('--lp-primary-light', mix(hex, 255, 0.55));
        el.style.setProperty('--lp-primary-bg', mix(hex, 255, 0.9));
        el.style.setProperty('--lp-check', isLight(hex) ? '#1C1917' : '#FFFFFF');
    }

    // Push theme-color changes from each picker into its side preview panel
    document.querySelectorAll('.theme-picker[data-preview-target]').forEach(picker => {
        const target = document.getElementById(picker.dataset.previewTarget);
        if (!target) return;

        picker.addEventListener('themechange', function(e) {
            applyLivePreview(target, e.detail.hex);
            const hexEl = target.querySelector('.lp-theme-hex');
            if (hexEl) hexEl.textContent = e.detail.hex;
            const dotEl = target.querySelector('.lp-row-value .color-dot');
            if (dotEl) dotEl.style.background = e.detail.hex;
        });

        const hidden = picker.querySelector('input[name="theme_color"]') ||
            (picker.dataset.form
                ? document.querySelector('#' + picker.dataset.form + ' input[name="theme_color"]')
                : null);
        if (hidden && hidden.value) {
            applyLivePreview(target, normalizeHex(hidden.value) || '#059669');
            const hexEl = target.querySelector('.lp-theme-hex');
            if (hexEl) hexEl.textContent = hidden.value;
            const dotEl = target.querySelector('.lp-row-value .color-dot');
            if (dotEl) dotEl.style.background = hidden.value;
        }
    });

    // Keep the preview panel in sync with the form fields as the user types
    document.querySelectorAll('.brgy-live-preview[data-preview-for]').forEach(previewEl => {
        const form = document.getElementById(previewEl.dataset.previewFor);
        if (!form) return;

        const nameEl = previewEl.querySelector('[data-fill="name"]');
        const chairmanEl = previewEl.querySelector('[data-fill="chairman_name"]');
        const addressEl = previewEl.querySelector('[data-fill="address"]');
        const contactEl = previewEl.querySelector('[data-fill="contact_number"]');
        const emailEl = previewEl.querySelector('[data-fill="email"]');
        const statusEl = previewEl.querySelector('.lp-badge');
        const logoImg = previewEl.querySelector('.lp-logo img');
        const logoFallback = previewEl.querySelector('.lp-logo-fallback');

        function fill() {
            if (nameEl) nameEl.textContent = (form.name.value || '').trim() || 'Barangay Name';
            if (chairmanEl) chairmanEl.textContent = (form.chairman_name.value || '').trim() || '—';
            if (addressEl) addressEl.textContent = (form.address.value || '').trim() || '—';
            if (contactEl) contactEl.textContent = (form.contact_number.value || '').trim() || '—';
            if (emailEl) emailEl.textContent = (form.email.value || '').trim() || '—';
            const active = form.is_active ? form.is_active.checked : true;
            if (statusEl) {
                statusEl.textContent = active ? 'Active' : 'Inactive';
                statusEl.classList.toggle('inactive', !active);
            }
        }

        ['name', 'chairman_name', 'address', 'contact_number', 'email'].forEach(field => {
            const input = form.querySelector('[name="' + field + '"]');
            if (input) input.addEventListener('input', fill);
        });
        const activeInput = form.querySelector('[name="is_active"]');
        if (activeInput) activeInput.addEventListener('change', fill);

        const logoInput = form.querySelector('input[type="file"][name="logo"]');
        if (logoInput) {
            logoInput.addEventListener('change', function() {
                const file = logoInput.files && logoInput.files[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = function(ev) {
                    if (logoImg) {
                        logoImg.src = ev.target.result;
                        logoImg.style.display = 'block';
                    }
                    if (logoFallback) logoFallback.style.display = 'none';
                };
                reader.readAsDataURL(file);
            });
        }

        fill();
    });
})();
