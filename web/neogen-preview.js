(() => {
  const $ = (id) => document.getElementById(id);
  const api = async (path, options = {}) => {
    if (typeof request === 'function') return request(path, options);
    throw new Error('NeoGen API client is unavailable');
  };

  function button(label, view, icon) {
    const b = document.createElement('button');
    b.dataset.view = view;
    b.innerHTML = `<span>${icon}</span>${label}`;
    b.addEventListener('click', () => {
      if (typeof switchView === 'function') switchView(view);
      document.querySelectorAll('.neo-mobile-nav button,.neo-rail-nav button').forEach(x => x.classList.toggle('active', x.dataset.view === view));
    });
    return b;
  }

  function ensureShell() {
    const app = $('app');
    if (!app || $('neoRail')) return;
    const top = app.querySelector('.top');
    const nav = app.querySelector('.nav');
    const sections = [...app.querySelectorAll('.view')];
    if (!top || !nav || !sections.length) return;

    const shell = document.createElement('div');
    shell.className = 'neo-shell';

    const rail = document.createElement('aside');
    rail.id = 'neoRail';
    rail.className = 'neo-rail';
    rail.innerHTML = `
      <div class="neo-logo"><div class="neo-logo-mark">N</div><div><strong>NEOGEN</strong><div class="muted">Afterlife OS</div></div></div>
      <div class="neo-player">
        <div class="neo-player-row"><div class="neo-avatar-mini">N</div><div><strong id="neoPlayerName">Unnamed</strong><div class="muted">Level <span id="neoPlayerLevel">1</span></div></div></div>
        <div class="neo-xp"><span id="neoXpBar"></span></div>
        <small class="muted"><span id="neoXpText">0</span> XP</small>
      </div>
      <div class="neo-wallet"><small class="muted">ACOIN WALLET</small><strong><span id="neoWalletBalance">0</span> AC</strong><small class="muted">Persistent economy</small></div>
      <div class="neo-card"><small class="muted">ASSISTANT</small><h3 id="neoAssistantName">VERA</h3><div class="status">● Online</div><small class="muted" id="neoAutonomy">Approval required</small></div>
      <div class="neo-rail-nav" id="neoRailNav"></div>`;

    const main = document.createElement('main');
    main.className = 'neo-main';
    const tabs = document.createElement('div');
    tabs.className = 'neo-top-tabs';
    ['dashboard','assistant','workspace','avatar','world','economy','governance'].forEach((view, i) => {
      const b = document.createElement('button');
      b.dataset.view = view;
      b.textContent = ['Command','Assistant','VERA Studio','Avatar','World','ACoin','Governance'][i];
      b.addEventListener('click', () => typeof switchView === 'function' && switchView(view));
      tabs.appendChild(b);
    });
    main.appendChild(tabs);
    sections.forEach(section => main.appendChild(section));
    shell.append(rail, main);
    top.after(shell);
    nav.remove();

    const railNav = $('neoRailNav');
    [
      ['Command','dashboard','⌂'],['Assistant','assistant','✦'],['Studio','workspace','⌘'],['Avatar','avatar','◉'],['World','world','◇'],['ACoin','economy','◈'],['Governance','governance','⚖']
    ].forEach(args => railNav.appendChild(button(...args)));

    const mobile = document.createElement('nav');
    mobile.className = 'neo-mobile-nav';
    [['Home','dashboard','⌂'],['VERA','assistant','✦'],['Studio','workspace','⌘'],['World','world','◇'],['Wallet','economy','◈']].forEach(args => mobile.appendChild(button(...args)));
    app.appendChild(mobile);

    const fab = document.createElement('button');
    fab.className = 'neo-fab';
    fab.textContent = '✦';
    fab.addEventListener('click', () => typeof switchView === 'function' && switchView('assistant'));
    app.appendChild(fab);

    const statusbar = document.createElement('div');
    statusbar.className = 'neo-statusbar';
    statusbar.innerHTML = '<span id="neoStatusLeft">NeoGen v1 · local tablet runtime</span><span id="neoStatusRight">Assistant ready</span>';
    app.appendChild(statusbar);
  }

  function ensureAssistantView() {
    if ($('assistant')) return;
    const workspace = $('workspace');
    if (!workspace) return;
    const section = document.createElement('section');
    section.id = 'assistant';
    section.className = 'view';
    section.innerHTML = `
      <div class="neo-assistant-grid">
        <div class="neo-card">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:center"><div><small class="muted">NEOGEN ASSISTANT</small><h1 id="assistantTitle">VERA Command Center</h1></div><button id="assistantRefresh">Refresh</button></div>
          <p class="muted">Shared context, memory, plans, permissions and audit history.</p>
          <div class="stack"><input id="assistantGoal" placeholder="Describe a goal for VERA"><button id="assistantCreatePlan">Create plan</button></div>
          <h3>Active plan</h3><div id="assistantPlan"><p class="muted">No active plan.</p></div>
        </div>
        <div class="neo-card"><h3>Live context</h3><div id="assistantContext"></div><h3>Controls</h3><label>Autonomy<select id="assistantAutonomy"><option value="manual">Manual</option><option value="approval_required">Approval required</option><option value="trusted_safe_actions">Trusted safe actions</option></select></label><label><input id="assistantMemoryEnabled" type="checkbox"> Memory enabled</label><label><input id="assistantEmergencyStop" type="checkbox"> Emergency stop</label><button id="assistantSaveSettings">Save controls</button></div>
        <div class="neo-card"><h3>Memory</h3><div class="stack"><input id="assistantMemoryTitle" placeholder="Memory title"><textarea id="assistantMemoryContent" rows="3" placeholder="What should VERA remember?"></textarea><button id="assistantRemember">Remember</button></div><div id="assistantMemories"></div></div>
        <div class="neo-card"><h3>Approvals and audit</h3><div id="assistantApprovals"></div><div id="assistantAudit"></div></div>
      </div>`;
    workspace.before(section);
    $('assistantRefresh').onclick = loadAssistantDashboard;
    $('assistantCreatePlan').onclick = createAssistantPlan;
    $('assistantRemember').onclick = rememberAssistantFact;
    $('assistantSaveSettings').onclick = saveAssistantSettings;
  }

  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  async function loadAssistantDashboard() {
    if (!state?.token) return;
    try {
      const data = await api('/assistant');
      const identity = data.identity || {};
      $('assistantTitle').textContent = `${identity.assistant_name || 'VERA'} Command Center`;
      $('neoAssistantName').textContent = identity.assistant_name || 'VERA';
      $('neoAutonomy').textContent = String(identity.autonomy || 'approval_required').replaceAll('_',' ');
      $('assistantAutonomy').value = identity.autonomy || 'approval_required';
      $('assistantMemoryEnabled').checked = !!identity.memory_enabled;
      $('assistantEmergencyStop').checked = !!identity.emergency_stop;

      const context = data.context || {};
      const avatar = context.avatar || {};
      const wallet = context.wallet || {};
      const world = context.world || {};
      $('neoPlayerName').textContent = avatar.name || 'Unnamed';
      $('neoPlayerLevel').textContent = avatar.level || 1;
      $('neoWalletBalance').textContent = wallet.balance ?? 0;
      $('neoXpText').textContent = world.experience ?? 0;
      $('neoXpBar').style.width = `${Math.min(100, Number(world.experience || 0) % 500 / 5)}%`;
      $('assistantContext').innerHTML = `
        <div class="kpis"><div class="kpi"><strong>${escapeHtml(avatar.level || 1)}</strong>Avatar</div><div class="kpi"><strong>${escapeHtml(wallet.balance || 0)}</strong>ACoin</div><div class="kpi"><strong>${escapeHtml(context.inventory_count || 0)}</strong>Items</div><div class="kpi"><strong>${escapeHtml(world.legacy_score || 0)}</strong>Legacy</div></div>`;

      const plan = data.active_plan;
      $('assistantPlan').innerHTML = plan ? `<h3>${escapeHtml(plan.goal)}</h3>${(plan.steps || []).map(step => `<div class="neo-plan-step"><span class="neo-step-dot ${step.status === 'completed' ? 'done' : step.status === 'running' ? 'running' : ''}"></span><div><strong>${escapeHtml(step.title)}</strong><div class="muted">${escapeHtml(step.scope)}${step.sensitive ? ' · approval-sensitive' : ''}</div></div></div>`).join('')}` : '<p class="muted">No active plan.</p>';
      $('assistantMemories').innerHTML = (data.memories || []).map(m => `<div class="neo-memory"><strong>${escapeHtml(m.title)}</strong><div>${escapeHtml(m.content)}</div><small class="muted">${escapeHtml(m.category)} · importance ${escapeHtml(m.importance)}</small></div>`).join('') || '<p class="muted">No durable memories yet.</p>';
      const approvals = data.approvals?.pending || [];
      $('assistantApprovals').innerHTML = approvals.length ? approvals.map(a => `<div class="neo-quest"><div><strong>${escapeHtml(a.scope)}</strong><div class="muted">${escapeHtml(a.reason)}</div></div><span class="pill">${escapeHtml(a.status)}</span></div>`).join('') : '<p class="muted">No pending approvals.</p>';
      $('assistantAudit').innerHTML = (data.audit || []).map(a => `<div class="neo-audit">${escapeHtml(a.created_at)} · ${escapeHtml(a.action)}</div>`).join('') || '<p class="muted">No assistant activity yet.</p>';
      if ($('neoStatusRight')) $('neoStatusRight').textContent = identity.emergency_stop ? 'Assistant stopped' : 'Assistant ready';
    } catch (error) {
      if ($('neoStatusRight')) $('neoStatusRight').textContent = `Assistant error: ${error.message}`;
    }
  }

  async function createAssistantPlan() {
    const goal = $('assistantGoal').value.trim();
    if (!goal) return;
    await api('/assistant/plans', {method:'POST', body:JSON.stringify({goal})});
    $('assistantGoal').value = '';
    await loadAssistantDashboard();
  }

  async function rememberAssistantFact() {
    const title = $('assistantMemoryTitle').value.trim();
    const content = $('assistantMemoryContent').value.trim();
    if (!title || !content) return;
    await api('/assistant/memory', {method:'POST', body:JSON.stringify({title, content, category:'user', importance:0.75})});
    $('assistantMemoryTitle').value = '';
    $('assistantMemoryContent').value = '';
    await loadAssistantDashboard();
  }

  async function saveAssistantSettings() {
    await api('/assistant/settings', {method:'POST', body:JSON.stringify({autonomy:$('assistantAutonomy').value,memory_enabled:$('assistantMemoryEnabled').checked,emergency_stop:$('assistantEmergencyStop').checked})});
    await loadAssistantDashboard();
  }

  async function enhanceWorld() {
    const world = $('world');
    if (!world || $('neoWorldLive')) return;
    const live = document.createElement('div');
    live.id = 'neoWorldLive';
    live.className = 'neo-card';
    live.style.marginTop = '12px';
    live.innerHTML = '<h2>Live expeditions</h2><div id="neoWorldProfile"></div><div id="neoWorldRegions" class="grid"></div><h3>Recent expedition history</h3><div id="neoExpeditionHistory"></div>';
    world.appendChild(live);
    await loadWorldLive();
  }

  async function loadWorldLive() {
    try {
      const [profile, regions, history] = await Promise.all([api('/world/profile'), api('/world/regions'), api('/world/expeditions')]);
      $('neoWorldProfile').innerHTML = `<div class="kpis"><div class="kpi"><strong>${profile.world_level}</strong>World level</div><div class="kpi"><strong>${profile.essence}</strong>Essence</div><div class="kpi"><strong>${profile.expeditions_completed}</strong>Expeditions</div><div class="kpi"><strong>${profile.legacy_score}</strong>Legacy</div></div>`;
      $('neoWorldRegions').innerHTML = regions.items.map(region => `<div class="neo-card"><span class="pill">Threat ${region.threat}</span><h3>${escapeHtml(region.name)}</h3><p class="muted">${escapeHtml(region.description)}</p><button data-region="${escapeHtml(region.id)}">Begin expedition</button></div>`).join('');
      $('neoWorldRegions').querySelectorAll('[data-region]').forEach(button => button.onclick = async () => {
        button.disabled = true;
        try { await api('/world/expeditions', {method:'POST', body:JSON.stringify({region_id:button.dataset.region})}); await Promise.all([loadWorldLive(), loadAssistantDashboard()]); }
        catch (error) { alert(error.message); }
        finally { button.disabled = false; }
      });
      $('neoExpeditionHistory').innerHTML = history.items.map(item => `<div class="neo-quest"><div><strong>${escapeHtml(item.region_name)}</strong><div class="muted">${item.success ? 'Success' : 'Failed'} · ${escapeHtml(item.discovery)}</div></div><span>${item.reward_acoin} AC</span></div>`).join('') || '<p class="muted">No expeditions yet.</p>';
    } catch (error) {
      $('neoWorldProfile').textContent = error.message;
    }
  }

  function patchNavigation() {
    const oldSwitch = window.switchView;
    if (typeof oldSwitch !== 'function' || oldSwitch.__neoPatched) return;
    const patched = function(id) {
      oldSwitch(id);
      document.querySelectorAll('.neo-top-tabs button,.neo-rail-nav button,.neo-mobile-nav button').forEach(b => b.classList.toggle('active', b.dataset.view === id));
      if (id === 'assistant') loadAssistantDashboard();
      if (id === 'world') enhanceWorld();
    };
    patched.__neoPatched = true;
    window.switchView = patched;
  }

  function start() {
    ensureAssistantView();
    ensureShell();
    patchNavigation();
    const observer = new MutationObserver(() => {
      if ($('app') && !$('app').classList.contains('hidden')) {
        loadAssistantDashboard();
        enhanceWorld();
      }
    });
    if ($('app')) observer.observe($('app'), {attributes:true, attributeFilter:['class']});
    if (state?.token) Promise.allSettled([loadAssistantDashboard(), enhanceWorld()]);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
