(function() {
    var hex = document.documentElement.dataset.themeColor || '';
    if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return;
    // Parse hex to RGB
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);

    // Generate light variant (mix with white)
    var lr = Math.round(r + (255 - r) * 0.65);
    var lg = Math.round(g + (255 - g) * 0.65);
    var lb = Math.round(b + (255 - b) * 0.65);
    var light = '#' + [lr, lg, lb].map(c => c.toString(16).padStart(2, '0')).join('');

    // Generate dark variant (mix with black)
    var dr = Math.round(r * 0.75);
    var dg = Math.round(g * 0.75);
    var db = Math.round(b * 0.75);
    var dark = '#' + [dr, dg, db].map(c => c.toString(16).padStart(2, '0')).join('');

    // Generate very light background tint
    var blr = Math.round(r + (255 - r) * 0.9);
    var blg = Math.round(g + (255 - g) * 0.9);
    var blb = Math.round(b + (255 - b) * 0.9);
    var bgLight = '#' + [blr, blg, blb].map(c => c.toString(16).padStart(2, '0')).join('');

    // Generate a soft translucent tint used for glass accents
    function rgba(alpha) {
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

    var root = document.documentElement.style;
    root.setProperty('--primary-light', light);
    root.setProperty('--primary-dark', dark);
    root.setProperty('--primary-bg', bgLight);

    // Hero banner gradient + shadow tinted to match the theme color
    root.setProperty('--hero-bg', 'linear-gradient(120deg, ' + dark + ' 0%, ' + hex + ' 100%)');
    root.setProperty('--hero-shadow', 'rgba(' + dr + ',' + dg + ',' + db + ',0.25)');

    root.setProperty('--glass-primary', rgba(0.08));
    root.setProperty('--glass-primary-border', rgba(0.22));
    root.setProperty('--primary', hex, 'important');
})();