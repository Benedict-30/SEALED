document.addEventListener("DOMContentLoaded", function() {
    const nameInput = document.getElementById('id_name');
    const descInput = document.getElementById('id_description');
    const feeInput = document.getElementById('id_fee');
    const activeInput = document.getElementById('id_is_active');

    const previewName = document.getElementById('previewName');
    const previewDesc = document.getElementById('previewDesc');
    const previewFee = document.getElementById('previewFee');
    const previewStatus = document.getElementById('previewStatus');

    // Live Update Listeners
    if (nameInput) {
        nameInput.addEventListener('input', function() {
            previewName.textContent = this.value || "Document Name";
        });
    }

    if (descInput) {
        descInput.addEventListener('input', function() {
            previewDesc.textContent = this.value || "Click to request document";
        });
    }
    
    if (feeInput) {
        feeInput.addEventListener('input', function() {
            const val = parseFloat(this.value);
            previewFee.textContent = (!isNaN(val) && val > 0) ? 'Fee: ₱' + val.toFixed(2) : 'No Fee';
        });
    }

    if (activeInput) {
        activeInput.addEventListener('change', function() {
            if (this.checked) {
                previewStatus.textContent = 'Available';
                previewStatus.classList.remove('unavailable');
            } else {
                previewStatus.textContent = 'Unavailable';
                previewStatus.classList.add('unavailable');
            }
        });
    }

    // Update file upload text when a file is selected
    const fileInput = document.getElementById('id_template_file');
    if (fileInput) {
        const fileArea = fileInput.closest('.file-upload-area');
        fileInput.addEventListener('change', function() {
            if (this.files && this.files[0]) {
                fileArea.querySelector('p').innerHTML = "<strong>" + this.files[0].name + "</strong> selected";
                fileArea.style.borderColor = 'var(--success, #155724)';
                fileArea.style.background = 'var(--success-bg, #d4edda)';
            }
        });
    }
});