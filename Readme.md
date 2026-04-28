Here’s a **clean, professional, production-ready `README.md`** based on your content. I’ve structured it so it’s readable for GitHub, recruiters, and contributors 👇

---

# 🚀 ClozeHive

A scalable AI-powered wardrobe and lifestyle platform built with a modular architecture using FastAPI, LangGraph, and MCP services.

---

## 📦 Architecture Overview

ClozeHive follows a **modular-monolith + AI microservices architecture**:

```
Frontend
  → API Gateway
      → Postgres
      → Redis
      → AI Agent
          → MCP Services (weather, vision, outfit, packing)
```

---

## 🧱 Core Components

### 🔹 Frontend (`frontend/`)

* **Tech:** React + Vite + TypeScript + Tailwind
* **Responsibilities:**

  * User authentication (login/signup)
  * Dashboard & profile
  * Closet management
  * Image uploads
  * AI stylist chat
  * Travel planner
  * Social/groups features
  * Streaming AI responses

```env
VITE_API_URL=http://localhost:8000
```

👉 Frontend communicates **only with API Gateway**

---

### 🔹 API Gateway (`services/api-gateway/`)

* **Tech:** FastAPI + SQLAlchemy (async) + Alembic + Redis
* **Responsibilities:**

  * Public API layer
  * JWT authentication & session handling
  * Closet CRUD APIs
  * Social/group APIs
  * File uploads
  * AI request proxying
  * SSE streaming
  * WebSocket handling
  * Rate limiting & caching

#### Main Routes

```
/api/v1/auth
/api/v1/closet
/api/v1/social
/api/v1/ai
/api/v1/ws
```

#### Internal Structure

```
app/api/v1/        → controllers
app/services/      → business logic
app/repositories/  → DB access
app/models/        → ORM models
app/schemas/       → Pydantic schemas
app/core/          → config, security, logging
app/db/            → DB setup
```

---

### 🤖 AI Agent (`services/ai-agent/`)

* **Tech:** FastAPI + LangGraph + LangChain + OpenAI
* **Responsibilities:**

  * AI orchestration layer
  * Streaming LLM responses
  * Tool calling (MCP services)
  * Outfit, packing, and vision analysis

#### Endpoints

```
/api/v1/agent/chat
/api/v1/agent/chat/stream
/api/v1/agent/outfit
/api/v1/agent/packing
/api/v1/agent/vision/analyze
```

---

### 🧩 MCP Tool Services (`services/mcp/`)

Each service is **independent + single responsibility**:

| Service | Purpose                 |
| ------- | ----------------------- |
| weather | Forecast + trip weather |
| vision  | Image analysis          |
| outfit  | Outfit generation       |
| packing | Travel packing          |

---

## 🗄️ Data Layer

### PostgreSQL

Stores:

* Users & credentials
* Closet items & outfits
* Social groups
* Vector embeddings

Extensions:

* `pgcrypto` → UUIDs
* `pg_trgm` → search
* `pgvector` → semantic search

---

### Redis

Used for:

* Cache
* Rate limiting
* WebSocket Pub/Sub
* Cross-instance communication

Example keys:

```
clozehive:v1:profile:{user_id}
clozehive:v1:closet:{user_id}
clozehive:v1:ws:broadcast
```

---

## 🔄 Request Flows

### 🔐 Login

```
Frontend → API Gateway → Postgres → JWT tokens
```

### 👕 Closet

```
Frontend → API → Service → Repository → Postgres
```

### 📸 Image Upload

```
Frontend → API → AI Agent → Vision MCP → OpenAI → Postgres
```

### 💬 AI Chat (Streaming)

```
Frontend → API → AI Agent → LLM → Stream back tokens
```

### 🧳 Travel Planner

```
Frontend → API → AI Agent → Weather + Packing MCP
```

### 🔌 WebSockets

```
Client → API Gateway → Redis Pub/Sub → Broadcast across instances
```

---

## 🐳 Local Development

### 🔹 Run with Docker

```bash
docker compose up --build
```

### 🔹 Services

| Service     | URL                                            |
| ----------- | ---------------------------------------------- |
| Frontend    | [http://localhost:3001](http://localhost:3001) |
| API Gateway | [http://localhost:8000](http://localhost:8000) |
| AI Agent    | [http://localhost:8001](http://localhost:8001) |
| Weather MCP | [http://localhost:8010](http://localhost:8010) |
| Vision MCP  | [http://localhost:8011](http://localhost:8011) |
| Outfit MCP  | [http://localhost:8012](http://localhost:8012) |
| Packing MCP | [http://localhost:8013](http://localhost:8013) |

---

### 🔹 Health Checks

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
```

---

### 🔹 Non-Docker Dev

```bash
npm run dev:api
npm run dev:agent
npm run dev:frontend
```

---

## 🌐 Nginx (Production Proxy)

Path:

```
infra/nginx/nginx.conf
```

Handles:

* Reverse proxy
* Static frontend
* API routing
* WebSockets
* Security headers
* Rate limiting

---

## 📈 Scaling Strategy (10K+ Users)

* Load balancer + CDN
* Stateless API Gateway (JWT-based)
* Redis for session + Pub/Sub
* Postgres read replicas
* AI Agent horizontal scaling
* MCP services scale independently

---

## ⚡ Future Improvements

### Event-Driven Architecture

Use:

* Apache Kafka
  or
* Redpanda

Events:

```
item_uploaded
image_analyzed
outfit_generated
trip_planned
recommendation_requested
```

---

## 🏁 Final Architecture

```
Frontend
  → API Gateway
      → Auth / Closet / Social
      → Redis
      → Postgres + pgvector
      → AI Agent
          → LangGraph
          → MCP Services
          → OpenAI
```

---

## 📂 Notes

* Legacy stacks moved to `archive/legacy-2026-04-28`
* Use `services/*` as the source of truth
* Designed for scalability + AI-first workflows

---

📄 Source: 

---

If you want, I can next:

✅ Add **badges + screenshots (GitHub-ready UI)**
✅ Add **setup with .env + auth instructions**
✅ Make this **ATS-friendly for portfolio / resume**

Just tell me 👍
