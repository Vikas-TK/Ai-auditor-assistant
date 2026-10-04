/**
 * Shared confirmation dialog for destructive or hard-to-undo actions
 * (e.g. clearing filters data, injecting synthetic anomalies, logout).
 * Purely presentational — callers decide what the confirmed action does.
 */
export const ConfirmDialog = {
  _onConfirm: null,
  _lastFocused: null,

  open({
    title = 'Are you sure?',
    message = '',
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    danger = true,
    onConfirm = null
  } = {}) {
    let overlay = document.getElementById('global-confirm-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'global-confirm-overlay';
      overlay.className = 'confirm-overlay';
      overlay.innerHTML = `
        <div class="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" tabindex="-1">
          <div class="p-5">
            <div id="confirm-dialog-icon" class="confirm-dialog-icon">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M12 9v3.75m0 3.75h.008M10.29 3.86L1.82 18a1.5 1.5 0 001.29 2.25h17.78a1.5 1.5 0 001.29-2.25L13.71 3.86a1.5 1.5 0 00-2.42 0z"/></svg>
            </div>
            <h3 id="confirm-dialog-title" class="confirm-dialog-title"></h3>
            <p id="confirm-dialog-body" class="confirm-dialog-body"></p>
            <div class="confirm-dialog-actions">
              <button id="confirm-dialog-cancel" class="btn-ghost"></button>
              <button id="confirm-dialog-confirm" class="btn-danger"></button>
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);

      overlay.onclick = (e) => {
        if (e.target === overlay) ConfirmDialog.close();
      };
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.classList.contains('active')) ConfirmDialog.close();
      });
      overlay.querySelector('#confirm-dialog-cancel').onclick = () => ConfirmDialog.close();
      overlay.querySelector('#confirm-dialog-confirm').onclick = () => {
        const cb = ConfirmDialog._onConfirm;
        ConfirmDialog.close();
        if (cb) cb();
      };
    }

    document.getElementById('confirm-dialog-title').textContent = title;
    document.getElementById('confirm-dialog-body').textContent = message;
    document.getElementById('confirm-dialog-cancel').textContent = cancelLabel;
    const confirmBtn = document.getElementById('confirm-dialog-confirm');
    confirmBtn.textContent = confirmLabel;
    confirmBtn.className = danger ? 'btn-danger' : 'btn-amber';

    const iconEl = document.getElementById('confirm-dialog-icon');
    iconEl.className = `confirm-dialog-icon ${danger ? 'is-danger' : 'is-neutral'}`;

    ConfirmDialog._onConfirm = onConfirm;
    ConfirmDialog._lastFocused = document.activeElement;

    overlay.classList.add('active');
    const dialogEl = overlay.querySelector('.confirm-dialog');
    setTimeout(() => dialogEl.focus(), 10);

    dialogEl.onkeydown = (e) => {
      if (e.key !== 'Tab') return;
      const focusables = dialogEl.querySelectorAll('button');
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
  },

  close() {
    const overlay = document.getElementById('global-confirm-overlay');
    if (overlay) overlay.classList.remove('active');
    if (ConfirmDialog._lastFocused) ConfirmDialog._lastFocused.focus();
    ConfirmDialog._onConfirm = null;
  }
};
