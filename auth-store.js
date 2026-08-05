import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

const sessions = new Map();
const SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000;

function normalizeEmail(email) {
  return String(email || '').trim().toLowerCase();
}

function validEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function hashPassword(password, salt = crypto.randomBytes(16).toString('hex')) {
  return { salt, hash: crypto.scryptSync(password, salt, 64).toString('hex') };
}

function publicUser(user) {
  return { id: user.id, email: user.email, role: user.role || 'user', createdAt: user.createdAt };
}

export function createAuthStore(root) {
  const file = path.join(root, 'data', 'users.json');

  async function readUsers() {
    try {
      const parsed = JSON.parse(await fs.readFile(file, 'utf8'));
      return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      return [];
    }
  }

  async function writeUsers(users) {
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, JSON.stringify(users, null, 2), { mode: 0o600 });
  }

  async function register(email, password, role = 'user') {
    email = normalizeEmail(email);
    if (!validEmail(email)) throw new Error('Enter a valid email address.');
    if (String(password || '').length < 10) throw new Error('Password must be at least 10 characters.');
    const users = await readUsers();
    if (users.some((user) => user.email === email)) throw new Error('An account with this email already exists.');
    const credential = hashPassword(password);
    const user = { id: crypto.randomUUID(), email, role, ...credential, createdAt: new Date().toISOString() };
    users.push(user);
    await writeUsers(users);
    return publicUser(user);
  }

  async function ensureOwner(email, password) {
    email = normalizeEmail(email);
    if (!email || !password) return null;
    const users = await readUsers();
    const existing = users.find((user) => user.email === email);
    if (existing) {
      if (existing.role !== 'owner') {
        existing.role = 'owner';
        await writeUsers(users);
      }
      return publicUser(existing);
    }
    return register(email, password, 'owner');
  }

  async function authenticate(email, password) {
    email = normalizeEmail(email);
    const users = await readUsers();
    const user = users.find((item) => item.email === email);
    if (!user) return null;
    const candidate = Buffer.from(hashPassword(password, user.salt).hash, 'hex');
    const expected = Buffer.from(user.hash, 'hex');
    if (candidate.length !== expected.length || !crypto.timingSafeEqual(candidate, expected)) return null;
    return publicUser(user);
  }

  function createSession(user) {
    const id = crypto.randomBytes(32).toString('hex');
    sessions.set(id, { user, createdAt: Date.now(), expiresAt: Date.now() + SESSION_TTL_MS });
    return id;
  }

  function getSession(id) {
    if (!id) return null;
    const session = sessions.get(id);
    if (!session) return null;
    if (Date.now() > session.expiresAt) {
      sessions.delete(id);
      return null;
    }
    return session;
  }

  function destroySession(id) {
    if (id) sessions.delete(id);
  }

  return { register, ensureOwner, authenticate, createSession, getSession, destroySession };
}
