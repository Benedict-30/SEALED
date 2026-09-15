// ==========================================
// 1. LOGOUT CONFIRMATION
// ==========================================
document.querySelectorAll('[data-confirm]').forEach(element => {
    element.addEventListener('click', function(e) {
        e.preventDefault(); // Stop the link from going to logout immediately
        const message = this.getAttribute('data-confirm');
        
        if (confirm(message)) {
            // If user clicks "OK", send them to the logout URL
            window.location.href = this.getAttribute('href');
        }
    });
});

// ==========================================
// 2. NOTIFICATION DROPDOWN TOGGLE
// ==========================================
const notifBtn = document.getElementById('notifBtn');
const notifDropdown = document.getElementById('notifDropdown');

if (notifBtn && notifDropdown) {
    // Toggle dropdown when clicking the bell icon
    notifBtn.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevents it from closing instantly
        const isOpen = notifDropdown.classList.toggle('show');
        notifBtn.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        if (userMenu) userMenu.classList.remove('open');
        if (userDropdown) userDropdown.classList.remove('show');
        if (pagesBtn) pagesBtn.setAttribute('aria-expanded', 'false');
    });

    // Close dropdown when clicking ANYWHERE else on the page
    document.addEventListener('click', function() {
        if (notifDropdown.classList.remove('show')) notifBtn.focus();
        notifBtn.setAttribute('aria-expanded', 'false');
    });

    // Keep dropdown open if clicking inside the dropdown itself
    notifDropdown.addEventListener('click', function(e) {
        e.stopPropagation();
    });
}

// ==========================================
// 3. USER MENU DROPDOWN TOGGLE
// ==========================================
const userMenu = document.getElementById('userMenu');
const userMenuBtn = document.getElementById('userMenuBtn');
const userDropdown = document.getElementById('userDropdown');

if (userMenu && userMenuBtn && userDropdown) {
    userMenuBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        const isOpen = userDropdown.classList.contains('show');
        // Close notif dropdown when opening user menu
        if (notifDropdown) notifDropdown.classList.remove('show');
        if (notifBtn) notifBtn.setAttribute('aria-expanded', 'false');
        if (pagesBtn) pagesBtn.setAttribute('aria-expanded', 'false');
        userDropdown.classList.toggle('show');
        userMenu.classList.toggle('open', !isOpen);
        userMenuBtn.setAttribute('aria-expanded', (!isOpen) ? 'true' : 'false');
    });

    document.addEventListener('click', function() {
        if (userDropdown.classList.remove('show')) userMenuBtn.focus();
        userMenu.classList.remove('open');
        userMenuBtn.setAttribute('aria-expanded', 'false');
    });

    userDropdown.addEventListener('click', function(e) {
        e.stopPropagation();
    });
}

// ==========================================
// 4. PAGES DROPDOWN TOGGLE (mobile nav)
// ==========================================
const pagesBtn = document.getElementById('pagesBtn');
const pagesDropdown = document.getElementById('pagesDropdown');

if (pagesBtn && pagesDropdown) {
    pagesBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        const isOpen = pagesDropdown.classList.contains('show');
        if (notifDropdown) notifDropdown.classList.remove('show');
        if (notifBtn) notifBtn.setAttribute('aria-expanded', 'false');
        if (userDropdown) userDropdown.classList.remove('show');
        if (userMenu) userMenu.classList.remove('open');
        if (userMenuBtn) userMenuBtn.setAttribute('aria-expanded', 'false');
        pagesDropdown.classList.toggle('show', !isOpen);
        pagesBtn.setAttribute('aria-expanded', (!isOpen) ? 'true' : 'false');
    });

    document.addEventListener('click', function() {
        if (pagesDropdown.classList.remove('show')) pagesBtn.focus();
        pagesBtn.setAttribute('aria-expanded', 'false');
    });

    pagesDropdown.addEventListener('click', function(e) {
        e.stopPropagation();
    });
}

// ==========================================
// 5. PASSWORD VISIBILITY TOGGLE
// ==========================================
document.querySelectorAll('.password-toggle').forEach(function(btn) {
    btn.addEventListener('click', function() {
        const wrap = this.closest('.password-wrap');
        const input = wrap ? wrap.querySelector('input[type="password"], input[type="text"]') : null;
        if (!input) return;
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        const icon = this.querySelector('i');
        if (icon) {
            icon.className = show ? 'fa-regular fa-eye-slash' : 'fa-regular fa-eye';
        }
    });
});

// ==========================================
// 6. SIDEBAR TOGGLE (drawer, all screen sizes)
// ==========================================
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarClose = document.getElementById('sidebarClose');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');

function setSidebar(open) {
    if (!sidebar) return;
    sidebar.classList.toggle('open', open);
    if (sidebarOverlay) sidebarOverlay.classList.toggle('show', open);
    if (sidebarToggle) {
        sidebarToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        sidebarToggle.classList.toggle('active', open);
        const icon = sidebarToggle.querySelector('i');
        if (icon) icon.className = open ? 'fa-solid fa-xmark' : 'fa-solid fa-bars';
    }
    if (open) {
        setSidebar.lastFocus = document.activeElement;
        setTimeout(function() {
            const first = sidebar.querySelector('a[href], button:not([disabled])');
            if (first && sidebar.classList.contains('open')) first.focus();
        }, 320);
    } else if (setSidebar.lastFocus && document.contains(setSidebar.lastFocus)) {
        setSidebar.lastFocus.focus();
    }
}

if (sidebarToggle && sidebar) {
    sidebarToggle.setAttribute('aria-expanded', 'false');
    sidebarToggle.addEventListener('click', function() {
        setSidebar(!sidebar.classList.contains('open'));
    });
}

if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', function() {
        setSidebar(false);
    });
}

if (sidebarClose) {
    sidebarClose.addEventListener('click', function() {
        setSidebar(false);
    });
}

// ==========================================
// 7. FOCUS TRAP (sidebar drawer)
// ==========================================
document.addEventListener('keydown', function(e) {
    if (e.key !== 'Tab' || !sidebar || !sidebar.classList.contains('open')) return;
    const focusables = sidebar.querySelectorAll('a[href], button:not([disabled])');
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
    }
});

// ==========================================
// 8. ESCAPE KEY CLOSES LAYERS
// ==========================================
const modalClosers = [
    ['closeCamera', () => document.querySelector('.camera-modal') && document.querySelector('.camera-modal').style.display !== 'none'],
    ['closeIdModal', () => document.querySelector('.id-modal.show')],
    ['closeBrgyPreview', () => document.querySelector('.brgy-modal.show')],
    ['closeModal', () => document.getElementById('reqModal') && document.getElementById('reqModal').classList.contains('active')],
];

document.addEventListener('keydown', function(e) {
    if (e.key !== 'Escape') return;

    if (sidebar && sidebar.classList.contains('open')) {
        setSidebar(false);
        return;
    }
    if (pagesDropdown && pagesDropdown.classList.contains('show')) {
        pagesDropdown.classList.remove('show');
        if (pagesBtn) {
            pagesBtn.setAttribute('aria-expanded', 'false');
            pagesBtn.focus();
        }
        return;
    }
    if (typeof notifDropdown !== 'undefined' && notifDropdown && notifDropdown.classList.contains('show')) {
        notifDropdown.classList.remove('show');
        if (notifBtn) {
            notifBtn.setAttribute('aria-expanded', 'false');
            notifBtn.focus();
        }
        return;
    }
    if (typeof userDropdown !== 'undefined' && userDropdown && userDropdown.classList.contains('show')) {
        userDropdown.classList.remove('show');
        if (userMenu) userMenu.classList.remove('open');
        if (userMenuBtn) {
            userMenuBtn.setAttribute('aria-expanded', 'false');
            userMenuBtn.focus();
        }
        return;
    }

    for (const [fnName, isVisible] of modalClosers) {
        try {
            if (isVisible() && typeof window[fnName] === 'function') {
                window[fnName]();
                return;
            }
        } catch (err) { /* visibility probe failed - skip */ }
    }
});

// ==========================================
// 9. TOPBAR LIVE CLOCK (Asia/Manila)
// ==========================================
var clockEl = document.getElementById('topbarClock');
if (clockEl) {
    var tz = clockEl.getAttribute('data-tz') || 'Asia/Manila';
    var clockDateFmt = new Intl.DateTimeFormat('en-PH', { timeZone: tz, weekday: 'short', month: 'short', day: 'numeric' });
    var clockTimeFmt = new Intl.DateTimeFormat('en-PH', { timeZone: tz, hour: 'numeric', minute: '2-digit' });
    clockEl.innerHTML = '<span class="topbar-clock-icon"><i class="fa-solid fa-clock"></i></span>' +
        '<span class="topbar-clock-date"></span>' +
        '<span class="topbar-clock-sep">&middot;</span>' +
        '<span class="topbar-clock-time"></span>';

    function tickClock() {
        var now = new Date();
        var d = clockEl.querySelector('.topbar-clock-date');
        var t = clockEl.querySelector('.topbar-clock-time');
        if (d) d.textContent = clockDateFmt.format(now);
        if (t) t.textContent = clockTimeFmt.format(now);
    }
    tickClock();
    setInterval(tickClock, 30000);
}

// ==========================================
// 10. UNREAD NOTIFICATION COUNT POLLING
// ==========================================
var notifWrap = document.getElementById('topbarNotif');
var notifBadge = notifWrap ? notifWrap.querySelector('.topbar-badge') : null;
var pollUrl = notifWrap ? notifWrap.getAttribute('data-poll-url') : '';

if (notifWrap && pollUrl) {
    function renderNotifCount(n) {
        if (!notifBadge) notifBadge = notifWrap.querySelector('.topbar-badge');
        if (n > 0) {
            var label = n > 99 ? '+99' : String(n);
            if (!notifBadge) {
                notifBadge = document.createElement('span');
                notifBadge.className = 'topbar-badge';
                var btn = notifWrap.querySelector('#notifBtn');
                if (btn) btn.appendChild(notifBadge);
            }
            notifBadge.textContent = label;
        } else if (notifBadge) {
            notifBadge.remove();
            notifBadge = null;
        }
    }

    function pollNotifCount() {
        if (document.hidden) return;
        fetch(pollUrl, { headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' } })
            .then(function(res) { return res.json(); })
            .then(function(data) { if (typeof data.count === 'number') renderNotifCount(data.count); })
            .catch(function() { /* transient - ignore */ });
    }
    setInterval(pollNotifCount, 60000);
}

// ==========================================
// 11. TOPBAR SCROLL SHADOW
// ==========================================
var topbarEl = document.querySelector('.topbar');
if (topbarEl) {
    function updateTopbarShadow() {
        topbarEl.classList.toggle('scrolled', window.scrollY > 4);
    }
    updateTopbarShadow();
    document.addEventListener('scroll', updateTopbarShadow, { passive: true });
}

// ==========================================
// 12. DROPDOWN KEYBOARD NAVIGATION
// ==========================================
function setupDropdownKeys(trigger, dropdown) {
    if (!trigger || !dropdown) return;

    function dropdownItems() {
        return Array.prototype.slice.call(dropdown.querySelectorAll('a[href], button:not([disabled])'));
    }

    function goTo(index) {
        var items = dropdownItems();
        if (!items.length) return;
        index = (index + items.length) % items.length;
        items[index].focus();
    }

    trigger.addEventListener('keydown', function(e) {
        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
        if (dropdown.classList.contains('show')) {
            e.preventDefault();
            var items = dropdownItems();
            goTo(e.key === 'ArrowDown' ? 0 : items.length - 1);
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            trigger.click();
        }
    });

    dropdown.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            var items = dropdownItems();
            goTo(items.indexOf(document.activeElement) + (e.key === 'ArrowDown' ? 1 : -1));
        } else if (e.key === 'Home') {
            e.preventDefault();
            goTo(0);
        } else if (e.key === 'End') {
            e.preventDefault();
            goTo(dropdownItems().length - 1);
        }
    });
}

setupDropdownKeys(pagesBtn, pagesDropdown);
setupDropdownKeys(notifBtn, notifDropdown);
setupDropdownKeys(userMenuBtn, userDropdown);

// ==========================================
// 13. SCROLL REVEAL ([data-reveal] elements)
// ==========================================
document.documentElement.classList.add('js-reveal');

const revealEls = document.querySelectorAll('[data-reveal]');
if (revealEls.length) {
    if ('IntersectionObserver' in window) {
        const revealObserver = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('revealed');
                    revealObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.12 });
        revealEls.forEach(function(el) { revealObserver.observe(el); });
    } else {
        revealEls.forEach(function(el) { el.classList.add('revealed'); });
    }
}