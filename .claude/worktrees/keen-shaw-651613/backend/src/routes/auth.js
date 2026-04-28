const express = require('express');
const router = express.Router();
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const { randomUUID } = require('crypto');
const { getDb } = require('../db');
const { requireAuth } = require('../middleware/authMiddleware');

const JWT_SECRET = process.env.JWT_SECRET || 'closetiq_super_secret_key_2024';
const JWT_EXPIRY = '30d';

function makeToken(user) {
  return jwt.sign(
    { id: String(user.id), name: user.name, email: user.email, username: user.username },
    JWT_SECRET,
    { expiresIn: JWT_EXPIRY },
  );
}

function safeUser(user, auth) {
  return {
    id: String(user.id),
    name: user.name,
    email: user.email,
    username: auth?.username || user.username || null,
    bio: user.bio || null,
    avatar_url: user.avatar_url || null,
  };
}

// ── POST /api/auth/signup ──────────────────────────────────
router.post('/signup', async (req, res) => {
  const { name, email, username, password } = req.body;

  if (!name || !email || !username || !password)
    return res.status(400).json({ error: 'name, email, username and password are required' });

  if (password.length < 6)
    return res.status(400).json({ error: 'Password must be at least 6 characters' });

  if (!/^[a-zA-Z0-9_]{3,30}$/.test(username))
    return res.status(400).json({ error: 'Username must be 3–30 chars, letters/numbers/_ only' });

  const db = getDb();

  try {
    // Check duplicates
    if (db.prepare('SELECT id FROM users WHERE email = ?').get(email))
      return res.status(409).json({ error: 'Email already registered' });
    if (db.prepare('SELECT id FROM user_auth WHERE username = ?').get(username.toLowerCase()))
      return res.status(409).json({ error: 'Username already taken' });

    const passwordHash = await bcrypt.hash(password, 12);

    // Generate a unique TEXT id that matches the users.id column type
    const newId = randomUUID();

    const insert = db.transaction(() => {
      // Insert user with explicit id so user_auth FK can reference it
      db.prepare(
        `INSERT INTO users (id, name, email, username) VALUES (?, ?, ?, ?)`
      ).run(newId, name, email, username.toLowerCase());

      // user_auth.user_id stores the same TEXT id (SQLite stores as TEXT despite INTEGER declaration)
      db.prepare(
        `INSERT INTO user_auth (user_id, username, password_hash) VALUES (?, ?, ?)`
      ).run(newId, username.toLowerCase(), passwordHash);
    });

    insert();

    const user = db.prepare('SELECT * FROM users WHERE id = ?').get(newId);
    const auth = db.prepare('SELECT * FROM user_auth WHERE user_id = ?').get(newId);
    const token = makeToken({ ...user, username: auth.username });

    res.status(201).json({ user: safeUser(user, auth), token });
  } catch (err) {
    console.error('[Auth] Signup error:', err);
    res.status(500).json({ error: 'Signup failed', details: err.message });
  }
});

// ── POST /api/auth/login ───────────────────────────────────
router.post('/login', async (req, res) => {
  const { identifier, password } = req.body;

  if (!identifier || !password)
    return res.status(400).json({ error: 'identifier (email or username) and password are required' });

  const db = getDb();

  try {
    const isEmail = identifier.includes('@');
    let user, auth;

    if (isEmail) {
      user = db.prepare('SELECT * FROM users WHERE email = ?').get(identifier.toLowerCase());
      if (user) auth = db.prepare('SELECT * FROM user_auth WHERE user_id = ?').get(String(user.id));
    } else {
      auth = db.prepare('SELECT * FROM user_auth WHERE username = ?').get(identifier.toLowerCase());
      if (auth) user = db.prepare('SELECT * FROM users WHERE id = ?').get(String(auth.user_id));
    }

    if (!user || !auth)
      return res.status(401).json({ error: 'Invalid credentials' });

    const valid = await bcrypt.compare(password, auth.password_hash);
    if (!valid)
      return res.status(401).json({ error: 'Invalid credentials' });

    const token = makeToken({ ...user, username: auth.username });
    res.json({ user: safeUser(user, auth), token });
  } catch (err) {
    console.error('[Auth] Login error:', err);
    res.status(500).json({ error: 'Login failed' });
  }
});

// ── GET /api/auth/me ───────────────────────────────────────
router.get('/me', requireAuth, (req, res) => {
  const db = getDb();
  const userId = String(req.user.id);
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(userId);
  const auth = db.prepare('SELECT * FROM user_auth WHERE user_id = ?').get(userId);
  if (!user) return res.status(404).json({ error: 'User not found' });

  const followerCount  = db.prepare('SELECT COUNT(*) AS c FROM follows WHERE following_id = ?').get(userId)?.c ?? 0;
  const followingCount = db.prepare('SELECT COUNT(*) AS c FROM follows WHERE follower_id = ?').get(userId)?.c ?? 0;
  const itemCount      = db.prepare('SELECT COUNT(*) AS c FROM closet_items WHERE user_id = ?').get(userId)?.c ?? 0;

  res.json({
    ...safeUser(user, auth),
    follower_count: followerCount,
    following_count: followingCount,
    item_count: itemCount,
  });
});

// ── PATCH /api/auth/me (update profile) ───────────────────
router.patch('/me', requireAuth, (req, res) => {
  const db = getDb();
  const userId = String(req.user.id);
  const { name, bio, avatar_url } = req.body;

  db.prepare(`
    UPDATE users SET
      name       = COALESCE(?, name),
      bio        = COALESCE(?, bio),
      avatar_url = COALESCE(?, avatar_url),
      updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
  `).run(name || null, bio || null, avatar_url || null, userId);

  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(userId);
  const auth = db.prepare('SELECT * FROM user_auth WHERE user_id = ?').get(userId);

  const followerCount  = db.prepare('SELECT COUNT(*) AS c FROM follows WHERE following_id = ?').get(userId)?.c ?? 0;
  const followingCount = db.prepare('SELECT COUNT(*) AS c FROM follows WHERE follower_id = ?').get(userId)?.c ?? 0;
  const itemCount      = db.prepare('SELECT COUNT(*) AS c FROM closet_items WHERE user_id = ?').get(userId)?.c ?? 0;

  res.json({
    ...safeUser(user, auth),
    follower_count: followerCount,
    following_count: followingCount,
    item_count: itemCount,
  });
});

module.exports = router;
