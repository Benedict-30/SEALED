function toggleRejectionField() {
        const status = document.getElementById('statusSelect').value;
        const rejectionField = document.getElementById('rejectionField');
        const rejectionReason = document.getElementById('rejectionReason');

        if (status === 'rejected') {
            rejectionField.style.display = 'block';
            rejectionReason.setAttribute('required', 'required');
        } else {
            rejectionField.style.display = 'none';
            rejectionReason.removeAttribute('required');
        }
    }

    window.onload = toggleRejectionField;