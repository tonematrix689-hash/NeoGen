const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  permissions: JSON.parse(localStorage.getItem('neogen.permissions') || '{}'),
  activity: JSON.parse(localStorage.getItem('neogen.activity') || '[]'),
  activeFile: null,
  model: localStorage.getItem('neogen.model') || 'gpt-5-nano'
};

const permissionDefinitions = [
  ['read_repo', 'Read repository', 'View files, branches, issues, and pull requests.'],
  ['edit_repo', 'Edit repository', 'Prepare file changes inside the selected repository.'],
  ['commit_repo', 'Commit changes', 'Create commits only after explicit confirmation.'],
  ['open_pr', 'Open pull requests', 'Create draft pull requests for approved changes.'],
  ['run_tasks', 'Run development tasks', 'Execute approved local build and validation tasks.'],
  ['deploy', 'Deploy applications', 'Prepare deployments with a separate confirmation step.'],
  ['account_profile', 'Read account profile', 'Read basic connected-account identity details.'],
  ['notifications', 'Send notifications', 'Display alerts and task completion notices.'],
  ['web_access', 'Use web access', 'Research current documentation and external information.'],
  ['memory', 'Use project memory', 'Remember project preferences and prior approved decisions.']
];

const fileSamples = {
  'package.json': '{\n  "name": "neogen-web-app",\n  "version": "1.0.0",\n  "private": true\n}\n',
  'server.js': "// NeoGen server\n// Connect the live GitHub file API in the next milestone.\n",
  'public/index.html': '<!-- NeoGen interface loaded from the repository -->\n',
  'public/style.css': '/* Dark purple, gold, silica-glass visual system */\n',
  'public/app.js': '// NeoGen client controller\n'
};

function saveState() {
  localStorage.setItem('neogen.permissions', JSON.stringify(state.permissions));
  localStorage.setItem('neogen.activity', JSON.stringify(state.activity.slice(0, 100)));
  localStorage.setItem('neogen.model', state.model);
}

function logActivity(message, type = 'info') {
  state.activity.unshift({ message, type, time: new Date().toISOString() });
  saveState();
  renderActivity();
}

function renderActivity() {
  const container = $('#activityLog');
  if (!container) return;
  container.innerHTML = state.activity.length
    ? state.activity.map((entry) => `<div class="activity-entry"><strong>${escapeHtml(entry.message)}</strong><br><small>${new Date(entry.time).toLocaleString()}</small></div>`).join('')
    : '<div class="activity-entry"><strong>No activity yet.</strong><br><small>Approved and local actions will appear here.</small></div>';
}

function renderPermissions() {
  const grid = $('#permissionGrid');
  grid.innerHTML = permissionDefinitions.map(([key, title, description]) => `
    <div class="permission-item">
      <div><strong>${title}</strong><p>${description}</p></div>
      <label class="switch"><input type="checkbox" data-permission="${key}" ${state.permissions[key] ? 'checked' : ''}><span></span></label>
    </div>`).join('');

  $$('[data-permission]').forEach((input) => {
    input.addEventListener('change', () => {
      state.permissions[input.dataset.permission] = input.checked;
      $('#fullControl').checked = permissionDefinitions.every(([key]) => state.permissions[key]);
      saveState();
      logActivity(`${input.checked ? 'Granted' : 'Revoked'} permission: ${input.dataset.permission}`);
    });
  });

  $('#fullControl').checked = permissionDefinitions.every(([key]) => state.permissions[key]);
}

function setView(name) {
  $$('.nav-item').forEach((button) => button.classList.toggle('active', button.dataset.view === name));
  $$('.view').forEach((view) => view.classList.remove('active'));
  $(`#${name}View`).classList.add('active');
  const titles = { chat: 'Intelligence Console', workspace: 'Repository Workspace', permissions: 'Permission Control', activity: 'Audit Trail' };
  $('#viewTitle').textContent = titles[name] || 'NeoGen';
}

function appendMessage(role, text) {
  const article = document.createElement('article');
  article.className = `message ${role}`;
  article.innerHTML = role === 'assistant'
    ? `<div class="avatar">N</div><div><strong>NeoGen</strong><p>${escapeHtml(text)}</p></div>`
    : `<div><strong>You</strong><p>${escapeHtml(text)}</p></div>`;
  $('#messages').appendChild(article);
  article.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function normalizePuterResponse(response) {
  if (typeof response === 'string') return response;
  return response?.message?.content || response?.content || response?.text || JSON.stringify(response);
}

async function handleChat(event) {
  event.preventDefault();
  const input = $('#prompt');
  const prompt = input.value.trim();
  if (!prompt) return;
  appendMessage('user', prompt);
  input.value = '';
  input.style.height = 'auto';
  logActivity('Submitted a chat request');

  const waiting = document.createElement('article');
  waiting.className = 'message assistant';
  waiting.innerHTML = '<div class="avatar">N</div><div><strong>NeoGen</strong><p>Processing through Puter.js…</p></div>';
  $('#messages').appendChild(waiting);

  try {
    if (!window.puter?.ai?.chat) throw new Error('Puter.js is not available yet. Check your internet connection and reload.');
    const response = await window.puter.ai.chat(prompt, { model: state.model });
    waiting.querySelector('p').textContent = normalizePuterResponse(response);
    logActivity(`Completed AI response using ${state.model}`);
  } catch (error) {
    waiting.querySelector('p').textContent = `Unable to complete the request: ${error.message}`;
    logActivity(`AI request failed: ${error.message}`, 'error');
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function requirePermission(key, message) {
  if (state.permissions[key]) return true;
  alert(message);
  setView('permissions');
  return false;
}

function initWorkspace() {
  $$('#fileTree button').forEach((button) => {
    button.addEventListener('click', () => {
      if (!requirePermission('read_repo', 'Grant repository read permission first.')) return;
      state.activeFile = button.dataset.file;
      $('#activeFile').textContent = state.activeFile;
      $('#editor').value = fileSamples[state.activeFile] || '';
      logActivity(`Opened ${state.activeFile}`);
    });
  });

  $('#proposeChange').addEventListener('click', () => {
    if (!state.activeFile) return alert('Select a file first.');
    if (!requirePermission('edit_repo', 'Grant repository edit permission first.')) return;
    logActivity(`Prepared a proposed change for ${state.activeFile}`);
    alert('Proposal staged locally. Live repository writes are connected in the next backend milestone.');
  });

  $('#commitChange').addEventListener('click', async () => {
    if (!state.activeFile) return alert('Select a file first.');
    if (!requirePermission('commit_repo', 'Grant commit permission first.')) return;
    $('#confirmText').textContent = `Approve one commit for ${state.activeFile} on ${$('#branchName').value}?`;
    const dialog = $('#confirmDialog');
    dialog.showModal();
    const result = await new Promise((resolve) => dialog.addEventListener('close', () => resolve(dialog.returnValue), { once: true }));
    if (result === 'confirm') {
      logActivity(`Approved one-time commit for ${state.activeFile}`);
      alert('Approval recorded. The GitHub write endpoint will execute this in the next milestone.');
    }
  });

  $('#connectGithub').addEventListener('click', () => {
    if (!requirePermission('account_profile', 'Grant account profile permission first.')) return;
    logActivity('Requested GitHub connection');
    alert('GitHub OAuth backend connection is the next milestone.');
  });
}

function initMatrix() {
  const canvas = $('#matrix');
  const ctx = canvas.getContext('2d');
  const glyphs = 'NEOGEN01<>/{}[]$#*';
  let drops = [];
  let columns = 0;

  function resize() {
    const ratio = window.devicePixelRatio || 1;
    canvas.width = innerWidth * ratio;
    canvas.height = innerHeight * ratio;
    canvas.style.width = `${innerWidth}px`;
    canvas.style.height = `${innerHeight}px`;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    columns = Math.floor(innerWidth / 18);
    drops = Array.from({ length: columns }, () => Math.random() * -50);
  }

  function draw() {
    ctx.fillStyle = 'rgba(7, 4, 12, 0.11)';
    ctx.fillRect(0, 0, innerWidth, innerHeight);
    ctx.font = '14px monospace';
    drops.forEach((drop, index) => {
      ctx.fillStyle = Math.random() > 0.92 ? '#f4df91' : '#9a4dff';
      ctx.fillText(glyphs[Math.floor(Math.random() * glyphs.length)], index * 18, drop * 18);
      drops[index] = drop * 18 > innerHeight && Math.random() > 0.975 ? 0 : drop + 0.55;
    });
    requestAnimationFrame(draw);
  }

  resize();
  addEventListener('resize', resize);
  draw();
}

function init() {
  $$('.nav-item').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
  $('#chatForm').addEventListener('submit', handleChat);
  $('#prompt').addEventListener('input', (event) => {
    event.target.style.height = 'auto';
    event.target.style.height = `${Math.min(event.target.scrollHeight, 180)}px`;
  });
  $('#newChat').addEventListener('click', () => {
    $('#messages').innerHTML = '<article class="message assistant"><div class="avatar">N</div><div><strong>NeoGen</strong><p>New session created. What should we build?</p></div></article>';
    logActivity('Started a new local chat session');
  });
  $('#modelSelect').value = state.model;
  $('#modelSelect').addEventListener('change', (event) => {
    state.model = event.target.value;
    saveState();
    logActivity(`Changed AI model to ${state.model}`);
  });
  $('#fullControl').addEventListener('change', (event) => {
    permissionDefinitions.forEach(([key]) => { state.permissions[key] = event.target.checked; });
    saveState();
    renderPermissions();
    logActivity(`${event.target.checked ? 'Enabled' : 'Disabled'} all capability toggles`);
  });
  $('#clearLog').addEventListener('click', () => {
    state.activity = [];
    saveState();
    renderActivity();
  });
  $('#accountBtn').addEventListener('click', async () => {
    try {
      if (!window.puter?.auth) throw new Error('Puter.js has not loaded.');
      const signedIn = await window.puter.auth.isSignedIn();
      if (!signedIn) await window.puter.auth.signIn();
      const user = await window.puter.auth.getUser();
      alert(`Signed in as ${user?.username || 'Puter user'}`);
      logActivity('Connected Puter account');
    } catch (error) {
      alert(error.message);
    }
  });
  renderPermissions();
  renderActivity();
  initWorkspace();
  initMatrix();
  logActivity('NeoGen interface initialized');
}

document.addEventListener('DOMContentLoaded', init);
