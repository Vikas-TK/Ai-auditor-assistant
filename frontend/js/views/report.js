import { ApiClient } from '../api.js';
import { Toast } from '../components/toast.js';
import { Store } from '../store.js';

let currentPdfUrl = null;

export const ReportView = {
  init() {
    this.bindEvents();
  },

  bindEvents() {
    const generateBtn = document.getElementById('report-generate-btn');
    const downloadBtn = document.getElementById('report-download-btn');

    if (generateBtn) {
      generateBtn.onclick = () => this.generateWorkingPaper();
    }

    if (downloadBtn) {
      downloadBtn.onclick = () => this.downloadWorkingPaper();
    }
  },

  async generateWorkingPaper() {
    const generateBtn = document.getElementById('report-generate-btn');
    const downloadBtn = document.getElementById('report-download-btn');
    const notesInput = document.getElementById('report-notes-input');
    const iframe = document.getElementById('pdf-preview-frame');

    const auditorNotes = notesInput ? notesInput.value.trim() : '';

    if (generateBtn) generateBtn.disabled = true;
    Toast.show('Compiling PDF Working Paper (ReportLab engine)...', 'info', 4000);

    try {
      const summary = Store.get('anomaliesSummary') || {};
      const anomalies = Store.get('anomaliesData') || [];
      const reconciliationFindings = Store.get('reconciliationData') || [];

      const blob = await ApiClient.generateReport({
        summary,
        reconciliation_findings: reconciliationFindings,
        anomalies,
        auditor_notes: auditorNotes
      });

      if (currentPdfUrl) {
        URL.revokeObjectURL(currentPdfUrl);
      }

      currentPdfUrl = URL.createObjectURL(blob);

      if (iframe) {
        iframe.src = currentPdfUrl;
        iframe.classList.remove('hidden');
        if (iframe.parentElement) {
          const placeholder = iframe.parentElement.querySelector('div');
          if (placeholder) placeholder.classList.add('hidden');
        }
      }

      if (downloadBtn) {
        downloadBtn.classList.remove('hidden');
      }

      Toast.show('PDF Working Paper generated & preview loaded!', 'success');

    } catch (err) {
      console.error('Report error:', err);
      Toast.show(`PDF Generation Error: ${err.message}`, 'error');
    } finally {
      if (generateBtn) generateBtn.disabled = false;
    }
  },

  downloadWorkingPaper() {
    if (!currentPdfUrl) {
      Toast.show('No generated PDF available to download.', 'warning');
      return;
    }

    const a = document.createElement('a');
    a.href = currentPdfUrl;
    a.download = `Audit_Working_Paper_${new Date().toISOString().slice(0,10)}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    Toast.show('Downloading Working Paper PDF...', 'success');
  }
};
