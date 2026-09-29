/**
 * Shared Empty-State Renderer — used by all data-bearing views when the active
 * vendor scope has no records yet (e.g. a freshly provisioned vendor).
 */
export const EmptyState = {
  render(containerId, { title = 'No data yet', message = '', actionLabel = null, onAction = null } = {}) {
    const el = document.getElementById(containerId);
    if (!el) return;

    el.innerHTML = `
      <div class="flex flex-col items-center justify-center text-center py-12 px-6 rounded-xl border border-dashed border-stone-300 bg-[#fbf8f3]/40">
        <div class="w-12 h-12 rounded-2xl bg-white border border-stone-200 flex items-center justify-center mb-3 shadow-sm">
          <svg class="w-6 h-6 text-stone-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.6" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0l-3.5 3.5a2 2 0 01-1.4.6H8.9a2 2 0 01-1.4-.6L4 13"/>
          </svg>
        </div>
        <h4 class="text-sm font-semibold text-stone-800 tracking-tight">${title}</h4>
        <p class="text-xs text-stone-500 mt-1.5 max-w-sm leading-relaxed">${message}</p>
        ${actionLabel ? `<button id="${containerId}-empty-action" class="mt-5 px-5 py-2 bg-stone-900 hover:bg-stone-800 text-white text-xs font-semibold rounded-full transition-all shadow-md">${actionLabel}</button>` : ''}
      </div>
    `;

    if (actionLabel && onAction) {
      const btn = document.getElementById(`${containerId}-empty-action`);
      if (btn) btn.onclick = onAction;
    }
  }
};
