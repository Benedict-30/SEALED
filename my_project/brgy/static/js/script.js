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