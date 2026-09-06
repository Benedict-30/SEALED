document.addEventListener('DOMContentLoaded', function() {
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