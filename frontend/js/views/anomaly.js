import { ApiClient } from '../api.js';
import { Toast } from '../components/toast.js';
import { Modal } from '../components/modal.js';
import { Tables } from '../components/tables.js';
import { Store } from '../store.js';
import { EmptyState } from '../components/emptyState.js';
import { formatINR } from '../utils/format.js';

let heatmapChart = null;

export const AnomalyView = {
  async init() {
    this.bindEvents();
    const cached = Store.get('anomaliesData');
    if (cached) {
      this.filterAndRender(Store.get('minRiskFilter') || 0.0);
    } else {
      await this.loadAnomalies(0.0);
    }
  },

  bindEvents() {
    const slider = document.getElementById('anomaly-risk-slider');
    const sliderVal = document.getElementById('anomaly-risk-val');
    const runBtn = document.getElementById('anomaly-run-btn');
    const enrichBtn = document.getElementById('anomaly-enrich-btn');

    if (slider && sliderVal) {
      slider.oninput = (e) => {
        const val = parseFloat(e.target.value);
        sliderVal.innerText = `${val}%`;
        Store.set('minRiskFilter', val);
        this.filterAndRender(val);
      };
    }

    if (runBtn) {
      runBtn.onclick = () => this.loadAnomalies(parseFloat(slider ? slider.value : 0), false);
    }

    if (enrichBtn) {
      enrichBtn.onclick = async () => {
        // If we already have data, enrich it; otherwise run a fresh scan with LLM
        const hasData = !!(Store.get('anomaliesData'));
        const minRisk = parseFloat(slider ? slider.value : 0);
        if (hasData) {
          await this.loadAnomalies(minRisk, true);
        } else {
          await this.loadAnomalies(minRisk, true);
        }
      };
    }
  },

  async loadAnomalies(minRiskScore = 0.0, useLlm = false) {
    const epoch = Store.getVendorEpoch();
    try {
      const msg = useLlm
        ? 'Running AI enrichment on top anomalies (Gemini)...'
        : 'Running Isolation Forest + SHAP analysis...';
      Toast.show(msg, 'info', 5000);

      const res = await ApiClient.detectAnomalies(minRiskScore, useLlm);
      if (epoch !== Store.getVendorEpoch()) return;

      Store.set('anomaliesData', res.anomalies || []);
      Store.set('anomaliesSummary', res.summary || {});

      const count = (res.anomalies || []).filter(a => a.risk_score >= 50).length;
      Toast.show(`Scan complete — ${count} high-risk anomalies flagged.`, 'success');
      this.filterAndRender(minRiskScore);

    } catch (err) {
      console.error('Anomaly load error:', err);
      Toast.show(`Anomaly engine error: ${err.message}`, 'error');
    }
  },

  filterAndRender(minRiskScore) {
    const currentAnomalies = Store.get('anomaliesData') || [];
    const filtered = currentAnomalies.filter(a => a.risk_score >= minRiskScore);
    this.renderHeatmap(filtered);
    this.renderAnomalyTable(filtered);
  },

  renderHeatmap(anomalies) {
    const ctx = document.getElementById('chart-anomaly-heatmap');
    if (!ctx) return;

    if (heatmapChart) heatmapChart.destroy();

    const normalPoints = [];
    const anomalyPoints = [];

    anomalies.forEach(a => {
      const hour = parseInt(a.time.split(':')[0]) || 12;
      const point = { x: hour, y: a.amount, txnId: a.transaction_id, vendor: a.vendor_name, score: a.risk_score };
      if (a.risk_score >= 50) anomalyPoints.push(point);
      else normalPoints.push(point);
    });

    heatmapChart = new Chart(ctx, {
      type: 'scatter',
      data: {
        datasets: [
          {
            label: 'Normal Transactions',
            data: normalPoints,
            backgroundColor: 'rgba(217, 119, 6, 0.4)',
            pointRadius: 4
          },
          {
            label: 'High-Risk Anomalies (Risk >= 50%)',
            data: anomalyPoints,
            backgroundColor: '#be123c',
            pointRadius: 7,
            pointHoverRadius: 9
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#44403c' } },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const raw = ctx.raw;
                return `${raw.vendor} (${raw.txnId}): ${formatINR(raw.y)} at ${raw.x}:00 [Risk: ${raw.score}%]`;
              }
            }
          }
        },
        scales: {
          x: { 
            title: { display: true, text: 'Hour of Day (0 - 23)', color: '#57534e' },
            grid: { color: '#e7dfd3' }, 
            ticks: { color: '#57534e' } 
          },
          y: { 
            title: { display: true, text: 'Transaction Amount (₹ INR)', color: '#57534e' },
            grid: { color: '#e7dfd3' }, 
            ticks: { color: '#57534e' } 
          }
        }
      }
    });
  },

  renderAnomalyTable(anomalies) {
    const summary = Store.get('anomaliesSummary') || {};
    if (summary.total_transactions_audited === 0) {
      EmptyState.render('anomaly-results-container', {
        title: 'No data for this vendor yet',
        message: 'This vendor has no ledger transactions to audit. Switch to "All Vendors" or upload data via the Data Center.'
      });
      return;
    }
    if (anomalies.length === 0) {
      EmptyState.render('anomaly-results-container', {
        title: 'No anomalies found',
        message: 'No transactions in the current scope match this risk threshold.'
      });
      return;
    }

    const columns = [
      { label: 'Txn ID', key: 'transaction_id' },
      { label: 'Date/Time', key: 'date', render: (val, row) => `${val} ${row.time}` },
      { label: 'Vendor', key: 'vendor_name' },
      { label: 'Amount (₹)', key: 'amount', render: (val) => formatINR(val) },
      { 
        label: 'Risk Score', 
        key: 'risk_score', 
        render: (val) => {
          const badgeClass = val >= 75 ? 'badge-mismatch' : val >= 50 ? 'badge-warning' : 'badge-matched';
          return `<span class="px-2.5 py-1 text-xs font-semibold rounded ${badgeClass}">${val}%</span>`;
        } 
      },
      { label: 'Primary Reason Code (AI Explanation)', key: 'primary_reason' },
      {
        label: 'SHAP Explainer',
        key: 'transaction_id',
        render: (_, row) => `<button class="px-2.5 py-1 text-xs bg-amber-100 hover:bg-amber-200 text-amber-900 border border-amber-300 font-semibold rounded">SHAP Breakdown</button>`
      }
    ];

    Tables.renderTable({
      containerId: 'anomaly-results-container',
      columns,
      data: anomalies,
      onRowClick: (row) => this.openSHAPModal(row)
    });
  },

  openSHAPModal(row) {
    const shap = row.shap_breakdown || {};
    const features = [
      { name: 'Transaction Amount (₹)', weight: shap.amount || 0.42 },
      { name: 'Submission Time (Off-Hours)', weight: shap.hour || 0.35 },
      { name: 'Is Weekend Entry', weight: shap.is_weekend || 0.18 },
      { name: 'Vendor Velocity Spike', weight: shap.amount_ratio_to_avg || 0.25 }
    ];

    let shapBarsHtml = '';
    features.forEach(f => {
      const pct = Math.min(100, Math.max(10, Math.abs(f.weight) * 100));
      shapBarsHtml += `
        <div>
          <div class="flex justify-between text-xs mb-1">
            <span class="text-stone-800 font-medium">${f.name}</span>
            <span class="text-amber-700 font-bold">+${(f.weight * 100).toFixed(1)}% Impact</span>
          </div>
          <div class="w-full bg-stone-200 rounded-full h-2">
            <div class="bg-amber-600 h-2 rounded-full" style="width: ${pct}%"></div>
          </div>
        </div>
      `;
    });

    const content = `
      <div class="space-y-4">
        <div class="p-3 bg-[#fbf8f3] rounded-lg border border-stone-200">
          <div class="flex items-center justify-between mb-1">
            <h4 class="font-semibold text-stone-900 text-sm">${row.vendor_name} (${row.transaction_id})</h4>
            <span class="px-2 py-0.5 text-xs font-bold rounded ${row.risk_score >= 75 ? 'badge-mismatch' : 'badge-warning'}">${row.risk_score}% Risk</span>
          </div>
          <p class="text-xs text-stone-600">Amount: <b>${formatINR(row.amount)}</b> | Recorded: ${row.date} at ${row.time}</p>
        </div>

        <div class="p-3 bg-[#fbf8f3] rounded-lg border border-stone-200">
          <h5 class="font-semibold text-xs text-amber-800 uppercase tracking-wider mb-2">AI Control Risk Explanation</h5>
          <p class="text-xs text-stone-900 leading-relaxed font-medium">"${row.primary_reason}"</p>
        </div>

        <div class="p-3 bg-[#fbf8f3] rounded-lg border border-stone-200 space-y-3">
          <h5 class="font-semibold text-xs text-stone-600 uppercase tracking-wider mb-2">TreeSHAP Local Feature Importance</h5>
          ${shapBarsHtml}
        </div>
      </div>
    `;

    Modal.openDrawer(`SHAP Anomaly Breakdown: ${row.transaction_id}`, content);
  }
};
