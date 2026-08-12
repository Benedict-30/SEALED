/* ═══════════════════════════════════════════════════════════════
   Multi-Step Registration Logic
   ═══════════════════════════════════════════════════════════════ */

let currentStep = 1;
const totalSteps = 4;

function goToStep(step) {
    // Hide all panels
    document.querySelectorAll('.step-panel').forEach(function(panel) {
        panel.classList.remove('active');
    });

    // Show target panel
    const targetPanel = document.querySelector('.step-panel[data-panel="' + step + '"]');
    if (targetPanel) {
        targetPanel.classList.add('active');
    }

    // Update progress items
    document.querySelectorAll('.step-progress-item').forEach(function(item) {
        const itemStep = parseInt(item.getAttribute('data-step'));
        item.classList.remove('active', 'completed');

        if (itemStep < step) {
            item.classList.add('completed');
            item.querySelector('.step-circle').innerHTML = '<i class="fa-solid fa-check" style="font-size:14px;"></i>';
        } else if (itemStep === step) {
            item.classList.add('active');
            item.querySelector('.step-circle').textContent = itemStep;
        } else {
            item.querySelector('.step-circle').textContent = itemStep;
        }
    });

    // Update connectors
    document.querySelectorAll('.step-connector').forEach(function(conn, index) {
        conn.classList.remove('active', 'completed');
        if (index < step - 1) {
            conn.classList.add('completed');
        } else if (index === step - 1) {
            conn.classList.add('active');
        }
    });

    currentStep = step;

    // Scroll to top of form
    const formWrapper = document.querySelector('.auth-form-wrapper');
    if (formWrapper) {
        formWrapper.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function nextStep(current) {
    if (!validateStep(current)) return;
    if (current < totalSteps) goToStep(current + 1);
}

function validateStep(stepNum) {
    var panel = document.querySelector('.step-panel[data-panel="' + stepNum + '"]');
    if (!panel) return true;

    var inputs = panel.querySelectorAll('input[required], select[required], textarea[required]');
    var firstInvalid = null;
    var allValid = true;

    panel.querySelectorAll('.form-input').forEach(function(inp) {
        inp.classList.remove('is-invalid');
    });
    panel.querySelectorAll('.step-error-msg').forEach(function(el) {
        el.remove();
    });

    inputs.forEach(function(inp) {
        if (!inp.value || (inp.tagName === 'SELECT' && inp.value === '')) {
            allValid = false;
            inp.classList.add('is-invalid');

            var errDiv = document.createElement('div');
            errDiv.className = 'form-error step-error-msg';
            errDiv.textContent = 'This field is required.';
            inp.parentNode.insertBefore(errDiv, inp.nextSibling);

            if (!firstInvalid) firstInvalid = inp;
        }
    });

    if (!allValid && firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    return allValid;
}

function prevStep(current) {
    if (current > 1) {
        goToStep(current - 1);
    }
}

// ─── File Upload Preview ───────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    const fileInputs = document.querySelectorAll('input[type="file"]');
    fileInputs.forEach(function(input) {
        input.addEventListener('change', function() {
            const label = this.previousElementSibling;
            if (label && label.classList.contains('custom-file-upload')) {
                const span = label.querySelector('span[data-text]');
                if (span) {
                    if (this.files && this.files.length > 0) {
                        const fileName = this.files[0].name;
                        span.textContent = '✅ ' + fileName;
                        span.style.color = 'var(--success)';
                        span.style.fontWeight = '600';
                        label.style.borderColor = 'var(--success)';
                        label.style.background = 'var(--success-bg)';
                    } else {
                        span.textContent = span.getAttribute('data-text');
                        span.style.color = '';
                        span.style.fontWeight = '';
                        label.style.borderColor = '';
                        label.style.background = '';
                    }
                }
            }
        });
    });
});

// ─── Camera Capture ───────────────────────────────────────────
let currentCameraTarget = null;
let videoStream = null;

function openCamera(target) {
    currentCameraTarget = target;
    const modal = document.getElementById('cameraModal');
    const video = document.getElementById('cameraFeed');
    const title = document.getElementById('cameraModalTitle');

    // Updated titles for all 3 targets
    if (target === 'front') title.textContent = 'Capture ID Front';
    else if (target === 'back') title.textContent = 'Capture ID Back';
    else if (target === 'selfie') title.textContent = 'Capture Selfie with ID';

    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // Use front camera (user) for selfie, rear camera (environment) for ID pictures
    const facingMode = (target === 'selfie') ? 'user' : 'environment';
    
    navigator.mediaDevices.getUserMedia({ video: { facingMode: facingMode } })
        .then(function(stream) {
            videoStream = stream;
            video.srcObject = stream;
        })
        .catch(function(err) {
            alert('Could not access camera. Please check permissions or upload a file instead.');
            closeCamera();
            console.error('Camera error:', err);
        });
}

function closeCamera() {
    const modal = document.getElementById('cameraModal');
    const video = document.getElementById('cameraFeed');

    if (videoStream) {
        videoStream.getTracks().forEach(function(track) { track.stop(); });
        videoStream = null;
    }
    video.srcObject = null;
    modal.style.display = 'none';
    document.body.style.overflow = '';
    currentCameraTarget = null;
}

function capturePhoto() {
    const video = document.getElementById('cameraFeed');
    const canvas = document.getElementById('cameraCanvas');
    const context = canvas.getContext('2d');

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    // If taking a selfie, mirror the image so it looks natural to the user
    if (currentCameraTarget === 'selfie') {
        context.translate(canvas.width, 0);
        context.scale(-1, 1);
    }
    
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(function(blob) {
        if (!blob) {
            alert('Failed to capture image.');
            return;
        }

        const capturedFile = new File([blob], 'captured_' + currentCameraTarget + '.jpg', { type: 'image/jpeg' });
        
        // Map the target to the correct input ID
        let inputId;
        if (currentCameraTarget === 'front') inputId = 'id_id_front';
        else if (currentCameraTarget === 'back') inputId = 'id_id_back';
        else if (currentCameraTarget === 'selfie') inputId = 'id_id_selfie';

        const fileInput = document.getElementById(inputId);

        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(capturedFile);
        fileInput.files = dataTransfer.files;

        // Trigger change event for preview
        fileInput.dispatchEvent(new Event('change'));

        closeCamera();
    }, 'image/jpeg', 0.9);
}

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeCamera();
    }
});

// Close modal on overlay click
document.addEventListener('click', function(e) {
    const modal = document.getElementById('cameraModal');
    if (e.target === modal) {
        closeCamera();
    }
});