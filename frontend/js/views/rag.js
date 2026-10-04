import { ApiClient } from '../api.js';
import { Toast } from '../components/toast.js';
import { Modal } from '../components/modal.js';
import { Store } from '../store.js';
import { formatINR } from '../utils/format.js';

export const RagView = {
  async init() {
    this.bindEvents();
    await this.loadKnowledgeBaseStats();
    this.renderChatHistory();
    this.updateScopeBadge();
  },

  bindEvents() {
    const sendBtn = document.getElementById('rag-send-btn');
    const input = document.getElementById('rag-user-input');
    const reingestBtn = document.getElementById('rag-reingest-btn');

    if (sendBtn && input) {
      sendBtn.onclick = () => this.sendQuery();
      input.onkeypress = (e) => {
        if (e.key === 'Enter') this.sendQuery();
      };
      // update scope badge live as vendor switcher changes
      input.onfocus = () => this.updateScopeBadge();
    }

    if (reingestBtn) {
      reingestBtn.onclick = () => this.reingestPolicies();
    }

    document.querySelectorAll('.suggested-prompt-chip').forEach(chip => {
      chip.onclick = () => {
        if (input) {
          input.value = chip.innerText.replace(/^"|"$/g, '');
          this.sendQuery();
        }
      };
    });
    // also watch vendor switcher to update badge
    const vs = document.getElementById('vendor-switcher');
    if (vs) vs.addEventListener('change', () => this.updateScopeBadge());
  },

  updateScopeBadge() {
    const badge = document.getElementById('rag-active-scope');
    const ledgerScope = document.getElementById('rag-ledger-scope');
    const scope = Store.getEffectiveVendorId() || 'ALL';
    const label = scope === 'ALL' ? 'All Vendors (100/vendor)' : scope;
    if (badge) badge.textContent = `Scope: ${label}`;
    if (ledgerScope) ledgerScope.textContent = label;
  },

  async loadKnowledgeBaseStats() {
    try {
      const res = await ApiClient.listPolicyDocuments();
      const docCountEl = document.getElementById('rag-doc-count');
      const chunkCountEl = document.getElementById('rag-chunk-count');
      const docListEl = document.getElementById('rag-policy-doc-list');

      if (docCountEl) docCountEl.innerText = res.policy_files ? res.policy_files.length : 2;
      if (chunkCountEl) chunkCountEl.innerText = res.total_vector_chunks || 12;

      if (docListEl && res.policy_files) {
        docListEl.innerHTML = res.policy_files.map(f => `
          <div class="p-2.5 bg-white border border-stone-200 rounded-xl flex items-center justify-between text-xs text-stone-700 shadow-sm">
            <div class="flex items-center gap-2">
              <svg class="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V7.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 1H7a2 2 0 00-2 2v16a2 2 0 002 2z"/></svg>
              <span class="font-medium truncate max-w-[180px]">${f}</span>
            </div>
            <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300 font-semibold">INDEXED</span>
          </div>
        `).join('');
      }
      this.updateScopeBadge();
      // also pull ledger stats for this scope to show counts in left panel tooltip
      try {
        const stats = await ApiClient.getLedgerStats();
        if (stats && document.getElementById('rag-ledger-scope')) {
          document.getElementById('rag-ledger-scope').textContent = stats.vendor_scope === 'ALL' ? `${stats.total_records} rows (100/vendor)` : `${stats.total_records} rows`;
          document.getElementById('rag-ledger-scope').title = `Anomalies: ${stats.anomaly_records} • Amount: ${formatINR(stats.total_amount)}`;
        }
      } catch (e) { /* ignore stats failure */ }
    } catch (err) {
      console.error('KB stats error:', err);
    }
  },

  async reingestPolicies() {
    try {
      Toast.show('Re-indexing PDF policy documents into ChromaDB...', 'info');
      const res = await ApiClient.reingestPolicies();
      Toast.show(`Successfully indexed ${res.total_chunks} policy chunks into ChromaDB.`, 'success');
      await this.loadKnowledgeBaseStats();
    } catch (err) {
      Toast.show(`Re-ingestion error: ${err.message}`, 'error');
    }
  },

  async sendQuery() {
    const input = document.getElementById('rag-user-input');
    if (!input || !input.value.trim()) return;

    const userQuery = input.value.trim();
    input.value = '';

    // Push to store history
    const history = Store.get('ragChatHistory') || [];
    history.push({ role: 'user', text: userQuery });
    Store.set('ragChatHistory', history);

    this.renderChatHistory();
    const typingId = this.appendTypingIndicator();
    const epoch = Store.getVendorEpoch();
    const scope = Store.getEffectiveVendorId() || 'ALL';

    try {
      const res = await ApiClient.queryRAG(userQuery);
      this.removeTypingIndicator(typingId);
      // The vendor/session context changed mid-flight (e.g. logout) — the chat
      // history this answer would append to no longer exists in this scope.
      if (epoch !== Store.getVendorEpoch()) return;

      // Surface financial-only refusal differently if needed — still treat as ai msg
      history.push({
        role: 'ai',
        text: res.answer,
        citations: res.citations || [],
        ledgerCitations: res.ledger_citations || [],
        isFinancial: res.is_financial !== false,
        vendorScope: res.vendor_scope || scope
      });
      Store.set('ragChatHistory', history);
      this.renderChatHistory();

    } catch (err) {
      this.removeTypingIndicator(typingId);
      if (epoch !== Store.getVendorEpoch()) return;

      history.push({ role: 'ai', text: `Error querying financial copilot: ${err.message}`, citations: [], isFinancial: false });
      Store.set('ragChatHistory', history);
      this.renderChatHistory();
    }
  },

  renderChatHistory() {
    const chatContainer = document.getElementById('rag-chat-history');
    if (!chatContainer) return;

    const history = Store.get('ragChatHistory') || [];
    if (history.length === 0) return;

    let html = `
      <div class="flex gap-3 justify-start">
        <div class="max-w-[85%] p-4 bg-white border border-stone-200 rounded-2xl rounded-tl-none text-xs text-stone-800 leading-relaxed shadow-sm space-y-2">
          <div>Namaste! I am your <b>financial ledger copilot</b> — I answer <b>only</b> from your ledger records (scoped vendor) and India policy docs.</div>
          <div class="text-[11px] text-stone-600">Try: “Show me all threshold-bypass Txns for VND-1001”, “Total amount & count for current scope”, “Duplicate payments”, or “What is the 1 Lakh split-transaction rule? (cite page)”.</div>
          <div class="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1 inline-block">Financial chats only • ${Store.getEffectiveVendorId() || 'ALL'} scope (100/vendor)</div>
        </div>
      </div>
    `;

    history.forEach((msg) => {
      if (msg.role === 'user') {
        html += `
          <div class="flex gap-3 justify-end">
            <div class="max-w-[80%] p-3.5 bg-stone-900 text-white rounded-2xl rounded-tr-none text-xs leading-relaxed shadow-sm">
              ${this.escapeHtml(msg.text)}
            </div>
          </div>
        `;
      } else {
        const isNonFinancial = msg.isFinancial === false;
        let citationsHtml = '';
        const cits = msg.citations || [];
        const ledgerCits = cits.filter(c => (c.type === 'ledger') || (c.doc_name && c.doc_name.startsWith('Ledger')));
        const policyCits = cits.filter(c => c.type !== 'ledger' && !(c.doc_name && c.doc_name.startsWith('Ledger')));

        if (cits.length > 0) {
          citationsHtml = '<div class="pt-2 border-t border-stone-200 space-y-1.5">';
          if (ledgerCits.length) {
            citationsHtml += '<div class="flex flex-wrap gap-1.5 items-center text-[11px] text-stone-600"><span class="font-semibold text-stone-700">Ledger Sources:</span>';
            ledgerCits.forEach((c) => {
              const txn = (c.page || c.doc_name || '').toString().replace('Ledger Record — ','');
              citationsHtml += `
                <button class="citation-chip !bg-white !border-stone-300 !text-stone-700 hover:!bg-stone-50" data-doc="${this.escapeAttr(c.doc_name)}" data-page="${this.escapeAttr(c.page)}" data-snippet="${encodeURIComponent(c.snippet)}" data-type="ledger">
                  🧾 ${this.escapeHtml(txn)} 
                </button>
              `;
            });
            citationsHtml += '</div>';
          }
          if (policyCits.length) {
            citationsHtml += '<div class="flex flex-wrap gap-1.5 items-center text-[11px] text-stone-600"><span class="font-semibold text-stone-700">Policy Sources:</span>';
            policyCits.forEach((c) => {
              citationsHtml += `
                <button class="citation-chip" data-doc="${this.escapeAttr(c.doc_name)}" data-page="${this.escapeAttr(c.page)}" data-snippet="${encodeURIComponent(c.snippet)}" data-type="policy">
                  📄 ${this.escapeHtml((c.doc_name||'').replace('.pdf',''))} (Pg ${c.page})
                </button>
              `;
            });
            citationsHtml += '</div>';
          }
          if (msg.vendorScope) {
            citationsHtml += `<div class="text-[11px] text-stone-500">Scope: <b>${this.escapeHtml(msg.vendorScope)}</b> • 100 ledgers/vendor • Financial-grounded</div>`;
          }
          citationsHtml += '</div>';
        }

        const wrapClass = isNonFinancial
          ? 'bg-amber-50 border-amber-300 text-amber-900'
          : 'bg-white border-stone-200 text-stone-900';

        html += `
          <div class="flex gap-3 justify-start">
            <div class="max-w-[85%] p-4 ${wrapClass} border rounded-2xl rounded-tl-none text-xs leading-relaxed space-y-3 shadow-sm">
              ${isNonFinancial ? '<div class="text-[11px] font-bold tracking-widest uppercase text-amber-700">Financial-only Notice</div>' : ''}
              <div class="prose prose-xs font-sans">${this.formatAnswer(msg.text)}</div>
              ${citationsHtml}
            </div>
          </div>
        `;
      }
    });

    chatContainer.innerHTML = html;
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // Attach click listeners for citation chips
    chatContainer.querySelectorAll('.citation-chip').forEach(btn => {
      btn.onclick = () => {
        const docName = btn.getAttribute('data-doc');
        const page = btn.getAttribute('data-page');
        const snippet = decodeURIComponent(btn.getAttribute('data-snippet'));
        const type = btn.getAttribute('data-type');
        if (type === 'ledger') {
          Modal.openDrawer(`Ledger Citation: ${docName} — ${page}`, `
            <div class="space-y-3">
              <div class="p-3 bg-emerald-50 border border-emerald-200 rounded-lg">
                <h4 class="font-semibold text-emerald-800 text-xs mb-1">Ledger Record (scoped, 100/vendor)</h4>
                <p class="text-xs text-stone-800"><b>${this.escapeHtml(docName)}</b> — Txn ${this.escapeHtml(page)}</p>
              </div>
              <div class="p-3 bg-[#fbf8f3] border border-stone-200 rounded-lg">
                <h4 class="font-semibold text-stone-600 text-xs mb-2">Retrieved Ledger Text</h4>
                <p class="text-xs text-stone-900 leading-relaxed font-mono">${this.escapeHtml(snippet)}</p>
              </div>
              <p class="text-[11px] text-stone-500">Tip: Open <b>Ledger Data Center</b> and search <b>${this.escapeHtml(page)}</b> to see the full row & anomalies.</p>
            </div>
          `);
        } else {
          Modal.openDrawer(`Policy Citation: ${docName} (Page ${page})`, `
            <div class="space-y-3">
              <div class="p-3 bg-[#fbf8f3] border border-stone-200 rounded-lg">
                <h4 class="font-semibold text-amber-800 text-xs mb-1">Document Source</h4>
                <p class="text-xs text-stone-800"><b>${this.escapeHtml(docName)}</b> — Page ${this.escapeHtml(page)}</p>
              </div>
              <div class="p-3 bg-[#fbf8f3] border border-stone-200 rounded-lg">
                <h4 class="font-semibold text-stone-600 text-xs mb-2">Retrieved Vector Store Text Chunk</h4>
                <p class="text-xs text-stone-900 leading-relaxed font-mono">${this.escapeHtml(snippet)}</p>
              </div>
            </div>
          `);
        }
      };
    });
  },

  formatAnswer(text) {
    if (!text) return '';
    // keep markdown-like **bold** approximate
    let html = this.escapeHtml(text).replace(/\n/g, '<br/>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
    return html;
  },
  escapeHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  },
  escapeAttr(s) {
    return String(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  },

  appendTypingIndicator() {
    const chatContainer = document.getElementById('rag-chat-history');
    const scope = Store.getEffectiveVendorId() || 'ALL';
    const id = `typing-${Date.now()}`;
    const div = document.createElement('div');
    div.id = id;
    div.className = 'flex gap-3 justify-start';
    div.innerHTML = `
      <div class="p-3 bg-white border border-stone-200 rounded-2xl rounded-tl-none text-xs text-stone-600 flex items-center gap-2 shadow-sm">
        <span class="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
        <span class="animate-pulse">Searching ${scope} ledger (100/vendor) + policy vector store…</span>
      </div>
    `;
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return id;
  },

  removeTypingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }
};
