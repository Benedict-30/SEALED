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
        notifDropdown.classList.toggle('show');
        if (userMenu) userMenu.classList.remove('open');
        if (userDropdown) userDropdown.classList.remove('show');
    });

    // Close dropdown when clicking ANYWHERE else on the page
    document.addEventListener('click', function() {
        notifDropdown.classList.remove('show');
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
        userDropdown.classList.toggle('show');
        userMenu.classList.toggle('open', !isOpen);
    });

    document.addEventListener('click', function() {
        userDropdown.classList.remove('show');
        userMenu.classList.remove('open');
    });

    userDropdown.addEventListener('click', function(e) {
        e.stopPropagation();
    });
}

// ==========================================
// 4. PASSWORD VISIBILITY TOGGLE
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
// 5. SIDEBAR TOGGLE
// ==========================================
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebarOverlay');

if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function() {
        sidebar.classList.toggle('open');
        if (sidebarOverlay) sidebarOverlay.classList.toggle('show');
    });
}

if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', function() {
        if (sidebar) sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('show');
    });
}