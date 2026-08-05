import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { listApprovedTasks, runApprovedTask } from './task-runner.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const publicDir = path.join(__dirname, 'public');

function loadEnv() {
  const envPath = path.join(__dirname, '.env');
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const split = trimmed.indexOf('=');
    if (split < 1) continue;
    const key = trimmed.slice(0, split).trim();
    const value = trimmed.slice(split + 1).trim().replace(/^['"]|['"]$/g, '');
    if (!process.env[key]) process.env[key] = value;
  }
}
loadEnv();

const port = Number(process.env.PORT || 3000);
const clientId = process.env.GITHUB_CLIENT_ID || '';
const clientSecret = process.env.GITHUB_CLIENT_SECRET || '';
const callbackUrl = process.env.GITHUB_CALLBACK_URL || `http://127.0.0.1:${port}/api/github/callback`;
const sessions = new Map();

const mimeTypes = {
  '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon'
};

function sendJson(res, status, payload, headers = {}) {
  const body = JSON.stringify(payload);
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': Buffer.byteLength(body), 'Cache-Control': 'no-store', ...headers });
  res.end(body);
}

function redirect(res, location, headers = {}) {
  res.writeHead(302, { Location: location, 'Cache-Control': 'no-store', ...headers });
  res.end();
}

function getCookies(req) {
  return Object.fromEntries((req.headers.cookie || '').split(';').map((part) => part.trim()).filter(Boolean).map((part) => {
    const i = part.indexOf('=');
    return [part.slice(0, i), decodeURIComponent(part.slice(i + 1))];
  }));
}

function getSession(req) {
  const sid = getCookies(req).neogen_sid;
  return sid ? sessions.get(sid) : null;
}

function requireSession(req, res) {
  const session = getSession(req);
  if (!session?.token) sendJson(res, 401, { error: 'Connect GitHub first.' });
  return session?.token ? session : null;
}

async function readJson(req) {
  let raw = '';
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 2_000_000) throw new Error('Request body too large');
  }
  return raw ? JSON.parse(raw) : {};
}

async function github(token, endpoint, options = {}) {
  const response = await fetch(`https://api.github.com${endpoint}`, {
    ...options,
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'NeoGen',
      'Content-Type': 'application/json',
      ...(options.headers || {})
    }
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw Object.assign(new Error(data.message || `GitHub error ${response.status}`), { status: response.status, details: data });
  return data;
}

function parseRepo(repo) {
  const [owner, name, extra] = String(repo || '').split('/');
  if (!owner || !name || extra) throw new Error('Repository must use owner/name format.');
  return { owner, name };
}

function approved(req) {
  return req.headers['x-neogen-approval'] === 'confirmed';
}

async function handleApi(req, res, url) {
  if (url.pathname === '/api/health') return sendJson(res, 200, {
    ok: true,
    service: 'NeoGen',
    version: '1.2.0',
    githubConfigured: Boolean(clientId && clientSecret),
    approvedTasks: listApprovedTasks().map((task) => task.id),
    timestamp: new Date().toISOString()
  });

  if (url.pathname === '/api/tasks' && req.method === 'GET') {
    return sendJson(res, 200, { tasks: listApprovedTasks() });
  }

  if (url.pathname === '/api/tasks/run' && req.method === 'POST') {
    if (!approved(req)) return sendJson(res, 428, { error: 'Explicit approval header required.' });
    const body = await readJson(req);
    if (!body.taskId) return sendJson(res, 400, { error: 'taskId is required.' });
    const result = await runApprovedTask(body.taskId, __dirname);
    return sendJson(res, result.ok ? 200 : 422, result);
  }

  if (url.pathname === '/api/github/login') {
    if (!clientId || !clientSecret) return sendJson(res, 503, { error: 'GitHub OAuth is not configured. Add GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET to .env.' });
    const sid = crypto.randomUUID();
    const state = crypto.randomBytes(24).toString('hex');
    sessions.set(sid, { state, createdAt: Date.now() });
    const auth = new URL('https://github.com/login/oauth/authorize');
    auth.searchParams.set('client_id', clientId);
    auth.searchParams.set('redirect_uri', callbackUrl);
    auth.searchParams.set('scope', 'repo read:user');
    auth.searchParams.set('state', state);
    return redirect(res, auth.toString(), { 'Set-Cookie': `neogen_sid=${sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400` });
  }

  if (url.pathname === '/api/github/callback') {
    const session = getSession(req);
    if (!session || !url.searchParams.get('state') || url.searchParams.get('state') !== session.state) return sendJson(res, 400, { error: 'Invalid OAuth state.' });
    const code = url.searchParams.get('code');
    const response = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret, code, redirect_uri: callbackUrl })
    });
    const tokenData = await response.json();
    if (!response.ok || !tokenData.access_token) return sendJson(res, 400, { error: tokenData.error_description || 'OAuth exchange failed.' });
    session.token = tokenData.access_token;
    session.state = null;
    return redirect(res, '/?github=connected');
  }

  if (url.pathname === '/api/github/logout' && req.method === 'POST') {
    const sid = getCookies(req).neogen_sid;
    if (sid) sessions.delete(sid);
    return sendJson(res, 200, { ok: true }, { 'Set-Cookie': 'neogen_sid=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0' });
  }

  const session = requireSession(req, res);
  if (!session) return;

  if (url.pathname === '/api/github/status') {
    const user = await github(session.token, '/user');
    return sendJson(res, 200, { connected: true, user: { login: user.login, avatar_url: user.avatar_url } });
  }

  if (url.pathname === '/api/github/tree') {
    const { owner, name } = parseRepo(url.searchParams.get('repo'));
    const branch = url.searchParams.get('branch') || 'main';
    const tree = await github(session.token, `/repos/${owner}/${name}/git/trees/${encodeURIComponent(branch)}?recursive=1`);
    return sendJson(res, 200, { files: tree.tree.filter((item) => item.type === 'blob').map((item) => ({ path: item.path, sha: item.sha, size: item.size })) });
  }

  if (url.pathname === '/api/github/file') {
    const { owner, name } = parseRepo(url.searchParams.get('repo'));
    const branch = url.searchParams.get('branch') || 'main';
    const filePath = url.searchParams.get('path');
    if (!filePath) return sendJson(res, 400, { error: 'path is required.' });
    const data = await github(session.token, `/repos/${owner}/${name}/contents/${filePath.split('/').map(encodeURIComponent).join('/')}?ref=${encodeURIComponent(branch)}`);
    if (data.type !== 'file') return sendJson(res, 400, { error: 'Path is not a file.' });
    return sendJson(res, 200, { path: data.path, sha: data.sha, content: Buffer.from(data.content || '', 'base64').toString('utf8') });
  }

  if (url.pathname === '/api/github/commit' && req.method === 'POST') {
    if (!approved(req)) return sendJson(res, 428, { error: 'Explicit approval header required.' });
    const body = await readJson(req);
    const { owner, name } = parseRepo(body.repo);
    if (!body.path || !body.branch || !body.message || typeof body.content !== 'string') return sendJson(res, 400, { error: 'repo, branch, path, message, and content are required.' });
    const payload = { message: body.message, content: Buffer.from(body.content, 'utf8').toString('base64'), branch: body.branch };
    if (body.sha) payload.sha = body.sha;
    const result = await github(session.token, `/repos/${owner}/${name}/contents/${body.path.split('/').map(encodeURIComponent).join('/')}`, { method: 'PUT', body: JSON.stringify(payload) });
    return sendJson(res, 200, { ok: true, commit: result.commit, content: result.content });
  }

  if (url.pathname === '/api/github/pull-request' && req.method === 'POST') {
    if (!approved(req)) return sendJson(res, 428, { error: 'Explicit approval header required.' });
    const body = await readJson(req);
    const { owner, name } = parseRepo(body.repo);
    const result = await github(session.token, `/repos/${owner}/${name}/pulls`, { method: 'POST', body: JSON.stringify({ title: body.title, body: body.body || '', head: body.head, base: body.base || 'main', draft: body.draft !== false }) });
    return sendJson(res, 201, { ok: true, pullRequest: { number: result.number, html_url: result.html_url, title: result.title, draft: result.draft } });
  }

  return sendJson(res, 404, { error: 'API route not found.' });
}

function resolvePublicPath(urlPath) {
  const relativePath = decodeURIComponent(urlPath) === '/' ? '/index.html' : decodeURIComponent(urlPath);
  const requested = path.normalize(path.join(publicDir, relativePath));
  return requested.startsWith(publicDir) ? requested : null;
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url || '/', `http://${req.headers.host || '127.0.0.1'}`);
    if (url.pathname.startsWith('/api/')) return await handleApi(req, res, url);
    const filePath = resolvePublicPath(url.pathname);
    if (!filePath) return sendJson(res, 403, { error: 'Forbidden' });
    fs.stat(filePath, (error, stats) => {
      if (error || !stats.isFile()) return sendJson(res, 404, { error: 'Not found' });
      const type = mimeTypes[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': type, 'Cache-Control': type.startsWith('text/html') ? 'no-store' : 'public, max-age=300', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()' });
      fs.createReadStream(filePath).pipe(res);
    });
  } catch (error) {
    sendJson(res, error.status || 500, { error: error.message, details: error.details || undefined });
  }
});

server.listen(port, '0.0.0.0', () => console.log(`NeoGen is running at http://127.0.0.1:${port}`));
