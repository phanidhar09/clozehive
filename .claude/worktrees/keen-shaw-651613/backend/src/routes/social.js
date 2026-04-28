const express = require('express');
const router = express.Router();
const { getDb } = require('../db');
const { requireAuth } = require('../middleware/authMiddleware');

// Always coerce ids to strings — users.id is TEXT (UUID), never parse as int
const sid = (v) => String(v);

function formatUser(user, auth, followedByMe = false, followerCount = 0, followingCount = 0) {
  return {
    id: sid(user.id),
    name: user.name,
    email: user.email,
    username: auth?.username || user.username || null,
    bio: user.bio || null,
    avatar_url: user.avatar_url || null,
    follower_count: followerCount,
    following_count: followingCount,
    is_following: followedByMe,
  };
}

function getUserCounts(db, userId) {
  const followerCount  = db.prepare('SELECT COUNT(*) AS c FROM follows WHERE following_id = ?').get(sid(userId))?.c ?? 0;
  const followingCount = db.prepare('SELECT COUNT(*) AS c FROM follows WHERE follower_id = ?').get(sid(userId))?.c ?? 0;
  const itemCount      = db.prepare('SELECT COUNT(*) AS c FROM closet_items WHERE user_id = ?').get(sid(userId))?.c ?? 0;
  return { followerCount, followingCount, itemCount };
}

// ── GET /api/social/users?q=search ────────────────────────
router.get('/users', requireAuth, (req, res) => {
  const db = getDb();
  const q = (req.query.q || '').trim();
  const meId = sid(req.user.id);

  const users = q
    ? db.prepare(`
        SELECT u.*, a.username AS auth_username FROM users u
        LEFT JOIN user_auth a ON a.user_id = u.id
        WHERE (u.name LIKE ? OR a.username LIKE ? OR u.username LIKE ?)
          AND u.id != ?
        LIMIT 30
      `).all(`%${q}%`, `%${q}%`, `%${q}%`, meId)
    : db.prepare(`
        SELECT u.*, a.username AS auth_username FROM users u
        LEFT JOIN user_auth a ON a.user_id = u.id
        WHERE u.id != ?
        ORDER BY u.created_at DESC
        LIMIT 30
      `).all(meId);

  const result = users.map(u => {
    const uId = sid(u.id);
    const followedByMe = !!db.prepare(
      'SELECT 1 FROM follows WHERE follower_id = ? AND following_id = ?'
    ).get(meId, uId);
    const { followerCount, followingCount, itemCount } = getUserCounts(db, uId);
    return {
      ...formatUser(u, { username: u.auth_username || u.username }, followedByMe, followerCount, followingCount),
      item_count: itemCount,
    };
  });

  res.json(result);
});

// ── GET /api/social/profile/:id ───────────────────────────
router.get('/profile/:id', requireAuth, (req, res) => {
  const db = getDb();
  const targetId = sid(req.params.id);
  const meId = sid(req.user.id);

  const user = db.prepare('SELECT * FROM users WHERE id = ?').get(targetId);
  if (!user) return res.status(404).json({ error: 'User not found' });

  const auth = db.prepare('SELECT * FROM user_auth WHERE user_id = ?').get(targetId);
  const followedByMe = !!db.prepare(
    'SELECT 1 FROM follows WHERE follower_id = ? AND following_id = ?'
  ).get(meId, targetId);
  const { followerCount, followingCount, itemCount } = getUserCounts(db, targetId);

  const closetPreview = db.prepare(`
    SELECT id, name, category, color, image_url FROM closet_items
    WHERE user_id = ? ORDER BY created_at DESC LIMIT 6
  `).all(targetId);

  res.json({
    ...formatUser(user, auth, followedByMe, followerCount, followingCount),
    item_count: itemCount,
    closet_preview: closetPreview,
  });
});

// ── POST /api/social/follow/:id ───────────────────────────
router.post('/follow/:id', requireAuth, (req, res) => {
  const db = getDb();
  const followingId = sid(req.params.id);
  const followerId  = sid(req.user.id);

  if (followingId === followerId)
    return res.status(400).json({ error: 'Cannot follow yourself' });

  if (!db.prepare('SELECT id FROM users WHERE id = ?').get(followingId))
    return res.status(404).json({ error: 'User not found' });

  try {
    db.prepare(
      'INSERT OR IGNORE INTO follows (follower_id, following_id) VALUES (?, ?)'
    ).run(followerId, followingId);

    const fCount = db.prepare('SELECT COUNT(*) AS c FROM follows WHERE following_id = ?').get(followingId)?.c ?? 0;
    res.json({ following: true, follower_count: fCount });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// ── DELETE /api/social/follow/:id ─────────────────────────
router.delete('/follow/:id', requireAuth, (req, res) => {
  const db = getDb();
  const followingId = sid(req.params.id);
  const followerId  = sid(req.user.id);

  db.prepare(
    'DELETE FROM follows WHERE follower_id = ? AND following_id = ?'
  ).run(followerId, followingId);

  const fCount = db.prepare('SELECT COUNT(*) AS c FROM follows WHERE following_id = ?').get(followingId)?.c ?? 0;
  res.json({ following: false, follower_count: fCount });
});

// ── GET /api/social/followers/:id ─────────────────────────
router.get('/followers/:id', requireAuth, (req, res) => {
  const db = getDb();
  const targetId = sid(req.params.id);
  const meId = sid(req.user.id);

  const followers = db.prepare(`
    SELECT u.*, a.username AS auth_username FROM follows f
    JOIN users u ON u.id = f.follower_id
    LEFT JOIN user_auth a ON a.user_id = u.id
    WHERE f.following_id = ?
    ORDER BY f.created_at DESC
  `).all(targetId);

  const result = followers.map(u => {
    const uId = sid(u.id);
    const followedByMe = !!db.prepare(
      'SELECT 1 FROM follows WHERE follower_id = ? AND following_id = ?'
    ).get(meId, uId);
    const { followerCount } = getUserCounts(db, uId);
    return formatUser(u, { username: u.auth_username || u.username }, followedByMe, followerCount, 0);
  });
  res.json(result);
});

// ── GET /api/social/following/:id ─────────────────────────
router.get('/following/:id', requireAuth, (req, res) => {
  const db = getDb();
  const targetId = sid(req.params.id);
  const meId = sid(req.user.id);

  const following = db.prepare(`
    SELECT u.*, a.username AS auth_username FROM follows f
    JOIN users u ON u.id = f.following_id
    LEFT JOIN user_auth a ON a.user_id = u.id
    WHERE f.follower_id = ?
    ORDER BY f.created_at DESC
  `).all(targetId);

  const result = following.map(u => {
    const uId = sid(u.id);
    const followedByMe = !!db.prepare(
      'SELECT 1 FROM follows WHERE follower_id = ? AND following_id = ?'
    ).get(meId, uId);
    const { followerCount } = getUserCounts(db, uId);
    return formatUser(u, { username: u.auth_username || u.username }, followedByMe, followerCount, 0);
  });
  res.json(result);
});

module.exports = router;
