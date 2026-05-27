"""
Generate CLOZEHIVE Master Application Outline PDF
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import BalancedColumns
from reportlab.lib.colors import HexColor, white, black
import os

# ── Brand colours ──────────────────────────────────────────────────────────────
INDIGO       = HexColor("#4F46E5")
INDIGO_LIGHT = HexColor("#6366F1")
INDIGO_PALE  = HexColor("#EEF2FF")
VIOLET       = HexColor("#7C3AED")
TEAL         = HexColor("#0D9488")
SLATE_DARK   = HexColor("#1E293B")
SLATE_MID    = HexColor("#475569")
SLATE_LIGHT  = HexColor("#94A3B8")
BG_LIGHT     = HexColor("#F8FAFC")
GREEN        = HexColor("#059669")
AMBER        = HexColor("#D97706")
RED          = HexColor("#DC2626")

OUTPUT = "/Users/phanidharreddy/Desktop/my_project/Clozehive/CLOZEHIVE_Master_Outline.pdf"

# ── Document ───────────────────────────────────────────────────────────────────
doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=A4,
    rightMargin=1.8*cm, leftMargin=1.8*cm,
    topMargin=1.5*cm, bottomMargin=1.5*cm,
    title="CLOZEHIVE — Master Application Outline",
    author="Engineering Team",
)
W, H = A4
CONTENT_W = W - 3.6*cm

styles = getSampleStyleSheet()
story  = []

# ── Custom styles ──────────────────────────────────────────────────────────────

def sty(name, **kw):
    return ParagraphStyle(name, **kw)

cover_title = sty("CoverTitle",
    fontSize=36, leading=44, textColor=white,
    fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=6)

cover_sub = sty("CoverSub",
    fontSize=14, leading=18, textColor=HexColor("#C7D2FE"),
    fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4)

cover_tag = sty("CoverTag",
    fontSize=11, leading=14, textColor=HexColor("#E0E7FF"),
    fontName="Helvetica-Oblique", alignment=TA_CENTER)

section_header = sty("SectionHeader",
    fontSize=18, leading=24, textColor=white,
    fontName="Helvetica-Bold", alignment=TA_LEFT,
    spaceBefore=0, spaceAfter=0)

sub_header = sty("SubHeader",
    fontSize=12, leading=16, textColor=INDIGO,
    fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=4)

body = sty("Body",
    fontSize=9.5, leading=14, textColor=SLATE_DARK,
    fontName="Helvetica", spaceAfter=3)

body_sm = sty("BodySm",
    fontSize=8.5, leading=12, textColor=SLATE_MID,
    fontName="Helvetica", spaceAfter=2)

bullet_style = sty("Bullet",
    fontSize=9.5, leading=13, textColor=SLATE_DARK,
    fontName="Helvetica", leftIndent=12, spaceAfter=2,
    bulletIndent=0, bulletFontSize=9.5)

code_style = sty("Code",
    fontSize=8, leading=11, textColor=HexColor("#1D4ED8"),
    fontName="Courier", backColor=HexColor("#EFF6FF"),
    leftIndent=8, spaceAfter=2)

caption = sty("Caption",
    fontSize=8, leading=10, textColor=SLATE_LIGHT,
    fontName="Helvetica-Oblique", alignment=TA_CENTER)

toc_style = sty("TOC",
    fontSize=10, leading=16, textColor=SLATE_DARK,
    fontName="Helvetica")

toc_num = sty("TOCNum",
    fontSize=10, leading=16, textColor=INDIGO,
    fontName="Helvetica-Bold")


# ── Helpers ────────────────────────────────────────────────────────────────────

def hr(color=INDIGO_LIGHT, thickness=0.5):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=6, spaceBefore=4)

def sp(h=6):
    return Spacer(1, h)

def badge(text, bg=INDIGO, fg=white, w=None):
    """Inline coloured badge rendered as a 1-row table."""
    p = Paragraph(f'<font color="#{fg.hexval()[2:] if hasattr(fg,"hexval") else "FFFFFF"}">'
                  f'<b> {text} </b></font>', sty("B", fontSize=7.5, leading=10,
                  fontName="Helvetica-Bold", alignment=TA_CENTER))
    t = Table([[p]], colWidths=[w or (len(text)*6.5+12)], rowHeights=[14])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("ROUNDEDCORNERS", [3]),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 1),
        ("BOTTOMPADDING", (0,0), (-1,-1), 1),
    ]))
    return t

def section_banner(num, title, subtitle=""):
    """Full-width indigo banner for section headings."""
    rows = [[Paragraph(f"{num}. {title}", section_header)]]
    if subtitle:
        rows.append([Paragraph(subtitle, sty("SBSub", fontSize=9.5, leading=13,
            textColor=HexColor("#C7D2FE"), fontName="Helvetica"))])
    t = Table(rows, colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), INDIGO),
        ("LEFTPADDING",   (0,0), (-1,-1), 14),
        ("RIGHTPADDING",  (0,0), (-1,-1), 14),
        ("TOPPADDING",    (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    return t

def info_table(rows, col_widths=None, header=True):
    """Styled data table."""
    cw = col_widths or [CONTENT_W*0.38, CONTENT_W*0.62]
    t  = Table(rows, colWidths=cw, repeatRows=1 if header else 0)
    style = [
        ("FONTNAME",      (0,0), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,0), (-1,-1), 8.5),
        ("LEADING",       (0,0), (-1,-1), 12),
        ("TEXTCOLOR",     (0,0), (-1,-1), SLATE_DARK),
        ("ALIGN",         (0,0), (-1,-1), "LEFT"),
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0), (-1,-1), 7),
        ("RIGHTPADDING",  (0,0), (-1,-1), 7),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("ROWBACKGROUNDS",(0,0), (-1,-1), [white, BG_LIGHT]),
        ("GRID",          (0,0), (-1,-1), 0.3, HexColor("#E2E8F0")),
    ]
    if header:
        style += [
            ("BACKGROUND",  (0,0), (-1,0), INDIGO_PALE),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica-Bold"),
            ("TEXTCOLOR",   (0,0), (-1,0), INDIGO),
            ("FONTSIZE",    (0,0), (-1,0), 9),
        ]
    t.setStyle(TableStyle(style))
    return t

def two_col(items_left, items_right):
    """Render two lists side by side."""
    def fmt(items):
        return [Paragraph(f"<bullet>&bull;</bullet> {i}", bullet_style) for i in items]
    tbl = Table([[fmt(items_left), fmt(items_right)]],
                colWidths=[CONTENT_W*0.5 - 5, CONTENT_W*0.5 - 5])
    tbl.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 4),
        ("RIGHTPADDING", (0,0), (-1,-1), 4),
    ]))
    return tbl

def pill(text, color=TEAL):
    return Paragraph(
        f'<font color="#{color.hexval()[2:]}">[{text}]</font>',
        sty("Pill", fontSize=8, leading=11, fontName="Courier"))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — COVER
# ══════════════════════════════════════════════════════════════════════════════

cover_bg = Table(
    [[
        Paragraph("CLOZEHIVE", cover_title),
        Paragraph("AI-Powered Smart Wardrobe &amp; Personal Stylist Platform", cover_sub),
        Paragraph("Master Application Outline  ·  Engineering Reference  ·  v2.0", cover_tag),
    ]],
    colWidths=[CONTENT_W],
    rowHeights=[None],
)
# Wrap in a coloured banner
cover_wrap = Table(
    [[cover_bg]],
    colWidths=[CONTENT_W],
)
cover_wrap.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,-1), INDIGO),
    ("LEFTPADDING",   (0,0), (-1,-1), 20),
    ("RIGHTPADDING",  (0,0), (-1,-1), 20),
    ("TOPPADDING",    (0,0), (-1,-1), 28),
    ("BOTTOMPADDING", (0,0), (-1,-1), 28),
]))
story.append(cover_wrap)
story.append(sp(16))

# Tag-line cards
taglines = [
    ("AI-First", "LangGraph ReAct agent + 4 MCP tool servers", INDIGO),
    ("Event-Driven", "Redpanda / Kafka async processing pipeline", VIOLET),
    ("Full-Stack", "React + FastAPI + PostgreSQL + Redis", TEAL),
    ("Observable", "LangSmith tracing for every tool call", GREEN),
]
tag_rows = []
for label, desc, col in taglines:
    tag_rows.append(Table(
        [[Paragraph(f"<b>{label}</b>", sty("TL", fontSize=10, leading=13,
            textColor=col, fontName="Helvetica-Bold")),
          Paragraph(desc, sty("TD", fontSize=8.5, leading=12,
            textColor=SLATE_MID, fontName="Helvetica"))]],
        colWidths=[CONTENT_W*0.27, CONTENT_W*0.73],
    ))

tl_table = Table(
    [[tag_rows[0], sp(4), tag_rows[1]],
     [sp(4), sp(4), sp(4)],
     [tag_rows[2], sp(4), tag_rows[3]]],
    colWidths=[(CONTENT_W-8)*0.5, 8, (CONTENT_W-8)*0.5],
)
tl_table.setStyle(TableStyle([
    ("VALIGN", (0,0),(-1,-1),"TOP"),
    ("BACKGROUND",(0,0),(0,0), HexColor("#F5F3FF")),
    ("BACKGROUND",(2,0),(2,0), HexColor("#F5F3FF")),
    ("BACKGROUND",(0,2),(0,2), HexColor("#F0FDFB")),
    ("BACKGROUND",(2,2),(2,2), HexColor("#F0FDFB")),
    ("LEFTPADDING",(0,0),(-1,-1),10),
    ("RIGHTPADDING",(0,0),(-1,-1),10),
    ("TOPPADDING",(0,0),(-1,-1),8),
    ("BOTTOMPADDING",(0,0),(-1,-1),8),
    ("BOX",(0,0),(0,0),0.4,HexColor("#DDD6FE")),
    ("BOX",(2,0),(2,0),0.4,HexColor("#DDD6FE")),
    ("BOX",(0,2),(0,2),0.4,HexColor("#99F6E4")),
    ("BOX",(2,2),(2,2),0.4,HexColor("#99F6E4")),
]))
story.append(tl_table)
story.append(sp(18))

# ── Table of Contents ──────────────────────────────────────────────────────────
story.append(Paragraph("Table of Contents", sty("TOCHead",
    fontSize=14, leading=18, textColor=SLATE_DARK,
    fontName="Helvetica-Bold", spaceAfter=8)))
story.append(hr())

toc_entries = [
    ("1", "Product Overview",            "Application purpose, core value proposition"),
    ("2", "Architecture Overview",       "System diagram narrative, service topology"),
    ("3", "Services Deep-Dive",          "API Gateway, AI Agent, AI Worker, MCP Servers"),
    ("4", "Frontend Application",        "React pages, components, state management"),
    ("5", "Data Model",                  "PostgreSQL schema, ORM models, migrations"),
    ("6", "API Reference",               "All REST endpoints + WebSocket"),
    ("7", "AI & MCP Integration",        "LangGraph ReAct, tool calling, SSE streaming"),
    ("8", "Event-Driven Pipeline",       "Kafka topics, producer/consumer, async flow"),
    ("9", "Infrastructure & DevOps",     "Docker Compose, Nginx, Redis, pgvector"),
    ("10", "Observability",              "LangSmith tracing, structured logging"),
    ("11", "Security",                   "JWT auth, rate limiting, input validation"),
    ("12", "Tech Stack Summary",         "Full dependency inventory"),
]

for num, title, desc in toc_entries:
    row = Table(
        [[Paragraph(f"<b>{num}</b>", toc_num),
          Paragraph(title, sty("TT", fontSize=10, leading=14,
              textColor=SLATE_DARK, fontName="Helvetica-Bold")),
          Paragraph(desc, sty("TD2", fontSize=9, leading=13,
              textColor=SLATE_MID, fontName="Helvetica"))]],
        colWidths=[18, CONTENT_W*0.32, CONTENT_W*0.62],
    )
    row.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),3),
        ("BOTTOMPADDING",(0,0),(-1,-1),3),
        ("LINEBELOW",(0,0),(-1,-1),0.3,HexColor("#E2E8F0")),
    ]))
    story.append(row)

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — PRODUCT OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("1", "Product Overview",
    "What CLOZEHIVE does and why it exists"))
story.append(sp(10))

story.append(Paragraph("Vision Statement", sub_header))
story.append(Paragraph(
    "CLOZEHIVE is a full-stack, AI-first wardrobe management platform that transforms "
    "the way people interact with their clothing. Using GPT-4o vision and a network of "
    "specialised MCP microservices, it provides intelligent outfit recommendations, "
    "AI-powered packing lists, real-time weather-aware styling, and social wardrobe sharing — "
    "all in a single, coherent product.",
    body))
story.append(sp(8))

story.append(Paragraph("Core Feature Modules", sub_header))
features = [
    ("Smart Wardrobe", "Digital closet with image upload, AI auto-tagging (color, fabric, season, eco-score), wear tracking, and category management."),
    ("AI Stylist Chat", "Conversational interface powered by a LangGraph ReAct agent. The agent calls weather, outfit, packing, and vision MCP tools autonomously."),
    ("Outfit Generator", "AI-generated outfit suggestions based on occasion, weather conditions, and temperature using the user's actual closet items."),
    ("Travel Planner", "End-to-end trip packing assistant: inputs destination + dates, fetches live weather, matches closet items, generates daily outfit plans."),
    ("Vision Upload", "Drag-and-drop garment image upload. GPT-4o Vision auto-detects name, category, color, fabric, pattern, season, occasion, eco-score."),
    ("Social Layer", "Follow/unfollow system, user profiles with closet previews, invite-code style-groups with owner/admin/member roles."),
    ("Wear Logging", "Track outfit sessions (multiple items worn together), view history per item, bumps wear_count and last_worn automatically."),
    ("Analytics Dashboard", "Wardrobe utilisation, most-worn items, eco-score trends, cost-per-wear metrics."),
]
feat_rows = [["Feature", "Description"]]
for f, d in features:
    feat_rows.append([Paragraph(f"<b>{f}</b>", body), Paragraph(d, body_sm)])
story.append(info_table(feat_rows, [CONTENT_W*0.24, CONTENT_W*0.76]))
story.append(sp(10))

story.append(Paragraph("User Personas", sub_header))
personas = [
    ("Fashion-Conscious User", "Wants AI outfit advice, builds curated looks, tracks what's overused."),
    ("Frequent Traveller",     "Needs smart packing lists tailored to destination weather and trip purpose."),
    ("Sustainable Shopper",    "Tracks eco-scores, longevity tips, upcycling suggestions per garment."),
    ("Social Stylist",         "Shares wardrobe publicly, joins style groups, follows other users."),
]
p_rows = [["Persona", "Primary Need"]]
for p, n in personas:
    p_rows.append([Paragraph(f"<b>{p}</b>", body), Paragraph(n, body_sm)])
story.append(info_table(p_rows, [CONTENT_W*0.3, CONTENT_W*0.7]))

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — ARCHITECTURE OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("2", "Architecture Overview",
    "Service topology and data flow"))
story.append(sp(10))

story.append(Paragraph("System Topology", sub_header))
story.append(Paragraph(
    "CLOZEHIVE follows a <b>microservices event-driven architecture</b> with a clear separation "
    "between the request path (synchronous REST/SSE) and the async processing pipeline "
    "(Kafka events). All services communicate via HTTP internally; the message bus is "
    "Redpanda (Kafka-compatible).",
    body))
story.append(sp(8))

# Architecture diagram (text-based)
arch_data = [
    ["Layer", "Component", "Technology", "Port"],
    ["Client", "Web Browser", "React 18 + Vite + TypeScript", "—"],
    ["Edge", "Nginx Reverse Proxy", "nginx:alpine, rate limiting, WebSocket upgrade", "80"],
    ["Frontend", "SPA Server", "Node serve, React Router SPA fallback", "3001"],
    ["API Layer", "API Gateway", "FastAPI 0.111, asyncpg, SQLAlchemy 2.0", "8000"],
    ["AI Layer", "AI Agent Service", "FastAPI, LangGraph, LangChain, MultiServerMCPClient", "8001"],
    ["AI Layer", "AI Worker", "AIOKafka consumer, asyncpg result writer", "—"],
    ["MCP Tools", "Weather MCP", "FastMCP SSE, climate profile DB + OpenAI", "8010"],
    ["MCP Tools", "Vision MCP", "FastMCP SSE, GPT-4o Vision", "8011"],
    ["MCP Tools", "Outfit MCP", "FastMCP SSE, GPT-4o outfit generation", "8012"],
    ["MCP Tools", "Packing MCP", "FastMCP SSE, daily plan + recommendations", "8013"],
    ["Data", "PostgreSQL + pgvector", "pgvector/pgvector:pg16, vector similarity search", "5433"],
    ["Data", "Redis", "redis:7-alpine, cache + Pub/Sub fan-out", "6382"],
    ["Messaging", "Redpanda", "Kafka-compatible, 6 topics, 6 partitions each", "19092"],
    ["Observability", "LangSmith", "Distributed tracing for all LangGraph runs", "Cloud"],
    ["Observability", "Redpanda Console", "Kafka topic browser UI", "8080"],
]
arch_rows_fmt = [[
    Paragraph(r[0], sty("AH", fontSize=8.5, leading=12, fontName="Helvetica-Bold" if i==0 else "Helvetica", textColor=INDIGO if i==0 else SLATE_DARK)),
    Paragraph(r[1], sty("AH2", fontSize=8.5, leading=12, fontName="Helvetica-Bold" if i==0 else "Helvetica", textColor=INDIGO if i==0 else SLATE_DARK)),
    Paragraph(r[2], sty("AH3", fontSize=8, leading=11, fontName="Helvetica", textColor=SLATE_MID if i>0 else INDIGO)),
    Paragraph(r[3], sty("AH4", fontSize=8.5, leading=12, fontName="Courier" if i>0 else "Helvetica-Bold", textColor=TEAL if i>0 else INDIGO)),
] for i, r in enumerate(arch_data)]

arch_tbl = Table(arch_rows_fmt, colWidths=[CONTENT_W*0.14, CONTENT_W*0.22, CONTENT_W*0.50, CONTENT_W*0.14], repeatRows=1)
arch_tbl.setStyle(TableStyle([
    ("FONTNAME",      (0,0),(-1,-1),"Helvetica"),
    ("FONTSIZE",      (0,0),(-1,-1),8.5),
    ("VALIGN",        (0,0),(-1,-1),"TOP"),
    ("ALIGN",         (3,0),(-1,-1),"CENTER"),
    ("BACKGROUND",    (0,0),(-1,0), INDIGO_PALE),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[white, BG_LIGHT]),
    ("GRID",          (0,0),(-1,-1), 0.3, HexColor("#E2E8F0")),
    ("TOPPADDING",    (0,0),(-1,-1),5),
    ("BOTTOMPADDING", (0,0),(-1,-1),5),
    ("LEFTPADDING",   (0,0),(-1,-1),6),
]))
story.append(arch_tbl)
story.append(sp(10))

story.append(Paragraph("Request Flow — Synchronous (SSE Chat)", sub_header))
flow_steps = [
    ("1", "User types message in AIStylist page", "Browser → Nginx (port 80)"),
    ("2", "Nginx proxies to API Gateway",          "POST /api/v1/ai/chat/stream"),
    ("3", "Gateway fetches user's closet items",   "PostgreSQL query via SQLAlchemy async"),
    ("4", "Gateway streams request to AI Agent",   "POST /api/v1/agent/chat/stream (HTTP SSE)"),
    ("5", "Agent invokes LangGraph ReAct loop",    "create_react_agent with 8 MCP tools"),
    ("6", "Agent calls MCP tool(s) as needed",     "e.g. get_weather_forecast → mcp-weather:8010/sse"),
    ("7", "Tokens stream back to browser",         "text/event-stream → ReadableStream → React state"),
]
fl_rows = [["Step", "Action", "Details"]]
for s, a, d in flow_steps:
    fl_rows.append([
        Paragraph(f"<b>{s}</b>", sty("FS", fontSize=9, leading=12, fontName="Helvetica-Bold", textColor=INDIGO, alignment=TA_CENTER)),
        Paragraph(a, body),
        Paragraph(d, body_sm),
    ])
story.append(info_table(fl_rows, [CONTENT_W*0.07, CONTENT_W*0.40, CONTENT_W*0.53]))

story.append(sp(10))
story.append(Paragraph("Request Flow — Asynchronous (Kafka)", sub_header))
async_steps = [
    ("1", "Client POST /ai/chat/async",              "Returns {request_id, status:'queued'} immediately"),
    ("2", "Gateway publishes EventEnvelope to Kafka", "Topic: ai.chat.requested, key=user_id"),
    ("3", "AI Worker consumes event",                 "AIOKafka consumer group: ai-worker"),
    ("4", "Worker calls AI Agent HTTP API",           "POST /api/v1/agent/chat with payload"),
    ("5", "Worker writes result to ai_requests table","PostgreSQL upsert with result_payload"),
    ("6", "Client polls GET /ai/requests/{id}",       "Or subscribes via WebSocket for push"),
    ("7", "WebSocket fan-out via Redis Pub/Sub",      "All gateway instances receive the result"),
]
as_rows = [["Step", "Action", "Details"]]
for s, a, d in async_steps:
    as_rows.append([
        Paragraph(f"<b>{s}</b>", sty("AS", fontSize=9, leading=12, fontName="Helvetica-Bold", textColor=VIOLET, alignment=TA_CENTER)),
        Paragraph(a, body),
        Paragraph(d, body_sm),
    ])
story.append(info_table(as_rows, [CONTENT_W*0.07, CONTENT_W*0.40, CONTENT_W*0.53]))

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — SERVICES DEEP-DIVE
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("3", "Services Deep-Dive",
    "Internal structure of every backend service"))
story.append(sp(10))

# 3.1 API Gateway
story.append(Paragraph("3.1  API Gateway  (services/api-gateway)", sub_header))
story.append(Paragraph(
    "The API Gateway is the single entry point for all client requests. "
    "It handles authentication, request routing, database access, caching, "
    "Kafka event publishing, and WebSocket management.",
    body))
story.append(sp(6))

gw_modules = [
    ["Module / File",              "Responsibility"],
    ["app/main.py",                "FastAPI factory, lifespan (DB pool, Kafka producer, result listener, migrations)"],
    ["app/api/v1/auth.py",         "Signup, login, refresh token rotation, /me CRUD, change-password, logout"],
    ["app/api/v1/closet.py",       "CRUD, /upload with vision AI, /wear-log session, /{id}/wear-history"],
    ["app/api/v1/ai.py",           "Chat/outfit/packing stream + async endpoints, vision analyze, request polling"],
    ["app/api/v1/social.py",       "Follow/unfollow, profiles, groups (create/join/leave/manage roles)"],
    ["app/api/v1/ws.py",           "WebSocket /ws — JWT handshake, Redis Pub/Sub subscription, result push"],
    ["app/models/user.py",         "User, UserCredential, RefreshToken ORM models"],
    ["app/models/closet.py",       "ClosetItem, Outfit ORM models (pgvector-ready)"],
    ["app/models/social.py",       "Follow, Group, GroupMember ORM models"],
    ["app/repositories/base.py",   "Generic async CRUD: get, list, count, create, update, delete, exists"],
    ["app/services/auth_service.py","JWT HS256 create/verify, bcrypt hashing, refresh token rotation"],
    ["app/services/cache_service.py","Redis GET/SET/DELETE with JSON serialisation, closet_key() helper"],
    ["app/services/ai_client.py",  "HTTP client to AI Agent: chat, stream_chat, generate_outfits, packing, vision"],
    ["app/events/producer.py",     "AIOKafka async producer, best-effort no-op when Kafka disabled"],
    ["app/events/result_listener.py","AIOKafka consumer → Redis Pub/Sub broadcast on ai_results topics"],
    ["app/middleware/logging.py",  "Structlog request/response middleware with request_id injection"],
]
story.append(info_table(gw_modules, [CONTENT_W*0.36, CONTENT_W*0.64]))
story.append(sp(10))

# 3.2 AI Agent
story.append(Paragraph("3.2  AI Agent Service  (services/ai-agent)", sub_header))
story.append(Paragraph(
    "Stateful LangGraph agent that holds one persistent MultiServerMCPClient connection "
    "to all four MCP servers. Exposes both synchronous (JSON) and streaming (SSE) endpoints.",
    body))
story.append(sp(6))

agent_modules = [
    ["Module / File",                   "Responsibility"],
    ["app/agent/wardrobe_agent.py",     "WardrobeAgent class: start(), stop(), chat(), stream_chat(). Uses create_react_agent with state_modifier system prompt."],
    ["app/agent/prompts.py",            "WARDROBE_AGENT_SYSTEM_PROMPT — role, tool usage guidance, output format rules"],
    ["app/api/v1/agent.py",             "Routes: /agent/chat, /agent/chat/stream, /agent/outfit, /agent/packing, /agent/vision/analyze"],
    ["app/services/vector_store.py",    "pgvector similarity search for closet context injection"],
    ["app/core/config.py",              "Settings: MCP URLs, OpenAI model, timeout, retry, LangSmith vars"],
]
story.append(info_table(agent_modules, [CONTENT_W*0.33, CONTENT_W*0.67]))
story.append(sp(6))

agent_tools = [
    ["MCP Tool",                        "Server",       "Capability"],
    ["get_weather_forecast",            "mcp-weather",  "Day-by-day forecast for a destination and date range"],
    ["get_weather_summary",             "mcp-weather",  "Dominant condition, avg temp, rainy-day count, packing recommendation"],
    ["analyze_clothing_image",          "mcp-vision",   "GPT-4o Vision: name, category, color, fabric, pattern, eco-score"],
    ["analyze_clothing_from_bytes",     "mcp-vision",   "Base64 image input variant"],
    ["generate_outfit_suggestions",     "mcp-outfit",   "GPT-4o outfit builder from closet items + occasion + weather"],
    ["get_outfit_style_tips",           "mcp-outfit",   "Style advice for a specific occasion/weather combo"],
    ["generate_trip_packing_list",      "mcp-packing",  "Full PackingResult: packing_list, daily_plan, weather_summary, recommendations"],
    ["get_packing_checklist",           "mcp-packing",  "Simplified checklist by category"],
]
story.append(info_table(agent_tools, [CONTENT_W*0.34, CONTENT_W*0.18, CONTENT_W*0.48]))
story.append(sp(10))

# 3.3 AI Worker
story.append(Paragraph("3.3  AI Worker  (services/ai-worker)", sub_header))
story.append(Paragraph(
    "Async Kafka consumer that bridges the event bus to the AI Agent. "
    "Writes results to the ai_requests table and publishes to result topics for WebSocket fan-out.",
    body))
story.append(sp(4))
story.append(two_col(
    ["Consumes topics: ai.chat.requested, ai.outfit.requested, ai.trip.planned, ai.image.uploaded",
     "Idempotency via processed_events table — survives restart without double-processing",
     "Calls AI Agent REST API with event payload",],
    ["Writes result/error to ai_requests table via asyncpg",
     "Publishes completion to ai_response_stream / outfit_generated / packing_ready topics",
     "Consumer group: ai-worker (3 instances can scale horizontally)",]
))
story.append(sp(10))

# 3.4 MCP Servers
story.append(Paragraph("3.4  MCP Microservices  (services/mcp/)", sub_header))
story.append(Paragraph(
    "Each MCP server is a FastMCP SSE server exposing tools over the Model Context Protocol. "
    "The AI Agent connects to all four simultaneously via MultiServerMCPClient.",
    body))
story.append(sp(6))
mcp_detail = [
    ["Server",      "Port", "Tools Exposed",                                         "Key Logic"],
    ["mcp-weather", "8010", "get_weather_forecast\nget_weather_summary",             "Climate profile database (25 cities). Generates realistic forecast data. Summarises to dominant condition + recommendation."],
    ["mcp-vision",  "8011", "analyze_clothing_image\nanalyze_clothing_from_bytes",   "GPT-4o Vision with structured JSON output. Returns: name, category, color, material, pattern, season, occasion, eco_score, longevity_tips, upcycling_suggestions."],
    ["mcp-outfit",  "8012", "generate_outfit_suggestions\nget_outfit_style_tips",    "GPT-4o outfit builder. Accepts closet_items[], occasion, weather, temperature. Returns scored OutfitSuggestion list with style_notes."],
    ["mcp-packing", "8013", "generate_trip_packing_list\nget_packing_checklist",     "Builds PackingResult: packing_list (with closet matches), daily_plan (per-day outfit), weather_summary, 3-6 smart recommendations."],
]
mcp_rows = []
for i, r in enumerate(mcp_detail):
    mcp_rows.append([
        Paragraph(f"<b>{r[0]}</b>", sty("MC", fontSize=8.5, leading=12, fontName="Helvetica-Bold" if i==0 else "Courier", textColor=TEAL if i>0 else INDIGO)),
        Paragraph(r[1], sty("MP", fontSize=8.5, leading=12, fontName="Courier" if i>0 else "Helvetica-Bold", textColor=TEAL if i>0 else INDIGO, alignment=TA_CENTER)),
        Paragraph(r[2].replace("\n","<br/>"), body_sm),
        Paragraph(r[3], body_sm),
    ])
mcp_tbl = Table(mcp_rows, colWidths=[CONTENT_W*0.15, CONTENT_W*0.08, CONTENT_W*0.27, CONTENT_W*0.50], repeatRows=1)
mcp_tbl.setStyle(TableStyle([
    ("FONTNAME",     (0,0),(-1,-1),"Helvetica"),
    ("FONTSIZE",     (0,0),(-1,-1),8.5),
    ("VALIGN",       (0,0),(-1,-1),"TOP"),
    ("BACKGROUND",   (0,0),(-1,0), INDIGO_PALE),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[white, BG_LIGHT]),
    ("GRID",         (0,0),(-1,-1), 0.3, HexColor("#E2E8F0")),
    ("TOPPADDING",   (0,0),(-1,-1),5),
    ("BOTTOMPADDING",(0,0),(-1,-1),5),
    ("LEFTPADDING",  (0,0),(-1,-1),6),
]))
story.append(mcp_tbl)

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — FRONTEND
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("4", "Frontend Application",
    "React SPA — pages, components, state management, API layer"))
story.append(sp(10))

story.append(Paragraph("Pages", sub_header))
pages = [
    ["Page",            "Route",           "Description"],
    ["Dashboard",       "/dashboard",      "Overview cards: total items, recent wears, eco-score average, quick actions"],
    ["My Closet",       "/closet",         "Paginated grid of ClosetItemCards with filter bar (category/season/search)"],
    ["Upload",          "/upload",         "Drag-and-drop image upload, vision AI pre-fills form fields, confirm and save"],
    ["AI Stylist",      "/stylist",        "Streaming chat interface with SSE, message history, outfit card embeds"],
    ["Outfit Generator","/outfits",        "Occasion/weather/temp inputs, SSE stream, OutfitCard grid with style scores"],
    ["Travel Planner",  "/travel",         "Destination + dates + purpose, SSE stream, daily outfit plan, packing list, tips"],
    ["Analytics",       "/analytics",      "Wear frequency, cost-per-wear, eco trends, most/least worn items"],
    ["Profile",         "/profile",        "Avatar, bio, follower/following counts, public closet preview"],
    ["Groups",          "/groups",         "My groups, discover public groups, create group, join via invite code"],
    ["Avatar Builder",  "/avatar",         "3-D avatar customisation (planned feature)"],
]
story.append(info_table(pages, [CONTENT_W*0.20, CONTENT_W*0.18, CONTENT_W*0.62]))
story.append(sp(10))

story.append(Paragraph("Component Library", sub_header))
comps = [
    ["Component",          "Location",                      "Purpose"],
    ["ClosetItemCard",     "components/closet/",            "Item thumbnail, wear count badge, archive/delete actions"],
    ["ItemDetailModal",    "components/closet/",            "Full item editor modal with all fields"],
    ["OutfitCard",         "components/outfit/",            "Outfit suggestion with item chips and style score"],
    ["ChatMessage",        "components/chat/",              "Renders user/assistant messages, markdown, outfit embeds"],
    ["Layout + Sidebar",   "components/layout/",            "App shell, collapsible nav, mobile-responsive"],
    ["Button / Input",     "components/ui/",                "Shared design system primitives with Tailwind variants"],
    ["Badge / Modal",      "components/ui/",                "Status badges, generic modal wrapper"],
    ["UserCard / GroupCard","components/ui/",               "Social entity cards with follow button and stats"],
    ["RevealCard",         "components/ui/",                "Animated reveal for AI-generated outfit reveal animation"],
    ["ProtectedRoute",     "components/auth/",              "Redirects unauthenticated users to /login"],
]
story.append(info_table(comps, [CONTENT_W*0.22, CONTENT_W*0.25, CONTENT_W*0.53]))
story.append(sp(10))

story.append(Paragraph("State Management & API Layer", sub_header))
state_items = [
    "Global state in store/index.ts (React Context + useState/useCallback)",
    "closetItems[], currentUser, closetLoading/Error managed centrally",
    "lib/api.ts: typed API client — authApi, closetApi, socialApi, wearLogApi",
    "streamChat(), streamOutfit(), streamPacking() — SSE via fetch + ReadableStream",
    "Token storage in localStorage (ch_access, ch_refresh)",
    "Auto-logout on 401 via custom ch:unauthenticated window event",
    "types/index.ts: ClosetItem, PackingResult, WearLogResponse, AuthUser, Group, etc.",
]
for item in state_items:
    story.append(Paragraph(f"<bullet>&bull;</bullet> {item}", bullet_style))

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — DATA MODEL
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("5", "Data Model",
    "PostgreSQL schema, ORM models, migrations"))
story.append(sp(10))

story.append(Paragraph("Database Tables", sub_header))
db_tables = [
    ["Table",               "Primary Key",  "Key Columns",                                                          "Notes"],
    ["users",               "UUID",         "email, username, name, bio, avatar_url, role, is_active, google_id",   "Central entity; owns all other records"],
    ["user_credentials",    "UUID",         "user_id FK, password_hash",                                            "Separated for OAuth extensibility"],
    ["refresh_tokens",      "UUID",         "user_id FK, token_hash, expires_at, is_revoked",                       "7-day TTL, rotation on use"],
    ["closet_items",        "UUID",         "user_id FK, name, category, color, fabric, pattern, season, occasion[], eco_score, tags[], wear_count, last_worn, is_archived", "ARRAY columns for occasion/tags"],
    ["outfits",             "UUID",         "user_id FK, name, occasion, item_ids[], explanation, style_score",     "Saved AI-generated outfits"],
    ["follows",             "Composite",    "follower_id FK, following_id FK, created_at",                          "Compound PK (follower, following)"],
    ["groups",              "UUID",         "name, owner_id FK, is_private, invite_code, avatar_url",               "invite_code unique 20-char string"],
    ["group_members",       "Composite",    "group_id FK, user_id FK, role (owner/admin/member), joined_at",        "Compound PK"],
    ["ai_requests",         "UUID",         "request_id, user_id, type, status, result_payload JSONB, error",       "Async request tracking table"],
    ["processed_events",    "UUID",         "event_id (Kafka), processed_at",                                       "Idempotency guard for AI Worker"],
]
story.append(info_table(db_tables,
    [CONTENT_W*0.18, CONTENT_W*0.10, CONTENT_W*0.42, CONTENT_W*0.30]))
story.append(sp(10))

story.append(Paragraph("Alembic Migrations", sub_header))
migrations = [
    ["Migration",                        "Changes"],
    ["001_initial_schema.py",            "users, user_credentials, refresh_tokens, closet_items, outfits, follows, groups, group_members"],
    ["002_vector_search_indexes.py",     "pgvector extension, embedding VECTOR(1536) column on closet_items, HNSW index"],
    ["003_event_driven_ai_requests.py",  "ai_requests table (status enum: queued/processing/completed/failed), processed_events table"],
]
story.append(info_table(migrations, [CONTENT_W*0.35, CONTENT_W*0.65]))

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — API REFERENCE
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("6", "API Reference",
    "All REST endpoints — /api/v1/*"))
story.append(sp(10))

def method_badge(m):
    colours = {"GET": HexColor("#059669"),"POST": INDIGO,"PATCH": AMBER,"DELETE": RED,"WS": VIOLET}
    return Paragraph(
        f'<font color="#{colours.get(m, SLATE_MID).hexval()[2:]}"><b>{m}</b></font>',
        sty("MB", fontSize=8, leading=11, fontName="Courier"))

def ep_table(title, rows):
    story.append(Paragraph(title, sub_header))
    fmt = [["Method","Endpoint","Description"]]
    for m, path, desc in rows:
        fmt.append([method_badge(m),
                    Paragraph(path, code_style),
                    Paragraph(desc, body_sm)])
    t = Table(fmt, colWidths=[CONTENT_W*0.09, CONTENT_W*0.38, CONTENT_W*0.53], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME",     (0,0),(-1,-1),"Helvetica"),
        ("FONTSIZE",     (0,0),(-1,-1),8.5),
        ("VALIGN",       (0,0),(-1,-1),"TOP"),
        ("BACKGROUND",   (0,0),(-1,0), INDIGO_PALE),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[white, BG_LIGHT]),
        ("GRID",         (0,0),(-1,-1), 0.3, HexColor("#E2E8F0")),
        ("TOPPADDING",   (0,0),(-1,-1),4),
        ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",  (0,0),(-1,-1),5),
    ]))
    story.append(t)
    story.append(sp(8))

ep_table("Auth  —  /api/v1/auth", [
    ("POST",  "/auth/signup",            "Register: {name, username, email, password} → {user, access_token, refresh_token}"),
    ("POST",  "/auth/login",             "Login: {identifier, password} → {user, access_token, refresh_token}"),
    ("POST",  "/auth/refresh",           "Rotate refresh token → new token pair"),
    ("GET",   "/auth/me",                "Get current user profile"),
    ("PATCH", "/auth/me",                "Update display_name, bio, avatar_url"),
    ("POST",  "/auth/change-password",   "Old + new password validation"),
    ("POST",  "/auth/logout",            "Revoke single refresh token"),
    ("POST",  "/auth/logout-all",        "Revoke all refresh tokens for user"),
])

ep_table("Closet  —  /api/v1/closet", [
    ("GET",   "/closet/",                "List items (paginated). Query: category, season, page, per_page"),
    ("POST",  "/closet/",                "Create item manually"),
    ("POST",  "/closet/upload",          "Upload image → GPT-4o Vision auto-fill → save item"),
    ("POST",  "/closet/wear-log",        "Log outfit session (multiple items). Bumps wear_count + last_worn"),
    ("GET",   "/closet/wear-log",        "List all wear-log sessions newest first"),
    ("GET",   "/closet/{id}",            "Get single item"),
    ("PATCH", "/closet/{id}",            "Update item fields"),
    ("DELETE","/closet/{id}",            "Delete item (204)"),
    ("POST",  "/closet/{id}/wear",       "Single-item wear bump + optional worn_date"),
    ("GET",   "/closet/{id}/wear-history","Wear sessions that include this specific item"),
])

ep_table("AI  —  /api/v1/ai", [
    ("POST",  "/ai/chat/stream",         "SSE stream: Thinking → token chunks → done"),
    ("POST",  "/ai/chat/async",          "Queue chat → {request_id, status:queued}"),
    ("POST",  "/ai/outfit/stream",       "SSE: status → result{outfits[]} → done"),
    ("POST",  "/ai/outfit/async",        "Queue outfit generation"),
    ("POST",  "/ai/packing/stream",      "SSE: status → tokens(summary) → tokens(tips) → result → done"),
    ("POST",  "/ai/packing/async",       "Queue packing list generation"),
    ("POST",  "/ai/vision/analyze",      "Analyse garment image (multipart) → VisionAnalysisResult"),
    ("GET",   "/ai/requests/{id}",       "Poll async request status: queued/processing/completed/failed"),
])

ep_table("Social  —  /api/v1/social", [
    ("GET",   "/social/users",           "Search users by query string"),
    ("GET",   "/social/profile/{id}",    "Public profile with follower/following counts"),
    ("POST",  "/social/follow/{id}",     "Follow user → {following:true, follower_count}"),
    ("DELETE","/social/follow/{id}",     "Unfollow user"),
    ("GET",   "/social/followers/{id}",  "List followers of user"),
    ("GET",   "/social/following/{id}",  "List accounts user is following"),
    ("GET",   "/social/groups",          "My groups"),
    ("POST",  "/social/groups",          "Create group"),
    ("GET",   "/social/groups/discover", "Public groups discovery"),
    ("POST",  "/social/groups/join",     "Join by {invite_code}"),
    ("GET",   "/social/groups/{id}",     "Group detail + members"),
    ("PATCH", "/social/groups/{id}/members/{uid}/role","Change member role"),
    ("DELETE","/social/groups/{id}/members/{uid}",     "Remove member"),
    ("DELETE","/social/groups/{id}",     "Delete group (owner only)"),
])

ep_table("WebSocket  —  /api/v1/ws", [
    ("WS", "/ws?token=<jwt>",           "Connect → subscribe → receive AI result push events. Redis Pub/Sub fan-out across all gateway replicas."),
])

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — AI & MCP INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("7", "AI & MCP Integration",
    "LangGraph ReAct agent, tool calling loop, SSE streaming"))
story.append(sp(10))

story.append(Paragraph("LangGraph ReAct Agent Loop", sub_header))
story.append(Paragraph(
    "The WardrobeAgent wraps a LangGraph <b>create_react_agent</b> graph. "
    "At startup it connects to all four MCP servers via <b>MultiServerMCPClient</b> "
    "and loads all 8 tools. The graph runs a ReAct loop: decide → call tool → observe → decide "
    "until no more tool calls are needed.",
    body))
story.append(sp(6))

react_steps = [
    ["Phase",          "Graph Node",      "What Happens"],
    ["Decide",         "call_model",      "ChatOpenAI (GPT-4o) processes system prompt + messages. Emits tool_calls JSON or final content."],
    ["Route",          "should_continue", "If tool_calls present → route to 'tools'. If content → END."],
    ["Execute",        "tools",           "LangChain ToolExecutor calls each MCP tool via MultiServerMCPClient SSE transport."],
    ["Observe",        "—",               "Tool result appended as ToolMessage. Loop back to call_model."],
    ["Stream",         "astream_events",  "on_chat_model_stream events yield token chunks to the SSE response."],
]
story.append(info_table(react_steps, [CONTENT_W*0.16, CONTENT_W*0.18, CONTENT_W*0.66]))
story.append(sp(10))

story.append(Paragraph("Hardening & Reliability", sub_header))
story.append(two_col(
    ["asyncio.wait_for() wraps every ainvoke() — hard timeout (default 60s)",
     "asyncio.timeout() context manager on astream_events for streaming",
     "Tenacity retry: 3 attempts, exponential backoff on TimeoutError",
     "Input validation before agent invocation (max 4000 chars, 50-turn history cap)"],
    ["History capped at last 10 turns before passing to LangGraph",
     "Graceful degradation: agent starts in degraded mode if MCP unavailable",
     "state_modifier= for system prompt (stable across langgraph>=0.2.0)",
     "LangSmith traces every run with token count, latency, tool I/O"]
))
story.append(sp(10))

story.append(Paragraph("SSE Streaming Protocol", sub_header))
sse_events = [
    ["Event Type",  "Payload",                              "When Sent"],
    ["status",      '{"type":"status","message":"..."}',    "Before processing starts, between pipeline steps"],
    ["token",       '{"type":"token","content":"..."}',     "Each streamed text chunk from the model"],
    ["result",      '{"type":"result","data":{...}}',       "Outfit/packing full structured result"],
    ["done",        '{"type":"done"}',                      "Stream complete — client closes connection"],
    ["error",       '{"type":"error","message":"..."}',     "Any AppError or unhandled exception"],
]
story.append(info_table(sse_events, [CONTENT_W*0.15, CONTENT_W*0.44, CONTENT_W*0.41]))

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — EVENT-DRIVEN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("8", "Event-Driven Pipeline",
    "Redpanda / Kafka topics, EventEnvelope, producer/consumer"))
story.append(sp(10))

story.append(Paragraph("Kafka Topics", sub_header))
topics = [
    ["Topic",                 "Producer",      "Consumer",      "Purpose"],
    ["ai.chat.requested",     "API Gateway",   "AI Worker",     "Async chat request payload"],
    ["ai.outfit.requested",   "API Gateway",   "AI Worker",     "Async outfit generation request"],
    ["ai.trip.planned",       "API Gateway",   "AI Worker",     "Async packing list request"],
    ["ai.image.uploaded",     "API Gateway",   "AI Worker",     "Async vision analysis request"],
    ["ai_response_stream",    "AI Worker",     "API Gateway",   "Chat completion result fan-out"],
    ["outfit_generated",      "AI Worker",     "API Gateway",   "Outfit result fan-out"],
    ["packing_ready",         "AI Worker",     "API Gateway",   "Packing list result fan-out"],
    ["image_analyzed",        "AI Worker",     "API Gateway",   "Vision result fan-out"],
]
story.append(info_table(topics, [CONTENT_W*0.28, CONTENT_W*0.18, CONTENT_W*0.18, CONTENT_W*0.36]))
story.append(sp(4))
story.append(Paragraph("All topics: 6 partitions, replication factor 1 (local dev). Retention: 7 days.", body_sm))
story.append(sp(10))

story.append(Paragraph("EventEnvelope Schema", sub_header))
story.append(Paragraph(
    "Every Kafka message is serialised as a JSON <b>EventEnvelope</b>:",
    body))
env_fields = [
    ["Field",          "Type",   "Description"],
    ["event_id",       "UUID",   "Unique ID for idempotency check"],
    ["event_type",     "str",    "e.g. ai_chat_requested, outfit_requested, trip_planned"],
    ["event_version",  "str",    "Schema version (default '1.0')"],
    ["request_id",     "UUID",   "Correlates request to result; returned to client"],
    ["user_id",        "str",    "Owner of the request"],
    ["created_at",     "datetime","Event creation timestamp (UTC)"],
    ["source",         "str",    "Originating service (default 'api-gateway')"],
    ["payload",        "dict",   "Event-specific data (message, closet_items, dates, etc.)"],
]
story.append(info_table(env_fields, [CONTENT_W*0.20, CONTENT_W*0.12, CONTENT_W*0.68]))
story.append(sp(10))

story.append(Paragraph("Redis Pub/Sub Fan-out", sub_header))
story.append(Paragraph(
    "When the AI Worker writes a result, it also publishes to a Redis channel keyed by "
    "<b>user_id</b>. All API Gateway instances subscribe to this channel. When a message "
    "arrives, any open WebSocket for that user receives the result immediately — enabling "
    "horizontal scaling of the gateway without sticky sessions.",
    body))

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("9", "Infrastructure & DevOps",
    "Docker Compose, Nginx, volumes, health checks"))
story.append(sp(10))

story.append(Paragraph("Docker Compose Services", sub_header))
docker_svcs = [
    ["Service",           "Image / Build",               "Ports",         "Health Check Strategy"],
    ["postgres",          "pgvector/pgvector:pg16",      "5433:5432",     "pg_isready -U clozehive"],
    ["redis",             "redis:7-alpine",              "6382:6379",     "redis-cli ping"],
    ["redpanda",          "redpandadata/redpanda:v24.2.9","19092, 19644", "rpk cluster info"],
    ["kafka-topics",      "redpandadata/redpanda",        "—",            "One-shot init container (restart:no)"],
    ["redpanda-console",  "redpandadata/console:v2.7.2", "8080",         "Depends on redpanda healthy"],
    ["mcp-weather",       "services/mcp/weather",         "8010",         "TCP socket connect :8010"],
    ["mcp-vision",        "services/mcp/vision",          "8011",         "TCP socket connect :8011"],
    ["mcp-outfit",        "services/mcp/outfit",          "8012",         "TCP socket connect :8012"],
    ["mcp-packing",       "services/mcp/packing",         "8013",         "TCP socket connect :8013"],
    ["ai-agent",          "services/ai-agent",            "8001",         "HTTP GET /health → 200"],
    ["ai-worker",         "services/ai-worker",           "—",            "Depends on ai-agent healthy"],
    ["api-gateway",       "services/api-gateway",         "8000",         "HTTP GET /health → 200"],
    ["frontend",          "frontend/",                   "3001:3000",     "wget localhost:3000"],
    ["nginx",             "nginx:alpine",                "80",            "Depends on gateway + frontend"],
    ["migrate",           "services/api-gateway",         "—",            "One-shot: alembic upgrade head"],
]
story.append(info_table(docker_svcs,
    [CONTENT_W*0.18, CONTENT_W*0.25, CONTENT_W*0.15, CONTENT_W*0.42]))
story.append(sp(10))

story.append(Paragraph("Nginx Configuration Highlights", sub_header))
story.append(two_col(
    ["Rate limit zone api: 30 req/s per IP",
     "Rate limit zone auth: 5 req/s per IP (brute-force protection)",
     "WebSocket upgrade headers: Connection: Upgrade, Upgrade: websocket",
     "proxy_buffering off for SSE endpoints"],
    ["X-Accel-Buffering: no on /ai/* routes",
     "gzip on (text/*, application/json)",
     "SPA fallback: try_files $uri /index.html",
     "Structured JSON access log format"]
))
story.append(sp(10))

story.append(Paragraph("Volumes & Persistence", sub_header))
vols = [
    ["Volume",          "Service",     "Data Persisted"],
    ["postgres_data",   "postgres",    "All database tables, user data, closet items"],
    ["redis_data",      "redis",       "AOF persistence (appendonly yes, appendfsync everysec)"],
    ["redpanda_data",   "redpanda",    "Kafka topic log segments, consumer offsets"],
    ["uploads",         "api-gateway", "Uploaded garment images (local dev; use S3 in prod)"],
]
story.append(info_table(vols, [CONTENT_W*0.22, CONTENT_W*0.18, CONTENT_W*0.60]))

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — OBSERVABILITY
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("10", "Observability",
    "LangSmith distributed tracing + structured logging"))
story.append(sp(10))

story.append(Paragraph("LangSmith Tracing", sub_header))
story.append(Paragraph(
    "Every LangGraph agent run is automatically traced via <b>LangSmith SDK 0.7.x</b> "
    "when <code>LANGSMITH_TRACING=true</code> and <code>LANGSMITH_API_KEY</code> are set. "
    "Traces are uploaded asynchronously to the <b>clozehive</b> project.",
    body))
story.append(sp(6))

ls_spans = [
    ["Span Type",        "Name",              "What It Shows"],
    ["chain (root)",     "LangGraph",         "Total run: token count, cost, latency, success/failure"],
    ["chain",            "agent",             "Full ReAct decision cycle per iteration"],
    ["chain",            "call_model",        "Single LLM invocation inside the graph"],
    ["llm",              "ChatOpenAI",        "System prompt, all messages, tool_calls JSON, completion tokens"],
    ["chain",            "Prompt",            "How messages are assembled before the LLM call"],
    ["tool",             "get_weather_forecast","MCP tool: exact input JSON → exact output JSON"],
    ["tool",             "generate_outfit_suggestions","MCP tool: closet_items[], occasion, weather → outfits[]"],
    ["chain",            "should_continue",   "Routing decision: continue ReAct loop or END"],
]
story.append(info_table(ls_spans, [CONTENT_W*0.15, CONTENT_W*0.28, CONTENT_W*0.57]))
story.append(sp(10))

story.append(Paragraph("Structured Logging", sub_header))
story.append(Paragraph(
    "All Python services use <b>structlog</b> with JSON output in production and "
    "coloured ConsoleRenderer in development. Every log line includes:",
    body))
story.append(two_col(
    ["timestamp (ISO 8601 UTC)",
     "log level (info / warning / error)",
     "service name (e.g. closet_service, wardrobe_agent)",
     "request_id (injected by RequestIdMiddleware)"],
    ["user_id where applicable",
     "latency_ms for HTTP requests",
     "tool name + elapsed_ms for MCP calls",
     "Kafka consumer group and partition info"]
))
story.append(sp(8))
story.append(Paragraph("Redpanda Console  (http://localhost:8080)", sub_header))
story.append(Paragraph(
    "Visual Kafka topic browser — inspect messages, consumer lag, partition offsets. "
    "Useful for debugging async pipeline: verify EventEnvelope is published, "
    "confirm AI Worker consumed and published result.",
    body))

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — SECURITY
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("11", "Security",
    "Authentication, authorisation, rate limiting, validation"))
story.append(sp(10))

story.append(Paragraph("Authentication — JWT HS256", sub_header))
auth_items = [
    ["Aspect",              "Implementation"],
    ["Access Token",        "JWT HS256, 15-minute TTL, signed with JWT_SECRET env var"],
    ["Refresh Token",       "Opaque 32-byte random token, 7-day TTL, stored hashed in DB"],
    ["Rotation",            "Every /auth/refresh call issues a new token pair and revokes the old refresh token"],
    ["Logout",              "/logout revokes single token; /logout-all revokes all tokens for the user"],
    ["Password Hashing",    "bcrypt with 12 rounds (passlib[bcrypt])"],
    ["CurrentUser dep",     "FastAPI dependency extracts sub from JWT; raises 401 on invalid/expired token"],
    ["Internal Auth",       "X-Internal-Key header for service-to-service calls (AI Worker → AI Agent)"],
]
story.append(info_table(auth_items, [CONTENT_W*0.25, CONTENT_W*0.75]))
story.append(sp(10))

story.append(Paragraph("Authorisation & Input Validation", sub_header))
story.append(two_col(
    ["All closet endpoints verify item.user_id == current_user before any operation",
     "Social endpoints prevent self-follow, enforce group owner-only delete",
     "Image upload: MIME type allowlist (JPEG, PNG, WebP, HEIC), 10 MB hard limit",
     "Category allowlist on closet upload prevents invalid data entry"],
    ["Chat messages: max 4000 chars validated in Pydantic schema + agent layer",
     "Date patterns validated with Pydantic regex r'^\\d{4}-\\d{2}-\\d{2}$'",
     "Nginx rate limiting: 30 r/s general, 5 r/s on /auth/* endpoints",
     "CORS restricted to ALLOWED_ORIGINS env var"]
))

story.append(PageBreak())


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — TECH STACK
# ══════════════════════════════════════════════════════════════════════════════

story.append(section_banner("12", "Tech Stack Summary",
    "Complete dependency inventory across all services"))
story.append(sp(10))

stack = [
    ("Frontend",           [
        "React 18 + TypeScript 5",
        "Vite 5 (build tool)",
        "Tailwind CSS + shadcn/ui components",
        "React Router v6",
        "fetch API + ReadableStream for SSE",
    ]),
    ("API Gateway",        [
        "Python 3.12",
        "FastAPI 0.111 + uvicorn[standard]",
        "SQLAlchemy 2.0 async + asyncpg",
        "Alembic (migrations)",
        "python-jose[cryptography] (JWT)",
        "passlib[bcrypt]",
        "aiohttp (AI Agent HTTP client)",
        "aiokafka (Kafka producer + consumer)",
        "redis[hiredis] (cache + Pub/Sub)",
        "pydantic-settings 2.x",
        "structlog 24.x",
    ]),
    ("AI Agent",           [
        "Python 3.12",
        "FastAPI 0.111",
        "LangChain >= 0.2.0",
        "LangChain-OpenAI >= 0.1.7",
        "LangGraph >= 0.2.0 (ReAct graph)",
        "langchain-mcp-adapters >= 0.1.0",
        "langsmith 0.7.x (tracing)",
        "OpenAI SDK >= 1.30",
        "tenacity (retry)",
        "asyncpg + pgvector",
    ]),
    ("AI Worker",          [
        "Python 3.12",
        "aiokafka (consumer)",
        "asyncpg (DB writes)",
        "aiohttp (AI Agent calls)",
        "redis (Pub/Sub publish)",
    ]),
    ("MCP Servers (x4)",   [
        "Python 3.12",
        "FastMCP (SSE server framework)",
        "OpenAI SDK (GPT-4o calls)",
        "pydantic 2.x (shared schemas)",
    ]),
    ("Infrastructure",     [
        "PostgreSQL 16 + pgvector extension",
        "Redis 7 (AOF persistence)",
        "Redpanda v24.2.9 (Kafka-compatible)",
        "Nginx alpine (reverse proxy)",
        "Docker Compose (orchestration)",
        "LangSmith (cloud tracing)",
        "Redpanda Console (Kafka UI)",
    ]),
]

col1 = []
col2 = []
for i, (category, items) in enumerate(stack):
    block = [Paragraph(f"<b>{category}</b>", sty("SC", fontSize=9.5, leading=13,
                textColor=INDIGO, fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=3))]
    for item in items:
        block.append(Paragraph(f"<bullet>&bull;</bullet> {item}", bullet_style))
    if i % 2 == 0:
        col1.extend(block)
    else:
        col2.extend(block)

stack_tbl = Table([[col1, col2]],
    colWidths=[CONTENT_W*0.5 - 6, CONTENT_W*0.5 - 6])
stack_tbl.setStyle(TableStyle([
    ("VALIGN",       (0,0),(-1,-1),"TOP"),
    ("LEFTPADDING",  (0,0),(-1,-1),6),
    ("RIGHTPADDING", (0,0),(-1,-1),6),
    ("BACKGROUND",   (0,0),(0,0), HexColor("#F8FAFC")),
    ("BACKGROUND",   (1,0),(1,0), HexColor("#F8FAFC")),
    ("BOX",          (0,0),(0,0), 0.4, HexColor("#E2E8F0")),
    ("BOX",          (1,0),(1,0), 0.4, HexColor("#E2E8F0")),
    ("TOPPADDING",   (0,0),(-1,-1),10),
    ("BOTTOMPADDING",(0,0),(-1,-1),10),
]))
story.append(stack_tbl)
story.append(sp(14))

# ── Closing banner ─────────────────────────────────────────────────────────────
close = Table(
    [[Paragraph("CLOZEHIVE  ·  v2.0  ·  Engineering Reference",
        sty("CL", fontSize=11, leading=16, textColor=white,
            fontName="Helvetica-Bold", alignment=TA_CENTER)),
      Paragraph("Full-stack AI wardrobe platform  ·  FastAPI + LangGraph + React + Kafka + pgvector",
        sty("CL2", fontSize=9, leading=13, textColor=HexColor("#C7D2FE"),
            fontName="Helvetica", alignment=TA_CENTER))]],
    colWidths=[CONTENT_W],
)
close.setStyle(TableStyle([
    ("BACKGROUND",    (0,0),(-1,-1), INDIGO),
    ("TOPPADDING",    (0,0),(-1,-1), 14),
    ("BOTTOMPADDING", (0,0),(-1,-1), 14),
    ("LEFTPADDING",   (0,0),(-1,-1), 20),
]))
story.append(close)


# ══════════════════════════════════════════════════════════════════════════════
# BUILD
# ══════════════════════════════════════════════════════════════════════════════

def on_page(canvas, doc):
    """Footer with page number."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SLATE_LIGHT)
    canvas.drawString(1.8*cm, 10*mm, "CLOZEHIVE  ·  Master Application Outline  ·  Confidential")
    canvas.drawRightString(W - 1.8*cm, 10*mm, f"Page {doc.page}")
    canvas.setStrokeColor(HexColor("#E2E8F0"))
    canvas.setLineWidth(0.3)
    canvas.line(1.8*cm, 13*mm, W - 1.8*cm, 13*mm)
    canvas.restoreState()

doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print(f"PDF written to: {OUTPUT}")
