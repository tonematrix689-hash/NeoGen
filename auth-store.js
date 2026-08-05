import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

const sessions = new Map();

function normalizeEmail(email) {
  return String(email || '').trim().toLowerCase();
}

function validEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function hashPassword(password, salt = crypto.randomBytes(16).toString('hex')) {
  const derived = crypto.scryptSync(password, salt, 64).toString('hex');
  return { salt, hash: derived };
}

export function createAuthStore(root) {
  const file = path.join(root, 'data', 'users.json');

  async function readUsers() {
    try {
      return JSON.parse(await fs.readFile(file, 'utf8'));
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      return [];
    }
  }

  async function writeUsers(users) {
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, JSON.stringify(users, null, 2), { mode: 0o600 });
  }

  async function register(email, password) {
    email = normalizeEmail(email);
    if (!validEmail(email)) throw new Error('Enter a valid email address.');
    if (String(password || '').length < 10) throw new Error('Password must be at least 10 characters.');
    const users = await readUsers();
    if (users.some((user) => user.email === email)) throw new Error('An account with this email already exists.');
    const credential = hashPassword(password);
    const user = { id: crypto.randomUUID(), email, ...credential, createdAt: new Date().toISOString() };
    users.push(user);
    await writeUsers(users);
    return { id: user.id, email: user.email };
  }

  async function authenticate(email, password) {
    email = normalizeEmail(email);
    const users = await readUsers();
    const user = users.find((item) => item.email === email);
    if (!user) return null;
    const candidate = Buffer.from(hashPassword(password, user.salt).hash, 'hex');
    const expected = Buffer.from(user.hash, 'hex');
    if (candidate.length !== expected.length || !crypto.timingSafeEqual(candidate, expected)) return null;
    return { id: user.id, email: user.email };
  }

  function createSession(user) {
    const id = crypto.randomUUID();
    sessions.set(id, { user, createdAt: Date.now() });
    return id;
  }

  function getSession(id) {
    return id ? sessions.get(id) || null : null;
  }

  function destroySession(id) {
    if (id) sessions.delete(id);
  }

  return { register, authenticate, createSession, getSession, destroySession };
}
