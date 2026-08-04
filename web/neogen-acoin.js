(() => {
  const byId = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const callApi = async (path, options = {}) => {
    if (typeof request !== 'function') throw new Error('NeoGen API client unavailable');
    return request(path, options);
  };

  function ensureDashboard() {
    const economy = byId('economy');
    if (!economy || byId('acoinLedgerDashboard')) return;
    const panel = document.createElement('div');
    panel.id = 'acoinLedgerDashboard';
    panel.className = 'neo-assistant-grid';
    panel.style.marginTop = '14px';
    panel.innerHTML = `
      <div class="neo-card">
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
          <div><small class="muted">DOUBLE-ENTRY LEDGER</small><h2>ACoin Wallet</h2></div>
          <button id="acoinRefresh">Refresh</button>
        </div>
        <div class="kpis">
          <div class="kpi"><strong id="acoinNeoBalance">0</strong>NEO</div>
          <div class="kpi"><strong id="acoinEssenceBalance">0</strong>Essence</div>
          <div class="kpi"><strong id="acoinLedgerState">—</strong>Ledger</div>
        </div>
        <p class="muted" id="acoinWalletOwner"></p>
      </div>
      <div class="neo-card">
        <h3>Transfer assets</h3>
        <label>Recipient owner ID<input id="acoinTransferOwner" placeholder="user ID"></label>
        <label>Asset<select id="acoinTransferAsset"><option value="NEO">NEO</option><option value="ESSENCE">Essence</option></select></label>
        <label>Amount<input id="acoinTransferAmount" type="number" min="0" step="0.00000001" placeholder="0.00"></label>
        <label>Description<input id="acoinTransferDescription" placeholder="Transfer reason"></label>
        <button id="acoinTransferButton">Review and transfer</button>
        <p class="muted">Transfers are recorded as governed high-risk economy actions.</p>
      </div>
      <div class="neo-card">
        <h3>Marketplace settlement</h3>
        <label>Seller ID<input id="acoinSellerId" placeholder="seller user ID"></label>
        <label>Listing ID<input id="acoinListingId" placeholder="listing ID"></label>
        <label>Price<input id="acoinSettlementPrice" type="number" min="0" step="0.00000001" placeholder="0.00"></label>
        <button id="acoinSettlementButton">Settle purchase</button>
        <p class="muted">Default treasury fee: 2.5%.</p>
      </div>
      <div class="neo-card">
        <h3>Ledger integrity</h3>
        <div id="acoinReconciliation"></div>
      </div>
      <div class="neo-card" style="grid-column:1/-1">
        <h3>Transaction history</h3>
        <div id="acoinTransactions"><p class="muted">No transactions loaded.</p></div>
      </div>`;
    economy.appendChild(panel);
    byId('acoinRefresh').onclick = loadACoin;
    byId('acoinTransferButton').onclick = submitTransfer;
    byId('acoinSettlementButton').onclick = submitSettlement;
  }

  async function loadACoin() {
    if (!window.state?.token) return;
    ensureDashboard();
    try {
      const [wallet, transactions, reconciliation] = await Promise.all([
        callApi('/acoin/wallet'),
        callApi('/acoin/transactions'),
        callApi('/acoin/reconciliation')
      ]);
      byId('acoinNeoBalance').textContent = wallet.balances?.NEO ?? '0';
      byId('acoinEssenceBalance').textContent = wallet.balances?.ESSENCE ?? '0';
      byId('acoinWalletOwner').textContent = `Owner: ${wallet.owner_id}`;
      byId('acoinLedgerState').textContent = reconciliation.balanced ? 'Balanced' : 'Review';
      byId('acoinReconciliation').innerHTML = `
        <div class="neo-quest"><div><strong>${reconciliation.balanced ? 'Ledger balanced' : 'Ledger requires review'}</strong><div class="muted">Checked ${escapeHtml(reconciliation.checked_at)}</div></div><span class="pill">${reconciliation.balanced ? 'OK' : 'ALERT'}</span></div>
        <div class="neo-audit">NEO net: ${escapeHtml(reconciliation.asset_totals?.NEO ?? '0')}</div>
        <div class="neo-audit">Essence net: ${escapeHtml(reconciliation.asset_totals?.ESSENCE ?? '0')}</div>
        <div class="neo-audit">Orphan entries: ${(reconciliation.orphan_entries || []).length}</div>`;
      const items = transactions.items || [];
      byId('acoinTransactions').innerHTML = items.length ? items.map(tx => {
        const entries = (tx.entries || []).map(entry => `${escapeHtml(entry.amount)} ${escapeHtml(entry.asset)}`).join(' · ');
        return `<div class="neo-quest"><div><strong>${escapeHtml(tx.description)}</strong><div class="muted">${escapeHtml(tx.reference)} · ${escapeHtml(tx.created_at)}</div><div class="muted">${entries}</div></div><span class="pill">Posted</span></div>`;
      }).join('') : '<p class="muted">No ledger transactions yet.</p>';
      const sidebar = byId('neoWalletBalance');
      if (sidebar) sidebar.textContent = wallet.balances?.NEO ?? '0';
    } catch (error) {
      const target = byId('acoinTransactions');
      if (target) target.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
    }
  }

  async function submitTransfer() {
    const to_owner_id = byId('acoinTransferOwner').value.trim();
    const asset = byId('acoinTransferAsset').value;
    const amount = byId('acoinTransferAmount').value;
    const description = byId('acoinTransferDescription').value.trim() || 'User transfer';
    if (!to_owner_id || !amount) return;
    if (!confirm(`Transfer ${amount} ${asset} to ${to_owner_id}? This action is recorded in the audit log.`)) return;
    const button = byId('acoinTransferButton');
    button.disabled = true;
    try {
      await callApi('/acoin/transfer', {method:'POST', body:JSON.stringify({to_owner_id, asset, amount, description})});
      byId('acoinTransferAmount').value = '';
      byId('acoinTransferDescription').value = '';
      await loadACoin();
    } catch (error) {
      alert(error.message);
    } finally {
      button.disabled = false;
    }
  }

  async function submitSettlement() {
    const seller_id = byId('acoinSellerId').value.trim();
    const listing_id = byId('acoinListingId').value.trim();
    const price = byId('acoinSettlementPrice').value;
    if (!seller_id || !listing_id || !price) return;
    if (!confirm(`Purchase listing ${listing_id} for ${price} NEO?`)) return;
    const button = byId('acoinSettlementButton');
    button.disabled = true;
    try {
      await callApi('/acoin/settlement', {method:'POST', body:JSON.stringify({seller_id, listing_id, price})});
      byId('acoinSettlementPrice').value = '';
      await loadACoin();
    } catch (error) {
      alert(error.message);
    } finally {
      button.disabled = false;
    }
  }

  function patchViewNavigation() {
    const original = window.switchView;
    if (typeof original !== 'function' || original.__acoinPatched) return;
    const patched = function(view) {
      original(view);
      if (view === 'economy') loadACoin();
    };
    patched.__acoinPatched = true;
    window.switchView = patched;
  }

  function start() {
    ensureDashboard();
    patchViewNavigation();
    if (window.state?.token) loadACoin();
    const app = byId('app');
    if (app) new MutationObserver(() => {
      if (!app.classList.contains('hidden')) loadACoin();
    }).observe(app, {attributes:true, attributeFilter:['class']});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
