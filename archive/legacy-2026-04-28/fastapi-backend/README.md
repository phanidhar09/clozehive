# CLOZEHIVE FastAPI Backend

Production-ready FastAPI backend for the CLOZEHIVE AI wardrobe + travel stylist app.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.111 |
| Database | PostgreSQL 16 + SQLAlchemy 2 (async) |
| Cache / Pub-Sub | Redis 7 |
| Auth | JWT (access + refresh) + bcrypt |
| Real-time | WebSockets + Redis Pub/Sub |
| AI | LangChain + OpenAI (GPT-4o-mini) |
| Migrations | Alembic |
| Rate limiting | SlowAPI |

---

## Project Structure

```
fastapi-backend/
├── app/
│   ├── main.py                  ← FastAPI application factory
│   ├── api/v1/
│   │   ├── auth.py              ← POST /auth/signup, /login, /google, /refresh, GET /me
│   │   ├── users.py             ← GET /users/{username}, /users/search
│   │   ├── social.py            ← POST/DELETE /social/follow/{id}
│   │   ├── groups.py            ← Full group CRUD
│   │   ├── ai.py                ← POST /ai/outfit, /ai/travel-pack, /ai/chat
│   │   ├── closet.py            ← Full closet CRUD
│   │   └── router.py            ← Aggregate router
│   ├── core/
│   │   ├── config.py            ← Pydantic Settings (reads .env)
│   │   ├── security.py          ← JWT + bcrypt
│   │   ├── deps.py              ← FastAPI dependency injection
│   │   └── middleware.py        ← CORS, rate-limiting, request ID
│   ├── db/
│   │   ├── base.py              ← DeclarativeBase
│   │   ├── session.py           ← Async engine + session factory
│   │   └── init_db.py           ← create_all_tables()
│   ├── models/                  ← SQLAlchemy ORM models
│   │   ├── user.py              ← User, RefreshToken
│   │   ├── social.py            ← Follow
│   │   ├── group.py             ← Group, GroupMember
│   │   └── closet.py            ← ClosetItem, Outfit
│   ├── schemas/                 ← Pydantic request/response models
│   ├── services/                ← Business logic layer
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   ├── social_service.py
│   │   ├── group_service.py
│   │   ├── ai_service.py        ← LangChain + AI service proxy
│   │   └── cache_service.py     ← Redis abstraction
│   └── websockets/
│       ├── manager.py           ← ConnectionManager + Redis pub/sub
│       └── handlers.py          ← WS endpoint logic
├── alembic/                     ← Database migrations
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Quick Start

### Option A: Docker (recommended)

```bash
cd fastapi-backend
cp .env.example .env
# Edit .env — set SECRET_KEY and OPENAI_API_KEY at minimum

docker-compose up --build
```

API available at: http://localhost:8000  
Swagger docs: http://localhost:8000/docs

---

### Option B: Local (requires PostgreSQL + Redis running)

```bash
cd fastapi-backend

# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your DATABASE_URL, REDIS_URL, SECRET_KEY, OPENAI_API_KEY

# 4. Start PostgreSQL and Redis (if not using Docker)
# PostgreSQL: createdb clozehive
# Redis: redis-server

# 5. Run the server
python -m app.main
# or
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Database Migrations (Alembic)

```bash
# Create a new migration after model changes
alembic revision --autogenerate -m "describe your change"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1

# View migration history
alembic history
```

> In development, `create_all_tables()` runs on startup automatically.
> In production, set `APP_ENV=production` and run `alembic upgrade head` before deploying.

---

## API Reference & curl Examples

### 🔐 Authentication

#### Sign up
```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Phani Reddy",
    "email": "phani@example.com",
    "username": "phanireddy",
    "password": "SecurePass123"
  }'
```

**Response:**
```json
{
  "user": {
    "id": 1,
    "name": "Phani Reddy",
    "username": "phanireddy",
    "email": "phani@example.com"
  },
  "tokens": {
    "access_token": "eyJ...",
    "refresh_token": "eyJ...",
    "token_type": "bearer"
  }
}
```

#### Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"identifier": "phanireddy", "password": "SecurePass123"}'
```

#### Get current user
```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer eyJ..."
```

#### Refresh tokens
```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```

#### Update profile
```bash
curl -X PATCH http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"bio": "Fashion lover & minimalist.", "name": "Phani R"}'
```

---

### 👤 Users

#### Get profile by username
```bash
curl http://localhost:8000/api/v1/users/phanireddy \
  -H "Authorization: Bearer eyJ..."
```

#### Search users
```bash
curl "http://localhost:8000/api/v1/users/search?q=phani" \
  -H "Authorization: Bearer eyJ..."
```

---

### 👥 Social (Follow)

#### Follow a user
```bash
curl -X POST http://localhost:8000/api/v1/social/follow/2 \
  -H "Authorization: Bearer eyJ..."
```

**Response:**
```json
{"following": true, "follower_count": 42}
```

#### Unfollow a user
```bash
curl -X DELETE http://localhost:8000/api/v1/social/follow/2 \
  -H "Authorization: Bearer eyJ..."
```

#### Get followers
```bash
curl http://localhost:8000/api/v1/social/followers/1 \
  -H "Authorization: Bearer eyJ..."
```

#### Get following
```bash
curl http://localhost:8000/api/v1/social/following/1 \
  -H "Authorization: Bearer eyJ..."
```

---

### 👨‍👩‍👧 Groups

#### Create a group
```bash
curl -X POST http://localhost:8000/api/v1/groups/ \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Minimalist Wardrobe Club",
    "description": "For fans of capsule wardrobes",
    "is_public": true
  }'
```

#### Join via invite code
```bash
curl -X POST http://localhost:8000/api/v1/groups/join \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"invite_code": "A3B7F2E1"}'
```

#### Get group details
```bash
curl http://localhost:8000/api/v1/groups/1 \
  -H "Authorization: Bearer eyJ..."
```

#### Invite a member (admin only)
```bash
curl -X POST http://localhost:8000/api/v1/groups/1/invite \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"user_id": 3}'
```

#### Promote to admin
```bash
curl -X PATCH http://localhost:8000/api/v1/groups/1/members/3/role \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```

#### Remove member (admin only)
```bash
curl -X DELETE http://localhost:8000/api/v1/groups/1/members/3 \
  -H "Authorization: Bearer eyJ..."
```

#### Leave group
```bash
curl -X DELETE http://localhost:8000/api/v1/groups/1/leave \
  -H "Authorization: Bearer eyJ..."
```

---

### 🤖 AI Features

#### Generate outfit (JSON)
```bash
curl -X POST http://localhost:8000/api/v1/ai/outfit \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "occasion": "casual Friday at office",
    "weather": "sunny 22°C",
    "preferences": "minimalist, neutral tones",
    "closet_items": [
      {"name": "White Oxford Shirt", "category": "tops"},
      {"name": "Navy Chinos", "category": "bottoms"},
      {"name": "White Sneakers", "category": "shoes"}
    ]
  }'
```

**Response:**
```json
{
  "outfits": [
    {
      "name": "Smart Casual Friday",
      "items": [
        {"name": "White Oxford Shirt", "category": "tops", "why": "Clean and professional"},
        {"name": "Navy Chinos", "category": "bottoms", "why": "Elevated but relaxed"}
      ],
      "style_notes": "Roll the sleeves for a casual Friday vibe"
    }
  ],
  "explanation": "For a casual Friday in 22°C sunny weather...",
  "missing_items": ["Light jacket for air-conditioned office"]
}
```

#### Generate outfit (SSE stream)
```bash
curl -X POST http://localhost:8000/api/v1/ai/outfit/stream \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"occasion": "date night", "weather": "cool 18°C"}' \
  --no-buffer
```

#### Generate travel packing list
```bash
curl -X POST http://localhost:8000/api/v1/ai/travel-pack \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "destination": "Tokyo, Japan",
    "duration_days": 7,
    "activities": ["city touring", "temples", "food markets"],
    "weather": "mild 18°C, chance of rain"
  }'
```

#### AI Chat
```bash
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What should I wear to a job interview at a tech startup?",
    "history": []
  }'
```

---

### 👗 Closet

#### List items
```bash
curl http://localhost:8000/api/v1/closet/ \
  -H "Authorization: Bearer eyJ..."
```

#### Add item
```bash
curl -X POST http://localhost:8000/api/v1/closet/ \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{
    "name": "White Oxford Shirt",
    "category": "tops",
    "color": "white",
    "brand": "Uniqlo",
    "tags": ["formal", "office", "classic"]
  }'
```

#### Update item
```bash
curl -X PATCH http://localhost:8000/api/v1/closet/1 \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"color": "off-white", "tags": ["formal", "classic", "spring"]}'
```

#### Delete item
```bash
curl -X DELETE http://localhost:8000/api/v1/closet/1 \
  -H "Authorization: Bearer eyJ..."
```

---

### ⚡ WebSocket

Connect:
```javascript
const token = localStorage.getItem("clozehive_token");
const ws = new WebSocket(`ws://localhost:8000/ws/1?token=${token}`);

ws.onopen = () => console.log("Connected");
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  // msg.type: "connected" | "follower_update" | "group_update" | "user_login" | "ping" | "pong"
  console.log(msg);
};

// Ping
ws.send(JSON.stringify({ type: "ping" }));
```

Server events you'll receive:
```json
// Someone followed you
{"type": "follower_update", "follower_count": 43, "actor_id": 5, "action": "follow"}

// Group member joined
{"type": "member_joined", "user_id": 5, "group_id": 2}

// Another user logged in (broadcast)
{"type": "user_login", "username": "alice", "name": "Alice Smith"}
```

---

### 🏥 Health Check

```bash
curl http://localhost:8000/health
# {"status": "ok", "version": "1.0.0", "redis": "ok"}
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | ✅ | — | 64-char random hex for JWT signing |
| `DATABASE_URL` | ✅ | — | `postgresql+asyncpg://user:pass@host/db` |
| `SYNC_DATABASE_URL` | ✅ | — | `postgresql+psycopg2://...` (Alembic) |
| `REDIS_URL` | — | `redis://localhost:6379/0` | Redis connection |
| `OPENAI_API_KEY` | ✅ | — | For AI features |
| `AI_SERVICE_URL` | — | `http://localhost:8001` | Existing AI service |
| `ALLOWED_ORIGINS` | — | localhost ports | Comma-separated CORS origins |
| `APP_ENV` | — | `development` | `development` or `production` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | — | `15` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | — | `7` | Refresh token TTL |

Generate a secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Frontend Integration

The existing Node.js backend at `http://localhost:3001` is still active.
This FastAPI backend runs in parallel at `http://localhost:8000`.

Update your frontend `src/lib/api.ts` base URL:
```typescript
// Use FastAPI backend
const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1"
```

Or keep using the Node.js backend — both are compatible with the same JWT format.
