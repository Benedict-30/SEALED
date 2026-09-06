document.addEventListener('DOMContentLoaded', function() {
    const formBody = document.getElementById('createBrgyFormBody');
    const toggleBtn = document.getElementById('createBrgyToggle');
    const previewPanel = document.getElementById('createPreviewPanel');
    if (!formBody || !toggleBtn) return;

    const updateBtn = function(open) {
        toggleBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
        const icon = toggleBtn.querySelector('i');
        if (icon) icon.className = open ? 'fa-solid fa-chevron-up' : 'fa-solid fa-plus';
    };

    const syncPreviewPanel = function(open) {
        if (previewPanel) previewPanel.classList.toggle('hidden', !open);
    };

    updateBtn(!formBody.classList.contains('hidden'));
    syncPreviewPanel(!formBody.classList.contains('hidden'));

    toggleBtn.addEventListener('click', function() {
        const open = formBody.classList.toggle('hidden') === false;
        updateBtn(open);
        syncPreviewPanel(open);
        if (open) formBody.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
});

window.openBrgyPreview = function(dataStr) {
    let brgy;
    try {
        brgy = JSON.parse(dataStr);
    } catch (e) {
        return;
    }

    const logoEl = document.getElementById('brgyPreviewLogo');
    logoEl.innerHTML = brgy.logo_url
        ? '<img src="' + brgy.logo_url + '" alt="' + (brgy.name || 'Barangay') + ' logo">'
        : '<div class="no-logo"><i class="fa-solid fa-building"></i></div>';

    const theme = brgy.theme_color || '#059669';
    document.getElementById('brgyPreviewThemeBar').style.background = theme;
    document.getElementById('brgyPreviewThemeBar').parentElement.style.boxShadow =
        '0 2px 8px -2px ' + theme;
    document.getElementById('brgyPreviewName').textContent = brgy.name || '';
    document.getElementById('brgyPreviewTheme').innerHTML =
        '<span class="color-dot" style="background:' + theme + ';margin-right:6px;"></span>' + theme;
    document.getElementById('brgyPreviewChairman').textContent = brgy.chairman_name || '-';
    document.getElementById('brgyPreviewAddress').textContent = brgy.address || '-';
    document.getElementById('brgyPreviewContact').textContent = brgy.contact_number || '-';
    document.getElementById('brgyPreviewEmail').textContent = brgy.email || '-';
    document.getElementById('brgyPreviewResidents').textContent = brgy.resident_count || '0';
    document.getElementById('brgyPreviewStaff').textContent = brgy.staff_count || '0';
    document.getElementById('brgyPreviewCreated').textContent = brgy.created_at || '-';

    const statusEl = document.getElementById('brgyPreviewStatus');
    const active = brgy.is_active === true || brgy.is_active === 'true';
    statusEl.textContent = active ? 'Active' : 'Inactive';
    statusEl.className = 'brgy-preview-badge ' + (active ? 'badge-success' : 'badge-danger');

    const form = document.getElementById('changeLogoForm');
    form.action = document.querySelector('[data-manage-url]').dataset.manageUrl.replace(/\/$/, '') + '/' + brgy.pk + '/logo/';
    form.reset();
    document.getElementById('newLogoPreview').classList.remove('visible');
    document.getElementById('newLogoPreview').innerHTML = '';

    document.getElementById('brgyModal').classList.add('show');
};

window.closeBrgyPreview = function() {
    document.getElementById('brgyModal').classList.remove('show');
};

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeBrgyPreview();
});

document.addEventListener('DOMContentLoaded', function() {
    const logoInput = document.getElementById('brgyLogoInput');
    const preview = document.getElementById('newLogoPreview');
    logoInput.addEventListener('change', function() {
        const file = logoInput.files && logoInput.files[0];
        if (!file) {
            preview.classList.remove('visible');
            preview.innerHTML = '';
            return;
        }
        const reader = new FileReader();
        reader.onload = function(ev) {
            preview.innerHTML = '<img src="' + ev.target.result + '" alt="New logo preview">';
            preview.classList.add('visible');
        };
        reader.readAsDataURL(file);
    });
});
