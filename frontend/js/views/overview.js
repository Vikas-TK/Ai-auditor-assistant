import { ApiClient } from '../api.js';
import { Toast } from '../components/toast.js';
import { Store } from '../store.js';
import { EmptyState } from '../components/emptyState.js';

let deptChart = null;
let trendChart = null;

export const OverviewView = {
  async init() {
    try {
      let anomalies = Store.get('anomaliesData');
      let summary = Store.get('anomaliesSummary');

      if (!anomalies) {
        const epoch = Store.getVendorEpoch();
        this.setLoading(true);
        const data = await ApiClient.detectAnomalies(0.0);
        this.setLoading(false);
        // Bail if the vendor/session context moved on while this was in flight.
        if (epoch !== Store.getVendorEpoch()) return;

        summary = data.summary || {};
        anomalies = data.anomalies || [];
        Store.set('anomaliesData', anomalies);
        Store.set('anomaliesSummary', summary);
      }

      // Update KPI Bar (INR ₹). Use `?? 0`, not `||`, so a genuine zero
      // (e.g. a freshly provisioned vendor with no transactions) isn't
      // masked by the placeholder fallback.
      document.getElementById('kpi-total-ledger').innerText = '₹1,84,50,200';
      document.getElementById('kpi-audited-count').innerText = (summary.total_transactions_audited ?? 0).toLocaleString('en-IN');
      document.getElementById('kpi-flagged-count').innerText = summary.total_anomalies_flagged ?? 0;
      document.getElementById('kpi-at-risk-amt').innerText = `₹${(summary.total_at_risk_amount ?? 0).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

      this.renderCharts(anomalies);
      this.renderActivityStream(anomalies);

    } catch (err) {
      this.setLoading(false);
      console.error('Overview init error:', err);
      Toast.show('Failed to load overview data', 'error');
    }
  },

  setLoading(isLoading) {
    ['kpi-audited-count', 'kpi-flagged-count', 'kpi-at-risk-amt'].forEach(id => {
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
            backgroundColor: 'rgba(217, 119, 6, 0.75)',
            borderColor: '#d97706',
            borderWidth: 1,
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: '#e7dfd3' }, ticks: { color: '#57534e' } },
            y: { grid: { color: '#e7dfd3' }, ticks: { color: '#57534e' } }
          }
        }
      });
    }

    // 2. Risk Severity Trend Line Chart
    const trendCtx = document.getElementById('chart-risk-trend');
    if (trendCtx) {
      if (trendChart) trendChart.destroy();

      trendChart = new Chart(trendCtx, {
        type: 'line',
        data: {
          labels: ['Jan 05', 'Jan 15', 'Jan 25', 'Feb 05', 'Feb 15', 'Feb 25', 'Mar 05'],
          datasets: [
            {
              label: 'Critical Risk Items',
              data: [3, 8, 4, 12, 18, 9, 15],
              borderColor: '#be123c',
              backgroundColor: 'rgba(190, 18, 60, 0.08)',
              fill: true,
              tension: 0.4
            },
            {
              label: 'Medium Risk Items',
              data: [12, 19, 15, 25, 30, 22, 28],
              borderColor: '#b45309',
              backgroundColor: 'rgba(180, 83, 9, 0.08)',
              fill: true,
              tension: 0.4
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { labels: { color: '#44403c' } } },
          scales: {
            x: { grid: { color: '#e7dfd3' }, ticks: { color: '#57534e' } },
            y: { grid: { color: '#e7dfd3' }, ticks: { color: '#57534e' } }
          }
        }
      });
    }
  },

  renderActivityStream(anomalies) {
    const container = document.getElementById('activity-stream-container');
    if (!container) return;

    const summary = Store.get('anomaliesSummary') || {};
    if (summary.total_transactions_audited === 0) {
      EmptyState.render('activity-stream-container', {
        title: 'No data for this vendor yet',
        message: 'This vendor has no ledger transactions. Switch to "All Vendors" or upload data via the Data Center.'
      });
      return;
    }

    const topItems = anomalies.filter(a => a.risk_score >= 50).slice(0, 6);
    let html = '';

    topItems.forEach(item => {
      const isCritical = item.risk_score >= 75;
      const badgeClass = isCritical ? 'badge-mismatch' : 'badge-warning';

      html += `
        <div class="p-3 bg-[#fbf8f3] border border-stone-200 rounded-lg flex items-start gap-3 shadow-xs">
          <div class="p-2 rounded-lg ${isCritical ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800'}">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center justify-between">
              <span class="font-semibold text-stone-900 text-xs">${item.vendor_name} (${item.transaction_id})</span>
              <span class="text-xs px-2 py-0.5 rounded font-semibold ${badgeClass}">${item.risk_score}% Risk</span>
            </div>
            <p class="text-xs text-stone-600 mt-1 line-clamp-1">${item.primary_reason}</p>
            <div class="flex items-center gap-3 mt-1.5 text-[11px] text-stone-500">
              <span>Amt: <b>₹${item.amount.toLocaleString('en-IN', {minimumFractionDigits: 2})}</b></span>
              <span>Time: ${item.time}</span>
              <span>Dept: ${item.department || 'General'}</span>
            </div>
          </div>
        </div>
      `;
    });

    container.innerHTML = html || '<p class="text-stone-500 text-xs">No recent high-risk anomalies.</p>';
  }
};
