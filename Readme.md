# ClozeHive

Canonical architecture:

- `frontend` — React + Vite
- `services/api-gateway` — public FastAPI API layer
- `services/ai-agent` — FastAPI + LangGraph AI orchestration
- `services/mcp/*` — independent MCP tool services

Legacy stacks were archived under `archive/legacy-2026-04-28`.

## Local Development

```sh
docker compose up --build
```

Health checks:

```sh
curl http://localhost:8000/health      # API gateway
curl http://localhost:8001/health      # AI agent
curl http://localhost:3001             # Frontend
```

For non-Docker development, start dependencies first, then run:

```sh
npm run dev:api
npm run dev:agent
npm run dev:frontend
```


Architecture:

frontend
  -> services/api-gateway
      -> Postgres
      -> Redis
      -> services/ai-agent
            -> services/mcp/weather
            -> services/mcp/vision
            -> services/mcp/outfit
            -> services/mcp/packing

Technology:

React + Vite + TypeScript + Tailwind
Responsibilities:

User login/signup
Dashboard
Closet management
Image upload
AI stylist chat
Travel packing planner
Social/groups/profile pages
Streaming AI responses through API gateway
Frontend talks only to the API gateway:


VITE_API_URL=http://localhost:8000
Frontend API base = /api/v1


2. API Gateway
Path:

services/api-gateway/
Technology:

FastAPI + SQLAlchemy async + Alembic + Redis
Responsibilities:

Public API layer
Authentication and JWT handling
User/session management
Closet CRUD
Social/group APIs
File upload handling
AI request proxying
SSE streaming to frontend
WebSocket endpoint
Rate limiting
Redis caching
Database access
Main routers:

/api/v1/auth
/api/v1/closet
/api/v1/social
/api/v1/ai
/api/v1/ws
Internal layering:

app/api/v1/        -> routes/controllers
app/services/      -> business logic
app/repositories/  -> database access
app/models/        -> SQLAlchemy models
app/schemas/       -> Pydantic request/response schemas
app/core/          -> config, security, logging, exceptions
app/db/            -> DB session/base
3. AI Agent
Path:

services/ai-agent/
Technology:

FastAPI + LangGraph + LangChain + OpenAI + MCP client
Responsibilities:

AI orchestration only
Loads MCP tools
Runs wardrobe stylist agent
Streams real model tokens
Calls tool services for weather, vision, outfit, and packing
Uses pgvector retrieval context when available
Endpoints:

/api/v1/agent/chat
/api/v1/agent/chat/stream
/api/v1/agent/outfit
/api/v1/agent/packing
/api/v1/agent/vision/analyze
Flow:

API Gateway
  -> AI Agent
      -> LangGraph agent
          -> MCP tools
          -> OpenAI model
          -> optional vector search context
4. MCP Tool Services
Path:

services/mcp/
Each MCP service has a single responsibility and runs independently over SSE.

services/mcp/weather
services/mcp/vision
services/mcp/outfit
services/mcp/packing
Weather MCP
Responsibilities:

Weather forecast
Weather summary for trips
Used by packing planner
Tools:

get_weather_forecast
get_weather_summary
Vision MCP
Responsibilities:

Analyze clothing images
Extract item metadata
Return category, color, material, pattern, occasion, tags, notes
Used when uploading closet images.

Outfit MCP
Responsibilities:

Generate outfit combinations
Style tips
Weather-aware outfit suggestions
Packing MCP
Responsibilities:

Travel packing list generation
Daily outfit plan
Missing item detection
Weather-aware packing recommendations
Data Layer
Postgres
Used as the main database.

Stores:

Users
Credentials
Refresh tokens
Closet items
Outfits
Social follows
Groups
Group members
Vector embeddings
Important additions:

pgcrypto -> UUID generation
pg_trgm  -> scalable fuzzy user search
pgvector -> semantic wardrobe/vector search
Redis
Used for:

Cache
Rate limiting
WebSocket Pub/Sub
Cross-instance broadcast
AI/session support
Redis keys are namespaced:

clozehive:v1:profile:{user_id}
clozehive:v1:closet:{user_id}
clozehive:v1:social:{kind}:{user_id}
clozehive:v1:weather:{destination}:{start}:{end}
clozehive:v1:ws:user:{user_id}
clozehive:v1:ws:broadcast
Request Flow
Login Flow
Frontend
  -> API Gateway /api/v1/auth/login
      -> Postgres users + credentials
      -> returns access token + refresh token
  -> Frontend stores token
Closet Flow
Frontend
  -> API Gateway /api/v1/closet
      -> ClosetService
          -> ClosetRepository
              -> Postgres
      -> Redis cache for list responses
Image Upload Flow
Frontend uploads garment image
  -> API Gateway /api/v1/closet/upload
      -> AI Agent /api/v1/agent/vision/analyze
          -> Vision MCP
              -> OpenAI Vision
      -> API Gateway creates closet item in Postgres
      -> Redis closet cache invalidated
AI Chat Streaming Flow
Frontend SSE request
  -> API Gateway /api/v1/ai/chat/stream
      -> AI Agent /api/v1/agent/chat/stream
          -> LangGraph agent
              -> OpenAI streaming model
              -> optional MCP tools
              -> optional pgvector wardrobe context
      -> API Gateway streams tokens back to frontend
Travel Packing Flow
Frontend travel planner
  -> API Gateway /api/v1/ai/packing
      -> AI Agent /api/v1/agent/packing
          -> Weather MCP
          -> Packing MCP
              -> OpenAI summary if key exists
      -> structured packing result
WebSocket Flow
Frontend WebSocket
  -> API Gateway /api/v1/ws?token=JWT
      -> validates JWT
      -> local socket connection
      -> Redis Pub/Sub for cross-instance broadcast
This means multiple API gateway replicas can publish messages to each other through Redis.

DevOps Architecture
Docker Compose
Main services:

postgres
redis
mcp-weather
mcp-vision
mcp-outfit
mcp-packing
ai-agent
api-gateway
migrate
frontend
nginx
Run:

docker compose up --build
Default ports:

Frontend:    http://localhost:3001
API Gateway: http://localhost:8000
AI Agent:    http://localhost:8001
Weather MCP: http://localhost:8010
Vision MCP:  http://localhost:8011
Outfit MCP:  http://localhost:8012
Packing MCP: http://localhost:8013
Nginx:       http://localhost
Nginx
Path:

infra/nginx/nginx.conf
Responsibilities:

Reverse proxy
Static frontend proxy
API proxy
WebSocket proxy
Gzip
Security headers
Rate limit zones
Structured access logs
Production Scaling Strategy
For 10k+ concurrent users:

Load Balancer / CDN
  -> Frontend static hosting
  -> Nginx / API Gateway replicas
      -> Postgres primary + read replicas
      -> Redis HA / managed Redis
      -> AI Agent replicas
          -> MCP service replicas
Key scaling choices:

API gateway is stateless except WebSockets.
WebSockets use Redis Pub/Sub to work across instances.
Redis-backed rate limiting avoids per-process limits.
Uploads should eventually move from local volume to S3/object storage.
AI requests should be queue-backed for long-running work.
pgvector works for early scale; Qdrant/Weaviate/Pinecone can replace it later if vector load grows.
Recommended Event-Driven Layer
For future production scale, add Kafka or Redpanda.

Suggested events:

item_uploaded
image_analyzed
outfit_generated
trip_planned
recommendation_requested
Example event flow:

item_uploaded
  -> vision analysis worker
  -> embedding worker
  -> recommendation worker
This would reduce synchronous load on the API gateway and make AI workflows more reliable.

Final Architecture Summary
Frontend
  -> API Gateway
      -> Auth Service
      -> Closet Service
      -> Social Service
      -> AI Proxy Service
      -> Redis Cache / PubSub / Rate Limit
      -> Postgres + pgvector
      -> AI Agent
          -> LangGraph Orchestration
          -> Vector Retrieval
          -> MCP Weather
          -> MCP Vision
          -> MCP Outfit
          -> MCP Packing
          -> OpenAI
This is a modular-monolith plus AI microservices architecture: the API gateway keeps core product logic together, while heavy AI/tool responsibilities are split into independent MCP services.
