document.addEventListener("DOMContentLoaded", function() {
    
    let isEditing = false;

    // Make functions global so the HTML 'onclick' attributes can find them
    window.toggleEditMode = function() {
        isEditing = !isEditing;
        const viewElements = document.querySelectorAll('.view-mode');
        const editElements = document.querySelectorAll('.edit-mode');
        const editBtn = document.getElementById('editProfileBtn');
        const saveActions = document.getElementById('saveActions');

        if (isEditing) {
            viewElements.forEach(el => el.style.display = 'none');
            editElements.forEach(el => el.style.display = (el.tagName === 'DIV') ? 'flex' : 'block');
            if(saveActions) saveActions.style.display = 'flex';
            if(editBtn) editBtn.style.display = 'none';
            document.getElementById('editModeFlag').value = 'true';
        } else {
            viewElements.forEach(el => el.style.display = 'block');
            editElements.forEach(el => el.style.display = 'none');
            if(saveActions) saveActions.style.display = 'none';
            if(editBtn) editBtn.style.display = 'inline-flex';
            document.getElementById('editModeFlag').value = 'false';
        }
    };

    window.previewAvatar = function(input) {
        if (input.files && input.files[0]) {
            var reader = new FileReader();
            reader.onload = function(e) {
                const wrapper = document.querySelector('.profile-avatar-wrapper');
                let avatarEl = wrapper.querySelector('img');
                
                if (!avatarEl) {
                    const divIcon = wrapper.querySelector('.profile-avatar');
                    avatarEl = document.createElement('img');
                    avatarEl.className = 'profile-avatar';
                    wrapper.replaceChild(avatarEl, divIcon);
                }
                
                avatarEl.src = e.target.result;
                
                if(!isEditing) {
                    window.toggleEditMode();
                }
            }
            reader.readAsDataURL(input.files[0]);
        }
    };

    // Sidebar smooth scroll
    document.querySelectorAll('.sidebar-menu a').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);
            if(targetElement) {
                targetElement.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            
            document.querySelectorAll('.sidebar-menu a').forEach(a => a.classList.remove('active'));
            this.classList.add('active');
        });
    });

});