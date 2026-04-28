const express = require('express');
const router = express.Router();
const path = require('path');
const fs = require('fs');
const axios = require('axios');
const { v4: uuidv4 } = require('uuid');
const { getDb } = require('../db');
const upload = require('../middleware/upload');

const AI_SERVICE_PORT = process.env.AI_SERVICE_PORT || 8000;
const AI_SERVICE_URL  = process.env.AI_SERVICE_URL  || `http://localhost:${AI_SERVICE_PORT}`;
const AI_TIMEOUT = parseInt(process.env.AI_TIMEOUT_MS || '12000');

// ── Helpers ────────────────────────────────────────────────
function buildImageUrl(req, filename) {
  return filename ? `${req.protocol}://${req.get('host')}/uploads/${path.basename(filename)}` : null;
}

// ── GET /api/items  (all closet items for user) ────────────
router.get('/', (req, res) => {
  const db = getDb();
  const userId = req.query.user_id || 1;
  const category = req.query.category;
  let stmt = 'SELECT * FROM closet_items WHERE user_id = ?';
  const params = [userId];
  if (category) { stmt += ' AND category = ?'; params.push(category); }
  stmt += ' ORDER BY created_at DESC';
  const items = db.prepare(stmt).all(...params);
  res.json(items.map(i => ({ ...i, tags: i.tags ? JSON.parse(i.tags) : [], occasion: i.occasion ? JSON.parse(i.occasion) : [] })));
});

// ── GET /api/items/:id ─────────────────────────────────────
router.get('/:id', (req, res) => {
  const db = getDb();
  const item = db.prepare('SELECT * FROM closet_items WHERE id = ?').get(req.params.id);
  if (!item) return res.status(404).json({ error: 'Item not found' });
  res.json({ ...item, tags: item.tags ? JSON.parse(item.tags) : [], occasion: item.occasion ? JSON.parse(item.occasion) : [] });
});

// ── POST /api/items/upload  (vision AI + create item) ──────
router.post('/upload', upload.single('image'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'Image file is required' });

  const imageUrl = buildImageUrl(req, req.file.filename);
  const imageLocalPath = req.file.path;
  let vision = {};

  // Call AI service for vision analysis
  if (process.env.AI_SERVICE_ENABLED === 'true') {
    try {
      const formData = new (require('form-data'))();
      formData.append('image', fs.createReadStream(imageLocalPath), req.file.originalname);
      const response = await axios.post(`${AI_SERVICE_URL}/api/vision/analyze`, formData, {
        headers: formData.getHeaders(),
        timeout: AI_TIMEOUT,
      });
      vision = response.data;
    } catch (err) {
      console.warn('Vision AI unavailable, proceeding without analysis:', err.message);
    }
  }

  // Merge manual body fields over AI vision results
  const body = req.body;
  const now = new Date().toISOString();
  const item = {
    id: uuidv4(),
    user_id: body.user_id !== undefined && body.user_id !== null && body.user_id !== '' ? String(body.user_id) : '1',
    name: body.name || vision.garment_type || 'Clothing Item',
    category: body.category || vision.garment_type || 'tops',
    color: body.color || vision.color_primary || null,
    fabric: body.fabric || vision.fabric || null,
    pattern: body.pattern || vision.pattern || null,
    season: body.season || vision.season || null,
    occasion: JSON.stringify(body.occasion ? (Array.isArray(body.occasion) ? body.occasion : [body.occasion]) : (vision.occasion || [])),
    eco_score: vision.eco_score || null,
    tags: JSON.stringify(body.tags ? (Array.isArray(body.tags) ? body.tags : [body.tags]) : []),
    image_url: imageUrl,
    notes: body.notes || (vision.care_instructions ? vision.care_instructions.join('; ') : null),
    brand: body.brand || null,
    size: body.size || null,
    price: body.price ? parseFloat(body.price) : null,
  };

  const db = getDb();
  db.prepare(`
    INSERT INTO closet_items (id, user_id, name, category, color, fabric, pattern, season, occasion, eco_score, tags, image_url, notes, brand, size, price, created_at, updated_at)
    VALUES (@id, @user_id, @name, @category, @color, @fabric, @pattern, @season, @occasion, @eco_score, @tags, @image_url, @notes, @brand, @size, @price, '${now}', '${now}')
  `).run(item);

  res.status(201).json({
    item,
    vision_analysis: vision,
    message: Object.keys(vision).length ? 'Item created with AI vision analysis' : 'Item created (vision AI unavailable)',
  });
});

// ── POST /api/items  (create without image) ────────────────
router.post('/', (req, res) => {
  const db = getDb();
  const body = req.body;
  const now = new Date().toISOString();
  const item = {
    id: uuidv4(),
    user_id: body.user_id !== undefined && body.user_id !== null && body.user_id !== '' ? String(body.user_id) : '1',
    name: body.name || 'Clothing Item',
    category: body.category || 'tops',
    color: body.color || null,
    fabric: body.fabric || null,
    pattern: body.pattern || null,
    season: body.season || null,
    occasion: JSON.stringify(Array.isArray(body.occasion) ? body.occasion : (body.occasion ? [body.occasion] : [])),
    eco_score: body.eco_score || null,
    tags: JSON.stringify(Array.isArray(body.tags) ? body.tags : (body.tags ? [body.tags] : [])),
    image_url: body.image_url || null,
    notes: body.notes || null,
    brand: body.brand || null,
    size: body.size || null,
    price: body.price ? parseFloat(body.price) : null,
  };
  db.prepare(`
    INSERT INTO closet_items (id, user_id, name, category, color, fabric, pattern, season, occasion, eco_score, tags, image_url, notes, brand, size, price, created_at, updated_at)
    VALUES (@id, @user_id, @name, @category, @color, @fabric, @pattern, @season, @occasion, @eco_score, @tags, @image_url, @notes, @brand, @size, @price, '${now}', '${now}')
  `).run(item);
  res.status(201).json(item);
});

// ── PATCH /api/items/:id ───────────────────────────────────
router.patch('/:id', (req, res) => {
  const db = getDb();
  const existing = db.prepare('SELECT * FROM closet_items WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: 'Item not found' });
  const body = req.body;
  db.prepare(`
    UPDATE closet_items SET
      name = COALESCE(?, name), category = COALESCE(?, category), color = COALESCE(?, color),
      fabric = COALESCE(?, fabric), pattern = COALESCE(?, pattern), season = COALESCE(?, season),
      brand = COALESCE(?, brand), size = COALESCE(?, size), notes = COALESCE(?, notes),
      updated_at = CURRENT_TIMESTAMP
    WHERE id = ?
  `).run(body.name, body.category, body.color, body.fabric, body.pattern, body.season, body.brand, body.size, body.notes, req.params.id);
  const updated = db.prepare('SELECT * FROM closet_items WHERE id = ?').get(req.params.id);
  res.json(updated);
});

// ── DELETE /api/items/:id ──────────────────────────────────
router.delete('/:id', (req, res) => {
  const db = getDb();
  const item = db.prepare('SELECT * FROM closet_items WHERE id = ?').get(req.params.id);
  if (!item) return res.status(404).json({ error: 'Item not found' });
  // Remove uploaded image file if exists
  if (item.image_url) {
    const localPath = path.join(__dirname, '../../uploads', path.basename(item.image_url));
    if (fs.existsSync(localPath)) fs.unlinkSync(localPath);
  }
  db.prepare('DELETE FROM closet_items WHERE id = ?').run(req.params.id);
  res.json({ message: 'Item deleted', id: req.params.id });
});

module.exports = router;
