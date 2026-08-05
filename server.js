import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { listApprovedTasks, runApprovedTask } from './task-runner.js';
import { buildRepositoryIndex, searchRepositoryIndex } from './repository-indexer.js';
import { createAuthStore } from './auth-store.js';

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
const auth = createAuthStore(__dirname);
const githubSessions = new Map();
const clientId = process.env.GITHUB_CLIENT_ID || '';
const clientSecret = process.env.GITHUB_CLIENT_SECRET || '';
const callbackUrl = process.env.GITHUB_CALLBACK_URL || `http://127.0.0.1:${port}/api/github/callback`;
let repositoryIndex = null;
let repositoryIndexBuiltAt = 0;
let repositoryIndexPromise = null;

await auth.ensureOwner(process.env.NEOGEN_OWNER_EMAIL, process.env.NEOGEN_OWNER_PASSWORD);

const mimeTypes = { '.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.ico':'image/x-icon' };

function cookies(req) {
  return Object.fromEntries((req.headers.cookie || '').split(';').map((x) => x.trim()).filter(Boolean).map((x) => {
    const i = x.indexOf('='); return [x.slice(0, i), decodeURIComponent(x.slice(i + 1))];
  }));
}

function json(res, status, payload, headers = {}) {
  const body = JSON.stringify(payload);
  res.writeHead(status, { 'Content-Type':'application/json; charset=utf-8','Content-Length':Buffer.byteLength(body),'Cache-Control':'no-store',...headers });
  res.end(body);
}

function redirect(res, location, headers = {}) { res.writeHead(302, { Location:location,'Cache-Control':'no-store',...headers }); res.end(); }

async function body(req) {
  let raw = '';
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 2_000_000) throw new Error('Request body too large.');
  }
  return raw ? JSON.parse(raw) : {};
}

function userSession(req) { return auth.getSession(cookies(req).neogen_user); }
function requireUser(req, res) { const session = userSession(req); if (!session) json(res, 401, { error:'Sign in required.' }); return session; }
function approved(req) { return req.headers['x-neogen-approval'] === 'confirmed'; }

async function getIndex(force = false) {
  if (!force && repositoryIndex && Date.now() - repositoryIndexBuiltAt < 30000) return repositoryIndex;
  if (!repositoryIndexPromise) repositoryIndexPromise = buildRepositoryIndex(__dirname).then((index) => {
    repositoryIndex = index; repositoryIndexBuiltAt = Date.now(); return index;
  }).finally(() => { repositoryIndexPromise = null; });
  return repositoryIndexPromise;
}

async function github(token, endpoint, options = {}) {
  const response = await fetch(`https://api.github.com${endpoint}`, { ...options, headers:{ Accept:'application/vnd.github+json',Authorization:`Bearer ${token}`,'X-GitHub-Api-Version':'2022-11-28','User-Agent':'NeoGen','Content-Type':'application/json',...(options.headers || {}) } });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw Object.assign(new Error(data.message || `GitHub error ${response.status}`), { status:response.status });
  return data;
}

function parseRepo(repo) {
  const [owner, name, extra] = String(repo || '').split('/');
  if (!owner || !name || extra) throw new Error('Repository must use owner/name format.');
  return { owner, name };
}

async function api(req, res, url) {
  if (url.pathname === '/api/health') return json(res, 200, { ok:true,service:'NeoGen',version:'1.4.0',authenticated:Boolean(userSession(req)),githubConfigured:Boolean(clientId && clientSecret),approvedTasks:listApprovedTasks().map((x) => x.id),repositoryIndexReady:Boolean(repositoryIndex),timestamp:new Date().toISOString() });

  if (url.pathname === '/api/auth/register' && req.method === 'POST') {
    const data = await body(req); const user = await auth.register(data.email, data.password, 'user'); const sid = auth.createSession(user);
    return json(res, 201, { user }, { 'Set-Cookie':`neogen_user=${sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800` });
  }
  if (url.pathname === '/api/auth/login' && req.method === 'POST') {
    const data = await body(req); const user = await auth.authenticate(data.email, data.password);
    if (!user) return json(res, 401, { error:'Invalid email or password.' });
    const sid = auth.createSession(user); return json(res, 200, { user }, { 'Set-Cookie':`neogen_user=${sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800` });
  }
  if (url.pathname === '/api/auth/logout' && req.method === 'POST') {
    auth.destroySession(cookies(req).neogen_user); return json(res, 200, { ok:true }, { 'Set-Cookie':'neogen_user=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0' });
  }
  if (url.pathname === '/api/auth/me') {
    const session = userSession(req); return session ? json(res, 200, { user:session.user }) : json(res, 401, { error:'Not signed in.' });
  }

  const local = requireUser(req, res); if (!local) return;

  if (url.pathname === '/api/tasks') return json(res, 200, { tasks:listApprovedTasks() });
  if (url.pathname === '/api/tasks/run' && req.method === 'POST') {
    if (!approved(req)) return json(res, 428, { error:'Explicit approval header required.' });
    const data = await body(req); const result = await runApprovedTask(data.taskId, __dirname); return json(res, result.ok ? 200 : 422, result);
  }
  if (url.pathname === '/api/index/summary') { const index = await getIndex(url.searchParams.get('refresh') === '1'); return json(res, 200, { generatedAt:index.generatedAt,summary:index.summary }); }
  if (url.pathname === '/api/index/search') { const index = await getIndex(); return json(res, 200, { query:url.searchParams.get('q') || '',results:searchRepositoryIndex(index, url.searchParams.get('q') || '', Math.min(Number(url.searchParams.get('limit') || 50), 100)) }); }
  if (url.pathname === '/api/index/symbols') { const index = await getIndex(); const q=(url.searchParams.get('q') || '').toLowerCase(); const symbols=q?index.symbols.filter((s)=>s.name.toLowerCase().includes(q)):index.symbols; return json(res,200,{symbols:symbols.slice(0,500),total:symbols.length}); }

  if (url.pathname === '/api/github/login') {
    if (!clientId || !clientSecret) return json(res, 503, { error:'GitHub OAuth is not configured.' });
    const sid = crypto.randomUUID(), state = crypto.randomBytes(24).toString('hex'); githubSessions.set(sid,{state});
    const target = new URL('https://github.com/login/oauth/authorize'); target.searchParams.set('client_id',clientId); target.searchParams.set('redirect_uri',callbackUrl); target.searchParams.set('scope','repo read:user'); target.searchParams.set('state',state);
    return redirect(res,target.toString(),{'Set-Cookie':`neogen_github=${sid}; HttpOnly; SameSite=Lax; Path=/; Max-Age=86400`});
  }
  if (url.pathname === '/api/github/callback') {
    const session = githubSessions.get(cookies(req).neogen_github);
    if (!session || url.searchParams.get('state') !== session.state) return json(res,400,{error:'Invalid OAuth state.'});
    const response = await fetch('https://github.com/login/oauth/access_token',{method:'POST',headers:{Accept:'application/json','Content-Type':'application/json'},body:JSON.stringify({client_id:clientId,client_secret:clientSecret,code:url.searchParams.get('code'),redirect_uri:callbackUrl})});
    const data = await response.json(); if (!data.access_token) return json(res,400,{error:data.error_description || 'OAuth exchange failed.'}); session.token=data.access_token; return redirect(res,'/?github=connected');
  }
  const gh = githubSessions.get(cookies(req).neogen_github);
  if (url.pathname.startsWith('/api/github/') && !gh?.token) return json(res,401,{error:'Connect GitHub first.'});
  if (url.pathname === '/api/github/status') { const user=await github(gh.token,'/user'); return json(res,200,{connected:true,user:{login:user.login,avatar_url:user.avatar_url}}); }
  if (url.pathname === '/api/github/tree') { const {owner,name}=parseRepo(url.searchParams.get('repo')); const branch=url.searchParams.get('branch') || 'main'; const tree=await github(gh.token,`/repos/${owner}/${name}/git/trees/${encodeURIComponent(branch)}?recursive=1`); return json(res,200,{files:tree.tree.filter((x)=>x.type==='blob').map((x)=>({path:x.path,sha:x.sha,size:x.size}))}); }
  if (url.pathname === '/api/github/file') { const {owner,name}=parseRepo(url.searchParams.get('repo')); const branch=url.searchParams.get('branch') || 'main'; const filePath=url.searchParams.get('path'); const data=await github(gh.token,`/repos/${owner}/${name}/contents/${filePath.split('/').map(encodeURIComponent).join('/')}?ref=${encodeURIComponent(branch)}`); return json(res,200,{path:data.path,sha:data.sha,content:Buffer.from(data.content || '','base64').toString('utf8')}); }
  if (url.pathname === '/api/github/commit' && req.method === 'POST') { if(!approved(req)) return json(res,428,{error:'Explicit approval header required.'}); const data=await body(req); const {owner,name}=parseRepo(data.repo); const payload={message:data.message,content:Buffer.from(data.content,'utf8').toString('base64'),branch:data.branch,...(data.sha?{sha:data.sha}:{})}; const result=await github(gh.token,`/repos/${owner}/${name}/contents/${data.path.split('/').map(encodeURIComponent).join('/')}`,{method:'PUT',body:JSON.stringify(payload)}); repositoryIndex=null; return json(res,200,{ok:true,commit:result.commit,content:result.content}); }
  if (url.pathname === '/api/github/pull-request' && req.method === 'POST') { if(!approved(req)) return json(res,428,{error:'Explicit approval header required.'}); const data=await body(req); const {owner,name}=parseRepo(data.repo); const result=await github(gh.token,`/repos/${owner}/${name}/pulls`,{method:'POST',body:JSON.stringify({title:data.title,body:data.body || '',head:data.head,base:data.base || 'main',draft:data.draft !== false})}); return json(res,201,{ok:true,pullRequest:{number:result.number,html_url:result.html_url,title:result.title,draft:result.draft}}); }

  return json(res,404,{error:'API route not found.'});
}

function publicPath(urlPath) {
  const clean = decodeURIComponent(urlPath);
  const relative = clean === '/' ? '/index.html' : clean;
  const requested = path.normalize(path.join(publicDir, relative));
  return requested.startsWith(publicDir) ? requested : null;
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url || '/', `http://${req.headers.host || '127.0.0.1'}`);
    if (url.pathname.startsWith('/api/')) return await api(req,res,url);
    if (url.pathname === '/' && !userSession(req)) return redirect(res,'/login.html');
    const filePath = publicPath(url.pathname);
    if (!filePath) return json(res,403,{error:'Forbidden'});
    fs.stat(filePath,(error,stat)=>{
      if(error || !stat.isFile()) return json(res,404,{error:'Not found'});
      const type=mimeTypes[path.extname(filePath).toLowerCase()] || 'application/octet-stream';
      res.writeHead(200,{'Content-Type':type,'Cache-Control':type.startsWith('text/html')?'no-store':'public, max-age=300','X-Content-Type-Options':'nosniff','Referrer-Policy':'same-origin'});
      fs.createReadStream(filePath).pipe(res);
    });
  } catch (error) { json(res,error.status || 500,{error:error.message}); }
});

server.listen(port,'0.0.0.0',()=>console.log(`NeoGen is running at http://127.0.0.1:${port}`));
