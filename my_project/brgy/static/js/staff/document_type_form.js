document.addEventListener("DOMContentLoaded", function() {
    const $ = function(id) { return document.getElementById(id); };

    const nameInput   = $('id_name');
    const descInput   = $('id_description');
    const feeInput    = $('id_fee');
    const reqInput    = $('id_requirements');
    const activeInput = $('id_is_active');
    const fileInput   = $('id_template_file');

    const previewName   = $('previewName');
    const previewDesc   = $('previewDesc');
    const previewFee    = $('previewFee');
    const previewStatus = $('previewStatus');
    const previewReqs   = $('previewReqs');
    const heroPill      = $('heroStatusPill');
    const heroIcon      = $('heroStatusIcon');
    const heroText      = $('heroStatusText');
    const nameCount     = $('nameCount');
    const reqCount      = $('reqCount');

    // ── Requirements counter ────────────────────────────────
    function countRequirements() {
        const txt = (reqInput.value || '').split(/\r?\n/).map(function(s) { return s.trim(); }).filter(Boolean);
        if (reqCount) reqCount.textContent = txt.length;
        if (previewReqs) previewReqs.textContent = txt.length;
    }

    // ── Availability pill/status sync ────────────────────────
    function syncStatus() {
        const on = activeInput.checked;
        previewStatus.textContent = on ? 'Available' : 'Unavailable';
        previewStatus.classList.toggle('unavailable', !on);
        if (heroPill) {
            heroPill.classList.toggle('is-live', on);
            heroPill.classList.toggle('is-off', !on);
        }
        if (heroIcon) heroIcon.className = 'fa-solid ' + (on ? 'fa-circle-check' : 'fa-circle-pause');
        if (heroText) heroText.textContent = on ? 'Available' : 'Unavailable';
    }

    // ── Initial values ──────────────────────────────────────
    if (nameInput && nameCount) nameCount.textContent = nameInput.value.length;
    if (reqInput) countRequirements();

    // ── Live update listeners ───────────────────────────────
    if (nameInput) {
        nameInput.addEventListener('input', function() {
            previewName.textContent = this.value.trim() || "Document Name";
            if (nameCount) nameCount.textContent = this.value.length;
        });
    }

    if (descInput) {
        descInput.addEventListener('input', function() {
            previewDesc.textContent = this.value.trim() || "Click to request document";
        });
    }

    if (feeInput) {
        feeInput.addEventListener('input', function() {
            const val = parseFloat(this.value);
            if (!isNaN(val) && val > 0) {
                previewFee.textContent = 'Fee: \u20B1' + val.toFixed(2);
            } else {
                previewFee.textContent = 'No Fee';
            }
        });
    }

    if (reqInput) {
        reqInput.addEventListener('input', countRequirements);
    }

    if (activeInput) {
        activeInput.addEventListener('change', syncStatus);
    }

    // ── File upload feedback ────────────────────────────────
    if (fileInput) {
        const uploadArea = $('uploadArea');
        const uploadTitle = $('uploadTitle');

        function updateUploadArea() {
            if (!fileInput.files || !fileInput.files[0]) return;
            if (uploadTitle) {
                uploadTitle.innerHTML = '<strong>' + fileInput.files[0].name + '</strong> selected';
            }
            if (uploadArea) {
                uploadArea.classList.add('has-file');
                uploadArea.classList.remove('dragover');
            }
        }

        fileInput.addEventListener('change', updateUploadArea);

        if (uploadArea) {
            ['dragenter', 'dragover'].forEach(function(ev) {
                uploadArea.addEventListener(ev, function(e) {
                    e.preventDefault();
                    uploadArea.classList.add('dragover');
                });
            });
            ['dragleave', 'drop'].forEach(function(ev) {
                uploadArea.addEventListener(ev, function(e) {
                    e.preventDefault();
                    uploadArea.classList.remove('dragover');
                });
            });
            uploadArea.addEventListener('drop', updateUploadArea);
        }
    }
});