-- CLOZEHIVE — full gateway schema bootstrap (alembic 001 → 032).
-- Generated with: alembic upgrade head --sql
--
-- WHEN TO USE: to create the schema directly on a fresh Postgres (e.g. Neon)
-- when the app's startup migrations can't land it. Run this whole file in the
-- target database's SQL editor. It is one transaction (BEGIN…COMMIT), creates
-- every table + the vector/pg_trgm extensions, and stamps alembic_version='032'
-- so the app then sees the DB as already at head (no migrations re-run).
--
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 001

CREATE TABLE users (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    username VARCHAR(50) NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    bio TEXT, 
    avatar_url TEXT, 
    role VARCHAR(20) DEFAULT 'user' NOT NULL, 
    is_active BOOLEAN DEFAULT 'true' NOT NULL, 
    is_verified BOOLEAN DEFAULT 'false' NOT NULL, 
    google_id VARCHAR(255), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (email), 
    UNIQUE (username), 
    UNIQUE (google_id)
);

CREATE INDEX idx_users_email ON users (email);

CREATE INDEX idx_users_username ON users (username);

CREATE TABLE user_credentials (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    password_hash TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE refresh_tokens (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked BOOLEAN DEFAULT 'false' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (token_hash)
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens (token_hash);

CREATE TABLE follows (
    follower_id UUID NOT NULL, 
    following_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (follower_id, following_id), 
    FOREIGN KEY(follower_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(following_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_follows_follower_id ON follows (follower_id);

CREATE INDEX idx_follows_following_id ON follows (following_id);

CREATE TABLE groups (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    description TEXT, 
    owner_id UUID NOT NULL, 
    is_private BOOLEAN DEFAULT 'false' NOT NULL, 
    invite_code VARCHAR(20) NOT NULL, 
    avatar_url TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (invite_code)
);

CREATE INDEX idx_groups_owner_id ON groups (owner_id);

CREATE TABLE group_members (
    group_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    role VARCHAR(20) DEFAULT 'member' NOT NULL, 
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (group_id, user_id), 
    FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_group_members_user_id ON group_members (user_id);

CREATE TABLE closet_items (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    category VARCHAR(100) NOT NULL, 
    color VARCHAR(100), 
    fabric VARCHAR(100), 
    pattern VARCHAR(100), 
    season VARCHAR(50), 
    occasion VARCHAR[], 
    eco_score NUMERIC(3, 1), 
    tags VARCHAR[], 
    image_url TEXT, 
    notes TEXT, 
    brand VARCHAR(100), 
    size VARCHAR(20), 
    price NUMERIC(10, 2), 
    wear_count INTEGER DEFAULT '0' NOT NULL, 
    last_worn DATE, 
    is_archived BOOLEAN DEFAULT 'false' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_closet_items_user_id ON closet_items (user_id);

CREATE INDEX idx_closet_items_category ON closet_items (category);

CREATE TABLE outfits (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    name VARCHAR(255), 
    occasion VARCHAR(100), 
    item_ids VARCHAR[], 
    explanation TEXT, 
    style_score INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';;

CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON users
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();;

CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON groups
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();;

CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON closet_items
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();;

INSERT INTO alembic_version (version_num) VALUES ('001') RETURNING alembic_version.version_num;

-- Running upgrade 001 -> 002

SAVEPOINT _optional_stmt;

CREATE EXTENSION IF NOT EXISTS "vector";

RELEASE SAVEPOINT _optional_stmt;

SAVEPOINT _optional_stmt;

CREATE EXTENSION IF NOT EXISTS "pg_trgm";

RELEASE SAVEPOINT _optional_stmt;

CREATE TABLE closet_item_embeddings (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    closet_item_id UUID NOT NULL, 
    content TEXT NOT NULL, 
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL, 
    embedding TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (closet_item_id), 
    FOREIGN KEY(closet_item_id) REFERENCES closet_items (id) ON DELETE CASCADE
);

ALTER TABLE closet_item_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector;

CREATE INDEX idx_closet_item_embeddings_vector ON closet_item_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_closet_item_embeddings_user_id ON closet_item_embeddings (user_id);

CREATE INDEX idx_outfits_user_id ON outfits (user_id);

SAVEPOINT _optional_stmt;

CREATE INDEX idx_users_username_trgm ON users USING gin (username gin_trgm_ops);

RELEASE SAVEPOINT _optional_stmt;

SAVEPOINT _optional_stmt;

CREATE INDEX idx_users_name_trgm ON users USING gin (name gin_trgm_ops);

RELEASE SAVEPOINT _optional_stmt;

UPDATE alembic_version SET version_num='002' WHERE alembic_version.version_num = '001';

-- Running upgrade 002 -> 003

CREATE TABLE ai_requests (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    request_type VARCHAR(50) NOT NULL, 
    status VARCHAR(30) DEFAULT 'accepted' NOT NULL, 
    input_payload JSONB DEFAULT '{}'::jsonb NOT NULL, 
    result_payload JSONB, 
    error_message TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_ai_requests_user_status ON ai_requests (user_id, status);

CREATE INDEX idx_ai_requests_type_created ON ai_requests (request_type, created_at);

CREATE TABLE processed_events (
    event_id UUID NOT NULL, 
    topic VARCHAR(100) NOT NULL, 
    request_id UUID, 
    processed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (event_id)
);

UPDATE alembic_version SET version_num='003' WHERE alembic_version.version_num = '002';

-- Running upgrade 003 -> 004

ALTER TABLE users ADD COLUMN body_profile JSONB;

ALTER TABLE users ADD COLUMN style_profile JSONB;

ALTER TABLE users ADD COLUMN preferences JSONB;

ALTER TABLE users ADD COLUMN permissions JSONB;

ALTER TABLE users ADD COLUMN avatar_config JSONB;

UPDATE alembic_version SET version_num='004' WHERE alembic_version.version_num = '003';

-- Running upgrade 004 -> 005

CREATE TABLE trips (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    destination VARCHAR(255) NOT NULL, 
    start_date DATE NOT NULL, 
    end_date DATE NOT NULL, 
    purpose VARCHAR(50) NOT NULL, 
    notes TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_trips_user_id ON trips (user_id);

CREATE INDEX idx_trips_destination ON trips (destination);

CREATE TRIGGER set_updated_at
        BEFORE UPDATE ON trips
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();;

UPDATE alembic_version SET version_num='005' WHERE alembic_version.version_num = '004';

-- Running upgrade 005 -> 006

CREATE INDEX IF NOT EXISTS ix_closet_items_user_id ON closet_items (user_id);

CREATE INDEX IF NOT EXISTS ix_closet_items_category ON closet_items (category);

CREATE INDEX IF NOT EXISTS ix_closet_items_created_at ON closet_items (created_at);

CREATE INDEX IF NOT EXISTS ix_trips_user_id ON trips (user_id);

CREATE INDEX IF NOT EXISTS ix_outfits_user_id ON outfits (user_id);

UPDATE alembic_version SET version_num='006' WHERE alembic_version.version_num = '005';

-- Running upgrade 006 -> 007

SAVEPOINT _optional_stmt;

CREATE EXTENSION IF NOT EXISTS vector;

RELEASE SAVEPOINT _optional_stmt;

SAVEPOINT _optional_stmt;

ALTER TABLE closet_items ADD COLUMN IF NOT EXISTS embedding vector(1536);

RELEASE SAVEPOINT _optional_stmt;

SAVEPOINT _optional_stmt;

CREATE INDEX IF NOT EXISTS ix_closet_items_embedding_hnsw
        ON closet_items
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);

RELEASE SAVEPOINT _optional_stmt;

UPDATE alembic_version SET version_num='007' WHERE alembic_version.version_num = '006';

-- Running upgrade 007 -> 008

ALTER TABLE closet_items ADD COLUMN original_image_url TEXT;

ALTER TABLE closet_items ADD COLUMN processed_image_url TEXT;

ALTER TABLE closet_items ADD COLUMN background_removed BOOLEAN DEFAULT 'false' NOT NULL;

ALTER TABLE closet_items ADD COLUMN background_removal_status VARCHAR(20);

ALTER TABLE closet_items ADD COLUMN analysis_source VARCHAR(50);

ALTER TABLE closet_items ADD COLUMN confidence_score NUMERIC(4, 2);

ALTER TABLE closet_items ADD COLUMN scan_batch_id VARCHAR(36);

CREATE INDEX idx_closet_items_scan_batch_id ON closet_items (scan_batch_id);

UPDATE alembic_version SET version_num='008' WHERE alembic_version.version_num = '007';

-- Running upgrade 008 -> 009

ALTER TABLE closet_items
        ALTER COLUMN season TYPE VARCHAR[]
        USING CASE
            WHEN season IS NULL OR trim(season) = '' THEN NULL
            ELSE ARRAY[season]
        END;

UPDATE alembic_version SET version_num='009' WHERE alembic_version.version_num = '008';

-- Running upgrade 009 -> 010

CREATE TABLE packing_plans (
    id UUID NOT NULL, 
    trip_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    take_from_your_closet JSONB DEFAULT '[]'::jsonb NOT NULL, 
    you_might_still_need JSONB DEFAULT '[]'::jsonb NOT NULL, 
    daily_plan JSONB, 
    weather_summary JSONB, 
    raw_result JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(trip_id) REFERENCES trips (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_packing_plans_user_id ON packing_plans (user_id);

CREATE INDEX ix_packing_plans_trip_id ON packing_plans (trip_id);

UPDATE alembic_version SET version_num='010' WHERE alembic_version.version_num = '009';

-- Running upgrade 010 -> 011

ALTER TABLE trips ADD COLUMN is_saved BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE packing_plans ADD COLUMN is_saved BOOLEAN DEFAULT false NOT NULL;

UPDATE alembic_version SET version_num='011' WHERE alembic_version.version_num = '010';

-- Running upgrade 011 -> 012

CREATE TABLE user_style_profiles (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    gender VARCHAR(32), 
    custom_gender VARCHAR(120), 
    height_value NUMERIC(6, 2), 
    height_unit VARCHAR(8), 
    weight_value NUMERIC(7, 2), 
    weight_unit VARCHAR(8), 
    age_range VARCHAR(32), 
    body_types JSONB DEFAULT '[]'::jsonb NOT NULL, 
    custom_body_type VARCHAR(200), 
    fit_preferences JSONB DEFAULT '[]'::jsonb NOT NULL, 
    custom_fit_notes VARCHAR(500), 
    size_profile JSONB DEFAULT '{}'::jsonb NOT NULL, 
    custom_size_notes VARCHAR(500), 
    style_preferences JSONB DEFAULT '[]'::jsonb NOT NULL, 
    favorite_colors JSONB DEFAULT '[]'::jsonb NOT NULL, 
    avoided_colors JSONB DEFAULT '[]'::jsonb NOT NULL, 
    neutral_color_preference BOOLEAN, 
    bold_color_preference BOOLEAN, 
    occasion_preferences JSONB DEFAULT '[]'::jsonb NOT NULL, 
    climate_preferences JSONB DEFAULT '[]'::jsonb NOT NULL, 
    onboarding_completed BOOLEAN DEFAULT false NOT NULL, 
    onboarding_skipped BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_user_style_profiles_user_id ON user_style_profiles (user_id);

UPDATE alembic_version SET version_num='012' WHERE alembic_version.version_num = '011';

-- Running upgrade 012 -> 013

INSERT INTO user_style_profiles (
                id, user_id,
                body_types, fit_preferences, size_profile, style_preferences,
                favorite_colors, avoided_colors, occasion_preferences, climate_preferences,
                onboarding_completed, onboarding_skipped,
                created_at, updated_at
            )
            SELECT
                gen_random_uuid(),
                u.id,
                '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, '[]'::jsonb,
                '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
                true, false,
                NOW(), NOW()
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM user_style_profiles p WHERE p.user_id = u.id
            );

UPDATE alembic_version SET version_num='013' WHERE alembic_version.version_num = '012';

-- Running upgrade 013 -> 014

ALTER TABLE packing_plans ADD CONSTRAINT uq_packing_plans_trip_user UNIQUE (trip_id, user_id);

UPDATE alembic_version SET version_num='014' WHERE alembic_version.version_num = '013';

-- Running upgrade 014 -> 015

ALTER TABLE users ADD COLUMN auth_provider VARCHAR(20) DEFAULT 'local' NOT NULL;

UPDATE users SET auth_provider = 'google' WHERE google_id IS NOT NULL;

UPDATE alembic_version SET version_num='015' WHERE alembic_version.version_num = '014';

-- Running upgrade 015 -> 016

UPDATE users
        SET    name = SPLIT_PART(email, '@', 1)
        WHERE  name IS NULL OR TRIM(name) = '';

UPDATE users
        SET    username = LOWER(REGEXP_REPLACE(SPLIT_PART(email, '@', 1), '[^a-zA-Z0-9_]', '', 'g'))
        WHERE  username IS NULL OR TRIM(username) = '';

UPDATE users
        SET    username = 'user_' || SUBSTRING(REPLACE(id::text, '-', ''), 1, 8)
        WHERE  username IS NULL OR TRIM(username) = '';

WITH ranked AS (
            SELECT id,
                   username,
                   ROW_NUMBER() OVER (PARTITION BY username ORDER BY created_at ASC, id ASC) AS rn
            FROM   users
        )
        UPDATE users u
        SET    username = u.username || '_' || SUBSTRING(REPLACE(u.id::text, '-', ''), 1, 6)
        FROM   ranked r
        WHERE  u.id = r.id
          AND  r.rn > 1;

UPDATE alembic_version SET version_num='016' WHERE alembic_version.version_num = '015';

-- Running upgrade 016 -> 017

ALTER TABLE user_style_profiles ADD COLUMN style_summary TEXT;

UPDATE alembic_version SET version_num='017' WHERE alembic_version.version_num = '016';

-- Running upgrade 017 -> 018

CREATE TABLE fashion_knowledge_documents (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    title VARCHAR(255) NOT NULL, 
    content TEXT NOT NULL, 
    category VARCHAR(100) NOT NULL, 
    season VARCHAR(50), 
    occasion VARCHAR(100), 
    tags JSONB, 
    embedding TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX idx_fkd_category ON fashion_knowledge_documents (category);

CREATE INDEX idx_fkd_title ON fashion_knowledge_documents (title);

SAVEPOINT _rag_stmt;

ALTER TABLE fashion_knowledge_documents ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector;

RELEASE SAVEPOINT _rag_stmt;

SAVEPOINT _rag_stmt;

CREATE INDEX idx_fkd_embedding ON fashion_knowledge_documents USING hnsw (embedding vector_cosine_ops);

RELEASE SAVEPOINT _rag_stmt;

CREATE TABLE outfit_history (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    occasion VARCHAR(100), 
    weather_context JSONB, 
    selected_item_ids JSONB, 
    matching_score INTEGER, 
    recommendation_text TEXT, 
    improvement_tips JSONB, 
    user_feedback TEXT, 
    was_saved BOOLEAN DEFAULT 'false' NOT NULL, 
    was_worn BOOLEAN DEFAULT 'false' NOT NULL, 
    embedding TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_outfit_history_user_id ON outfit_history (user_id);

CREATE INDEX idx_outfit_history_occasion ON outfit_history (occasion);

CREATE INDEX idx_outfit_history_created_at ON outfit_history (created_at);

SAVEPOINT _rag_stmt;

ALTER TABLE outfit_history ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector;

RELEASE SAVEPOINT _rag_stmt;

SAVEPOINT _rag_stmt;

CREATE INDEX idx_outfit_history_embedding ON outfit_history USING hnsw (embedding vector_cosine_ops);

RELEASE SAVEPOINT _rag_stmt;

CREATE TABLE packing_memory (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    trip_id UUID, 
    destination VARCHAR(255) NOT NULL, 
    start_date VARCHAR(10), 
    end_date VARCHAR(10), 
    purpose VARCHAR(50), 
    weather_summary JSONB, 
    packed_item_ids JSONB, 
    missing_items JSONB, 
    saved_plan_id UUID, 
    user_feedback TEXT, 
    embedding TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(trip_id) REFERENCES trips (id) ON DELETE SET NULL, 
    FOREIGN KEY(saved_plan_id) REFERENCES packing_plans (id) ON DELETE SET NULL
);

CREATE INDEX idx_packing_memory_user_id ON packing_memory (user_id);

CREATE INDEX idx_packing_memory_trip_id ON packing_memory (trip_id);

CREATE INDEX idx_packing_memory_destination ON packing_memory (destination);

SAVEPOINT _rag_stmt;

ALTER TABLE packing_memory ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector;

RELEASE SAVEPOINT _rag_stmt;

SAVEPOINT _rag_stmt;

CREATE INDEX idx_packing_memory_embedding ON packing_memory USING hnsw (embedding vector_cosine_ops);

RELEASE SAVEPOINT _rag_stmt;

CREATE TABLE purchase_gaps (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    gap_type VARCHAR(50) NOT NULL, 
    missing_category VARCHAR(100) NOT NULL, 
    missing_color VARCHAR(50), 
    missing_season VARCHAR(50), 
    missing_occasion VARCHAR(100), 
    reason TEXT NOT NULL, 
    priority_score NUMERIC(4, 2) DEFAULT '0.5' NOT NULL, 
    source_context JSONB, 
    resolved BOOLEAN DEFAULT 'false' NOT NULL, 
    suggested_attributes JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_purchase_gaps_user_id ON purchase_gaps (user_id);

CREATE INDEX idx_purchase_gaps_resolved ON purchase_gaps (resolved);

CREATE INDEX idx_purchase_gaps_gap_type ON purchase_gaps (gap_type);

UPDATE alembic_version SET version_num='018' WHERE alembic_version.version_num = '017';

-- Running upgrade 018 -> 019

CREATE TABLE ai_chat_sessions (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    title VARCHAR(255), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_chat_sessions_user_id ON ai_chat_sessions (user_id);

CREATE INDEX ix_ai_chat_sessions_created_at ON ai_chat_sessions (created_at);

CREATE TABLE ai_chat_messages (
    id UUID NOT NULL, 
    session_id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    message TEXT NOT NULL, 
    structured_response JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES ai_chat_sessions (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_ai_chat_messages_session_id ON ai_chat_messages (session_id);

CREATE INDEX ix_ai_chat_messages_user_id ON ai_chat_messages (user_id);

CREATE INDEX ix_ai_chat_messages_created_at ON ai_chat_messages (created_at);

CREATE TABLE outfit_feedback (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    outfit_id UUID, 
    closet_item_ids JSONB, 
    rating INTEGER, 
    feedback_text TEXT, 
    occasion VARCHAR(100), 
    mood VARCHAR(100), 
    was_worn BOOLEAN DEFAULT 'false' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(outfit_id) REFERENCES outfits (id) ON DELETE SET NULL
);

CREATE INDEX ix_outfit_feedback_user_id ON outfit_feedback (user_id);

CREATE INDEX ix_outfit_feedback_outfit_id ON outfit_feedback (outfit_id);

CREATE INDEX ix_outfit_feedback_occasion ON outfit_feedback (occasion);

CREATE INDEX ix_outfit_feedback_created_at ON outfit_feedback (created_at);

UPDATE alembic_version SET version_num='019' WHERE alembic_version.version_num = '018';

-- Running upgrade 019 -> 020

ALTER TABLE user_style_profiles ADD COLUMN styling_goals JSONB DEFAULT '[]'::jsonb;

ALTER TABLE user_style_profiles ADD COLUMN avoidances JSONB DEFAULT '[]'::jsonb;

ALTER TABLE user_style_profiles ADD COLUMN pattern_preferences JSONB DEFAULT '[]'::jsonb;

ALTER TABLE user_style_profiles ADD COLUMN style_archetype VARCHAR(100);

ALTER TABLE user_style_profiles ADD COLUMN recommendation_rules JSONB;

ALTER TABLE user_style_profiles ADD COLUMN ai_stylist_context TEXT;

UPDATE alembic_version SET version_num='020' WHERE alembic_version.version_num = '019';

-- Running upgrade 020 -> 021

ALTER TABLE trips ADD COLUMN trip_style VARCHAR(50);

ALTER TABLE trips ADD COLUMN bag_size VARCHAR(50);

ALTER TABLE trips ADD COLUMN activities JSONB DEFAULT '[]'::jsonb;

ALTER TABLE packing_plans ADD COLUMN activities JSONB;

ALTER TABLE packing_plans ADD COLUMN day_plans_rich JSONB;

ALTER TABLE packing_plans ADD COLUMN rewear_strategy JSONB;

ALTER TABLE packing_plans ADD COLUMN bag_capacity_summary JSONB;

ALTER TABLE packing_plans ADD COLUMN packing_checklist JSONB;

ALTER TABLE packing_plans ADD COLUMN checklist_state JSONB;

UPDATE alembic_version SET version_num='021' WHERE alembic_version.version_num = '020';

-- Running upgrade 021 -> 022

ALTER TABLE closet_items ADD COLUMN section VARCHAR(50);

CREATE INDEX ix_closet_items_section ON closet_items (section);

UPDATE alembic_version SET version_num='022' WHERE alembic_version.version_num = '021';

-- Running upgrade 022 -> 023

CREATE TABLE password_reset_tokens (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    used_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_password_reset_tokens_token_hash ON password_reset_tokens (token_hash);

CREATE INDEX ix_password_reset_tokens_user_id ON password_reset_tokens (user_id);

UPDATE alembic_version SET version_num='023' WHERE alembic_version.version_num = '022';

-- Running upgrade 023 -> 024

CREATE TABLE shopping_checks (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    image_url TEXT, 
    item_analysis JSONB, 
    matched_items JSONB, 
    buy_score FLOAT, 
    buy_recommendation VARCHAR(20), 
    closet_boost_pct FLOAT, 
    reasoning TEXT, 
    purchase_decision BOOLEAN, 
    decision_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_shopping_checks_user_id ON shopping_checks (user_id);

CREATE INDEX ix_shopping_checks_created_at ON shopping_checks (created_at);

CREATE INDEX ix_shopping_checks_purchase_decision ON shopping_checks (purchase_decision);

UPDATE alembic_version SET version_num='024' WHERE alembic_version.version_num = '023';

-- Running upgrade 024 -> 025

ALTER TABLE ai_chat_sessions ADD COLUMN summary TEXT;

ALTER TABLE ai_chat_sessions ADD COLUMN summary_through_msg_count INTEGER DEFAULT '0' NOT NULL;

CREATE TABLE daily_nudges (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    nudge_date DATE NOT NULL, 
    message TEXT NOT NULL, 
    nudge_type VARCHAR(40) NOT NULL, 
    payload JSONB, 
    dismissed BOOLEAN DEFAULT 'false' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

ALTER TABLE daily_nudges ADD CONSTRAINT uq_daily_nudges_user_date UNIQUE (user_id, nudge_date);

CREATE INDEX ix_daily_nudges_user_date ON daily_nudges (user_id, nudge_date);

UPDATE alembic_version SET version_num='025' WHERE alembic_version.version_num = '024';

-- Running upgrade 025 -> 026

CREATE TABLE virtual_tryon_sessions (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    closet_item_id UUID, 
    person_image_url TEXT NOT NULL, 
    garment_image_url TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    fal_request_id VARCHAR(255), 
    result_image_url TEXT, 
    error_message TEXT, 
    label VARCHAR(255), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(closet_item_id) REFERENCES closet_items (id) ON DELETE SET NULL
);

CREATE INDEX ix_vt_sessions_user_id ON virtual_tryon_sessions (user_id);

CREATE INDEX ix_vt_sessions_status ON virtual_tryon_sessions (status);

CREATE INDEX ix_vt_sessions_closet_item_id ON virtual_tryon_sessions (closet_item_id);

UPDATE alembic_version SET version_num='026' WHERE alembic_version.version_num = '025';

-- Running upgrade 026 -> 027

ALTER TABLE user_style_profiles ADD COLUMN skin_tone VARCHAR(32);

ALTER TABLE user_style_profiles ADD COLUMN undertone VARCHAR(16);

UPDATE alembic_version SET version_num='027' WHERE alembic_version.version_num = '026';

-- Running upgrade 027 -> 028

CREATE TABLE purge_outbox (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    target VARCHAR(40) NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    attempts INTEGER DEFAULT '0' NOT NULL, 
    last_error TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_purge_outbox_status ON purge_outbox (status);

UPDATE alembic_version SET version_num='028' WHERE alembic_version.version_num = '027';

-- Running upgrade 028 -> 029

CREATE TABLE user_style_memory (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    content TEXT NOT NULL, 
    kind VARCHAR(40) DEFAULT 'general' NOT NULL, 
    source VARCHAR(40) DEFAULT 'chat' NOT NULL, 
    embedding TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_user_style_memory_user_id ON user_style_memory (user_id);

CREATE INDEX idx_user_style_memory_user_created ON user_style_memory (user_id, created_at);

SAVEPOINT _style_mem_stmt;

ALTER TABLE user_style_memory ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector;

RELEASE SAVEPOINT _style_mem_stmt;

SAVEPOINT _style_mem_stmt;

CREATE INDEX idx_user_style_memory_embedding ON user_style_memory USING hnsw (embedding vector_cosine_ops);

RELEASE SAVEPOINT _style_mem_stmt;

UPDATE alembic_version SET version_num='029' WHERE alembic_version.version_num = '028';

-- Running upgrade 029 -> 030

CREATE TABLE planned_outfits (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    user_id UUID NOT NULL, 
    plan_date DATE NOT NULL, 
    item_ids VARCHAR[], 
    occasion VARCHAR(100), 
    weather_condition VARCHAR(100), 
    temp_high NUMERIC(5, 1), 
    temp_low NUMERIC(5, 1), 
    reasoning TEXT, 
    source VARCHAR(20) DEFAULT 'fani' NOT NULL, 
    is_worn BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_planned_outfits_user_date UNIQUE (user_id, plan_date), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX idx_planned_outfits_user_id ON planned_outfits (user_id);

CREATE INDEX idx_planned_outfits_plan_date ON planned_outfits (plan_date);

UPDATE alembic_version SET version_num='030' WHERE alembic_version.version_num = '029';

-- Running upgrade 030 -> 031

ALTER TABLE closet_items ADD COLUMN availability VARCHAR(20) DEFAULT 'available' NOT NULL;

UPDATE alembic_version SET version_num='031' WHERE alembic_version.version_num = '030';

-- Running upgrade 031 -> 032

DROP INDEX IF EXISTS idx_planned_outfits_user_id;

DROP INDEX IF EXISTS idx_planned_outfits_plan_date;

UPDATE alembic_version SET version_num='032' WHERE alembic_version.version_num = '031';

COMMIT;

