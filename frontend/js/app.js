import { ApiClient, setAuthFailureHandler } from './api.js';
import { Toast } from './components/toast.js';
import { Modal } from './components/modal.js';
import { Store } from './store.js';
import { VendorPickerView } from './views/vendorPicker.js';
import { OverviewView } from './views/overview.js';
import { ReconView } from './views/recon.js';
import { AnomalyView } from './views/anomaly.js';
import { RagView } from './views/rag.js';
import { DataCenterView } from './views/datacenter.js';
import { ReportView } from './views/report.js';

const ADD_NEW_VENDOR_VALUE = '__add_new__';

class App {
  constructor() {
    this.currentView = 'overview';
    this.views = {
      overview: OverviewView,
      recon: ReconView,
      anomaly: AnomalyView,
      rag: RagView,
      datacenter: DataCenterView,
      report: ReportView
    };
  }

  async init() {
    Store.hydrateFromStorage();
    setAuthFailureHandler(() => this.showSignIn());

    this.bindNavigation();
    this.bindVendorSwitcher();
    this.bindLogout();

    if (!Store.isAuthenticated()) {
      this.showSignIn();
      return;
    }

    // Resumed session (valid token from a previous visit) — skip the sign-in
    // screen and go straight back to whichever vendor was last active.
    await this.enterDashboard(Store.get('activeVendorContext') || 'ALL');
  }

  showSignIn() {
    document.getElementById('app-shell').classList.add('hidden');
    document.getElementById('vendor-picker-screen').classList.remove('hidden');
    VendorPickerView.init();
  }

  async enterDashboard(vendorId) {
    Store.set('activeVendorContext', vendorId);
    Store.persistAuth();
    Store.clearVendorScopedCache();

    document.getElementById('vendor-picker-screen').classList.add('hidden');
    document.getElementById('app-shell').classList.remove('hidden');

    await this.checkSystemHealth();
    await this.refreshVendorSwitcherOptions(vendorId);
    this.switchView('overview');
  }

  bindLogout() {
    const btn = document.getElementById('logout-btn');
    if (btn) {
      btn.onclick = async () => {
        await ApiClient.logout();
        this.showSignIn();
      };
    }
  }

  bindNavigation() {
    document.querySelectorAll('[data-view-target]').forEach(btn => {
      btn.onclick = (e) => {
        e.preventDefault();
        const target = btn.getAttribute('data-view-target');
        this.switchView(target);
      };
    });
  }

  async refreshVendorSwitcherOptions(selectValue) {
    const switcherSelect = document.getElementById('vendor-switcher');
    if (!switcherSelect) return;

    try {
      const vendors = await ApiClient.listPublicVendors();
      const options = [
        `<option value="ALL">All Vendors (Global)</option>`,
        ...vendors.map(v => `<option value="${v.vendor_id}">${v.vendor_name} (${v.vendor_id})</option>`),
        `<option value="${ADD_NEW_VENDOR_VALUE}">+ Add New Vendor</option>`
      ];
      switcherSelect.innerHTML = options.join('');
      switcherSelect.value = selectValue || Store.get('activeVendorContext') || 'ALL';
    } catch (e) {
      console.warn('Failed to load vendor switcher options:', e);
    }
  }

  bindVendorSwitcher() {
    const switcherSelect = document.getElementById('vendor-switcher');
    if (!switcherSelect) return;

    switcherSelect.onchange = async () => {
      const value = switcherSelect.value;

      if (value === ADD_NEW_VENDOR_VALUE) {
        this.openAddVendorModal();
        switcherSelect.value = Store.get('activeVendorContext') || 'ALL';
        return;
      }

      Store.set('activeVendorContext', value);
      Store.persistAuth();
      Store.clearVendorScopedCache();
      Toast.show(`Switched to ${switcherSelect.options[switcherSelect.selectedIndex].text}`, 'info', 2000);

      // Re-fetch the currently active view under the new vendor context
      const view = this.views[this.currentView];
      if (view && view.init) view.init();
    };
  }

  openAddVendorModal() {
    Modal.openDrawer('Provision New Vendor', `
      <form id="add-vendor-form" class="space-y-4">
        <div class="space-y-1.5">
          <label class="text-xs font-semibold text-stone-700 block">Vendor Name</label>
          <input type="text" id="new-vendor-name" required placeholder="e.g. Acme Technologies Pvt Ltd" class="w-full px-3.5 py-2.5 bg-white border border-stone-300 rounded-xl text-xs text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/10">
        </div>
        <div class="space-y-1.5">
          <label class="text-xs font-semibold text-stone-700 block">Department (optional)</label>
          <input type="text" id="new-vendor-dept" placeholder="e.g. Operations" class="w-full px-3.5 py-2.5 bg-white border border-stone-300 rounded-xl text-xs text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/10">
        </div>
        <div class="space-y-1.5">
          <label class="text-xs font-semibold text-stone-700 block">Category (optional)</label>
          <input type="text" id="new-vendor-category" placeholder="e.g. Software & Hardware" class="w-full px-3.5 py-2.5 bg-white border border-stone-300 rounded-xl text-xs text-stone-900 placeholder:text-stone-400 focus:outline-none focus:border-amber-500 focus:ring-2 focus:ring-amber-500/10">
        </div>
        <button type="submit" class="w-full py-2.5 bg-stone-900 hover:bg-stone-800 text-white text-xs font-semibold rounded-full transition-all shadow-md">
          Create Vendor
        </button>
      </form>
    `);

    document.getElementById('add-vendor-form').onsubmit = async (e) => {
      e.preventDefault();
      const vendor_name = document.getElementById('new-vendor-name').value.trim();
      const department = document.getElementById('new-vendor-dept').value.trim() || null;
      const category = document.getElementById('new-vendor-category').value.trim() || null;

      try {
        const vendor = await ApiClient.createVendor({ vendor_name, department, category });
        Toast.show(`Vendor ${vendor.vendor_id} created`, 'success');
        Modal.closeDrawer();

        Store.set('activeVendorContext', vendor.vendor_id);
        Store.persistAuth();
        Store.clearVendorScopedCache();
        await this.refreshVendorSwitcherOptions(vendor.vendor_id);

        const view = this.views[this.currentView];
        if (view && view.init) view.init();
      } catch (err) {
        Toast.show(err.message || 'Vendor creation failed', 'error');
      }
    };
  }

  switchView(viewName) {
    if (!Store.isAuthenticated()) {
      this.showSignIn();
      return;
    }
    if (!this.views[viewName]) return;

    const viewTitles = {
      overview: 'Audit Copilot Control Center',
      recon: '3-Way Reconciliation Workspace',
      anomaly: 'Anomaly & Fraud Lab',
      rag: 'Policy RAG Copilot',
      datacenter: 'Ledger Data Center',
      report: 'Working Paper Report'
    };
    const titleEl = document.getElementById('header-title');
    if (titleEl && viewTitles[viewName]) {
      titleEl.style.opacity = '0';
      titleEl.style.transform = 'translateY(4px)';
      setTimeout(() => {
        titleEl.textContent = viewTitles[viewName];
        titleEl.style.transition = 'all 0.3s cubic-bezier(0.16,1,0.3,1)';
        titleEl.style.opacity = '1';
        titleEl.style.transform = 'translateY(0)';
      }, 120);
    }

    // Smooth cross-fade between panels
    const panels = document.querySelectorAll('[data-view-panel]');
    const outgoing = document.querySelector(`[data-view-panel]:not(.hidden)`);
    const incoming = document.querySelector(`[data-view-panel="${viewName}"]`);

    if (outgoing && outgoing !== incoming) {
      outgoing.style.opacity = '0';
      outgoing.style.transform = 'translateY(6px)';
      setTimeout(() => {
        panels.forEach(panel => {
          if (panel.getAttribute('data-view-panel') === viewName) {
            panel.classList.remove('hidden');
            // trigger reflow for animation
            void panel.offsetWidth;
            panel.style.opacity = '1';
            panel.style.transform = 'translateY(0)';
          } else {
            panel.classList.add('hidden');
          }
        });
      }, 140);
    } else {
      panels.forEach(panel => {
        if (panel.getAttribute('data-view-panel') === viewName) {
          panel.classList.remove('hidden');
          panel.style.opacity = '1';
          panel.style.transform = 'translateY(0)';
        } else {
          panel.classList.add('hidden');
        }
      });
    }

    // Update nav item highlighting — premium amber glow
    document.querySelectorAll('[data-view-target]').forEach(btn => {
      const isMatch = btn.getAttribute('data-view-target') === viewName;
      if (isMatch) {
        btn.classList.add('bg-amber-600/20', 'text-amber-400', 'border-amber-600');
        btn.classList.remove('text-stone-400', 'hover:bg-stone-800/60');
      } else {
        btn.classList.remove('bg-amber-600/20', 'text-amber-400', 'border-amber-600');
        btn.classList.add('text-stone-400', 'hover:bg-stone-800/60');
      }
    });

    this.currentView = viewName;

    // Trigger view init with tiny stagger for smoothness
    setTimeout(() => {
      if (this.views[viewName] && this.views[viewName].init) {
        this.views[viewName].init();
      }
    }, 60);
  }

  async checkSystemHealth() {
    try {
      await ApiClient.getHealth();
    } catch (err) {
      console.warn('System health check failed:', err);
    }
  }
}

// Global App Launch
document.addEventListener('DOMContentLoaded', () => {
  window.app = new App();
  window.app.init();
});
