document.addEventListener("DOMContentLoaded", function () {

    var isEditing = false;

    window.toggleEditMode = function () {
        isEditing = !isEditing;
        var page = document.getElementById('profilePage');
        var editBtn = document.getElementById('editProfileBtn');
        var saveActions = document.getElementById('saveActions');
        var editFields = document.querySelectorAll('.edit-mode');

        if (isEditing) {
            page.classList.add('editing');
            editFields.forEach(function (el) {
                el.style.display = '';
            });
            if (saveActions) saveActions.style.display = 'block';
            if (editBtn) {
                editBtn.innerHTML = '<i class="fa-solid fa-xmark"></i> Cancel Editing';
                editBtn.classList.remove('hero-btn-edit');
                editBtn.classList.add('hero-btn-cancel');
            }
            document.getElementById('editModeFlag').value = 'true';
        } else {
            page.classList.remove('editing');
            editFields.forEach(function (el) {
                el.style.display = 'none';
            });
            if (saveActions) saveActions.style.display = 'none';
            if (editBtn) {
                editBtn.innerHTML = '<i class="fa-solid fa-pen-to-square"></i> Edit Profile';
                editBtn.classList.remove('hero-btn-cancel');
                editBtn.classList.add('hero-btn-edit');
            }
            document.getElementById('editModeFlag').value = 'false';
        }
    };

    window.previewAvatar = function (input) {
        if (input.files && input.files[0]) {
            var reader = new FileReader();
            reader.onload = function (e) {
                var ring = document.querySelector('.avatar-ring');
                var img = ring.querySelector('img');

                if (!img) {
                    var placeholder = ring.querySelector('.avatar-placeholder');
                    img = document.createElement('img');
                    img.alt = 'Profile Picture';
                    ring.replaceChild(img, placeholder);
                }

                img.src = e.target.result;

                if (!isEditing) {
                    window.toggleEditMode();
                }
            };
            reader.readAsDataURL(input.files[0]);
        }
    };

    // Animate completion ring on load
    var ring = document.querySelector('.ring-fill');
    if (ring) {
        var target = ring.getAttribute('stroke-dashoffset');
        ring.setAttribute('stroke-dashoffset', '263.89');
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                ring.style.transition = 'stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1)';
                ring.setAttribute('stroke-dashoffset', target);
            });
        });
    }

});
