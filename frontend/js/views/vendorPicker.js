import { ApiClient } from '../api.js';
import { Store } from '../store.js';
import { Toast } from '../components/toast.js';

// This screen IS the sign-in screen — there are no credentials. Picking (or
// creating) a vendor is what authenticates the session.
export const VendorPickerView = {
  async init() {
    this.showList();
    await this.loadVendors();
    this.bindEvents();
  },

  bindEvents() {
    const newVendorBtn = document.getElementById('vendor-picker-new-btn');
    if (newVendorBtn) newVendorBtn.onclick = () => this.showNewVendorForm();

    const backBtn = document.getElementById('vendor-picker-back-btn');
    if (backBtn) backBtn.onclick = () => this.showList();

    const form = document.getElementById('vendor-picker-new-form');
    if (form) {
      form.onsubmit = (e) => {
        e.preventDefault();
        this.signInAsNewVendor();
      };
    }

    const allVendorsBtn = document.getElementById('vendor-picker-all-btn');
    if (allVendorsBtn) allVendorsBtn.onclick = () => this.signIn({});
  },

  showList() {
    document.getElementById('vendor-picker-list-view')?.classList.remove('hidden');
    document.getElementById('vendor-picker-new-view')?.classList.add('hidden');
  },

  showNewVendorForm() {
    document.getElementById('vendor-picker-list-view')?.classList.add('hidden');
    document.getElementById('vendor-picker-new-view')?.classList.remove('hidden');
    document.getElementById('vendor-picker-new-name')?.focus();
  },

  async loadVendors() {
    const container = document.getElementById('vendor-picker-list');
    if (!container) return;
    container.innerHTML = '<p class="text-xs text-stone-500">Loading vendors…</p>';

    try {
      const vendors = await ApiClient.listPublicVendors();
      if (!vendors.length) {
        container.innerHTML = '<p class="text-xs text-stone-500">No vendors yet — start a new one below.</p>';
        return;
      }
      container.innerHTML = vendors.map(v => `
        <button data-vendor-id="${v.vendor_id}" class="vendor-picker-card w-full text-left px-4 py-3 bg-white hover:bg-amber-50 border border-stone-200 hover:border-amber-400 rounded-lg transition-all flex items-center justify-between">
          <div>
            <div class="text-sm font-semibold text-stone-900">${v.vendor_name}</div>
            <div class="text-[11px] text-stone-500">${v.vendor_id}${v.category ? ' · ' + v.category : ''}</div>
          </div>
          <svg class="w-4 h-4 text-stone-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
        </button>
      `).join('');

      container.querySelectorAll('.vendor-picker-card').forEach(btn => {
        btn.onclick = () => this.signIn({ vendor_id: btn.getAttribute('data-vendor-id') });
      });
    } catch (e) {
      container.innerHTML = '<p class="text-xs text-rose-700">Failed to load vendors.</p>';
    }
  },

  async signIn(payload) {
    try {
      const data = await ApiClient.login(payload);
      Store.update('auth', { token: data.access_token, refreshToken: data.refresh_token });
      Store.persistAuth();
      await window.app.enterDashboard(data.vendor_id);
    } catch (err) {
      Toast.show(err.message || 'Sign-in failed', 'error');
    }
  },

  async signInAsNewVendor() {
    const nameInput = document.getElementById('vendor-picker-new-name');
    const deptInput = document.getElementById('vendor-picker-new-dept');
    const categoryInput = document.getElementById('vendor-picker-new-category');
    const submitBtn = document.getElementById('vendor-picker-new-submit');

    const vendor_name = nameInput.value.trim();
    if (!vendor_name) return;

    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating...';

    try {
      const data = await ApiClient.login({
        vendor_name,
        department: deptInput.value.trim() || null,
        category: categoryInput.value.trim() || null
      });
      Store.update('auth', { token: data.access_token, refreshToken: data.refresh_token });
      Store.persistAuth();
      Toast.show(`${data.vendor_id} created — starting with a clean dashboard.`, 'success');
      await window.app.enterDashboard(data.vendor_id);
    } catch (err) {
      Toast.show(err.message || 'Vendor creation failed', 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Create & Sign In';
    }
  }
};
