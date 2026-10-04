/**
 * Dynamic Table Renderer Utility
 */
export const Tables = {
  renderTable({ containerId, columns, data, onRowClick }) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!data || data.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.6" d="M9 17.25v1.5m6-1.5v1.5m-10.5-15h15M4.5 3.75v16.5h15V3.75"/>
            </svg>
          </div>
          <h4 class="empty-state-title">No records found</h4>
          <p class="empty-state-message">Try adjusting filters or switching vendor scope.</p>
        </div>
      `;
      return;
    }

    let html = `
      <div class="overflow-x-auto table-wrap">
        <table class="custom-table">
          <thead>
            <tr>
              ${columns.map(col => `<th>${col.label}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
    `;

    data.forEach((row, idx) => {
      html += `<tr class="hover:bg-[#fdf8f0] cursor-pointer group" data-idx="${idx}">`;
      columns.forEach(col => {
        const val = row[col.key] !== undefined ? row[col.key] : '';
        const formatted = col.render ? col.render(val, row) : val;
        html += `<td>${formatted}</td>`;
      });
      html += `</tr>`;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;

    container.innerHTML = html;

    if (onRowClick) {
      container.querySelectorAll('tbody tr').forEach(tr => {
        tr.addEventListener('click', () => {
          const idx = parseInt(tr.getAttribute('data-idx'));
          onRowClick(data[idx]);
        });
      });
    }
  }
};
