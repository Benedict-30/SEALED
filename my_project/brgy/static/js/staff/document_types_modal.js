document.addEventListener('DOMContentLoaded', function () {
    var modal = document.getElementById('inlineAddForm');
    var openBtn = document.getElementById('openAddModal');
    var closeBtn = document.getElementById('closeAddModal');
    var cancelBtn = document.getElementById('cancelAddModal');
    var form = document.getElementById('addDocForm');
    var submitBtn = document.getElementById('addDocSubmit');
    var errorBox = document.getElementById('addFormErrors');

    var nameInput = document.getElementById('id_name');
    var feeInput = document.getElementById('id_fee');
    var descInput = document.getElementById('id_description');
    var reqInput = document.getElementById('id_requirements');
    var fileInput = document.getElementById('id_template_file');
    var activeInput = document.getElementById('id_is_active');

    var previewName = document.getElementById('previewName');
    var previewDesc = document.getElementById('previewDesc');
    var previewFee = document.getElementById('previewFee');
    var previewStatus = document.getElementById('previewStatus');

    var fileArea = document.getElementById('modalFileUploadArea');
    var fileInfo = document.getElementById('modalFileInfo');
    var fileName = document.getElementById('modalFileName');
    var fileSize = document.getElementById('modalFileSize');
    var fileRemove = document.getElementById('modalFileRemove');

    var MAX_FILE_SIZE = 5 * 1024 * 1024;

    // --- Modal open/close ---
    function open() {
        modal.hidden = false;
        document.body.style.overflow = 'hidden';
        if (nameInput) nameInput.focus();
    }
    function close() {
        modal.hidden = true;
        document.body.style.overflow = '';
        resetForm();
        if (openBtn) openBtn.focus();
    }
    function resetForm() {
        form.reset();
        errorBox.hidden = true;
        errorBox.innerHTML = '';
        clearFieldErrors();
        updatePreview();
        showUploadArea();
        fileInfo.hidden = true;
    }

    if (openBtn) openBtn.addEventListener('click', function (e) { e.preventDefault(); open(); });
    if (closeBtn) closeBtn.addEventListener('click', close);
    if (cancelBtn) cancelBtn.addEventListener('click', close);
    modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !modal.hidden) { e.preventDefault(); close(); }
    });

    // --- Live preview ---
    function updatePreview() {
        var name = nameInput.value.trim();
        var desc = descInput.value.trim();
        var fee = parseFloat(feeInput.value);
        var active = activeInput.checked;
        var reqLines = reqInput.value.split('\n').filter(function (l) { return l.trim(); });

        previewName.textContent = name || 'Document Name';
        previewDesc.textContent = desc || 'Click to request document';

        previewFee.textContent = (!isNaN(fee) && fee > 0) ? 'Fee: \u20B1' + fee.toFixed(2) : 'No Fee';

        if (active) {
            previewStatus.textContent = 'Available';
            previewStatus.classList.remove('unavailable');
        } else {
            previewStatus.textContent = 'Unavailable';
            previewStatus.classList.add('unavailable');
        }
    }

    if (nameInput) nameInput.addEventListener('input', updatePreview);
    if (descInput) descInput.addEventListener('input', updatePreview);
    if (feeInput) feeInput.addEventListener('input', updatePreview);
    if (reqInput) reqInput.addEventListener('input', updatePreview);
    if (activeInput) activeInput.addEventListener('change', updatePreview);

    // --- File upload handling ---
    function formatSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function showUploadArea() {
        fileArea.hidden = false;
        fileArea.style.borderColor = '';
        fileArea.style.background = '';
        fileArea.querySelector('p').innerHTML = 'Drag & drop your template here or <strong>browse</strong>';
    }

    function showFileInfo(file) {
        fileArea.hidden = true;
        fileInfo.hidden = false;
        fileName.textContent = file.name;
        var sizeStr = formatSize(file.size);
        var warning = file.size > MAX_FILE_SIZE;
        fileSize.textContent = sizeStr + (warning ? ' (exceeds 5 MB limit)' : '');
        fileSize.style.color = warning ? 'var(--danger)' : 'var(--text-muted)';
    }

    if (fileInput) {
        fileInput.addEventListener('change', function () {
            if (this.files && this.files[0]) {
                showFileInfo(this.files[0]);
            }
        });
    }

    if (fileRemove) {
        fileRemove.addEventListener('click', function () {
            fileInput.value = '';
            fileInfo.hidden = true;
            showUploadArea();
        });
    }

    // Drag and drop
    if (fileArea) {
        ['dragenter', 'dragover'].forEach(function (evt) {
            fileArea.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                fileArea.style.borderColor = 'var(--primary)';
                fileArea.style.background = 'var(--primary-50)';
            });
        });
        ['dragleave', 'drop'].forEach(function (evt) {
            fileArea.addEventListener(evt, function (e) {
                e.preventDefault();
                e.stopPropagation();
                fileArea.style.borderColor = '';
                fileArea.style.background = '';
            });
        });
        fileArea.addEventListener('drop', function (e) {
            var files = e.dataTransfer.files;
            if (files && files.length) {
                fileInput.files = files;
                showFileInfo(files[0]);
            }
        });
    }

    // --- Duplicate name detection ---
    function getExistingNames() {
        var names = [];
        var cards = document.querySelectorAll('.doc-card-wrap .doc-card h3');
        cards.forEach(function (h3) {
            var n = h3.textContent.trim().toLowerCase();
            if (n) names.push(n);
        });
        return names;
    }

    function checkDuplicate(name) {
        var existing = getExistingNames();
        return existing.indexOf(name.toLowerCase().trim()) !== -1;
    }

    // --- Field-level validation ---
    function clearFieldErrors() {
        document.querySelectorAll('.doc-modal-field-error').forEach(function (el) {
            el.textContent = '';
            el.hidden = true;
        });
        var inputs = form.querySelectorAll('.form-input');
        inputs.forEach(function (inp) { inp.style.borderColor = ''; });
    }

    function showFieldError(field, message) {
        var el = document.querySelector('.doc-modal-field-error[data-field="' + field + '"]');
        if (el) {
            el.textContent = message;
            el.hidden = false;
        }
        var input = document.getElementById('id_' + field);
        if (input) input.style.borderColor = 'var(--danger)';
    }

    function validate() {
        clearFieldErrors();
        var valid = true;
        var name = nameInput.value.trim();

        if (!name) {
            showFieldError('name', 'Document name is required.');
            valid = false;
        } else if (name.length < 2) {
            showFieldError('name', 'Name must be at least 2 characters.');
            valid = false;
        } else if (checkDuplicate(name)) {
            showFieldError('name', 'A document with this name already exists.');
            valid = false;
        }

        var fee = feeInput.value.trim();
        if (fee !== '') {
            var feeVal = parseFloat(fee);
            if (isNaN(feeVal) || feeVal < 0) {
                showFieldError('fee', 'Fee must be a valid positive number.');
                valid = false;
            }
        }

        return valid;
    }

    if (nameInput) {
        nameInput.addEventListener('blur', function () {
            clearFieldErrors();
            var name = nameInput.value.trim();
            if (name && checkDuplicate(name)) {
                showFieldError('name', 'A document with this name already exists.');
            }
        });
    }

    // --- AJAX submission ---
    if (form) {
        form.addEventListener('submit', function (e) {
            e.preventDefault();

            if (!validate()) return;

            errorBox.hidden = true;
            errorBox.innerHTML = '';
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Adding...';

            var formData = new FormData(form);

            fetch(window.location.href, {
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data.success) {
                    close();
                    window.location.reload();
                } else if (data.errors) {
                    var msgs = [];
                    for (var field in data.errors) {
                        data.errors[field].forEach(function (err) {
                            msgs.push('<li>' + err + '</li>');
                            if (field !== '__all__') showFieldError(field, err);
                        });
                    }
                    errorBox.innerHTML = msgs.join('');
                    errorBox.hidden = false;
                }
            })
            .catch(function () {
                errorBox.innerHTML = '<li>Something went wrong. Please try again.</li>';
                errorBox.hidden = false;
            })
            .finally(function () {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fa-solid fa-plus"></i> Add Document';
            });
        });
    }

    updatePreview();
});
