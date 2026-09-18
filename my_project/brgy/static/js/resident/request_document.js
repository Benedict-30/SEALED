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

    // Document type metadata (fee + required documents) supplied by the view.
    const DOC_TYPE_DATA = (function () {
        const el = document.getElementById('docTypesData');
        const map = {};
        if (!el) return map;
        try {
            JSON.parse(el.textContent).forEach(function (d) { map[d.id] = d; });
        } catch (e) { /* ignore malformed data */ }
        return map;
    })();

    function requirementsHtml(docId) {
        const data = DOC_TYPE_DATA[docId];
        const reqs = (data && data.requirements) || [];
        if (!reqs.length) {
            return '<div class="req-doc-reqs"><span class="req-doc-req-title">'
                + '<i class="fa-solid fa-circle-info"></i> No specific requirements</span></div>';
        }
        let items = '';
        reqs.forEach(function (r) { items += '<li>' + escHtml(r) + '</li>'; });
        return '<div class="req-doc-reqs"><span class="req-doc-req-title">'
            + '<i class="fa-solid fa-list-check"></i> Requirements'
            + ' <span class="req-req-required">Required</span></span><ul>' + items + '</ul></div>';
    }

    // Files chosen for each row (keyed by row id). Kept separate from the
    // live <input> so selecting/capturing more files ADDS to, not replaces,
    // what was already attached.
    const rowFiles = {};

    function renderFileList(rowId) {
        const list = document.getElementById('reqfilelist_' + rowId);
        if (!list) return;
        const files = rowFiles[rowId] || [];
        if (!files.length) {
            list.innerHTML = '';
            return;
        }
        let html = '';
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            const isImage = /\.(jpe?g|png|gif|webp)$/i.test(file.name)
                || file.type.indexOf('image/') === 0;
            html += '<span class="req-file-chip">'
                + '<i class="fa-solid ' + (isImage ? 'fa-image' : 'fa-file') + '"></i>'
                + escHtml(file.name) + '</span>';
        }
        list.innerHTML = html;
    }

    function addFilesToRow(rowId, newFiles) {
        if (!rowFiles[rowId]) rowFiles[rowId] = [];
        let added = 0;
        for (const file of newFiles) {
            if (!file) continue;
            const duplicate = rowFiles[rowId].some(function (existing) {
                return existing.name === file.name
                    && existing.size === file.size
                    && existing.lastModified === file.lastModified;
            });
            if (!duplicate) {
                rowFiles[rowId].push(file);
                added++;
            }
        }
        if (added) {
            const row = document.getElementById(rowId);
            if (row) row.classList.remove('req-missing-req');
        }
        rebuildFileInput(rowId);
    }

    function rebuildFileInput(rowId) {
        const input = document.getElementById('reqfile_' + rowId);
        if (!input) return;
        const files = rowFiles[rowId] || [];
        if (files.length) {
            const dataTransfer = new DataTransfer();
            for (const file of files) dataTransfer.items.add(file);
            input.files = dataTransfer.files;
        } else {
            input.value = '';
        }
        renderFileList(rowId);
    }

    function clearRowFiles(rowId) {
        delete rowFiles[rowId];
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
                <strong style="color:var(--text); display:block;">${escHtml(docName)}</strong>
                <div style="display:flex; align-items:center; gap:8px; margin-top:6px;">
                    <button type="button" class="qty-btn" onclick="changeQty('${rowId}', -1)">&minus;</button>
                    <input type="number" class="qty-input" value="1" min="1" max="20" readonly>
                    <button type="button" class="qty-btn" onclick="changeQty('${rowId}', 1)">+</button>
                    <span class="req-item-fee" id="${rowId}_fee">${fee ? 'Fee: ' + formatPeso(fee) : 'Free'}</span>
                </div>
                ${requirementsHtml(docId)}
                <div class="req-upload-block">
                    <input type="file" id="reqfile_${rowId}" name="requirements_${escHtml(docId)}" class="req-file-input" multiple
                           accept=".pdf,.doc,.docx,.jpg,.jpeg,.png">
                    <input type="file" id="reqimage_${rowId}" class="req-image-input"
                           accept="image/*,.jpg,.jpeg,.png,.heic,.webp">
                    <div class="req-upload-actions">
                        <button type="button" class="req-clip-btn" onclick="toggleClipMenu('${rowId}', this)">
                            <i class="fa-solid fa-paperclip"></i> Attach
                        </button>
                    </div>
                    <div class="req-clip-menu" id="reqclipmenu_${rowId}" role="menu">
                        <button type="button" class="req-clip-item" onclick="openFilePicker('${rowId}', false)">
                            <i class="fa-solid fa-folder-open"></i> Attach Files
                        </button>
                        <button type="button" class="req-clip-item" onclick="openFilePicker('${rowId}', true)">
                            <i class="fa-solid fa-image"></i> Choose Photo
                        </button>
                        <button type="button" class="req-clip-item" onclick="closeClipMenu('${rowId}'); openCamera('${rowId}')">
                            <i class="fa-solid fa-camera"></i> Take Photo
                        </button>
                    </div>
                    <div class="req-file-list" id="reqfilelist_${rowId}"></div>
                    <small class="req-file-hint">
                        Attach files, photos, or take a photo for this document (up to 5 MB each)
                    </small>
                </div>
            </div>
            <button type="button" class="remove-btn" onclick="removeDocument('${rowId}', '${docId}')" title="Remove document">
                <i class="fa-solid fa-times"></i>
            </button>
        `;
        listDiv.appendChild(row);

        const fileInput = document.getElementById('reqfile_' + rowId);
        if (fileInput) {
            fileInput.addEventListener('change', function () { addFilesToRow(rowId, fileInput.files); });
        }
        const imageInput = document.getElementById('reqimage_' + rowId);
        if (imageInput) {
            imageInput.addEventListener('change', function () { addFilesToRow(rowId, imageInput.files); });
        }

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
        clearRowFiles(rowId);

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
        bulkForm.addEventListener('submit', function (event) {
            const submitBtn = bulkForm.querySelector('button[type="submit"]');
            const hiddenInputs = document.getElementById('hiddenInputs');
            if (!hiddenInputs || hiddenInputs.querySelectorAll('input[name="document_type[]"]').length === 0) {
                event.preventDefault();
                alert('Please add at least one document to your request.');
                return;
            }
            const purposeEl = bulkForm.querySelector('textarea[name="purpose"]');
            if (purposeEl && !purposeEl.value.trim()) {
                event.preventDefault();
                if (purposeEl.reportValidity) {
                    purposeEl.reportValidity();
                } else {
                    alert('Please provide a purpose for your request.');
                }
                purposeEl.focus();
                return;
            }
            const missingRows = [];
            document.querySelectorAll('#documentList .req-item-row').forEach(function (row) {
                const fileInput = row.querySelector('.req-file-input');
                const docId = fileInput ? fileInput.name.substring('requirements_'.length) : null;
                const reqs = (DOC_TYPE_DATA[docId] && DOC_TYPE_DATA[docId].requirements) || [];
                if (!reqs.length) return;
                const files = rowFiles[row.id] || [];
                if (!files.length) {
                    missingRows.push(row);
                    row.classList.add('req-missing-req');
                }
            });
            if (missingRows.length) {
                event.preventDefault();
                let names = missingRows.map(function (row) {
                    const strong = row.querySelector('strong');
                    return '- ' + (strong ? strong.textContent : 'a selected document');
                });
                alert('Please upload the required documents before submitting:\n\n'
                    + names.join('\n') + '\n\nRequests with requirements cannot be submitted without them.');
                const first = missingRows[0];
                if (first && first.scrollIntoView) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

    // --- File picker & camera capture for requirement photos ---
    let currentCameraRowId = null;
    let reqVideoStream = null;

    function toggleClipMenu(rowId) {
        const menu = document.getElementById('reqclipmenu_' + rowId);
        if (!menu) return;
        const wasOpen = menu.classList.contains('open');
        closeAllClipMenus();
        if (!wasOpen) menu.classList.add('open');
    }

    function closeClipMenu(rowId) {
        const menu = document.getElementById('reqclipmenu_' + rowId);
        if (menu) menu.classList.remove('open');
    }

    function closeAllClipMenus() {
        document.querySelectorAll('.req-clip-menu.open').forEach(function (m) {
            m.classList.remove('open');
        });
    }

    document.addEventListener('click', function (e) {
        if (!e.target.closest('.req-clip-menu') && !e.target.closest('.req-clip-btn')) closeAllClipMenus();
    });

    function openFilePicker(rowId, imageOnly) {
        closeClipMenu(rowId);
        const input = imageOnly
            ? document.getElementById('reqimage_' + rowId)
            : document.getElementById('reqfile_' + rowId);
        if (input) input.click();
    }

    function openCamera(rowId) {
        const input = document.getElementById('reqfile_' + rowId);
        if (!input) return;

        const modal = document.getElementById('cameraModal');
        const video = document.getElementById('cameraFeed');
        if (!modal || !video) return;

        currentCameraRowId = rowId;
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';

        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            alert('Camera is not supported on this device. Please upload a file instead.');
            closeCamera();
            return;
        }

        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
            .then(function (stream) {
                reqVideoStream = stream;
                video.srcObject = stream;
            })
            .catch(function () {
                alert('Could not access the camera. Please allow camera permission or upload a file instead.');
                closeCamera();
            });
    }

    function closeCamera() {
        const modal = document.getElementById('cameraModal');
        const video = document.getElementById('cameraFeed');
        if (reqVideoStream) {
            reqVideoStream.getTracks().forEach(function (track) { track.stop(); });
            reqVideoStream = null;
        }
        if (video) video.srcObject = null;
        if (modal) modal.style.display = 'none';
        document.body.style.overflow = '';
        currentCameraRowId = null;
    }

    function capturePhoto() {
        const video = document.getElementById('cameraFeed');
        const canvas = document.getElementById('cameraCanvas');
        if (!video || !video.videoWidth) {
            alert('Camera is not ready yet. Please wait a moment and try again.');
            return;
        }

        const context = canvas.getContext('2d');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);

        const rowId = currentCameraRowId;
        canvas.toBlob(function (blob) {
            if (!blob || !rowId) { closeCamera(); return; }
            const photo = new File([blob], 'photo_' + Date.now() + '.jpg', { type: 'image/jpeg' });
            addFilesToRow(rowId, [photo]);
            closeCamera();
        }, 'image/jpeg', 0.9);
    }

    document.addEventListener('click', function (e) {
        const modal = document.getElementById('cameraModal');
        if (modal && e.target === modal) closeCamera();
    });
