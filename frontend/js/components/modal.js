/**
 * Modal & Side Drawer Inspector Component
 */
export const Modal = {
  _lastFocused: null,

  openDrawer(title, contentHtml) {
    let overlay = document.getElementById('global-drawer-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'global-drawer-overlay';
      overlay.className = 'drawer-overlay';
      overlay.innerHTML = `
        <div class="drawer-content" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabindex="-1">
          <div class="p-4 border-b border-stone-200 flex justify-between items-center bg-[#fbf8f3] sticky top-0 z-10">
            <h3 id="drawer-title" class="text-[13px] font-semibold text-stone-900 flex items-center gap-2 tracking-tight">Inspector</h3>
            <button id="drawer-close-btn" class="w-8 h-8 rounded-full bg-white border border-stone-200 text-stone-500 hover:text-stone-900 hover:border-stone-300 hover:shadow-sm flex items-center justify-center transition-all">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div id="drawer-body" class="p-5 overflow-y-auto flex-1 text-sm text-stone-700 space-y-4 bg-white"></div>
        </div>
      `;
      document.body.appendChild(overlay);

      overlay.querySelector('#drawer-close-btn').onclick = () => Modal.closeDrawer();
      overlay.onclick = (e) => {
        if (e.target === overlay) Modal.closeDrawer();
      };
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.classList.contains('active')) Modal.closeDrawer();
        if (e.key === 'Tab' && overlay.classList.contains('active')) Modal._trapTab(e, overlay);
      });
    }

    document.getElementById('drawer-title').innerHTML = title;
    document.getElementById('drawer-body').innerHTML = contentHtml;

    Modal._lastFocused = document.activeElement;
    overlay.classList.add('active');
    const content = overlay.querySelector('.drawer-content');
    setTimeout(() => content.focus(), 10);
  },

  closeDrawer() {
    const overlay = document.getElementById('global-drawer-overlay');
    if (overlay) {
      overlay.classList.remove('active');
    }
    if (Modal._lastFocused) Modal._lastFocused.focus();
  },

  _trapTab(e, overlay) {
    const focusables = overlay.querySelectorAll('button, a[href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
};
