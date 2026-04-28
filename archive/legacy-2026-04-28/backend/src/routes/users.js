const express = require('express');
const router = express.Router();
const { getDb } = require('../db');

// GET /api/users/:id
router.get('/:id', (req, res) => {
  const db = getDb();
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.params.id);
  if (!user) return res.status(404).json({ error: 'User not found' });
  res.json(user);
});

// GET /api/users  (list all — dev convenience)
router.get('/', (_req, res) => {
  const db = getDb();
  const users = db.prepare('SELECT id, name, email, style_preferences, body_type, created_at FROM users').all();
  res.json(users);
});

// POST /api/users
router.post('/', (req, res) => {
  const db = getDb();
  const { name, email, style_preferences, body_type } = req.body;
  if (!name || !email) return res.status(400).json({ error: 'name and email are required' });
  try {
    const result = db.prepare(
      'INSERT INTO users (name, email, style_preferences, body_type) VALUES (?, ?, ?, ?)'
    ).run(name, email, style_preferences || null, body_type || null);
    const user = db.prepare('SELECT * FROM users WHERE id = ?').get(result.lastInsertRowid);
    res.status(201).json(user);
  } catch (err) {
    if (err.message.includes('UNIQUE')) return res.status(409).json({ error: 'Email already exists' });
    throw err;
  }
});

// PATCH /api/users/:id
router.patch('/:id', (req, res) => {
  const db = getDb();
  const { name, style_preferences, body_type } = req.body;
  db.prepare(
    'UPDATE users SET name = COALESCE(?, name), style_preferences = COALESCE(?, style_preferences), body_type = COALESCE(?, body_type), updated_at = CURRENT_TIMESTAMP WHERE id = ?'
  ).run(name, style_preferences, body_type, req.params.id);
  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(req.params.id);
  if (!user) return res.status(404).json({ error: 'User not found' });
  res.json(user);
});

module.exports = router;
