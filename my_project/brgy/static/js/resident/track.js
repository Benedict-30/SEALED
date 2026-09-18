document.addEventListener('DOMContentLoaded', () => {
    // ── Copy request number ──────────────────────────────────────
    const copyBtn = document.querySelector('.track-copy-btn');
    if (copyBtn) {
        const originalHTML = copyBtn.innerHTML;
        copyBtn.addEventListener('click', () => {
            const text = copyBtn.getAttribute('data-copy-text') || '';
            const done = () => {
                copyBtn.innerHTML = '<i class="fa-solid fa-check"></i> Copied!';
                setTimeout(() => { copyBtn.innerHTML = originalHTML; }, 1800);
            };
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(done, () => {
                    _trackFallbackCopy(text);
                    done();
                });
            } else {
                _trackFallbackCopy(text);
                done();
            }
        });
    }

    // ── Print summary ────────────────────────────────────────────
    const printBtn = document.querySelector('.track-print-btn');
    if (printBtn) {
        printBtn.addEventListener('click', () => window.print());
    }

    // ── Live status sync (no reload → no scroll/zoom reset) ──────
    const root = document.querySelector('[data-track-status-url]');
    if (!root) return;

    const url = root.getAttribute('data-track-status-url');
    let timer = null;
    let lastSignature = '';

    const poll = () => {
        if (document.visibilityState !== 'visible') return;
        fetch(url, {
            cache: 'no-store',
            headers: { 'Accept': 'application/json' },
        })
            .then((res) => {
                if (!res.ok) throw new Error('status feed unavailable');
                return res.json();
            })
            .then((payload) => {
                if (payload.signature === lastSignature) return;
                lastSignature = payload.signature;
                _trackApply(payload);
                if (payload.terminal && timer !== null) {
                    clearInterval(timer);
                    timer = null;
                }
            })
            .catch(() => {});
    };

    timer = setInterval(poll, 30000);
});

function _trackFallbackCopy(text) {
    const input = document.createElement('textarea');
    input.value = text;
    input.setAttribute('readonly', '');
    input.style.position = 'fixed';
    input.style.opacity = '0';
    document.body.appendChild(input);
    input.select();
    input.setSelectionRange(0, input.value.length);
    try {
        document.execCommand('copy');
    } catch (e) {}
    document.body.removeChild(input);
}

function _trackSetBadge(el, text, color) {
    if (!el) return;
    if (el.textContent.trim() !== text) el.textContent = text;
    el.classList.remove('badge-primary', 'badge-success', 'badge-warning',
        'badge-danger', 'badge-info', 'badge-muted');
    el.classList.add('badge-' + color);
}

function _trackRingColor(color) {
    if (color === 'danger') return 'var(--danger)';
    if (color === 'muted') return 'var(--text-muted)';
    return 'var(--primary)';
}

function _trackIsActive(status) {
    return status === 'pending' || status === 'approved' ||
        status === 'printed' || status === 'ready_for_pickup';
}

function _trackApply(payload) {
    const root = document.querySelector('[data-track-status-url]');
    if (!root) return;

    // ── Hero card state ────────────────────────────────────────
    const hero = root.querySelector('.track-hero');
    if (hero) {
        hero.classList.toggle('track-hero-rejected',
            payload.display_status === 'rejected' || payload.display_status === 'cancelled');
    }

    // Badges (hero + timeline header)
    const heroBadge = root.querySelector('.track-hero-status .badge');
    const headerBadge = root.querySelector('.track-steps-header .badge');
    _trackSetBadge(heroBadge, payload.status_display, payload.status_color);
    if (headerBadge) _trackSetBadge(headerBadge, payload.status_display, payload.status_color);

    // Progress ring
    const circle = root.querySelector('.track-ring .progress-ring__circle');
    if (circle) {
        circle.setAttribute('stroke', _trackRingColor(payload.ring_color));
        circle.setAttribute('stroke-dashoffset', String(payload.offset));
        circle.setAttribute('data-percent', String(payload.percent));
        circle.classList.toggle('active', _trackIsActive(payload.display_status));
    }
    const pct = root.querySelector('.track-ring .percentage');
    if (pct && pct.textContent.trim() !== payload.percent + '%') {
        pct.textContent = payload.percent + '%';
    }

    // Last updated
    const updated = root.querySelector('.track-last-updated');
    if (updated) {
        updated.textContent = payload.updated_at
            ? 'Last updated ' + payload.updated_at
            : '';
    }

    // ── Timeline steps ─────────────────────────────────────────
    const stepsWrap = root.querySelector('.track-steps .card-body');
    if (stepsWrap) {
        const stepEls = stepsWrap.querySelectorAll(':scope > .track-step');
        payload.steps.forEach((step, idx) => {
            const el = stepEls[idx];
            if (!el) return;
            el.classList.toggle('done', step.state === 'done');
            el.classList.toggle('active', step.state === 'active');
            el.classList.toggle('todo', step.state === 'todo');

            const line = el.querySelector('.track-step-line');
            if (line) line.classList.toggle('line-done', step.state !== 'todo');

            const dateEl = el.querySelector('.track-step-date');
            if (dateEl) {
                if (dateEl.textContent !== step.date) dateEl.textContent = step.date;
            }

            if (step.key === 'ready_for_pickup') {
                const existingHint = el.querySelector('.track-step-hint');
                if (existingHint) existingHint.remove();
                if (step.state !== 'todo' && !payload.paid) {
                    const hint = document.createElement('span');
                    hint.className = 'track-step-hint';
                    hint.innerHTML =
                        '<i class="fa-solid fa-circle-info"></i> Bring payment &amp; OR # before pickup';
                    el.querySelector('.track-step-label').appendChild(hint);
                }
            }
        });
    }

    // ── Payment callout ────────────────────────────────────────
    const payment = root.querySelector('.track-payment');
    if (payment) {
        payment.hidden = !payload.payment_required;
        if (payload.payment_required) {
            const fee = payment.querySelector('[data-fee]');
            if (fee) fee.textContent = '\u20B1 ' + payload.total_fee;
            const pickup = payment.querySelector('[data-pickup]');
            if (pickup) pickup.textContent = payload.pickup_date;
        }
    }
}