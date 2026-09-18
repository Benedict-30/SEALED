// ==========================================
// RESPONSIVE TABLES (stacked cards on mobile)
// Adds data-label to each cell from its <th> so CSS can
// collapse any .table / .es-table into labeled rows <=768px.
// ==========================================
(function () {
    function labelTables() {
        var tables = document.querySelectorAll('table.table, table.es-table');
        tables.forEach(function (table) {
            var headers = table.querySelectorAll('thead th');
            if (!headers.length) return;

            table.classList.add('rtable-stack');

            table.querySelectorAll('tbody tr').forEach(function (row) {
                Array.prototype.forEach.call(row.children, function (cell, index) {
                    var th = headers[index];
                    var label = th ? th.textContent.replace(/\s+/g, ' ').trim() : '';
                    if (label) {
                        cell.setAttribute('data-label', label);
                    } else {
                        cell.removeAttribute('data-label');
                    }
                });
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', labelTables);
    } else {
        labelTables();
    }
})();
