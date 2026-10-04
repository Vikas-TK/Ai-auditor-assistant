import { ApiClient } from '../api.js';
import { Toast } from '../components/toast.js';
import { Tables } from '../components/tables.js';
import { EmptyState } from '../components/emptyState.js';
import { Modal } from '../components/modal.js';
import { ConfirmDialog } from '../components/confirmDialog.js';
import { Store } from '../store.js';

let currentPage = 1;
let currentLimit = 50;
let currentSortBy = 'date';
let currentSortDir = 'asc';
let lastRecords = [];
let lastTotal = 0;
let categoryCache = [];

export const DataCenterView = {
  async init() {
    this.bindEventsOnce();
    await this.refreshAll();
  },

  bindEventsOnce() {
    if (this._bound) return;
    this._bound = true;

    const searchInput = document.getElementById('datacenter-search');
    const clearSearchBtn = document.getElementById('datacenter-clear-search');
    const catSelect = document.getElementById('datacenter-category');
    const sortSelect = document.getElementById('datacenter-sort');
    const limitSelect = document.getElementById('datacenter-limit');
    const injectBtn = document.getElementById('datacenter-inject-btn');
    const prevBtn = document.getElementById('datacenter-prev-btn');
    const nextBtn = document.getElementById('datacenter-next-btn');
    const clearBtn = document.getElementById('datacenter-clear-filters');
    const gotoInput = document.getElementById('datacenter-goto');
    const gotoBtn = document.getElementById('datacenter-goto-btn');
    const refreshBtn = document.getElementById('datacenter-refresh-btn');
    const exportBtn = document.getElementById('datacenter-export-btn');

    if (searchInput) {
      let timer;
      searchInput.oninput = () => {
        if (clearSearchBtn) clearSearchBtn.classList.toggle('hidden', !searchInput.value);
        clearTimeout(timer);
        timer = setTimeout(() => {
          currentPage = 1;
          this.loadLedgerGrid();
        }, 320);
      };
      searchInput.onkeydown = (e) => {
        if (e.key === 'Enter') {
          currentPage = 1;
          this.loadLedgerGrid();
        }
      };
    }
    if (clearSearchBtn && searchInput) {
      clearSearchBtn.onclick = () => {
        searchInput.value = '';
        clearSearchBtn.classList.add('hidden');
        currentPage = 1;
        this.loadLedgerGrid();
      };
    }
    if (catSelect) {
      catSelect.onchange = () => {
        currentPage = 1;
        this.loadLedgerGrid();
      };
    }
    if (sortSelect) {
      sortSelect.onchange = () => {
        const [by, dir] = sortSelect.value.split('-');
        currentSortBy = by;
        currentSortDir = dir;
        currentPage = 1;
        this.loadLedgerGrid();
      };
      // init sort from select
      const [by, dir] = sortSelect.value.split('-');
      currentSortBy = by; currentSortDir = dir;
    }
    if (limitSelect) {
      limitSelect.onchange = () => {
        currentLimit = parseInt(limitSelect.value, 10) || 50;
        currentPage = 1;
        this.loadLedgerGrid();
      };
      currentLimit = parseInt(limitSelect.value, 10) || 50;
    }
    if (injectBtn) injectBtn.onclick = () => {
      ConfirmDialog.open({
        title: 'Regenerate ledger data?',
        message: 'This replaces the entire ledger with a freshly generated set of exactly 100 balanced transactions per vendor. The current ledger for this scope will be lost.',
        confirmLabel: 'Regenerate ledger',
        cancelLabel: 'Cancel',
        danger: true,
        onConfirm: () => this.triggerInjection()
      });
    };
    if (prevBtn) prevBtn.onclick = () => { if (currentPage > 1) { currentPage--; this.loadLedgerGrid(); } };
    if (nextBtn) nextBtn.onclick = () => { currentPage++; this.loadLedgerGrid(); };
    if (clearBtn) clearBtn.onclick = () => {
      if (searchInput) searchInput.value = '';
      if (catSelect) catSelect.value = 'ALL';
      if (sortSelect) { sortSelect.value = 'date-asc'; currentSortBy='date'; currentSortDir='asc'; }
      if (limitSelect) { limitSelect.value = '50'; currentLimit = 50; }
      if (clearSearchBtn) clearSearchBtn.classList.add('hidden');
      currentPage = 1;
      this.loadLedgerGrid();
    };
    const doGoto = () => {
      const v = parseInt(gotoInput.value, 10);
      if (!isNaN(v) && v >= 1) { currentPage = v; this.loadLedgerGrid(); }
    };
    if (gotoBtn) gotoBtn.onclick = doGoto;
    if (gotoInput) gotoInput.onkeydown = (e) => { if (e.key === 'Enter') doGoto(); };
    if (refreshBtn) refreshBtn.onclick = () => this.refreshAll();
    if (exportBtn) exportBtn.onclick = () => this.exportCsv();
  },

  async refreshAll() {
    // load stats + grid in parallel
    await Promise.all([this.loadStats(), this.loadLedgerGrid()]);
  },

  async loadStats() {
    try {
      const stats = await ApiClient.getLedgerStats();
      const totalEl = document.getElementById('dc-stat-total');
      const totalSub = document.getElementById('dc-stat-total-sub');
      const anomEl = document.getElementById('dc-stat-anomalies');
      const anomSub = document.getElementById('dc-stat-anomalies-sub');
      const amtEl = document.getElementById('dc-stat-amount');
      const scopeBadge = document.getElementById('datacenter-scope-badge');
      const distWrap = document.getElementById('dc-vendor-dist');
      const distGrid = document.getElementById('dc-vendor-dist-grid');

      if (totalEl) totalEl.textContent = stats.total_records.toLocaleString('en-IN');
      if (totalSub) {
        const vendors = Object.keys(stats.vendor_counts || {}).length;
        totalSub.textContent = stats.vendor_scope === 'ALL' ? `${vendors} vendors × 100 each` : `vendor ${stats.vendor_scope} • 100 ledgers`;
      }
      if (anomEl) anomEl.textContent = stats.anomaly_records.toLocaleString('en-IN');
      if (anomSub) anomSub.textContent = stats.total_records ? `${((stats.anomaly_records / stats.total_records) * 100).toFixed(1)}% flagged` : '0% flagged';
      if (amtEl) amtEl.textContent = `₹${stats.total_amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
      if (scopeBadge) {
        scopeBadge.textContent = stats.vendor_scope === 'ALL' ? 'Scope: All Vendors (Global)' : `Scope: ${stats.vendor_scope}`;
        scopeBadge.className = 'hidden sm:inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full ' + (stats.vendor_scope === 'ALL' ? 'bg-stone-900 text-white' : 'bg-amber-100 text-amber-800 border border-amber-300');
      }
      // vendor distribution mini cards (only when ALL)
      if (distWrap && distGrid) {
        if (stats.vendor_scope === 'ALL' && stats.vendor_counts && Object.keys(stats.vendor_counts).length) {
          distWrap.classList.remove('hidden');
          const entries = Object.entries(stats.vendor_counts).sort((a,b)=> a[0].localeCompare(b[0]));
          distGrid.innerHTML = entries.map(([vid, cnt]) => {
            const ok = cnt === 100;
            return `<div class="px-2.5 py-2 bg-white border rounded-lg flex items-center justify-between ${ok ? 'border-emerald-200' : 'border-amber-200'}">
              <span class="font-semibold text-stone-800">${vid}</span>
              <span class="text-xs px-2 py-0.5 rounded-full font-bold ${ok ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-amber-50 text-amber-800 border border-amber-300'}">${cnt}</span>
            </div>`;
          }).join('');
        } else {
          distWrap.classList.add('hidden');
        }
      }
      // populate category filter options from stats if present and not yet populated
      if (stats.categories && stats.categories.length) {
        this.populateCategories(stats.categories);
      }
    } catch (e) {
      console.warn('ledger stats failed', e);
    }
  },

  populateCategories(categories) {
    const sel = document.getElementById('datacenter-category');
    if (!sel) return;
    const current = sel.value;
    // keep ALL, rebuild rest
    const keepAll = '<option value="ALL">All Categories</option>';
    const opts = categories.map(c => `<option value="${c}">${c}</option>`).join('');
    // avoid flicker if same
    const newHtml = keepAll + opts;
    if (sel.innerHTML !== newHtml) {
      sel.innerHTML = newHtml;
      if (categories.includes(current)) sel.value = current;
    }
    categoryCache = categories;
  },

  showSkeleton() {
    const cont = document.getElementById('datacenter-table-container');
    if (!cont) return;
    const rows = Array.from({ length: 6 }).map(() => `
      <div class="grid grid-cols-7 gap-3 px-4 py-3 border-b border-stone-100 animate-pulse">
        <div class="h-3 bg-stone-200 rounded"></div><div class="h-3 bg-stone-200 rounded"></div><div class="h-3 bg-stone-100 rounded"></div><div class="h-3 bg-stone-200 rounded"></div><div class="h-3 bg-stone-100 rounded"></div><div class="h-3 bg-stone-200 rounded col-span-2"></div>
      </div>
    `).join('');
    cont.innerHTML = `<div class="border border-stone-200 rounded-xl overflow-hidden bg-white">${rows}</div>`;
  },

  async loadLedgerGrid() {
    const searchVal = document.getElementById('datacenter-search')?.value || '';
    const catVal = document.getElementById('datacenter-category')?.value || 'ALL';

    const epoch = Store.getVendorEpoch();
    this.showSkeleton();
    try {
      const data = await ApiClient.getLedgerData(currentPage, currentLimit, searchVal, catVal, currentSortBy, currentSortDir);
      if (epoch !== Store.getVendorEpoch()) return;

      // update pagination state from server (server may clamp page)
      currentPage = data.page;
      lastRecords = data.records;
      lastTotal = data.total_records;

      // categories from response
      if (data.categories) this.populateCategories(data.categories);

      // stats filtered count
      const filteredEl = document.getElementById('dc-stat-filtered');
      const pageMeta = document.getElementById('dc-stat-page');
      const pageInfo = document.getElementById('datacenter-page-info');
      if (filteredEl) filteredEl.textContent = data.total_records.toLocaleString('en-IN');
      if (pageMeta) pageMeta.textContent = data.total_pages ? `page ${data.page} of ${data.total_pages}` : 'no pages';
      if (pageInfo) pageInfo.textContent = `${data.total_records.toLocaleString('en-IN')} record${data.total_records!==1?'s':''} • page ${data.page}/${data.total_pages || 1} • ${data.limit}/page • sorted by ${currentSortBy} ${currentSortDir}`;

      // pagination buttons state
      const prevBtn = document.getElementById('datacenter-prev-btn');
      const nextBtn = document.getElementById('datacenter-next-btn');
      if (prevBtn) prevBtn.disabled = data.page <= 1;
      if (nextBtn) nextBtn.disabled = data.page >= data.total_pages || data.total_pages === 0;

      this.renderLedgerTable(data.records);
      this.renderPaginationNumbers(data.page, data.total_pages);
      // also refresh stats header (distribution only changes on scope change, but filtered stats cheap)
      // keep stats amount in sync with current scope? already loaded via stats endpoint separate.

    } catch (err) {
      console.error('Ledger fetch error:', err);
      Toast.show('Failed to fetch ledger dataset', 'error');
      const cont = document.getElementById('datacenter-table-container');
      if (cont) cont.innerHTML = `<div class="p-8 text-center text-sm text-stone-500">Failed to load ledgers. Please refresh.</div>`;
    }
  },

  renderPaginationNumbers(page, totalPages) {
    const wrap = document.getElementById('datacenter-pages');
    if (!wrap) return;
    if (!totalPages || totalPages <= 1) { wrap.innerHTML = ''; return; }
    const maxVisible = 5;
    let start = Math.max(1, page - Math.floor(maxVisible/2));
    let end = Math.min(totalPages, start + maxVisible - 1);
    start = Math.max(1, end - maxVisible + 1);
    let html = '';
    for (let p = start; p <= end; p++) {
      const active = p === page;
      html += `<button data-page="${p}" class="min-w-[28px] h-7 text-xs font-semibold rounded-full border ${active ? 'bg-stone-900 text-white border-stone-900' : 'bg-white text-stone-700 border-stone-300 hover:bg-stone-50'}">${p}</button>`;
    }
    if (totalPages > maxVisible && end < totalPages) {
      html += `<span class="px-1 text-stone-400">…</span><button data-page="${totalPages}" class="min-w-[28px] h-7 text-xs font-medium rounded-full bg-white border border-stone-300">${totalPages}</button>`;
    }
    wrap.innerHTML = html;
    wrap.querySelectorAll('button').forEach(btn => {
      btn.onclick = () => {
        const p = parseInt(btn.getAttribute('data-page'), 10);
        if (p && p !== currentPage) { currentPage = p; this.loadLedgerGrid(); }
      };
    });
  },

  async triggerInjection() {
    const injectBtn = document.getElementById('datacenter-inject-btn');
    if (injectBtn) { injectBtn.disabled = true; injectBtn.textContent = 'Regenerating…'; }
    try {
      Toast.show('Regenerating exactly 100 ledgers per vendor (balanced) — this replaces the ledger…', 'info', 4000);
      const res = await ApiClient.injectAnomalies(null, 100);
      Toast.show(res.message || `Done — ${res.total_records} ledgers ready.`, 'success', 5000);
      currentPage = 1;
      await this.refreshAll();
      // also ping overview/anomaly caches to clear
      Store.clearVendorScopedCache();
    } catch (err) {
      Toast.show(`Injection error: ${err.message}`, 'error');
    } finally {
      if (injectBtn) { injectBtn.disabled = false; injectBtn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg> Regenerate 100 / vendor`; }
    }
  },

  exportCsv() {
    if (!lastRecords || !lastRecords.length) {
      Toast.show('No records to export — adjust filters first.', 'warning');
      return;
    }
    const cols = ['transaction_id','date','time','vendor_id','vendor_name','department','category','amount','approval_status','payment_method','description','is_injected_anomaly','anomaly_type'];
    const header = cols.join(',');
    const rows = lastRecords.map(r => cols.map(k => {
      let v = r[k];
      if (v == null) v = '';
      let s = String(v).replace(/"/g, '""');
      if (s.includes(',') || s.includes('"') || s.includes('\n')) s = `"${s}"`;
      return s;
    }).join(',')).join('\n');
    const csv = header + '\n' + rows;
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ledger_export_${Store.getEffectiveVendorId()}_${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    Toast.show(`Exported ${lastRecords.length} rows to CSV.`, 'success');
  },

  renderLedgerTable(records) {
    if (!records || records.length === 0) {
      EmptyState.render('datacenter-table-container', {
        title: 'No ledger records',
        message: 'No transactions match these filters. Try clearing search/category, switching vendor scope, or clicking Regenerate 100 / vendor.'
      });
      return;
    }

    const columns = [
      { label: 'Txn ID', key: 'transaction_id', sortable: true },
      { label: 'Date', key: 'date', sortable: true, render: (val, row) => `<span class="whitespace-nowrap">${val}<span class="text-stone-400 ml-1">${(row.time||'').slice(0,5)}</span></span>` },
      { label: 'Vendor', key: 'vendor_name', render: (val, row) => `<div class="min-w-[160px]"><div class="font-medium text-stone-900 truncate max-w-[180px]" title="${row.vendor_name}">${val}</div><div class="text-[11px] text-stone-500">${row.vendor_id||''}</div></div>` },
      { label: 'Dept / Category', key: 'department', render: (val, row) => `<div><div class="text-xs font-medium text-stone-800">${val||'—'}</div><div class="text-[11px] text-stone-500">${row.category||'General'}</div></div>` },
      { label: 'Amount (₹)', key: 'amount', sortable: true, render: (val) => {
        const n = Number(val)||0;
        const cls = n < 0 ? 'text-rose-700' : 'text-stone-900';
        return `<span class="font-semibold ${cls} whitespace-nowrap">₹${n.toLocaleString('en-IN', {minimumFractionDigits: 2})}</span>`;
      }},
      { 
        label: 'Status', 
        key: 'is_injected_anomaly', 
        render: (val, row) => {
          if (val) {
            const map = { 'THRESHOLD_BYPASS':'THRESHOLD', 'OFF_HOURS_ENTRY':'OFF-HOURS', 'DUPLICATE_PAYMENT':'DUPLICATE' };
            const label = map[row.anomaly_type] || row.anomaly_type || 'ANOMALY';
            return `<span class="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-bold rounded-full badge-mismatch">${label}</span>`;
          }
          return `<span class="inline-flex px-2 py-0.5 text-[11px] font-semibold rounded-full badge-matched">NORMAL</span>`;
        } 
      },
      { label: '', key: 'transaction_id', render: () => `<span class="text-amber-700 font-semibold text-xs group-hover:underline">View →</span>` }
    ];

    Tables.renderTable({
      containerId: 'datacenter-table-container',
      columns,
      data: records,
      onRowClick: (row) => this.openDetailDrawer(row)
    });

    // wire header sorting clicks (Tables renders th without click, so add after)
    const container = document.getElementById('datacenter-table-container');
    if (container) {
      const ths = container.querySelectorAll('th');
      const sortableKeys = columns.map(c => c.key);
      // simple: make Amount/Date/Vendor/Txn clickable by attaching title
      ths.forEach((th, idx) => {
        const col = columns[idx];
        if (col && col.sortable) {
          th.style.cursor = 'pointer';
          th.title = 'Click to sort';
          let indicator = '';
          if (col.key === currentSortBy) indicator = currentSortDir === 'asc' ? ' ▲' : ' ▼';
          if (!th.innerHTML.includes('▲') && !th.innerHTML.includes('▼')) th.innerHTML = th.innerHTML + `<span class="text-amber-700">${indicator}</span>`;
          th.onclick = () => {
            if (currentSortBy === col.key) {
              currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
            } else {
              currentSortBy = col.key;
              currentSortDir = 'asc';
            }
            // sync select
            const sel = document.getElementById('datacenter-sort');
            if (sel) sel.value = `${currentSortBy}-${currentSortDir}`;
            this.loadLedgerGrid();
          };
        }
      });
    }
  },

  openDetailDrawer(row) {
    const amt = Number(row.amount)||0;
    const isAnom = !!row.is_injected_anomaly;
    const badge = isAnom ? `<span class="px-2 py-1 text-xs font-bold rounded-full badge-mismatch">${row.anomaly_type||'ANOMALY'}</span>` : `<span class="px-2 py-1 text-xs font-semibold rounded-full badge-matched">NORMAL</span>`;
    const desc = row.description || row['Purchase Order Description'] || `Procurement for ${row.category||'General'}`;
    const content = `
      <div class="space-y-4">
        <div class="p-3.5 bg-[#fbf8f3] rounded-xl border border-stone-200">
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="text-xs font-semibold tracking-widest uppercase text-stone-500">Transaction</div>
              <div class="text-sm font-bold text-stone-900 mt-0.5">${row.transaction_id}</div>
              <div class="text-xs text-stone-600 mt-1">${row.vendor_name} <span class="text-stone-500">• ${row.vendor_id||''}</span></div>
            </div>
            ${badge}
          </div>
          <div class="grid grid-cols-2 gap-3 mt-3 text-xs">
            <div><span class="text-stone-500">Date</span><div class="font-medium text-stone-900">${row.date} ${row.time||''}</div></div>
            <div><span class="text-stone-500">Amount</span><div class="font-bold ${amt<0?'text-rose-700':'text-stone-900'}">₹${amt.toLocaleString('en-IN', {minimumFractionDigits:2})}</div></div>
            <div><span class="text-stone-500">Department</span><div class="font-medium text-stone-900">${row.department||'—'}</div></div>
            <div><span class="text-stone-500">Category</span><div class="font-medium text-stone-900">${row.category||'General'}</div></div>
            <div><span class="text-stone-500">Payment</span><div class="font-medium text-stone-900">${row.payment_method||'—'}</div></div>
            <div><span class="text-stone-500">Approval</span><div class="font-medium text-stone-900">${row.approval_status||'APPROVED'}</div></div>
          </div>
        </div>
        <div class="p-3.5 bg-white rounded-xl border border-stone-200">
          <div class="text-xs font-semibold text-stone-700 mb-1">Description</div>
          <p class="text-xs leading-relaxed text-stone-800">${desc}</p>
          ${isAnom ? `<div class="mt-3 p-2.5 bg-rose-50 border border-rose-200 rounded-lg text-xs text-rose-800"><b>Injected anomaly:</b> ${row.anomaly_type} — this row is intentionally flagged for audit testing (threshold/off-hours/duplicate pattern).</div>` : `<div class="mt-3 p-2.5 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800">This transaction shows no injected anomaly pattern.</div>`}
        </div>
        <div class="grid grid-cols-2 gap-2 text-[11px]">
          <div class="p-2.5 bg-stone-50 border border-stone-200 rounded-lg"><span class="text-stone-500">Vendor</span><div class="font-medium text-stone-900">${row.vendor_name}</div></div>
          <div class="p-2.5 bg-stone-50 border border-stone-200 rounded-lg"><span class="text-stone-500">Txn ID</span><div class="font-medium text-stone-900">${row.transaction_id}</div></div>
        </div>
      </div>
    `;
    Modal.openDrawer(`Ledger Detail — ${row.transaction_id}`, content);
  }
};
