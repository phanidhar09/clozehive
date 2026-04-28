// Load local backend .env; root .env vars are already in process.env via dotenv-cli
require('dotenv').config({ path: require('path').join(__dirname, '../../.env') });
require('dotenv').config(); // backend/.env (doesn't overwrite already-set vars)

const express = require('express');
const cors = require('cors');
const path = require('path');
const rateLimit = require('express-rate-limit');

const { getDb } = require('./db');
const itemsRouter = require('./routes/items');
const aiRouter = require('./routes/ai');
const usersRouter = require('./routes/users');
const travelRouter = require('./routes/travel');
const authRouter = require('./routes/auth');
const socialRouter = require('./routes/social');
const groupsRouter = require('./routes/groups');

const app = express();
// Priority: BACKEND_PORT (root .env) → PORT → 3002
const PORT = process.env.BACKEND_PORT || process.env.PORT || 3002;

// ── Middleware ─────────────────────────────────────────────
app.use(cors({ origin: process.env.FRONTEND_URL || '*', credentials: true }));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

// Serve uploaded images statically
app.use('/uploads', express.static(path.join(__dirname, '../uploads')));

// Rate limit AI endpoints
const aiLimiter = rateLimit({ windowMs: 60_000, max: 30, message: { error: 'Too many AI requests' } });

// ── Routes ─────────────────────────────────────────────────
app.use('/api/auth', authRouter);
app.use('/api/social', socialRouter);
app.use('/api/groups', groupsRouter);
app.use('/api/users', usersRouter);
app.use('/api/items', itemsRouter);
app.use('/api/ai', aiLimiter, aiRouter);
app.use('/api/travel', travelRouter);

// Health check
app.get('/health', (_req, res) => {
  const db = getDb();
  const row = db.prepare('SELECT COUNT(*) AS count FROM closet_items').get();
  res.json({ status: 'ok', closet_items: row.count, timestamp: new Date().toISOString() });
});

// ── Boot ───────────────────────────────────────────────────
getDb(); // initialise schema on startup
app.listen(PORT, () => {
  console.log(`ClozéHive backend → http://localhost:${PORT}`);
  console.log(`AI service          → ${process.env.AI_SERVICE_URL}`);
});

module.exports = app;
