(function () {
    function closeAll(except) {
        document.querySelectorAll('[data-notif-menu]').forEach(function (menu) {
            if (menu === except) return;
            var dropdown = menu.querySelector('[data-notif-dropdown]');
            var toggle = menu.querySelector('[data-notif-menu-toggle]');
            if (dropdown) dropdown.hidden = true;
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
        });
    }

    document.addEventListener('click', function (event) {
        var toggle = event.target.closest('[data-notif-menu-toggle]');
        if (!toggle) {
            closeAll(null);
            return;
        }
        var menu = toggle.closest('[data-notif-menu]');
        if (!menu) return;
        var dropdown = menu.querySelector('[data-notif-dropdown]');
        var isOpen = dropdown && !dropdown.hidden;
        closeAll(menu);
        if (!isOpen && dropdown) {
            dropdown.hidden = false;
            toggle.setAttribute('aria-expanded', 'true');
        }
        event.preventDefault();
        event.stopPropagation();
    });
})();