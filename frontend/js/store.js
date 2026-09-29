/**
 * Light In-Memory State Store for Caching SPA State
 */
const AUTH_STORAGE_KEY = 'aa_auth';
const VENDOR_CONTEXT_STORAGE_KEY = 'aa_active_vendor';

const EMPTY_AUTH = { token: null, refreshToken: null, username: null };

export const Store = {
  state: {
    activeRoute: 'overview',
    anomaliesData: null,
    reconciliationData: null,
    ledgerData: null,
    ragChatHistory: [],
    minRiskFilter: 0.0,
    searchQuery: '',
    selectedCategory: 'ALL',
    auth: { ...EMPTY_AUTH },
    activeVendorContext: 'ALL',
    vendorEpoch: 0
  },

  get(key) {
    return this.state[key];
  },

  set(key, val) {
    this.state[key] = val;
  },

  update(key, partialVal) {
    if (typeof this.state[key] === 'object' && this.state[key] !== null) {
      this.state[key] = { ...this.state[key], ...partialVal };
    } else {
      this.state[key] = partialVal;
    }
  },

  hydrateFromStorage() {
    try {
      const rawAuth = localStorage.getItem(AUTH_STORAGE_KEY);
      if (rawAuth) this.state.auth = { ...EMPTY_AUTH, ...JSON.parse(rawAuth) };
      const rawVendorContext = localStorage.getItem(VENDOR_CONTEXT_STORAGE_KEY);
      if (rawVendorContext) this.state.activeVendorContext = rawVendorContext;
    } catch (e) {
      console.warn('Failed to hydrate auth state from localStorage:', e);
    }
  },

  persistAuth() {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(this.state.auth));
    localStorage.setItem(VENDOR_CONTEXT_STORAGE_KEY, this.state.activeVendorContext);
  },

  clearAuth() {
    this.state.auth = { ...EMPTY_AUTH };
    this.state.activeVendorContext = 'ALL';
    localStorage.removeItem(AUTH_STORAGE_KEY);
    localStorage.removeItem(VENDOR_CONTEXT_STORAGE_KEY);
    this.clearVendorScopedCache();
  },

  clearVendorScopedCache() {
    // All per-vendor fetched data must be dropped on any auth/vendor-context
    // boundary — otherwise a prior session's or vendor's cached results would
    // leak into the next one (the Store singleton persists across logout/login
    // within the same page load).
    this.state.anomaliesData = null;
    this.state.anomaliesSummary = null;
    this.state.reconciliationData = null;
    this.state.ledgerData = null;
    this.state.ragChatHistory = [];
    // Bumped so in-flight requests started under a previous vendor/session can
    // detect they're stale when they resolve and skip writing to the Store —
    // a slow request can otherwise land after logout/vendor-switch and clobber
    // fresh state with data scoped to the wrong vendor.
    this.state.vendorEpoch += 1;
  },

  getVendorEpoch() {
    return this.state.vendorEpoch;
  },

  isAuthenticated() {
    return !!this.state.auth.token;
  },

  getEffectiveVendorId() {
    return this.state.activeVendorContext || 'ALL';
  }
};
