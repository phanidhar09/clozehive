const Database = require('better-sqlite3');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../../.env') });

const DB_PATH = process.env.DB_PATH
  ? path.resolve(__dirname, '..', process.env.DB_PATH)
  : path.join(__dirname, '../data/closetiq.db');

let db;

function getDb() {
  if (!db) {
    db = new Database(DB_PATH);
    db.pragma('journal_mode = WAL');
    db.pragma('foreign_keys = ON');
    initSchema();
  }
  return db;
}

function initSchema() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT UNIQUE NOT NULL,
      style_preferences TEXT,
      body_type TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS closet_items (
      id TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL DEFAULT 1,
      name TEXT NOT NULL,
      category TEXT,
      color TEXT,
      color_hex TEXT,
      secondary_color TEXT,
      fabric TEXT,
      pattern TEXT,
      brand TEXT,
      size TEXT,
      price REAL,
      purchase_date TEXT,
      image_url TEXT,
      tags TEXT,
      wear_count INTEGER DEFAULT 0,
      last_worn TEXT,
      season TEXT,
      occasion TEXT,
      eco_score INTEGER,
      embedding BLOB,
      confidence_score REAL,
      is_favorite INTEGER DEFAULT 0,
      notes TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS outfits (
      id TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL DEFAULT 1,
      name TEXT,
      item_ids TEXT,
      occasion TEXT,
      weather_condition TEXT,
      temperature REAL,
      ai_explanation TEXT,
      style_score REAL,
      is_saved INTEGER DEFAULT 0,
      worn_count INTEGER DEFAULT 0,
      last_worn TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS packing_lists (
      id TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL DEFAULT 1,
      destination TEXT,
      start_date TEXT,
      end_date TEXT,
      duration_days INTEGER,
      trip_type TEXT,
      purpose TEXT,
      item_ids TEXT,
      generated_list TEXT,
      missing_items TEXT,
      daily_plan TEXT,
      alerts TEXT,
      weather_summary TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS travel_plans (
      id TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL DEFAULT 1,
      destination TEXT NOT NULL,
      start_date TEXT NOT NULL,
      end_date TEXT NOT NULL,
      purpose TEXT,
      notes TEXT,
      packing_list_id TEXT,
      status TEXT DEFAULT 'planned',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS feedback (
      id TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL DEFAULT 1,
      outfit_id TEXT,
      item_id TEXT,
      feedback_type TEXT,
      rating INTEGER,
      notes TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS chat_messages (
      id TEXT PRIMARY KEY,
      user_id INTEGER NOT NULL DEFAULT 1,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      context TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_closet_items_user ON closet_items(user_id);
    CREATE INDEX IF NOT EXISTS idx_closet_items_category ON closet_items(category);
    CREATE INDEX IF NOT EXISTS idx_outfits_user ON outfits(user_id);
    CREATE INDEX IF NOT EXISTS idx_packing_lists_user ON packing_lists(user_id);
    CREATE INDEX IF NOT EXISTS idx_travel_plans_user ON travel_plans(user_id);

    -- ── Auth ──────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS user_auth (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL REFERENCES users(id),
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_user_auth_user ON user_auth(user_id);

    -- ── Social: follows ───────────────────────────────────────
    CREATE TABLE IF NOT EXISTS follows (
      follower_id INTEGER NOT NULL REFERENCES users(id),
      following_id INTEGER NOT NULL REFERENCES users(id),
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (follower_id, following_id)
    );
    CREATE INDEX IF NOT EXISTS idx_follows_follower ON follows(follower_id);
    CREATE INDEX IF NOT EXISTS idx_follows_following ON follows(following_id);

    -- ── Groups ────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS groups (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      description TEXT,
      creator_id INTEGER NOT NULL REFERENCES users(id),
      invite_code TEXT UNIQUE NOT NULL,
      is_public INTEGER DEFAULT 1,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_groups_creator ON groups(creator_id);

    CREATE TABLE IF NOT EXISTS group_members (
      group_id TEXT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id),
      role TEXT DEFAULT 'member',
      joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (group_id, user_id)
    );
    CREATE INDEX IF NOT EXISTS idx_group_members_user ON group_members(user_id);
  `);

  // ── Safe column migrations (idempotent) ───────────────────
  const migrations = [
    // users: social profile columns
    "ALTER TABLE users ADD COLUMN username TEXT",
    "ALTER TABLE users ADD COLUMN bio TEXT",
    "ALTER TABLE users ADD COLUMN avatar_url TEXT",
    // closet_items
    "ALTER TABLE closet_items ADD COLUMN eco_score REAL",
    "ALTER TABLE closet_items ADD COLUMN color_hex TEXT",
    "ALTER TABLE closet_items ADD COLUMN secondary_color TEXT",
    "ALTER TABLE closet_items ADD COLUMN embedding BLOB",
    "ALTER TABLE closet_items ADD COLUMN confidence_score REAL",
    "ALTER TABLE closet_items ADD COLUMN is_favorite INTEGER DEFAULT 0",
    "ALTER TABLE packing_lists ADD COLUMN missing_items TEXT",
    "ALTER TABLE packing_lists ADD COLUMN daily_plan TEXT",
    "ALTER TABLE packing_lists ADD COLUMN alerts TEXT",
    "ALTER TABLE packing_lists ADD COLUMN weather_summary TEXT",
  ];
  for (const sql of migrations) {
    try { db.exec(sql); } catch (_) { /* column already exists — skip */ }
  }
}

module.exports = { getDb };
