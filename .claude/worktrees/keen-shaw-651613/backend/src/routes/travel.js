const express = require('express');
const router = express.Router();
const { v4: uuidv4 } = require('uuid');
const { getDb } = require('../db');

// ── GET /api/travel ────────────────────────────────────────
router.get('/', (req, res) => {
  const db = getDb();
  const userId = String(req.query.user_id ?? '1');
  const plans = db.prepare('SELECT * FROM travel_plans WHERE user_id = ? ORDER BY start_date DESC').all(userId);
  res.json(plans);
});

// ── GET /api/travel/:id ────────────────────────────────────
router.get('/:id', (req, res) => {
  const db = getDb();
  const plan = db.prepare('SELECT * FROM travel_plans WHERE id = ?').get(req.params.id);
  if (!plan) return res.status(404).json({ error: 'Travel plan not found' });
  res.json(plan);
});

// ── POST /api/travel ───────────────────────────────────────
router.post('/', (req, res) => {
  const db = getDb();
  const { user_id = '1', destination, start_date, end_date, purpose, notes } = req.body;
  if (!destination || !start_date || !end_date) {
    return res.status(400).json({ error: 'destination, start_date and end_date are required' });
  }
  const plan = {
    id: uuidv4(),
    user_id: String(user_id),
    destination,
    start_date,
    end_date,
    purpose: purpose || 'leisure',
    notes: notes || null,
    status: 'planned',
  };
  db.prepare(`
    INSERT INTO travel_plans (id, user_id, destination, start_date, end_date, purpose, notes, status, created_at, updated_at)
    VALUES (@id, @user_id, @destination, @start_date, @end_date, @purpose, @notes, @status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
  `).run(plan);
  res.status(201).json(plan);
});

// ── PATCH /api/travel/:id ──────────────────────────────────
router.patch('/:id', (req, res) => {
  const db = getDb();
  const { destination, start_date, end_date, purpose, notes, status, packing_list_id } = req.body;
  db.prepare(`
    UPDATE travel_plans SET
      destination = COALESCE(?, destination),
      start_date = COALESCE(?, start_date),
      end_date = COALESCE(?, end_date),
      purpose = COALESCE(?, purpose),
      notes = COALESCE(?, notes),
      status = COALESCE(?, status),
      packing_list_id = COALESCE(?, packing_list_id),
      updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
  `).run(destination, start_date, end_date, purpose, notes, status, packing_list_id, req.params.id);
  const plan = db.prepare('SELECT * FROM travel_plans WHERE id = ?').get(req.params.id);
  if (!plan) return res.status(404).json({ error: 'Travel plan not found' });
  res.json(plan);
});

// ── DELETE /api/travel/:id ─────────────────────────────────
router.delete('/:id', (req, res) => {
  const db = getDb();
  const result = db.prepare('DELETE FROM travel_plans WHERE id = ?').run(req.params.id);
  if (!result.changes) return res.status(404).json({ error: 'Travel plan not found' });
  res.json({ message: 'Travel plan deleted', id: req.params.id });
});

module.exports = router;
