/**
 * Toast Notification Utilities
 */
export const Toast = {
  show(message, type = 'info', duration = 4000) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none';
      document.body.appendChild(container);
    }

    const iconSvg = {
      success: '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>',
      error: '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/></svg>',
      warning: '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 9v3.75m0 3.75h.008M10.29 3.86L1.82 18a1.5 1.5 0 001.29 2.25h17.78a1.5 1.5 0 001.29-2.25L13.71 3.86a1.5 1.5 0 00-2.42 0z"/></svg>',
      info: '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 11.25v4.5m0-8.25h.008M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
    };
    const icons = {
      success: `<span class="w-6 h-6 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-300">${iconSvg.success}</span>`,
      error: `<span class="w-6 h-6 rounded-full bg-rose-500/20 flex items-center justify-center text-rose-300">${iconSvg.error}</span>`,
      warning: `<span class="w-6 h-6 rounded-full bg-amber-500/20 flex items-center justify-center text-amber-300">${iconSvg.warning}</span>`,
      info: `<span class="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center text-slate-200">${iconSvg.info}</span>`
    };
    const toast = document.createElement('div');
    toast.className = `pointer-events-auto pl-2 pr-3 py-2 rounded-full shadow-xl text-sm font-medium border backdrop-blur-xl transition-all transform translate-y-2 opacity-0 flex items-center gap-2.5 ${
      type === 'success' ? 'bg-emerald-950/95 text-emerald-100 border-emerald-500/30' :
      type === 'error' ? 'bg-rose-950/95 text-rose-100 border-rose-500/30' :
      type === 'warning' ? 'bg-amber-950/95 text-amber-100 border-amber-500/30' :
      'bg-stone-900/95 text-stone-100 border-white/10'
    }`;

    toast.innerHTML = `
      ${icons[type] || icons.info}
      <span class="pr-1 leading-none tracking-tight">${message}</span>
      <button class="ml-auto w-6 h-6 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center opacity-70 hover:opacity-100 text-white transition-colors">${iconSvg.error}</button>
    `;

    container.appendChild(toast);

    // Animate in — premium spring
    requestAnimationFrame(() => {
      toast.style.transition = 'all 0.42s cubic-bezier(0.16,1,0.3,1)';
      toast.classList.remove('translate-y-2', 'opacity-0');
    });

    toast.querySelector('button').onclick = () => toast.remove();

    setTimeout(() => {
      toast.classList.add('opacity-0', 'translate-y-2');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }
};
