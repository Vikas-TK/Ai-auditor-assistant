import { ApiClient } from '../api.js';
import { Toast } from '../components/toast.js';
import { Modal } from '../components/modal.js';
import { Tables } from '../components/tables.js';
import { Store } from '../store.js';
import { EmptyState } from '../components/emptyState.js';
import { formatINR } from '../utils/format.js';

let selectedFiles = [];

export const ReconView = {
  init() {
    this.bindEvents();
    const cached = Store.get('reconciliationData');
    if (cached) {
      this.renderResultsTable(cached);
    }
  },

  bindEvents() {
    const dropzone = document.getElementById('recon-dropzone');
    const fileInput = document.getElementById('recon-file-input');
    const runBtn = document.getElementById('recon-run-btn');

    if (dropzone && fileInput) {
      dropzone.onclick = () => fileInput.click();

      dropzone.ondragover = (e) => {
        e.preventDefault();
        dropzone.classList.add('border-amber-500', 'bg-amber-50/50');
      };

      dropzone.ondragleave = () => {
        dropzone.classList.remove('border-amber-500', 'bg-amber-50/50');
      };

      dropzone.ondrop = (e) => {
        e.preventDefault();
        dropzone.classList.remove('border-amber-500', 'bg-amber-50/50');
        if (e.dataTransfer.files.length) {
          this.handleFiles(Array.from(e.dataTransfer.files));
        }
      };

      fileInput.onchange = (e) => {
        if (e.target.files.length) {
          this.handleFiles(Array.from(e.target.files));
        }
      };
    }

    if (runBtn) {
      runBtn.onclick = () => this.runReconciliation();
    }
  },

  handleFiles(files) {
    selectedFiles = files.filter(f => f.name.endsWith('.pdf'));
    const listContainer = document.getElementById('recon-file-list');
    if (!listContainer) return;

    if (!selectedFiles.length) {
      Toast.show('Please select valid PDF invoice files.', 'warning');
      return;
    }

    listContainer.innerHTML = selectedFiles.map(f => `
      <div class="px-3 py-2 bg-white border border-stone-200 rounded flex items-center justify-between text-xs text-stone-700">
        <span class="truncate max-w-[200px] font-medium">${f.name}</span>
        <span class="text-stone-400">${(f.size / 1024).toFixed(1)} KB</span>
      </div>
    `).join('');

    Toast.show(`Loaded ${selectedFiles.length} PDF invoices for reconciliation.`, 'info');
  },

  async runReconciliation() {
    if (!selectedFiles.length) {
      Toast.show('No PDF invoices selected. Generating sample test run...', 'info');
    }

    const runBtn = document.getElementById('recon-run-btn');
    if (runBtn) runBtn.disabled = true;
    const epoch = Store.getVendorEpoch();

    try {
      const formData = new FormData();
      if (selectedFiles.length) {
        selectedFiles.forEach(f => formData.append('invoices', f));
      } else {
        const resp = await fetch('/data/sample_invoices/INV-2026-001.pdf');
        const blob = await resp.blob();
        formData.append('invoices', blob, 'INV-2026-001.pdf');
      }

      Toast.show('Extracting PDF text via Automated OCR Engine & matching against Ledger...', 'info', 5000);
      const res = await ApiClient.reconcileInvoices(formData);
      // Skip if the vendor/session context changed while this request was in flight.
      if (epoch !== Store.getVendorEpoch()) return;

      Store.set('reconciliationData', res.reconciliation_results || []);
      Toast.show('3-Way Reconciliation Complete!', 'success');
      this.renderResultsTable(res.reconciliation_results);

    } catch (err) {
      console.error('Recon error:', err);
      Toast.show(`Reconciliation error: ${err.message}`, 'error');
    } finally {
      if (runBtn) runBtn.disabled = false;
    }
  },

  renderResultsTable(results) {
    if (!results || results.length === 0) {
      EmptyState.render('recon-results-container', {
        title: 'No reconciliation results',
        message: 'No invoices were matched against the ledger for this vendor scope.'
      });
      return;
    }

    const columns = [
      { label: 'Invoice #', key: 'invoice_number_extracted' },
      { label: 'Vendor Name', key: 'vendor_name_extracted' },
      {
        label: 'PDF Amount (₹)',
        key: 'pdf_amount',
        render: (val) => formatINR(val)
      },
      {
        label: 'Ledger Amount (₹)',
        key: 'ledger_amount',
        render: (val) => formatINR(val)
      },
      {
        label: 'Variance (₹)',
        key: 'variance_amount',
        render: (val) => `<span class="${val !== 0 ? 'text-rose-700 font-bold' : 'text-stone-500'}">${val > 0 ? '+' : ''}${formatINR(val)}</span>`
      },
      { 
        label: 'Status', 
        key: 'status', 
        render: (val) => {
          const badge = val === 'MATCHED' ? 'badge-matched' :
                        val === 'AMOUNT_MISMATCH' ? 'badge-mismatch' : 'badge-warning';
          return `<span class="px-2.5 py-1 text-xs font-semibold rounded ${badge}">${val}</span>`;
        } 
      },
      {
        label: 'Action',
        key: 'status',
        render: (_, row) => `<button class="px-2.5 py-1 text-xs bg-amber-100 hover:bg-amber-200 text-amber-900 border border-amber-300 font-semibold rounded">Inspect</button>`
      }
    ];

    Tables.renderTable({
      containerId: 'recon-results-container',
      columns,
      data: results,
      onRowClick: (row) => this.openInspectorDrawer(row)
    });
  },

  openInspectorDrawer(row) {
    const content = `
      <div class="space-y-4">
        <div class="p-3 bg-[#fbf8f3] rounded-lg border border-stone-200">
          <h4 class="font-semibold text-stone-800 text-sm mb-2">Reconciliation Summary</h4>
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div><span class="text-stone-500">Status:</span> <b class="${row.status === 'MATCHED' ? 'text-emerald-700' : 'text-rose-700'}">${row.status}</b></div>
            <div><span class="text-stone-500">Confidence:</span> <b class="text-amber-700">${row.match_confidence}%</b></div>
            <div><span class="text-stone-500">Matched Txn ID:</span> <b class="text-stone-800">${row.matched_ledger_id}</b></div>
            <div><span class="text-stone-500">Variance:</span> <b class="text-amber-800">${formatINR(row.variance_amount)}</b></div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <!-- Extracted PDF Data -->
          <div class="p-3 bg-[#fbf8f3] rounded-lg border border-stone-200">
            <h5 class="font-semibold text-xs text-amber-800 uppercase tracking-wider mb-2">PDF OCR Data (Automated)</h5>
            <div class="space-y-1.5 text-xs text-stone-700">
              <div><span class="text-stone-500">Vendor:</span> ${row.vendor_name_extracted}</div>
              <div><span class="text-stone-500">Invoice #:</span> ${row.invoice_number_extracted}</div>
              <div><span class="text-stone-500">Total Amt:</span> <b>${formatINR(row.pdf_amount)}</b></div>
              <div><span class="text-stone-500">File:</span> ${row.invoice_filename}</div>
            </div>
          </div>

          <!-- General Ledger Data -->
          <div class="p-3 bg-[#fbf8f3] rounded-lg border border-stone-200">
            <h5 class="font-semibold text-xs text-stone-700 uppercase tracking-wider mb-2">General Ledger Row</h5>
            <div class="space-y-1.5 text-xs text-stone-700">
              <div><span class="text-stone-500">Vendor:</span> ${row.ledger_vendor_name || 'N/A'}</div>
              <div><span class="text-stone-500">Txn ID:</span> ${row.matched_ledger_id}</div>
              <div><span class="text-stone-500">Ledger Amt:</span> <b>${formatINR(row.ledger_amount || 0)}</b></div>
              <div><span class="text-stone-500">Source:</span> corporate_ledger.csv</div>
            </div>
          </div>
        </div>

        <div class="p-3 bg-[#fbf8f3] rounded-lg border border-stone-200">
          <h5 class="font-semibold text-xs text-stone-600 mb-1">Auditor Notes</h5>
          <p class="text-xs text-stone-800 leading-relaxed">${row.notes}</p>
        </div>
      </div>
    `;

    Modal.openDrawer(`Reconciliation Inspector: ${row.invoice_number_extracted}`, content);
  }
};
