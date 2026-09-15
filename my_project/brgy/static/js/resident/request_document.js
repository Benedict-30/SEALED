    const hiddenInputs = document.getElementById('hiddenInputs');
    const feeSummary = document.getElementById('feeSummary');
    const feeTotalEl = document.getElementById('feeTotal');

    function escHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function openModal(docId = null, docName = null) {
        document.getElementById('reqModal').classList.add('active');
        document.getElementById('reqModal').setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        if (docId && docName) {
            // If clicked from a card, pre-select that document
            const select = document.getElementById('docTypeSelect');
            for (let i = 0; i < select.options.length; i++) {
                if (select.options[i].value === docId) {
                    select.selectedIndex = i;
                    break;
                }
            }
        }
    }

    function syncBodyScroll() {
        const reqActive = document.getElementById('reqModal').classList.contains('active');
        const previewActive = document.getElementById('previewModal').classList.contains('active');
        document.body.style.overflow = (reqActive || previewActive) ? 'hidden' : '';
    }

    function closeModal() {
        document.getElementById('reqModal').classList.remove('active');
        document.getElementById('reqModal').setAttribute('aria-hidden', 'true');
        syncBodyScroll();
    }

    function getDocFee(docId) {
        const select = document.getElementById('docTypeSelect');
        for (let i = 0; i < select.options.length; i++) {
            if (select.options[i].value === docId) {
                return parseFloat(select.options[i].dataset.fee || '0') || 0;
            }
        }
        return 0;
    }

    function formatPeso(amount) {
        return '\u20B1' + amount.toFixed(2);
    }

    function updateFeeTotal() {
        let total = 0;
        const rows = document.querySelectorAll('#documentList .req-item-row');
        rows.forEach(row => {
            total += (parseFloat(row.dataset.fee) || 0) * (parseInt(row.dataset.qty) || 0);
        });
        feeTotalEl.textContent = formatPeso(total);
        feeSummary.style.display = rows.length ? 'flex' : 'none';
    }

    function addDocumentToList() {
        const select = document.getElementById('docTypeSelect');
        const docId = select.value;
        const docName = select.options[select.selectedIndex].text;

        if (!docId) {
            alert('Please select a document type.');
            return;
        }

        // If already in the list, just bump the quantity instead of rejecting.
        const docInputs = hiddenInputs.querySelectorAll('input[name="document_type[]"]');
        const qtyInputs = hiddenInputs.querySelectorAll('input[name="quantity[]"]');
        for (let i = 0; i < docInputs.length; i++) {
            if (docInputs[i].value === docId && qtyInputs[i] && qtyInputs[i].dataset.rowId) {
                changeQty(qtyInputs[i].dataset.rowId, 1);
                return;
            }
        }

        const fee = getDocFee(docId);
        const listDiv = document.getElementById('documentList');
        const rowId = 'row_' + Date.now();
        const row = document.createElement('div');
        row.className = 'req-item-row';
        row.id = rowId;
        row.dataset.fee = fee;
        row.dataset.qty = '1';
        row.innerHTML = `
            <div class="req-item-main">
                <strong class="req-item-name">${escHtml(docName)}</strong>
                <div class="qty-group">
                    <button type="button" class="qty-btn" onclick="changeQty('${rowId}', -1)">&minus;</button>
                    <input type="number" class="qty-input" value="1" min="1" max="20" readonly>
                    <button type="button" class="qty-btn" onclick="changeQty('${rowId}', 1)">+</button>
                    <span class="req-item-fee" id="${rowId}_fee">${fee ? 'Fee: ' + formatPeso(fee) : 'Free'}</span>
                </div>
                <div class="req-item-files">
                    <input type="file" name="requirements_${escHtml(docId)}" class="req-file-input" multiple
                           accept=".pdf,.doc,.docx,.jpg,.jpeg,.png">
                    <small class="req-item-files-hint">
                        Attach proof/requirement files (optional, up to 5 MB each)
                    </small>
                </div>
            </div>
            <button type="button" class="remove-btn" onclick="removeDocument('${rowId}', '${docId}')">
                <i class="fa-solid fa-times"></i>
            </button>
        `;
        listDiv.appendChild(row);

        // Hidden inputs for form submission (kept in sync by row order)
        const hiddenDoc = document.createElement('input');
        hiddenDoc.type = 'hidden';
        hiddenDoc.name = 'document_type[]';
        hiddenDoc.value = docId;
        hiddenInputs.appendChild(hiddenDoc);

        const hiddenQty = document.createElement('input');
        hiddenQty.type = 'hidden';
        hiddenQty.name = 'quantity[]';
        hiddenQty.value = '1';
        hiddenQty.dataset.rowId = rowId;
        hiddenInputs.appendChild(hiddenQty);

        updateFeeTotal();
    }

    function changeQty(rowId, change) {
        const row = document.getElementById(rowId);
        const qtyInput = row.querySelector('.qty-input');
        let qty = parseInt(qtyInput.value) + change;
        if (qty < 1) qty = 1;
        if (qty > 20) qty = 20;
        qtyInput.value = qty;
        row.dataset.qty = qty;

        const feeSpan = document.getElementById(rowId + '_fee');
        const fee = parseFloat(row.dataset.fee) || 0;
        feeSpan.textContent = fee ? 'Fee: ' + formatPeso(fee * qty) : 'Free';

        const qtyInputs = document.querySelectorAll('#hiddenInputs input[name="quantity[]"]');
        qtyInputs.forEach(inp => {
            if (inp.dataset.rowId === rowId) inp.value = qty;
        });

        updateFeeTotal();
    }

    function removeDocument(rowId, docId) {
        document.getElementById(rowId).remove();

        const docInputs = hiddenInputs.querySelectorAll('input[name="document_type[]"]');
        const qtyInputs = hiddenInputs.querySelectorAll('input[name="quantity[]"]');
        for (let i = 0; i < docInputs.length; i++) {
            if (docInputs[i].value === docId) {
                hiddenInputs.removeChild(docInputs[i]);
                if (qtyInputs[i]) hiddenInputs.removeChild(qtyInputs[i]);
                break;
            }
        }

        updateFeeTotal();
    }

    // Close modal on Escape and prevent double-submission while submitting.
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && document.getElementById('reqModal').classList.contains('active')) {
            closeModal();
        }
    });

    const bulkForm = document.getElementById('bulkRequestForm');
    if (bulkForm) {
        bulkForm.addEventListener('submit', function () {
            const submitBtn = bulkForm.querySelector('button[type="submit"]');
            const hiddenInputs = document.getElementById('hiddenInputs');
            if (!hiddenInputs || hiddenInputs.querySelectorAll('input[name="document_type[]"]').length === 0) {
                event.preventDefault();
                alert('Please add at least one document to your request.');
                return;
            }
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> SUBMITTING...';
            }
        });
    }

    // --- Document Preview ---
    var currentPreviewDocId = null;

    function openPreview(docId, docName, previewUrl) {
        currentPreviewDocId = docId;
        var modal = document.getElementById('previewModal');
        var loading = document.getElementById('previewLoading');
        var content = document.getElementById('previewContent');
        var title = document.getElementById('previewModalTitle');

        title.textContent = docName + ' — Preview';
        loading.hidden = false;
        content.hidden = true;
        content.innerHTML = '';
        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';

        fetch(previewUrl)
            .then(function (res) {
                if (!res.ok) throw new Error('No template');
                return res.json();
            })
            .then(function (data) {
                content.innerHTML = '<div class="preview-doc-paper">' + data.html + '</div>';
                loading.hidden = true;
                content.hidden = false;
            })
            .catch(function () {
                content.innerHTML = '<div class="preview-empty"><i class="fa-solid fa-file-circle-xmark"></i><p>Preview not available for this document.</p></div>';
                loading.hidden = true;
                content.hidden = false;
            });
    }

    function closePreview() {
        var modal = document.getElementById('previewModal');
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
        syncBodyScroll();
        currentPreviewDocId = null;
    }

    function requestFromPreview() {
        var docId = currentPreviewDocId;
        closePreview();
        if (docId) {
            var select = document.getElementById('docTypeSelect');
            for (var i = 0; i < select.options.length; i++) {
                if (select.options[i].value === docId) {
                    select.selectedIndex = i;
                    break;
                }
            }
            openModal(docId, select.options[select.selectedIndex].text);
        }
    }

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && document.getElementById('previewModal').classList.contains('active')) {
            closePreview();
        }
    });

    // Close modals on backdrop tap (mobile-friendly)
    document.getElementById('reqModal').addEventListener('click', function (e) {
        if (e.target === this) closeModal();
    });
    document.getElementById('previewModal').addEventListener('click', function (e) {
        if (e.target === this) closePreview();
    });
