document.addEventListener('DOMContentLoaded', function() {
    const formBody = document.getElementById('createDocTypeForm');
    const toggleBtn = document.getElementById('createDocTypeToggle');
    if (formBody && toggleBtn) {
        const updateBtn = function(open) {
            toggleBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
            const icon = toggleBtn.querySelector('i');
            if (icon) icon.className = open ? 'fa-solid fa-chevron-up' : 'fa-solid fa-plus';
        };

        updateBtn(!formBody.classList.contains('hidden'));

        toggleBtn.addEventListener('click', function() {
            const open = formBody.classList.toggle('hidden') === false;
            updateBtn(open);
            if (open) formBody.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        });
    }

    const scopeSelect = document.getElementById('id_scope');
    const barangayGroup = document.getElementById('barangayGroup');
    if (scopeSelect && barangayGroup) {
        const updateScope = function() {
            const isGlobal = scopeSelect.value === 'global';
            barangayGroup.style.display = isGlobal ? 'none' : '';
            const select = barangayGroup.querySelector('select');
            if (select) select.disabled = isGlobal;
        };
        scopeSelect.addEventListener('change', updateScope);
        updateScope();
    }
});