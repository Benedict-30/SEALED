/* ═══════════════════════════════════════════════════════════════
   Barangay Document Request System - JavaScript
   ═══════════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', function () {

    // ─── Sidebar Toggle (Mobile) ──────────────────────────────
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const toggleBtn = document.getElementById('sidebarToggle');

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', function () {
            sidebar.classList.toggle('open');
            if (sidebarOverlay) sidebarOverlay.classList.toggle('show');
        });
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', function () {
            sidebar.classList.remove('open');
            sidebarOverlay.classList.remove('show');
        });
    }

    // ─── Notification Dropdown ────────────────────────────────
    const notifBtn = document.getElementById('notifBtn');
    const notifDropdown = document.getElementById('notifDropdown');

    if (notifBtn && notifDropdown) {
        notifBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            notifDropdown.classList.toggle('show');
        });

        document.addEventListener('click', function (e) {
            if (!notifDropdown.contains(e.target) && e.target !== notifBtn) {
                notifDropdown.classList.remove('show');
            }
        });
    }

    // ─── Auto-dismiss Toast Messages ──────────────────────────
    const toasts = document.querySelectorAll('.toast');
    toasts.forEach(function (toast) {
        setTimeout(function () {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 4000);
    });

    // ─── Confirm Dialogs (replace window.confirm) ─────────────
    window.confirmAction = function (message, callback) {
        const existing = document.querySelector('.modal-overlay.confirm-modal');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay confirm-modal';
        overlay.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3>Confirm Action</h3>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
                </div>
                <div class="modal-body">
                    <p style="font-size:14px;color:var(--text-secondary);line-height:1.6">${message}</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-ghost" onclick="this.closest('.modal-overlay').remove()">Cancel</button>
                    <button class="btn btn-danger" id="confirmActionBtn">Confirm</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        overlay.querySelector('#confirmActionBtn').addEventListener('click', function () {
            overlay.remove();
            if (callback) callback();
        });

        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) overlay.remove();
        });
    };

    // ─── Make confirm links work with custom dialog ───────────
    document.querySelectorAll('[data-confirm]').forEach(function (el) {
        el.addEventListener('click', function (e) {
            e.preventDefault();
            const msg = el.getAttribute('data-confirm');
            const href = el.getAttribute('href');
            confirmAction(msg, function () {
                window.location.href = href;
            });
        });
    });

    // ─── Form Submit Confirmation ─────────────────────────────
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            const msg = form.getAttribute('data-confirm');
            confirmAction(msg, function () {
                form.submit();
            });
        });
    });

    // ─── Dynamic Form: Show rejection reason field ────────────
    const statusSelect = document.getElementById('id_status');
    const rejectionGroup = document.getElementById('rejectionReasonGroup');

    if (statusSelect && rejectionGroup) {
        statusSelect.addEventListener('change', function () {
            if (this.value === 'rejected') {
                rejectionGroup.classList.remove('hidden');
                rejectionGroup.querySelector('.form-input').setAttribute('required', 'required');
            } else {
                rejectionGroup.classList.add('hidden');
                rejectionGroup.querySelector('.form-input').removeAttribute('required');
            }
        });
        // Trigger on load
        statusSelect.dispatchEvent(new Event('change'));
    }

    // ─── Animate stat card numbers ────────────────────────────
    document.querySelectorAll('.stat-value[data-count]').forEach(function (el) {
        const target = parseInt(el.getAttribute('data-count'), 10);
        const duration = 600;
        const step = Math.max(1, Math.ceil(target / (duration / 16)));
        let current = 0;

        function animate() {
            current += step;
            if (current >= target) {
                el.textContent = target;
                return;
            }
            el.textContent = current;
            requestAnimationFrame(animate);
        }
        animate();
    });

    // ─── Bar chart animation ──────────────────────────────────
    document.querySelectorAll('.bar-fill').forEach(function (bar) {
        const width = bar.getAttribute('data-width');
        if (width) {
            bar.style.width = '0%';
            setTimeout(function () {
                bar.style.width = width + '%';
            }, 100);
        }
    });

    // ─── Auto-hide CSRF errors in forms ───────────────────────
    document.querySelectorAll('.form-error-list').forEach(function (list) {
        const errors = list.querySelectorAll('li');
        errors.forEach(function (err) {
            if (err.textContent.includes('CSRF') || err.textContent.includes('csrf')) {
                list.style.display = 'none';
            }
        });
    });

});