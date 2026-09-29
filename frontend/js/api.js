/**
 * Centralized API Client for Backend Endpoints
 */
import { Store } from './store.js';
import { Toast } from './components/toast.js';

const API_BASE = window.location.origin;

// Set by app.js so a failed silent-refresh can route the user back to the login view.
export let onAuthFailure = null;
export function setAuthFailureHandler(handler) {
  onAuthFailure = handler;
}

function authHeaders() {
  const { token } = Store.get('auth');
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  headers['X-Vendor-Context'] = Store.getEffectiveVendorId();
  return headers;
}

async function apiFetch(path, options = {}, _isRetry = false) {
  const hasToken = !!Store.get('auth').token;
  const headers = { ...(hasToken ? authHeaders() : {}), ...(options.headers || {}) };

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401 && hasToken && !_isRetry) {
    try {
      await ApiClient.refreshToken();
      return apiFetch(path, options, true);
    } catch (e) {
      Store.clearAuth();
      if (onAuthFailure) onAuthFailure();
      throw new Error('Session expired — please log in again.');
    }
  }

  if (res.status === 403) {
    Toast.show('Access denied — vendor scope mismatch', 'error');
  }

  return res;
}

export const ApiClient = {
  async login(payload) {
    const res = await apiFetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      if (res.status === 429) throw new Error('Too many attempts — please try again shortly.');
      const err = await res.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(err.detail || 'Login failed');
    }
    return res.json();
  },

  async refreshToken() {
    const { refreshToken } = Store.get('auth');
    if (!refreshToken) throw new Error('No refresh token available');
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken })
    });
    if (!res.ok) throw new Error('Refresh failed');
    const data = await res.json();
    Store.update('auth', {
      token: data.access_token,
      refreshToken: data.refresh_token,
      username: data.username
    });
    Store.persistAuth();
    return data;
  },

  async logout() {
    const { refreshToken } = Store.get('auth');
    if (refreshToken) {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken })
      }).catch(() => {});
    }
    Store.clearAuth();
  },

  async getMe() {
    const res = await apiFetch('/api/auth/me');
    if (!res.ok) throw new Error('Failed to fetch current user');
    return res.json();
  },

  async listPublicVendors() {
    const res = await fetch(`${API_BASE}/api/public/vendors`);
    if (!res.ok) throw new Error('Failed to fetch vendor list');
    return res.json();
  },

  async createVendor(payload) {
    const res = await apiFetch('/api/auditors/vendors/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Vendor creation failed' }));
      throw new Error(err.detail || 'Vendor creation failed');
    }
    return res.json();
  },

  async getHealth() {
    const res = await fetch(`${API_BASE}/api/health`);
    if (!res.ok) throw new Error('Health endpoint unreachable');
    return res.json();
  },

  async reconcileInvoices(formData) {
    const res = await apiFetch('/api/recon/upload', {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Reconciliation failed' }));
      throw new Error(err.detail || 'Reconciliation failed');
    }
    return res.json();
  },

  async detectAnomalies(minRiskScore = 0.0, useLlm = false) {
    const params = new URLSearchParams({ min_risk_score: minRiskScore, use_llm: useLlm ? 'true' : 'false' });
    const res = await apiFetch(`/api/audit/anomalies?${params.toString()}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Anomaly detection failed' }));
      throw new Error(err.detail || 'Anomaly detection failed');
    }
    return res.json();
  },

  async queryRAG(userQuery, topK = 3) {
    const res = await apiFetch('/api/rag/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: userQuery, top_k: topK })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'RAG query failed' }));
      throw new Error(err.detail || 'RAG query failed');
    }
    return res.json();
  },

  async listPolicyDocuments() {
    const res = await apiFetch('/api/rag/documents');
    if (!res.ok) throw new Error('Failed to fetch policy documents list');
    return res.json();
  },

  async reingestPolicies() {
    const res = await apiFetch('/api/rag/ingest', {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Policy re-ingestion failed');
    return res.json();
  },

  async getLedgerData(page = 1, limit = 50, search = '', category = 'ALL', sortBy = null, sortDir = null) {
    const params = new URLSearchParams({
      page: page.toString(),
      limit: limit.toString(),
      search: search || '',
      category: category || 'ALL'
    });
    if (sortBy) params.set('sort_by', sortBy);
    if (sortDir) params.set('sort_dir', sortDir);
    const res = await apiFetch(`/api/ledger?${params.toString()}`);
    if (!res.ok) throw new Error('Ledger data fetch failed');
    return res.json();
  },

  async getLedgerStats() {
    const res = await apiFetch(`/api/ledger/stats`);
    if (!res.ok) throw new Error('Ledger stats fetch failed');
    return res.json();
  },

  async injectAnomalies(count = null, perVendor = 100) {
    const params = new URLSearchParams();
    if (count != null) params.set('count', count.toString());
    else params.set('per_vendor', perVendor.toString());
    const res = await apiFetch(`/api/ledger/inject-anomalies?${params.toString()}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Synthetic injection failed');
    return res.json();
  },

  async generateReport(payload) {
    // Tries /api/report/export first, falls back to /api/report/generate
    let res = await apiFetch('/api/report/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      res = await apiFetch('/api/report/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    }

    if (!res.ok) throw new Error('PDF report generation failed');
    return res.blob();
  }
};
