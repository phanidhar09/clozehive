const express = require('express');
const router = express.Router();
const axios = require('axios');
const { v4: uuidv4 } = require('uuid');
const { getDb } = require('../db');

const AI_SERVICE_PORT = process.env.AI_SERVICE_PORT || 8000;
const AI_SERVICE_URL  = process.env.AI_SERVICE_URL  || `http://localhost:${AI_SERVICE_PORT}`;
const AI_TIMEOUT = parseInt(process.env.AI_TIMEOUT_MS || '12000');

async function callAI(endpoint, payload) {
  const response = await axios.post(`${AI_SERVICE_URL}${endpoint}`, payload, { timeout: AI_TIMEOUT });
  return response.data;
}

// ── POST /api/ai/generate-outfit ───────────────────────────
// Body: { user_id, occasion, weather, temperature }
router.post('/generate-outfit', async (req, res) => {
  const db = getDb();
  const { user_id = 1, occasion, weather, temperature } = req.body;
  const uid = String(user_id);

  const closetItems = db.prepare('SELECT * FROM closet_items WHERE user_id = ?').all(uid);
  if (!closetItems.length) return res.status(400).json({ error: 'No items in closet' });

  const payload = {
    closet_items: closetItems.map(i => ({
      ...i,
      tags: i.tags ? JSON.parse(i.tags) : [],
      occasion: i.occasion ? JSON.parse(i.occasion) : [],
    })),
    occasion: occasion || 'casual',
    weather: weather || 'sunny',
    temperature: temperature || 22,
  };

  try {
    const result = await callAI('/api/outfit/generate', payload);
    // Best-effort persist generated outfits
    for (const outfit of (result.outfits || [])) {
      try {
        db.prepare(`
          INSERT INTO outfits (id, user_id, name, item_ids, occasion, weather_condition, temperature, ai_explanation, style_score, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        `).run(uuidv4(), uid, outfit.name || 'AI Outfit', JSON.stringify(outfit.item_ids || []), occasion, weather, temperature, outfit.explanation, outfit.style_score || null);
      } catch (dbErr) {
        console.warn('Outfit persist failed (non-fatal):', dbErr.message);
      }
    }
    res.json(result);
  } catch (err) {
    console.error('Outfit generation error:', err.message);
    res.status(502).json({ error: 'AI service unavailable', details: err.message });
  }
});

// ── POST /api/ai/generate-packing-list ────────────────────
// Body: { user_id, destination, start_date, end_date, purpose }
router.post('/generate-packing-list', async (req, res) => {
  const db = getDb();
  const { user_id = 1, destination, start_date, end_date, purpose = 'leisure' } = req.body;
  const uid = String(user_id);

  if (!destination || !start_date || !end_date) {
    return res.status(400).json({ error: 'destination, start_date, end_date are required' });
  }

  const closetItems = db.prepare('SELECT * FROM closet_items WHERE user_id = ?').all(uid);
  const payload = {
    destination,
    start_date,
    end_date,
    purpose,
    closet_items: closetItems.map(i => ({
      ...i,
      tags: i.tags ? JSON.parse(i.tags) : [],
      occasion: i.occasion ? JSON.parse(i.occasion) : [],
    })),
  };

  try {
    const result = await callAI('/api/packing/generate', payload);

    // Best-effort persist packing list
    try {
      const id = uuidv4();
      const start = new Date(start_date);
      const end = new Date(end_date);
      const durationDays = Math.max(1, Math.round((end - start) / 86400000));
      db.prepare(`
        INSERT INTO packing_lists (id, user_id, destination, start_date, end_date, duration_days, trip_type, purpose, item_ids, generated_list, missing_items, daily_plan, alerts, weather_summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
      `).run(
        id, uid, destination, start_date, end_date, durationDays,
        result.trip_type || purpose, purpose,
        JSON.stringify(result.packing_item_ids || []),
        JSON.stringify(result.packing_list || []),
        JSON.stringify(result.missing_items || []),
        JSON.stringify(result.daily_plan || []),
        JSON.stringify(result.alerts || []),
        JSON.stringify(result.weather_summary || {}),
      );
      res.json({ ...result, packing_list_id: id });
    } catch (dbErr) {
      console.warn('Packing list persist failed (non-fatal):', dbErr.message);
      res.json(result);
    }
  } catch (err) {
    console.error('Packing list error:', err.message);
    res.status(502).json({ error: 'AI service unavailable', details: err.message });
  }
});

// ── GET /api/ai/packing-lists ──────────────────────────────
router.get('/packing-lists', (req, res) => {
  const db = getDb();
  const userId = req.query.user_id || 1;
  const lists = db.prepare('SELECT * FROM packing_lists WHERE user_id = ? ORDER BY created_at DESC').all(userId);
  res.json(lists.map(l => ({
    ...l,
    generated_list: l.generated_list ? JSON.parse(l.generated_list) : [],
    missing_items: l.missing_items ? JSON.parse(l.missing_items) : [],
    daily_plan: l.daily_plan ? JSON.parse(l.daily_plan) : [],
    alerts: l.alerts ? JSON.parse(l.alerts) : [],
    weather_summary: l.weather_summary ? JSON.parse(l.weather_summary) : {},
  })));
});

// ── GET /api/ai/outfits ────────────────────────────────────
router.get('/outfits', (req, res) => {
  const db = getDb();
  const userId = req.query.user_id || 1;
  const outfits = db.prepare('SELECT * FROM outfits WHERE user_id = ? ORDER BY created_at DESC LIMIT 50').all(userId);
  res.json(outfits.map(o => ({ ...o, item_ids: o.item_ids ? JSON.parse(o.item_ids) : [] })));
});

// ── POST /api/ai/chat ──────────────────────────────────────
router.post('/chat', async (req, res) => {
  const db = getDb();
  const { user_id = 1, message } = req.body;
  const uid = String(user_id); // ensure string for TEXT FK column
  if (!message) return res.status(400).json({ error: 'message is required' });

  const closetItems = db.prepare('SELECT * FROM closet_items WHERE user_id = ?').all(uid);

  try {
    const result = await callAI('/api/chat', { message, closet_items: closetItems });

    // Best-effort: store chat history (non-fatal if it fails)
    try {
      db.prepare('INSERT INTO chat_messages (id, user_id, role, content) VALUES (?, ?, ?, ?)').run(uuidv4(), uid, 'user', message);
      db.prepare('INSERT INTO chat_messages (id, user_id, role, content) VALUES (?, ?, ?, ?)').run(uuidv4(), uid, 'assistant', result.reply || '');
    } catch (dbErr) {
      console.warn('Chat history save failed (non-fatal):', dbErr.message);
    }

    res.json(result);
  } catch (err) {
    res.status(502).json({ error: 'AI service unavailable', details: err.message });
  }
});

// ══════════════════════════════════════════════════════════════
//  STREAMING PROXY ROUTES  (SSE pass-through to AI service)
// ══════════════════════════════════════════════════════════════

function setupSSEResponse(res) {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();
}

function proxySSEStream(aiStream, res, req, onEvent) {
  let buffer = '';

  aiStream.on('data', (chunk) => {
    buffer += chunk.toString();
    // Split on double newline (SSE event boundary)
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || ''; // keep last incomplete part

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data: ')) continue;
      const jsonStr = line.slice(6);
      try {
        const event = JSON.parse(jsonStr);
        if (onEvent) onEvent(event);
      } catch (_) {}
      res.write(line + '\n\n');
    }
  });

  aiStream.on('end', () => res.end());
  aiStream.on('error', (err) => {
    res.write(`data: ${JSON.stringify({ type: 'error', message: err.message })}\n\n`);
    res.end();
  });

  req.on('close', () => aiStream.destroy());
}

// ── POST /api/ai/chat/stream ───────────────────────────────
router.post('/chat/stream', async (req, res) => {
  setupSSEResponse(res);
  const db = getDb();
  const { user_id = 1, message } = req.body;
  const uid = String(user_id);
  if (!message) {
    res.write(`data: ${JSON.stringify({ type: 'error', message: 'message is required' })}\n\n`);
    return res.end();
  }

  const closetItems = db.prepare('SELECT * FROM closet_items WHERE user_id = ?').all(uid);
  let fullReply = '';

  try {
    const aiResponse = await axios.post(
      `${AI_SERVICE_URL}/api/chat/stream`,
      { message, closet_items: closetItems },
      { responseType: 'stream', timeout: AI_TIMEOUT * 5 }
    );

    proxySSEStream(aiResponse.data, res, req, (event) => {
      if (event.type === 'token') fullReply += event.content;
      if (event.type === 'done') {
        try {
          db.prepare('INSERT INTO chat_messages (id, user_id, role, content) VALUES (?, ?, ?, ?)')
            .run(uuidv4(), uid, 'user', message);
          db.prepare('INSERT INTO chat_messages (id, user_id, role, content) VALUES (?, ?, ?, ?)')
            .run(uuidv4(), uid, 'assistant', fullReply);
        } catch (dbErr) {
          console.warn('Chat history save failed (non-fatal):', dbErr.message);
        }
      }
    });
  } catch (err) {
    res.write(`data: ${JSON.stringify({ type: 'error', message: err.message })}\n\n`);
    res.end();
  }
});

// ── POST /api/ai/generate-outfit/stream ───────────────────
router.post('/generate-outfit/stream', async (req, res) => {
  setupSSEResponse(res);
  const db = getDb();
  const { user_id = 1, occasion, weather, temperature } = req.body;
  const uid = String(user_id);

  const closetItems = db.prepare('SELECT * FROM closet_items WHERE user_id = ?').all(uid);
  if (!closetItems.length) {
    res.write(`data: ${JSON.stringify({ type: 'error', message: 'No items in closet' })}\n\n`);
    return res.end();
  }

  const payload = {
    closet_items: closetItems.map(i => ({
      ...i,
      tags: i.tags ? JSON.parse(i.tags) : [],
      occasion: i.occasion ? JSON.parse(i.occasion) : [],
    })),
    occasion: occasion || 'casual',
    weather: weather || 'sunny',
    temperature: temperature || 22,
  };

  try {
    const aiResponse = await axios.post(
      `${AI_SERVICE_URL}/api/outfit/stream`,
      payload,
      { responseType: 'stream', timeout: AI_TIMEOUT * 5 }
    );

    proxySSEStream(aiResponse.data, res, req, (event) => {
      if (event.type === 'result') {
        const result = event.data || {};
        for (const outfit of (result.outfits || [])) {
          try {
            db.prepare(`
              INSERT INTO outfits (id, user_id, name, item_ids, occasion, weather_condition, temperature, ai_explanation, style_score, created_at, updated_at)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            `).run(
              uuidv4(), uid,
              outfit.name || 'AI Outfit',
              JSON.stringify(outfit.item_ids || []),
              occasion, weather, temperature,
              outfit.explanation,
              outfit.style_score || null,
            );
          } catch (dbErr) {
            console.warn('Outfit persist failed (non-fatal):', dbErr.message);
          }
        }
      }
    });
  } catch (err) {
    res.write(`data: ${JSON.stringify({ type: 'error', message: err.message })}\n\n`);
    res.end();
  }
});

// ── POST /api/ai/generate-packing-list/stream ─────────────
router.post('/generate-packing-list/stream', async (req, res) => {
  setupSSEResponse(res);
  const db = getDb();
  const { user_id = 1, destination, start_date, end_date, purpose = 'leisure' } = req.body;
  const uid = String(user_id);

  if (!destination || !start_date || !end_date) {
    res.write(`data: ${JSON.stringify({ type: 'error', message: 'destination, start_date, end_date are required' })}\n\n`);
    return res.end();
  }

  const closetItems = db.prepare('SELECT * FROM closet_items WHERE user_id = ?').all(uid);
  const payload = {
    destination, start_date, end_date, purpose,
    closet_items: closetItems.map(i => ({
      ...i,
      tags: i.tags ? JSON.parse(i.tags) : [],
      occasion: i.occasion ? JSON.parse(i.occasion) : [],
    })),
  };

  try {
    const aiResponse = await axios.post(
      `${AI_SERVICE_URL}/api/packing/stream`,
      payload,
      { responseType: 'stream', timeout: AI_TIMEOUT * 6 }
    );

    proxySSEStream(aiResponse.data, res, req, (event) => {
      if (event.type === 'result') {
        const result = event.data || {};
        try {
          const id = uuidv4();
          const start = new Date(start_date);
          const end = new Date(end_date);
          const durationDays = Math.max(1, Math.round((end - start) / 86400000));
          db.prepare(`
            INSERT INTO packing_lists (id, user_id, destination, start_date, end_date, duration_days, trip_type, purpose, item_ids, generated_list, missing_items, daily_plan, alerts, weather_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
          `).run(
            id, uid, destination, start_date, end_date, durationDays,
            result.trip_type || purpose, purpose,
            JSON.stringify(result.packing_item_ids || []),
            JSON.stringify(result.packing_list || []),
            JSON.stringify(result.missing_items || []),
            JSON.stringify(result.daily_plan || []),
            JSON.stringify(result.alerts || []),
            JSON.stringify(result.weather_summary || {}),
          );
          // Inject packing_list_id into the result event so frontend gets it
          event.data = { ...result, packing_list_id: id };
        } catch (dbErr) {
          console.warn('Packing list persist failed (non-fatal):', dbErr.message);
        }
      }
    });
  } catch (err) {
    res.write(`data: ${JSON.stringify({ type: 'error', message: err.message })}\n\n`);
    res.end();
  }
});

module.exports = router;
