const express = require('express');
const router = express.Router();
const { v4: uuidv4 } = require('uuid');
const { getDb } = require('../db');
const { requireAuth } = require('../middleware/authMiddleware');

function randomCode() {
  return Math.random().toString(36).slice(2, 10).toUpperCase();
}

function enrichGroup(db, group, myId) {
  const members = db.prepare(`
    SELECT u.id, u.name, u.avatar_url, a.username, gm.role, gm.joined_at
    FROM group_members gm
    JOIN users u ON u.id = gm.user_id
    LEFT JOIN user_auth a ON a.user_id = u.id
    WHERE gm.group_id = ?
    ORDER BY gm.joined_at ASC
  `).all(group.id);

  const myMembership = members.find(m => m.id === myId);

  return {
    ...group,
    member_count: members.length,
    members,
    my_role: myMembership?.role ?? null,
    is_member: !!myMembership,
  };
}

// ── GET /api/groups ────────────────────────────────────────
// List groups the user created or is a member of
router.get('/', requireAuth, (req, res) => {
  const db = getDb();
  const myId = req.user.id;

  const groups = db.prepare(`
    SELECT DISTINCT g.* FROM groups g
    LEFT JOIN group_members gm ON gm.group_id = g.id AND gm.user_id = ?
    WHERE g.creator_id = ? OR gm.user_id = ?
    ORDER BY g.created_at DESC
  `).all(myId, myId, myId);

  res.json(groups.map(g => enrichGroup(db, g, myId)));
});

// ── GET /api/groups/discover ───────────────────────────────
// List public groups the user hasn't joined
router.get('/discover', requireAuth, (req, res) => {
  const db = getDb();
  const myId = req.user.id;

  const groups = db.prepare(`
    SELECT g.* FROM groups g
    WHERE g.is_public = 1
      AND g.id NOT IN (
        SELECT group_id FROM group_members WHERE user_id = ?
      )
      AND g.creator_id != ?
    ORDER BY g.created_at DESC
    LIMIT 20
  `).all(myId, myId);

  res.json(groups.map(g => enrichGroup(db, g, myId)));
});

// ── GET /api/groups/:id ────────────────────────────────────
router.get('/:id', requireAuth, (req, res) => {
  const db = getDb();
  const group = db.prepare('SELECT * FROM groups WHERE id = ?').get(req.params.id);
  if (!group) return res.status(404).json({ error: 'Group not found' });
  res.json(enrichGroup(db, group, req.user.id));
});

// ── POST /api/groups ───────────────────────────────────────
router.post('/', requireAuth, (req, res) => {
  const db = getDb();
  const { name, description, is_public = true } = req.body;
  const myId = req.user.id;

  if (!name?.trim()) return res.status(400).json({ error: 'Group name is required' });

  const id = uuidv4();
  const invite_code = randomCode();
  const now = new Date().toISOString();

  const create = db.transaction(() => {
    db.prepare(`
      INSERT INTO groups (id, name, description, creator_id, invite_code, is_public, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `).run(id, name.trim(), description || null, myId, invite_code, is_public ? 1 : 0, now, now);

    // Creator is automatically admin member
    db.prepare(
      `INSERT INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, 'admin', ?)`
    ).run(id, myId, now);
  });

  create();

  const group = db.prepare('SELECT * FROM groups WHERE id = ?').get(id);
  res.status(201).json(enrichGroup(db, group, myId));
});

// ── POST /api/groups/join ──────────────────────────────────
// Join by invite code
router.post('/join', requireAuth, (req, res) => {
  const db = getDb();
  const { invite_code } = req.body;
  const myId = req.user.id;

  if (!invite_code) return res.status(400).json({ error: 'invite_code is required' });

  const group = db.prepare('SELECT * FROM groups WHERE invite_code = ?').get(invite_code.toUpperCase());
  if (!group) return res.status(404).json({ error: 'Invalid invite code' });

  const existing = db.prepare(
    'SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?'
  ).get(group.id, myId);
  if (existing) return res.status(409).json({ error: 'Already a member of this group' });

  db.prepare(
    `INSERT INTO group_members (group_id, user_id, role) VALUES (?, ?, 'member')`
  ).run(group.id, myId);

  res.json(enrichGroup(db, group, myId));
});

// ── POST /api/groups/:id/invite ────────────────────────────
// Admin invites a user by user ID
router.post('/:id/invite', requireAuth, (req, res) => {
  const db = getDb();
  const { user_id } = req.body;
  const myId = req.user.id;
  const groupId = req.params.id;

  // Must be admin
  const me = db.prepare(
    `SELECT role FROM group_members WHERE group_id = ? AND user_id = ?`
  ).get(groupId, myId);
  if (!me || me.role !== 'admin')
    return res.status(403).json({ error: 'Only admins can invite members' });

  const target = db.prepare('SELECT id FROM users WHERE id = ?').get(user_id);
  if (!target) return res.status(404).json({ error: 'User not found' });

  const existing = db.prepare(
    'SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?'
  ).get(groupId, user_id);
  if (existing) return res.status(409).json({ error: 'User is already a member' });

  db.prepare(
    `INSERT INTO group_members (group_id, user_id, role) VALUES (?, ?, 'member')`
  ).run(groupId, user_id);

  const group = db.prepare('SELECT * FROM groups WHERE id = ?').get(groupId);
  res.json(enrichGroup(db, group, myId));
});

// ── DELETE /api/groups/:id/members/:uid ───────────────────
// Admin removes a member
router.delete('/:id/members/:uid', requireAuth, (req, res) => {
  const db = getDb();
  const myId = req.user.id;
  const { id: groupId, uid } = req.params;
  const targetId = parseInt(uid, 10);

  const group = db.prepare('SELECT * FROM groups WHERE id = ?').get(groupId);
  if (!group) return res.status(404).json({ error: 'Group not found' });

  const me = db.prepare(
    `SELECT role FROM group_members WHERE group_id = ? AND user_id = ?`
  ).get(groupId, myId);

  // Admins can remove others; members can only remove themselves
  if (!me || (me.role !== 'admin' && myId !== targetId))
    return res.status(403).json({ error: 'Insufficient permissions' });

  if (group.creator_id === targetId)
    return res.status(400).json({ error: 'Cannot remove the group creator' });

  db.prepare('DELETE FROM group_members WHERE group_id = ? AND user_id = ?').run(groupId, targetId);
  res.json({ removed: true, user_id: targetId });
});

// ── PATCH /api/groups/:id/members/:uid/role ───────────────
// Promote / demote (admin only)
router.patch('/:id/members/:uid/role', requireAuth, (req, res) => {
  const db = getDb();
  const myId = req.user.id;
  const { id: groupId, uid } = req.params;
  const targetId = parseInt(uid, 10);
  const { role } = req.body;

  if (!['admin', 'member'].includes(role))
    return res.status(400).json({ error: 'role must be admin or member' });

  const group = db.prepare('SELECT * FROM groups WHERE id = ?').get(groupId);
  if (!group) return res.status(404).json({ error: 'Group not found' });

  const me = db.prepare(
    `SELECT role FROM group_members WHERE group_id = ? AND user_id = ?`
  ).get(groupId, myId);
  if (!me || me.role !== 'admin')
    return res.status(403).json({ error: 'Only admins can change roles' });

  db.prepare(
    'UPDATE group_members SET role = ? WHERE group_id = ? AND user_id = ?'
  ).run(role, groupId, targetId);

  res.json({ updated: true, user_id: targetId, role });
});

// ── DELETE /api/groups/:id ─────────────────────────────────
// Creator deletes the group
router.delete('/:id', requireAuth, (req, res) => {
  const db = getDb();
  const myId = req.user.id;
  const group = db.prepare('SELECT * FROM groups WHERE id = ?').get(req.params.id);

  if (!group) return res.status(404).json({ error: 'Group not found' });
  if (group.creator_id !== myId)
    return res.status(403).json({ error: 'Only the creator can delete this group' });

  db.prepare('DELETE FROM group_members WHERE group_id = ?').run(group.id);
  db.prepare('DELETE FROM groups WHERE id = ?').run(group.id);
  res.json({ deleted: true });
});

module.exports = router;
