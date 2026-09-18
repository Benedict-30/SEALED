document.querySelectorAll('.history-item-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
        const item = btn.closest('.history-item');
        const body = item.querySelector('.history-item-body');
        const expanded = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', String(!expanded));
        item.classList.toggle('open', !expanded);
        if (body) body.hidden = expanded;
    });
});