document.addEventListener('DOMContentLoaded', function() {
    const formBody = document.getElementById('createStaffForm');
    const toggleBtn = document.getElementById('createStaffButton');
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

    const emailInput = document.getElementById('id_email');
    const preview = document.getElementById('usernamePreview');
    const previewValue = document.getElementById('usernamePreviewValue');
    if (emailInput && preview && previewValue) {
        const update = function() {
            const prefix = (emailInput.value || '').trim().toLowerCase().split('@')[0].replace(/[^a-z0-9_.-]/g, '');
            previewValue.textContent = prefix ? '@' + prefix : '';
            preview.hidden = !prefix;
        };
        emailInput.addEventListener('input', update);
        update();
    }

    const copyBtn = document.getElementById('copyGeneratedPassword');
    const valueEl = document.getElementById('generatedPasswordValue');
    if (copyBtn && valueEl) {
        copyBtn.addEventListener('click', function() {
            const text = valueEl.textContent;
            const fallback = function() {
                const range = document.createRange();
                range.selectNodeContents(valueEl);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('copy');
                sel.removeAllRanges();
            };
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).catch(fallback);
            } else {
                fallback();
            }
            const icon = copyBtn.querySelector('i');
            const label = copyBtn.firstChild;
            if (icon) icon.className = 'fa-solid fa-check';
            if (label) label.textContent = ' Copied!';
            setTimeout(function() {
                if (icon) icon.className = 'fa-solid fa-copy';
                if (label) label.textContent = ' Copy';
            }, 2000);
        });
    }

    const dismissBtn = document.getElementById('dismissPasswordCard');
    const card = document.getElementById('generatedPasswordCard');
    if (dismissBtn && card) {
        dismissBtn.addEventListener('click', function() {
            card.remove();
        });
    }
});