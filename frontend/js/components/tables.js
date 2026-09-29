/**
 * Dynamic Table Renderer Utility
 */
export const Tables = {
  renderTable({ containerId, columns, data, onRowClick }) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!data || data.length === 0) {
      container.innerHTML = `
        <div class="p-10 text-center border border-dashed border-stone-300 rounded-xl bg-[#fbf8f3]/60">
          <div class="w-10 h-10 rounded-full bg-white border border-stone-200 flex items-center justify-center mx-auto mb-3 shadow-sm text-stone-400">—</div>
          <p class="text-sm font-semibold text-stone-700">No records found</p>
          <p class="text-xs text-stone-500 mt-1">Try adjusting filters or switching vendor scope.</p>
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
