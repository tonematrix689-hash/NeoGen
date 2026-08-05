const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  permissions: JSON.parse(localStorage.getItem('neogen.permissions') || '{}'),
  activity: JSON.parse(localStorage.getItem('neogen.activity') || '[]'),
  model: localStorage.getItem('neogen.model') || 'gpt-5-nano',
  activeFile: null,
  activeSha: null,
  treeCache: new Map(),
  fileCache: new Map()
};

const permissionDefinitions = [
  ['read_repo', 'Read repository', 'View files and branches.'],
  ['edit_repo', 'Edit repository', 'Prepare changes in the editor.'],
  ['commit_repo', 'Commit changes', 'Create commits after explicit confirmation.'],
  ['open_pr', 'Open pull requests', 'Create draft pull requests after confirmation.'],
  ['run_tasks', 'Run development tasks', 'Reserved for approved local validation tasks.'],
  ['deploy', 'Deploy applications', 'Reserved for confirmed deployment workflows.'],
  ['account_profile', 'Read account profile', 'Read the connected GitHub username.'],
  ['notifications', 'Send notifications', 'Display local status messages.'],
  ['web_access', 'Use web access', 'Allow external research workflows.'],
  ['memory', 'Use project memory', 'Remember local project preferences.']
];

function saveState() {
  localStorage.setItem('neogen.permissions', JSON.stringify(state.permissions));
  localStorage.setItem('neogen.activity', JSON.stringify(state.activity.slice(0, 100)));
  localStorage.setItem('neogen.model', state.model);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function logActivity(message) {
  state.activity.unshift({ message, time: new Date().toISOString() });
  saveState();
  renderActivity();
}

function renderActivity() {
  const container = $('#activityLog');
  container.innerHTML = state.activity.length
    ? state.activity.map((entry) => `<div class="activity-entry"><strong>${escapeHtml(entry.message)}</strong><br><small>${new Date(entry.time).toLocaleString()}</small></div>`).join('')
    : '<div class="activity-entry"><strong>No activity yet.</strong></div>';
}

function renderPermissions() {
  $('#permissionGrid').innerHTML = permissionDefinitions.map(([key, title, description]) => `
    <div class="permission-item">
      <div><strong>${title}</strong><p>${description}</p></div>
      <label class="switch"><input type="checkbox" data-permission="${key}" ${state.permissions[key] ? 'checked' : ''}><span></span></label>
    </div>`).join('');

  $$('[data-permission]').forEach((input) => input.addEventListener('change', () => {
    state.permissions[input.dataset.permission] = input.checked;
    $('#fullControl').checked = permissionDefinitions.every(([key]) => state.permissions[key]);
    saveState();
    logActivity(`${input.checked ? 'Granted' : 'Revoked'} ${input.dataset.permission}`);
  }));

  $('#fullControl').checked = permissionDefinitions.every(([key]) => state.permissions[key]);
}

function setView(name) {
  $$('.nav-item').forEach((button) => button.classList.toggle('active', button.dataset.view === name));
  $$('.view').forEach((view) => view.classList.remove('active'));
  $(`#${name}View`).classList.add('active');
  $('#viewTitle').textContent = {
    chat: 'Intelligence Console',
    workspace: 'Repository Workspace',
    permissions: 'Permission Control',
    activity: 'Audit Trail'
  }[name];
}

function requirePermission(key, message) {
  if (state.permissions[key]) return true;
  alert(message);
  setView('permissions');
  return false;
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, {
      credentials: 'same-origin',
      signal: controller.signal,
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    return data;
  } finally {
    clearTimeout(timeout);
  }
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

function normalizeAiResponse(response) {
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

  const waiting = document.createElement('article');
  waiting.className = 'message assistant';
  waiting.innerHTML = '<div class="avatar">N</div><div><strong>NeoGen</strong><p>Processing through Puter.js…</p></div>';
  $('#messages').appendChild(waiting);

  try {
    if (!window.puter?.ai?.chat) throw new Error('Puter.js is unavailable.');
    const response = await window.puter.ai.chat(prompt, { model: state.model });
    waiting.querySelector('p').textContent = normalizeAiResponse(response);
    logActivity(`Completed AI request with ${state.model}`);
  } catch (error) {
    waiting.querySelector('p').textContent = `Request failed: ${error.message}`;
    logActivity(`AI request failed: ${error.message}`);
  }
}

function repositoryContext() {
  return {
    repo: $('#repoName').value.trim(),
    branch: $('#branchName').value.trim()
  };
}

async function loadRepositoryTree(force = false) {
  if (!requirePermission('read_repo', 'Grant repository read permission first.')) return;
  const { repo, branch } = repositoryContext();
  const key = `${repo}@${branch}`;
  const tree = $('#fileTree');
  tree.innerHTML = '<button disabled>Loading repository…</button>';

  try {
    let files = state.treeCache.get(key);
    if (!files || force) {
      const data = await api(`/api/github/tree?repo=${encodeURIComponent(repo)}&branch=${encodeURIComponent(branch)}`);
      files = data.files;
      state.treeCache.set(key, files);
    }
    tree.innerHTML = files.slice(0, 500).map((file) => `<button data-file="${escapeHtml(file.path)}">◇ ${escapeHtml(file.path)}</button>`).join('');
    $$('#fileTree [data-file]').forEach((button) => button.addEventListener('click', () => openFile(button.dataset.file)));
    logActivity(`Loaded ${files.length} files from ${key}`);
  } catch (error) {
    tree.innerHTML = `<button disabled>${escapeHtml(error.message)}</button>`;
    logActivity(`Repository load failed: ${error.message}`);
  }
}

async function openFile(filePath) {
  if (!requirePermission('read_repo', 'Grant repository read permission first.')) return;
  const { repo, branch } = repositoryContext();
  const key = `${repo}@${branch}:${filePath}`;
  $('#activeFile').textContent = `Loading ${filePath}…`;

  try {
    let data = state.fileCache.get(key);
    if (!data) {
      data = await api(`/api/github/file?repo=${encodeURIComponent(repo)}&branch=${encodeURIComponent(branch)}&path=${encodeURIComponent(filePath)}`);
      state.fileCache.set(key, data);
    }
    state.activeFile = data.path;
    state.activeSha = data.sha;
    $('#activeFile').textContent = data.path;
    $('#editor').value = data.content;
    logActivity(`Opened ${data.path}`);
  } catch (error) {
    alert(error.message);
    logActivity(`File open failed: ${error.message}`);
  }
}

async function analyzeOrEditFile() {
  if (!state.activeFile) return alert('Select a file first.');
  if (!requirePermission('edit_repo', 'Grant repository edit permission first.')) return;
  const instruction = prompt('Describe the analysis or requested change:');
  if (!instruction) return;

  const button = $('#proposeChange');
  button.disabled = true;
  button.textContent = 'Analyzing…';
  try {
    if (!window.puter?.ai?.chat) throw new Error('Puter.js is unavailable.');
    const request = `You are reviewing ${state.activeFile}. ${instruction}\n\nReturn only the complete revised file if a code change is requested. Otherwise return concise findings.\n\nCURRENT FILE:\n${$('#editor').value}`;
    const result = normalizeAiResponse(await window.puter.ai.chat(request, { model: state.model }));
    const cleaned = result.replace(/^```[\w-]*\n?/, '').replace(/\n?```$/, '');
    if (instruction.toLowerCase().includes('analy') || instruction.toLowerCase().includes('review')) {
      appendMessage('assistant', result);
      setView('chat');
    } else {
      $('#editor').value = cleaned;
    }
    logActivity(`AI processed ${state.activeFile}`);
  } catch (error) {
    alert(error.message);
    logActivity(`AI file operation failed: ${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = 'Propose change';
  }
}

async function confirmSensitive(text) {
  $('#confirmText').textContent = text;
  const dialog = $('#confirmDialog');
  dialog.showModal();
  return new Promise((resolve) => dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true }));
}

async function commitActiveFile() {
  if (!state.activeFile) return alert('Select a file first.');
  if (!requirePermission('commit_repo', 'Grant commit permission first.')) return;
  const { repo, branch } = repositoryContext();
  const message = prompt('Commit message:', `Update ${state.activeFile}`);
  if (!message) return;
  if (!await confirmSensitive(`Approve one commit for ${state.activeFile} on ${repo}@${branch}?`)) return;

  try {
    const result = await api('/api/github/commit', {
      method: 'POST',
      headers: { 'X-NeoGen-Approval': 'confirmed' },
      body: JSON.stringify({ repo, branch, path: state.activeFile, sha: state.activeSha, message, content: $('#editor').value })
    });
    state.activeSha = result.content?.sha || state.activeSha;
    state.fileCache.delete(`${repo}@${branch}:${state.activeFile}`);
    state.treeCache.delete(`${repo}@${branch}`);
    logActivity(`Committed ${state.activeFile}`);
    alert('Commit completed successfully.');
  } catch (error) {
    alert(error.message);
    logActivity(`Commit failed: ${error.message}`);
  }
}

async function checkGithubStatus() {
  try {
    const data = await api('/api/github/status');
    $('#connectGithub').textContent = `Connected: ${data.user.login}`;
    if (state.permissions.read_repo) await loadRepositoryTree();
  } catch {
    $('#connectGithub').textContent = 'Connect GitHub';
  }
}

function initMatrix() {
  const canvas = $('#matrix');
  const ctx = canvas.getContext('2d');
  const glyphs = 'NEOGEN01<>/{}[]$#*';
  let drops = [];

  function resize() {
    const ratio = window.devicePixelRatio || 1;
    canvas.width = innerWidth * ratio;
    canvas.height = innerHeight * ratio;
    canvas.style.width = `${innerWidth}px`;
    canvas.style.height = `${innerHeight}px`;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    drops = Array.from({ length: Math.floor(innerWidth / 18) }, () => Math.random() * -50);
  }

  function draw() {
    ctx.fillStyle = 'rgba(7,4,12,.11)';
    ctx.fillRect(0, 0, innerWidth, innerHeight);
    ctx.font = '14px monospace';
    drops.forEach((drop, index) => {
      ctx.fillStyle = Math.random() > .92 ? '#f4df91' : '#9a4dff';
      ctx.fillText(glyphs[Math.floor(Math.random() * glyphs.length)], index * 18, drop * 18);
      drops[index] = drop * 18 > innerHeight && Math.random() > .975 ? 0 : drop + .55;
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
  $('#newChat').addEventListener('click', () => {
    $('#messages').innerHTML = '<article class="message assistant"><div class="avatar">N</div><div><strong>NeoGen</strong><p>New session created.</p></div></article>';
  });
  $('#modelSelect').value = state.model;
  $('#modelSelect').addEventListener('change', (event) => {
    state.model = event.target.value;
    saveState();
  });
  $('#fullControl').addEventListener('change', (event) => {
    permissionDefinitions.forEach(([key]) => { state.permissions[key] = event.target.checked; });
    saveState();
    renderPermissions();
  });
  $('#clearLog').addEventListener('click', () => {
    state.activity = [];
    saveState();
    renderActivity();
  });
  $('#connectGithub').addEventListener('click', () => {
    if (requirePermission('account_profile', 'Grant account profile permission first.')) location.href = '/api/github/login';
  });
  $('#repoName').addEventListener('change', () => loadRepositoryTree(true));
  $('#branchName').addEventListener('change', () => loadRepositoryTree(true));
  $('#proposeChange').addEventListener('click', analyzeOrEditFile);
  $('#commitChange').addEventListener('click', commitActiveFile);
  $('#accountBtn').addEventListener('click', async () => {
    try {
      if (!window.puter?.auth) throw new Error('Puter.js is unavailable.');
      if (!await window.puter.auth.isSignedIn()) await window.puter.auth.signIn();
      const user = await window.puter.auth.getUser();
      alert(`Signed in as ${user?.username || 'Puter user'}`);
    } catch (error) {
      alert(error.message);
    }
  });

  renderPermissions();
  renderActivity();
  initMatrix();
  checkGithubStatus();
  if (new URLSearchParams(location.search).get('github') === 'connected') {
    history.replaceState({}, '', location.pathname);
    setView('workspace');
  }
  logActivity('NeoGen interface initialized');
}

document.addEventListener('DOMContentLoaded', init);
