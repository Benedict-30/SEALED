function openIdModal(name, email, phone, address, frontUrl, backUrl) {
    document.getElementById('idModalTitle').textContent = name + ' — ID Verification';
    document.getElementById('idModalInfo').innerHTML = `
        <div><span class="info-label">Email:</span></div><div><span class="info-value">${email}</span></div>
        <div><span class="info-label">Phone:</span></div><div><span class="info-value">${phone}</span></div>
        <div><span class="info-label">Address:</span></div><div><span class="info-value" style="grid-column:1/-1;">${address}</span></div>
    `;
    let imgs = '';
    if (frontUrl) {
        imgs += `<div class="id-img-box"><img src="${frontUrl}" alt="ID Front"><div class="id-label">Front Side</div></div>`;
    }
    if (backUrl) {
        imgs += `<div class="id-img-box"><img src="${backUrl}" alt="ID Back"><div class="id-label">Back Side</div></div>`;
    }
    if (!frontUrl && !backUrl) {
        imgs = '<div style="grid-column:1/-1;text-align:center;color:var(--text-muted);padding:32px;">No ID photos uploaded.</div>';
    }
    document.getElementById('idModalImages').innerHTML = imgs;
    document.getElementById('idModal').classList.add('show');
    document.body.style.overflow = 'hidden';
}

function closeIdModal() {
    document.getElementById('idModal').classList.remove('show');
    document.body.style.overflow = '';
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeIdModal();
});
