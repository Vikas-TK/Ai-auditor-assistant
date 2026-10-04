import { ApiClient } from '../api.js';
import { Toast } from '../components/toast.js';
import { Store } from '../store.js';
import { EmptyState } from '../components/emptyState.js';
import { Tables } from '../components/tables.js';
import { formatINR } from '../utils/format.js';

let deptChart = null;
let trendChart = null;

export const OverviewView = {
  async init() {
    try {
      let anomalies = Store.get('anomaliesData');
      let summary = Store.get('anomaliesSummary');

      const epoch = Store.getVendorEpoch();
      this.setLoading(true);

      const statsPromise = ApiClient.getLedgerStats().catch(err => {
        console.warn('Ledger stats fetch failed:', err);
        return null;
      });

      if (!anomalies) {
        const data = await ApiClient.detectAnomalies(0.0);
        if (epoch !== Store.getVendorEpoch()) return;

        summary = data.summary || {};
        anomalies = data.anomalies || [];
        Store.set('anomaliesData', anomalies);
        Store.set('anomaliesSummary', summary);
      }

      const stats = await statsPromise;
      if (epoch !== Store.getVendorEpoch()) return;

      this.setLoading(false);

      document.getElementById('kpi-total-ledger').innerText = stats
        ? formatINR(stats.total_amount)
        : '—';
      document.getElementById('kpi-audited-count').innerText = (summary.total_transactions_audited ?? 0).toLocaleString('en-IN');
      document.getElementById('kpi-flagged-count').innerText = summary.total_anomalies_flagged ?? 0;
      document.getElementById('kpi-at-risk-amt').innerText = formatINR(summary.total_at_risk_amount ?? 0);

      this.renderCharts(anomalies);
      this.renderActivityStream(anomalies);

    } catch (err) {
      this.setLoading(false);
      console.error('Overview init error:', err);
      Toast.show('Failed to load overview data', 'error');
    }
  },

  setLoading(isLoading) {
    ['kpi-total-ledger', 'kpi-audited-count', 'kpi-flagged-count', 'kpi-at-risk-amt'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerText = isLoading ? '…' : el.innerText;
    });
    const stream = document.getElementById('activity-stream-container');
    if (isLoading && stream) {
      stream.innerHTML = '<p class="text-stone-500 text-xs col-span-2">Running Isolation Forest + SHAP analysis across the ledger…</p>';
    }
  },

  renderCharts(anomalies) {
    // 1. Departmental Risk Distribution Bar Chart
    const deptCtx = document.getElementById('chart-dept-risk');
    if (deptCtx) {
      if (deptChart) deptChart.destroy();
      const depts = {'IT': 0, 'Travel': 0, 'Operations': 0, 'Marketing': 0, 'Finance': 0, 'Logistics': 0};
      anomalies.forEach(a => {
        const d = a.department || 'Operations';
        if (depts[d] !== undefined) depts[d] += (a.risk_score >= 50 ? 1 : 0);
        else depts[d] = 1;
      });
      deptChart = new Chart(deptCtx, {
        type: 'bar',
        data: {
          labels: Object.keys(depts),
          datasets: [{
            label: 'Flagged Anomalies',
            data: Object.values(depts),
            backgroundColor: 'rgba(217, 119, 6, 0.85)',
            hoverBackgroundColor: '#d97706',
            borderRadius: 6,
            borderSkipped: false,
            maxBarThickness: 42
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: '#1c1917',
              padding: 10,
              titleFont: { size: 12, weight: '600' },
              bodyFont: { size: 12 },
              cornerRadius: 8,
              displayColors: false
            }
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: '#78716c', font: { size: 11 } }, border: { display: false } },
            y: { beginAtZero: true, ticks: { color: '#78716c', font: { size: 11 }, precision: 0 }, grid: { color: '#f0ebe1' }, border: { display: false } }
          }
        }
      });
    }

    // 2. Risk Severity Trend Line Chart
    // NOTE: this series is illustrative placeholder data, not derived from the
    // live ledger — left untouched per product decision; restyled only.
    const trendCtx = document.getElementById('chart-risk-trend');
    if (trendCtx) {
      if (trendChart) trendChart.destroy();
      trendChart = new Chart(trendCtx, {
        type: 'line',
        data: {
          labels: ['Jan 05', 'Jan 15', 'Jan 25', 'Feb 05', 'Feb 15', 'Feb 25', 'Mar 05'],
          datasets: [
            { label: 'Critical Risk Items', data: [3, 8, 4, 12, 18, 9, 15], borderColor: '#be123c', backgroundColor: 'rgba(190, 18, 60, 0.08)', pointBackgroundColor: '#be123c', pointBorderColor: '#fff', pointBorderWidth: 1.5, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2, fill: true, tension: 0.4 },
            { label: 'Medium Risk Items', data: [12, 19, 15, 25, 30, 22, 28], borderColor: '#b45309', backgroundColor: 'rgba(180, 83, 9, 0.08)', pointBackgroundColor: '#b45309', pointBorderColor: '#fff', pointBorderWidth: 1.5, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2, fill: true, tension: 0.4 }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { position: 'bottom', labels: { color: '#57534e', font: { size: 11.5 }, boxWidth: 10, boxHeight: 10, usePointStyle: true, pointStyle: 'circle' } },
            tooltip: {
              backgroundColor: '#1c1917',
              padding: 10,
              titleFont: { size: 12, weight: '600' },
              bodyFont: { size: 12 },
              cornerRadius: 8
            }
          },
          scales: {
            x: { grid: { display: false }, ticks: { color: '#78716c', font: { size: 11 } }, border: { display: false } },
            y: { beginAtZero: true, ticks: { color: '#78716c', font: { size: 11 }, precision: 0 }, grid: { color: '#f0ebe1' }, border: { display: false } }
          }
        }
      });
    }
  },

  renderActivityStream(anomalies) {
    const summary = Store.get('anomaliesSummary') || {};
    if (summary.total_transactions_audited === 0) {
      EmptyState.render('activity-stream-container', {
        title: 'No data for this vendor yet',
        message: 'This vendor has no ledger transactions. Switch to "All Vendors" or upload data via the Data Center.'
      });
      return;
    }

    const topItems = anomalies.filter(a => a.risk_score >= 50).slice(0, 6);

    if (topItems.length === 0) {
      EmptyState.render('activity-stream-container', {
        title: 'No high-risk anomalies',
        message: 'Nothing in this vendor scope is currently flagged at 50% risk or above.'
      });
      return;
    }

    const columns = [
      { label: 'Vendor / Txn ID', key: 'vendor_name', render: (val, row) => `${val} <span class="text-stone-400">(${row.transaction_id})</span>` },
      { label: 'Amount (₹)', key: 'amount', render: (val) => formatINR(val) },
      { label: 'Dept', key: 'department', render: (val) => val || 'General' },
      { label: 'Time', key: 'time' },
      { label: 'Primary Reason', key: 'primary_reason' },
      {
        label: 'Risk',
        key: 'risk_score',
        render: (val) => {
          const badgeClass = val >= 75 ? 'badge-mismatch' : 'badge-warning';
          return `<span class="px-2.5 py-1 text-xs font-semibold rounded ${badgeClass}">${val}%</span>`;
        }
      }
    ];

    Tables.renderTable({
      containerId: 'activity-stream-container',
      columns,
      data: topItems,
      onRowClick: () => window.app.switchView('anomaly')
    });
  }
};
