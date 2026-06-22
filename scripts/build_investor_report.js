const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, ImageRun,
  Header, Footer, TableOfContents, TabStopType, TabStopPosition,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "ClozeHive_Investor_Report.docx");

// ---------- palette ----------
const C = {
  brand: "6D28D9",      // violet
  brandDark: "4C1D95",
  accent: "DB2777",     // pink
  ink: "111827",
  sub: "6B7280",
  line: "D1D5DB",
  headFill: "6D28D9",
  zebra: "F5F3FF",
  good: "065F46",
  goodFill: "ECFDF5",
};

const CONTENT_W = 9360;

// ---------- helpers ----------
const T = (text, opts = {}) => new TextRun({ text, font: "Arial", ...opts });

const P = (children, opts = {}) =>
  new Paragraph({ children: Array.isArray(children) ? children : [children], ...opts });

const body = (text, opts = {}) =>
  new Paragraph({
    spacing: { after: 140, line: 276 },
    children: [T(text)],
    ...opts,
  });

const bullet = (runs, level = 0) =>
  new Paragraph({
    numbering: { reference: "bullets", level },
    spacing: { after: 70, line: 268 },
    children: Array.isArray(runs) ? runs : [T(runs)],
  });

const numItem = (runs) =>
  new Paragraph({
    numbering: { reference: "nums", level: 0 },
    spacing: { after: 70, line: 268 },
    children: Array.isArray(runs) ? runs : [T(runs)],
  });

const border = { style: BorderStyle.SINGLE, size: 1, color: C.line };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(content, { w, fill, bold, color, align, header } = {}) {
  const runs = Array.isArray(content) ? content : [content];
  return new TableCell({
    borders,
    width: { size: w, type: WidthType.DXA },
    shading: fill ? { fill, type: ShadingType.CLEAR } : undefined,
    margins: { top: 70, bottom: 70, left: 120, right: 120 },
    verticalAlign: VerticalAlign.CENTER,
    children: [
      new Paragraph({
        alignment: align || AlignmentType.LEFT,
        spacing: { after: 0, line: 256 },
        children: runs.map((r) =>
          typeof r === "string"
            ? T(r, { bold: !!bold || !!header, color: color || (header ? "FFFFFF" : C.ink), size: header ? 19 : 20 })
            : r
        ),
      }),
    ],
  });
}

function table(headersRow, rows, widths) {
  const trHead = new TableRow({
    tableHeader: true,
    children: headersRow.map((h, i) => cell(h, { w: widths[i], fill: C.headFill, header: true })),
  });
  const trBody = rows.map((r, ri) =>
    new TableRow({
      children: r.map((c, i) =>
        cell(c, { w: widths[i], fill: ri % 2 ? C.zebra : undefined })
      ),
    })
  );
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: [trHead, ...trBody],
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    pageBreakBefore: true,
    children: [T(text)],
  });
}
function h2(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, children: [T(text)] });
}
function h3(text) {
  return new Paragraph({ heading: HeadingLevel.HEADING_3, children: [T(text)] });
}

// callout box (single-cell shaded table)
function callout(title, lines, fill = C.zebra, accent = C.brand) {
  const kids = [
    new Paragraph({ spacing: { after: 60 }, children: [T(title, { bold: true, color: accent, size: 21 })] }),
    ...lines.map((l) => new Paragraph({ spacing: { after: 40, line: 264 }, children: [T(l, { size: 20 })] })),
  ];
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders: {
              top: { style: BorderStyle.SINGLE, size: 1, color: fill },
              bottom: { style: BorderStyle.SINGLE, size: 1, color: fill },
              right: { style: BorderStyle.SINGLE, size: 1, color: fill },
              left: { style: BorderStyle.SINGLE, size: 24, color: accent },
            },
            shading: { fill, type: ShadingType.CLEAR },
            margins: { top: 140, bottom: 140, left: 200, right: 160 },
            width: { size: CONTENT_W, type: WidthType.DXA },
            children: kids,
          }),
        ],
      }),
    ],
  });
}

const spacer = (h = 120) => new Paragraph({ spacing: { after: h }, children: [T("")] });

// ---------- cover ----------
const coverChildren = [];
const logoPath = path.join(ROOT, "frontend", "public", "og-image.png");
coverChildren.push(new Paragraph({ spacing: { before: 1200, after: 0 }, children: [T("")] }));
if (fs.existsSync(logoPath)) {
  coverChildren.push(
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 320 },
      children: [
        new ImageRun({
          type: "png",
          data: fs.readFileSync(logoPath),
          transformation: { width: 460, height: 241 },
          altText: { title: "ClozeHive", description: "ClozeHive brand", name: "logo" },
        }),
      ],
    })
  );
}
coverChildren.push(
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 60 },
    children: [T("ClozeHive", { bold: true, size: 64, color: C.brandDark })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 40 },
    children: [T("Wardrobe Intelligence, Powered by FANI", { size: 30, color: C.accent, bold: true })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 600 },
    children: [T("AI that understands what you already own — and what to do with it.", { italics: true, size: 22, color: C.sub })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 30 },
    children: [T("Investor Briefing & Technical Overview", { bold: true, size: 24, color: C.ink })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 30 },
    children: [T("June 2026  ·  Confidential", { size: 20, color: C.sub })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200 },
    children: [T("clozehive.netlify.app   ·   cloze-hive.onrender.com", { size: 18, color: C.brand })],
  }),
  new Paragraph({ children: [new PageBreak()] })
);

// ---------- TOC ----------
const tocChildren = [
  new Paragraph({ heading: HeadingLevel.HEADING_1, children: [T("Contents")] }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ================= SECTIONS =================
const docChildren = [];
const push = (...els) => docChildren.push(...els);

// 1. Executive Summary
push(
  h1("1. Executive Summary"),
  body("ClozeHive is a wardrobe intelligence platform that turns the clothes a person already owns into an interactive, AI-driven styling experience. Users build a digital closet, and FANI — Fashion AI Nurturing Individuality — recommends outfits, rates fits, fills wardrobe gaps, plans travel packing, and answers styling questions through chat, all grounded in the user's real items and history."),
  body("Unlike fashion apps that exist only to sell more clothing, ClozeHive's primary value is helping people get more out of what they have: rediscovering forgotten items, surfacing never-worn pieces, and making confident daily outfit decisions. Shopping guidance is gap-driven and additive, not the core loop."),
  callout("The one-line pitch", [
    "ClozeHive is the AI stylist for your own closet — a digital wardrobe where FANI builds outfits, rates them, plans your packing, and tells you what's actually missing, using retrieval-augmented intelligence grounded in your items and behavior.",
  ], C.zebra, C.brand),
  spacer(80),
  h2("Why now"),
  bullet("Multimodal AI (vision + language) is finally good and cheap enough to understand clothing from a phone photo and reason about style in natural language."),
  bullet("Retrieval-augmented generation (RAG) plus vector search lets recommendations be personal and explainable rather than generic — grounded in the user's actual wardrobe."),
  bullet("Consumers increasingly want sustainable, 'shop-your-closet' behavior; the cost-of-living and re-wear culture favors utilization over consumption."),
  spacer(60),
  h2("Status at a glance"),
  table(
    ["Dimension", "Where ClozeHive is today"],
    [
      ["Product stage", "Working MVP, deployed and publicly reachable (web app + marketing site)"],
      ["Architecture", "Production-shaped microservices: SPA, API gateway, AI agent, Postgres+pgvector, Redis, nginx"],
      ["AI capability", "FANI stylist (chat, outfit, rating, packing), in-process vision pipeline, RAG over closet + fashion knowledge"],
      ["Engineering maturity", "33 DB migrations, ~475 backend tests, CI pipeline, observability (Sentry, Prometheus, OpenTelemetry)"],
      ["Immediate focus", "Beta launch hardening: secret rotation, backups, onboarding polish"],
    ],
    [2600, 6760]
  )
);

// 2. Problem & Opportunity
push(
  h1("2. The Problem & The Opportunity"),
  h2("The problem"),
  body("People own far more than they wear. The familiar 'I have a closet full of clothes and nothing to wear' is a real, recurring friction point that wastes time every morning and money on redundant purchases."),
  bullet([T("Decision fatigue: ", { bold: true }), T("choosing outfits daily is a low-value, high-friction task with no good digital assistant.")]),
  bullet([T("Forgotten inventory: ", { bold: true }), T("items bought and never worn; no visibility into what you actually own.")]),
  bullet([T("Wasteful spend: ", { bold: true }), T("buying duplicates or pieces that don't combine with anything already owned.")]),
  bullet([T("Generic advice: ", { bold: true }), T("existing style tools recommend products to buy, not how to use your current wardrobe.")]),
  bullet([T("Travel stress: ", { bold: true }), T("packing the right, mix-and-matchable set for a trip is tedious and error-prone.")]),
  spacer(60),
  h2("The opportunity"),
  body("ClozeHive sits at the intersection of three large, growing markets — personal styling, wardrobe/closet management, and AI consumer assistants — and reframes the wardrobe from static storage into an intelligent, queryable asset."),
  callout("Strategic wedge", [
    "Start with the closet (data nobody else owns), become the daily styling habit, then expand into high-intent, gap-driven shopping and brand partnerships — all defensible because the recommendations are grounded in proprietary, per-user wardrobe data.",
  ], C.goodFill, C.good),
);

// 3. Product Overview
push(
  h1("3. Product Overview"),
  body("ClozeHive is a single-page web application backed by an AI-powered API. The experience is organized around the wardrobe and FANI, the in-product AI stylist available as a floating chat on every page and as a full-screen stylist."),
  h2("Meet FANI"),
  body("FANI (Fashion AI Nurturing Individuality) is ClozeHive's built-in AI stylist. FANI powers outfit recommendations, daily style tips, wardrobe gap detection, conversational chat, outfit ratings, and packing suggestions. FANI is personalized: it reasons over the user's style profile, real closet items, and outfit/wear history."),
  spacer(40),
  h2("Core features"),
  table(
    ["Area", "What the user gets"],
    [
      ["Home / Dashboard", "FANI Tip of the Day, 'Style at a Glance' (Most Worn / Never Worn / Closet Gaps), quick-action grid, Outfit of the Day with a 5-tier FANI rating."],
      ["Digital Closet", "Add/edit items with metadata and images (local or cloud), preview/confirm upload, 'similar items', and AI background removal."],
      ["Smart Ingest & Vision", "Photo-based item detection and background removal run in-process to turn a picture into a catalogued wardrobe item."],
      ["Outfit Builder", "Compose, save, and revisit outfits; outfit history feeds the recommendation engine."],
      ["FANI AI Stylist", "Structured stylist chat plus a floating assistant on every page; streaming responses."],
      ["Outfit Rating", "5-tier system — Needs Improvement → Average → Good → Excellent → Best Fit — each with stars, a color badge, and a stylist note."],
      ["Travel & Packing", "Trips and packing lists with AI packing tools and packing 'memory' that learns from past trips."],
      ["Intelligence / RAG", "Fashion-knowledge answers, closet similarity, and purchase-gap analysis grounded in embeddings stored in the database."],
      ["Shopping Check", "Gap-driven guidance on whether a prospective purchase fills a real wardrobe need."],
      ["Planner", "Weekly outfit planning and item availability awareness."],
      ["Profile & Settings", "Display name, location/weather, FANI preferences, privacy; style profile (incl. skin tone) personalizes recommendations."],
      ["Real-time", "WebSocket notifications for in-app updates."],
    ],
    [2300, 7060]
  )
);

// 4. How It Works (Workflow)
push(
  h1("4. How It Works — User Workflow"),
  body("The product is designed around a virtuous loop: the more a user catalogues and uses their closet, the smarter and more personal FANI's guidance becomes."),
  h2("Primary user journey"),
  numItem([T("Onboard & build a profile. ", { bold: true }), T("The user signs up (email or Google) and sets a style profile — preferences, location/weather, and personal attributes.")]),
  numItem([T("Populate the closet. ", { bold: true }), T("They photograph or upload items; the vision pipeline detects the garment and removes the background, producing a clean catalogued item.")]),
  numItem([T("Get styled daily. ", { bold: true }), T("The Home screen surfaces an Outfit of the Day, a FANI tip, and a 'Style at a Glance' view of most-worn, never-worn, and gaps.")]),
  numItem([T("Build & rate outfits. ", { bold: true }), T("The user composes outfits or accepts FANI's; each gets a 5-tier rating with an explanatory stylist note.")]),
  numItem([T("Ask FANI anything. ", { bold: true }), T("Via floating chat or the full stylist, the user asks for occasion outfits, advice, or packing — answered with RAG grounded in their wardrobe.")]),
  numItem([T("Plan travel. ", { bold: true }), T("For a trip, FANI assembles a weather-aware, mix-and-match packing list, improving from packing memory.")]),
  numItem([T("Shop smarter. ", { bold: true }), T("Purchase-gap analysis and Shopping Check tell the user what's genuinely missing before they buy.")]),
  spacer(60),
  h2("Behind a single request (example: 'What should I wear to dinner tonight?')"),
  numItem("The browser hits nginx, which routes the API call to the FastAPI gateway."),
  numItem("The gateway authenticates the user and assembles context: style profile, relevant closet items (via vector similarity), recent outfits, and weather."),
  numItem("It retrieves grounding facts (RAG) — fashion knowledge and closet matches — from Postgres/pgvector."),
  numItem("It calls the AI-agent (FANI) over internal HTTP with a signed service token; FANI reasons with its outfit/weather/packing tools."),
  numItem("The response streams back through the gateway and nginx to the user, and notifications/state update over WebSocket and Redis."),
);

// 5. Architecture
push(
  h1("5. System Architecture"),
  body("ClozeHive is built as a set of cooperating services with a clear separation between the public edge, application logic, the AI agent, and stateful storage. The same codebase runs locally via Docker Compose and in production."),
  h2("Logical components"),
  table(
    ["Layer", "Component", "Responsibility"],
    [
      ["Client", "React + Vite + TypeScript SPA", "Wardrobe UI, FANI chat, builder, analytics; PWA-capable."],
      ["Edge", "nginx", "Single browser entrypoint: serves the SPA, proxies all /api traffic, /uploads, and upgrades the WebSocket."],
      ["Application", "API Gateway (FastAPI)", "Auth, profile, closet, outfits, trips, analytics, RAG, AI orchestration, WebSocket hub — plus the in-process vision pipeline."],
      ["AI", "AI-Agent (FANI)", "LangGraph-style agent with inline weather / outfit / packing tools, called by the gateway over internal HTTP."],
      ["State", "PostgreSQL + pgvector", "Source of truth for users, items, outfits, trips, chat, and vector embeddings for similarity / RAG."],
      ["State", "Redis", "Caching, sessions, OAuth CSRF state, preview/staging, fast cross-request state."],
      ["State", "Uploads volume / GCS", "Item images on local disk or Google Cloud Storage."],
    ],
    [1400, 3000, 4960]
  ),
  spacer(80),
  h2("Architecture diagram"),
  body("The flow below shows the request path from browser to data, with the AI agent invoked internally by the gateway.")
);

// native architecture diagram (boxes + arrow rows)
function diagBox(lines, { fill, accent }) {
  const kids = lines.map((l, i) =>
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: i === lines.length - 1 ? 0 : 30, line: 240 },
      children: [T(l.t, { bold: i === 0, size: i === 0 ? 19 : 16, color: i === 0 ? accent : C.sub })],
    })
  );
  return new TableCell({
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: accent },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: accent },
      left: { style: BorderStyle.SINGLE, size: 6, color: accent },
      right: { style: BorderStyle.SINGLE, size: 6, color: accent },
    },
    shading: { fill, type: ShadingType.CLEAR },
    margins: { top: 90, bottom: 90, left: 100, right: 100 },
    verticalAlign: VerticalAlign.CENTER,
    width: { size: CONTENT_W, type: WidthType.DXA },
    children: kids,
  });
}
function diagRow(cells, widths) {
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE }, insideHorizontal: { style: BorderStyle.NONE }, insideVertical: { style: BorderStyle.NONE } },
    rows: [new TableRow({ children: cells })],
  });
}
const arrowDown = (label) => new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 50, after: 50 },
  children: [T("▼", { color: C.brand, size: 18 }), ...(label ? [T("  " + label, { color: C.sub, size: 15, italics: true })] : [])],
});

push(
  diagRow([diagBox([{ t: "USER'S BROWSER" }, { t: "React + Vite + TypeScript SPA (PWA)" }], { fill: "EEF2FF", accent: C.brand })], [CONTENT_W]),
  arrowDown("HTTPS  ·  /  ·  /api/v1/*  ·  /uploads  ·  /ws"),
  diagRow([diagBox([{ t: "nginx — single entrypoint :80" }, { t: "serves SPA · proxies /api · /uploads · upgrades WebSocket" }], { fill: "F3F4F6", accent: C.sub })], [CONTENT_W]),
  arrowDown(),
  diagRow([
    diagBox([{ t: "API GATEWAY (FastAPI) :8000" }, { t: "auth · closet · outfits · trips" }, { t: "analytics · RAG · WS hub" }, { t: "+ in-process VISION pipeline" }], { fill: "EDE9FE", accent: C.brandDark }),
    new TableCell({ borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }, width: { size: 600, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [T("◀▶", { color: C.brand, size: 18 })] }), new Paragraph({ alignment: AlignmentType.CENTER, children: [T("internal", { color: C.sub, size: 13, italics: true })] })] }),
    diagBox([{ t: "AI-AGENT — FANI :8001" }, { t: "LangGraph + LangChain" }, { t: "tools: weather · outfit · packing" }, { t: "OpenAI / Gemini" }], { fill: "FCE7F3", accent: C.accent }),
  ], [4380, 600, 4380]),
  arrowDown(),
  diagRow([
    diagBox([{ t: "PostgreSQL + pgvector" }, { t: "source of truth · embeddings" }], { fill: "ECFDF5", accent: C.good }),
    new TableCell({ borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }, width: { size: 240, type: WidthType.DXA }, children: [new Paragraph({ children: [T("")] })] }),
    diagBox([{ t: "Redis" }, { t: "cache · sessions · staging" }], { fill: "ECFDF5", accent: C.good }),
    new TableCell({ borders: { top: { style: BorderStyle.NONE }, bottom: { style: BorderStyle.NONE }, left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE } }, width: { size: 240, type: WidthType.DXA }, children: [new Paragraph({ children: [T("")] })] }),
    diagBox([{ t: "Uploads / GCS" }, { t: "item images" }], { fill: "ECFDF5", accent: C.good }),
  ], [2960, 240, 2960, 240, 2960]),
  spacer(80)
);

push(
  h2("How services are wired"),
  bullet([T("Browser → API: ", { bold: true }), T("the SPA uses a relative /api/v1 path; nginx is hit first and proxies every /api route to the gateway.")]),
  bullet([T("AI orchestration: ", { bold: true }), T("gateway AI routes assemble user/closet/RAG context, then call the AI-agent via an internal client, attaching an X-Internal-Token for service-to-service auth.")]),
  bullet([T("Vision in-process: ", { bold: true }), T("detection and background-removal run inside the gateway (no separate heavy container needed for the MVP), backed by Postgres/Redis.")]),
  bullet([T("Shared state: ", { bold: true }), T("Postgres is the source of truth; Redis handles cache, sessions, and staging.")]),
  bullet([T("Real-time: ", { bold: true }), T("the browser WebSocket connects to /api/v1/ws; nginx upgrades and forwards to the gateway's WS hub.")]),
  spacer(40),
  h2("Domain-driven API"),
  body("The gateway's API is organized into clear business domains, which keeps the platform extensible as new capabilities are added:"),
  table(
    ["Domain", "Capabilities"],
    [
      ["Identity", "Registration, login, JWT + refresh, Google OAuth, profile."],
      ["Wardrobe", "Closet CRUD, similarity, outfits, outfit history, planner, smart ingest, vision pipeline."],
      ["Intelligence", "FANI AI, AI chat, fashion RAG, purchase gaps, unified RAG, shopping check, background jobs."],
      ["Travel", "Trips, weather, packing memory."],
      ["Social", "Groups / sharing foundations."],
      ["Platform", "Analytics, admin, health, real-time monitoring (RUM), WebSocket hub."],
    ],
    [2200, 7160]
  )
);

// 6. Technology Stack
push(
  h1("6. Technology Stack"),
  table(
    ["Layer", "Technology"],
    [
      ["Frontend", "React 18, Vite 5, TypeScript, Tailwind CSS, React Router, Recharts, Framer Motion, PWA, Sentry."],
      ["API / Backend", "Python, FastAPI, SQLAlchemy (async), Alembic migrations, Pydantic."],
      ["AI agent", "LangGraph + LangChain orchestration; OpenAI and Google Gemini models; LangSmith tracing."],
      ["Vision", "In-process image detection and background removal (Pillow + model/API providers)."],
      ["Retrieval / RAG", "pgvector embeddings in Postgres for closet similarity, fashion knowledge, and purchase-gap reasoning."],
      ["Data & cache", "PostgreSQL + pgvector, Redis (cache/sessions/staging), Google Cloud Storage for images."],
      ["Edge / infra", "nginx, Docker Compose (dev + prod), Render / Netlify deployment, optional Kafka producers."],
      ["Observability", "Sentry (errors), Prometheus metrics, OpenTelemetry instrumentation, real-user monitoring."],
      ["Quality", "~475 backend tests + frontend tests, ESLint/Ruff, GitHub Actions CI."],
    ],
    [2100, 7260]
  ),
  spacer(60),
  callout("Why this stack matters to investors", [
    "It is modern, hireable, and cost-efficient: mainstream open frameworks (React/FastAPI/Postgres) keep talent costs low, while pgvector means AI retrieval runs on the same database — no extra vector-DB vendor bill. Model providers are swappable (OpenAI / Gemini), avoiding lock-in.",
  ], C.zebra, C.brand)
);

// 7. AI & Data Moat
push(
  h1("7. AI Capabilities & Data Moat"),
  h2("What the AI does"),
  bullet([T("Grounded recommendations (RAG): ", { bold: true }), T("FANI's answers are retrieved from the user's real items and a fashion-knowledge base, making them personal and explainable rather than generic.")]),
  bullet([T("Vision ingestion: ", { bold: true }), T("turns a phone photo into a clean, catalogued wardrobe item via detection + background removal.")]),
  bullet([T("Vector similarity: ", { bold: true }), T("'similar items', outfit matching, and gap detection use embeddings in pgvector.")]),
  bullet([T("Conversational styling: ", { bold: true }), T("persisted, streaming chat with the FANI stylist across the whole app.")]),
  bullet([T("Personalization memory: ", { bold: true }), T("style profile (incl. attributes like skin tone), outfit history, and packing memory continuously sharpen recommendations.")]),
  spacer(60),
  h2("The defensibility / moat"),
  body("The strategic asset is not the model — anyone can call an LLM. It is the proprietary, structured, per-user wardrobe data plus the behavioral history (what's worn, rated, packed) that makes ClozeHive's recommendations uniquely accurate and hard to replicate."),
  bullet("Each catalogued item and worn outfit increases switching costs and recommendation quality (a data network effect per user)."),
  bullet("Model-agnostic design means improving foundation models lift the product for free, while costs trend down."),
  bullet("RAG grounding keeps outputs explainable and on-brand, reducing hallucination risk versus pure-LLM competitors."),
);

// 8. Use Cases
push(
  h1("8. Use Cases"),
  h2("Consumer use cases (today)"),
  table(
    ["Persona", "Job-to-be-done", "ClozeHive answer"],
    [
      ["Busy professional", "Decide what to wear fast, every day", "Outfit of the Day + 5-tier rating + FANI chat"],
      ["Overwhelmed shopper", "Stop buying duplicates", "Purchase-gap analysis + Shopping Check"],
      ["Frequent traveler", "Pack right for a trip", "Weather-aware packing lists + packing memory"],
      ["Style explorer", "Get more from owned clothes", "Most/Never-worn insights + similar items"],
      ["Sustainability-minded", "Re-wear, not over-consume", "Utilization analytics; gap-driven (not push) shopping"],
    ],
    [1900, 3400, 4060]
  ),
  spacer(60),
  h2("Expansion use cases (roadmap)"),
  bullet([T("Affiliate & brand partnerships: ", { bold: true }), T("high-intent, gap-driven product recommendations (buy what genuinely completes the wardrobe).")]),
  bullet([T("Social & sharing: ", { bold: true }), T("groups, outfit sharing, and community styling (foundations already in the codebase).")]),
  bullet([T("Resale / circularity: ", { bold: true }), T("surface never-worn items for resale or donation.")]),
  bullet([T("Retail / brand B2B: ", { bold: true }), T("anonymized wardrobe insights and styling-as-a-service for brands.")]),
);

// 9. MVP / MSP
push(
  h1("9. MVP, MSP & Roadmap"),
  h2("MVP — Minimum Viable Product (shipped)"),
  body("The deployed product already delivers the core value loop end to end:"),
  bullet("Auth (email + Google OAuth), digital closet with image upload and vision ingestion."),
  bullet("FANI stylist: chat, Outfit of the Day, 5-tier ratings, daily tips."),
  bullet("RAG-grounded intelligence: similarity, purchase gaps, fashion knowledge."),
  bullet("Travel packing, analytics, profile/settings, real-time notifications."),
  spacer(40),
  h2("MSP — Minimum Sellable / Saleable Product (beta hardening, in progress)"),
  body("The near-term work converts the MVP into something ready to charge for and scale safely:"),
  bullet("Security hardening: secret rotation, credential hygiene (tracked in SECURITY.md)."),
  bullet("Reliability: automated backups, restore drills, migration safety (per-step commits already in place)."),
  bullet("Onboarding polish and conversion funnel; performance tuning on vision-heavy paths."),
  bullet("Billing / subscription plumbing for paid tiers."),
  spacer(40),
  h2("Roadmap themes (next)"),
  table(
    ["Horizon", "Focus"],
    [
      ["Now (beta)", "Harden, instrument conversion, paid-tier billing, mobile-quality PWA."],
      ["Next", "Affiliate/brand commerce, social & sharing, smarter personalization memory."],
      ["Later", "Native mobile, resale/circularity, B2B styling APIs for brands/retail."],
    ],
    [2000, 7360]
  )
);

// 10. Measures: security, reliability, quality
push(
  h1("10. Engineering Measures & Safeguards"),
  body("ClozeHive is built with production discipline rather than as a prototype, which de-risks scaling and reduces future technical debt."),
  h2("Security"),
  bullet("JWT access + refresh tokens; Google OAuth with Redis-backed CSRF state."),
  bullet("Service-to-service authentication between gateway and AI-agent (internal token)."),
  bullet("Documented security policy and disclosure process (SECURITY.md); known-credential rotation playbook for safe beta launch."),
  bullet("Privacy controls in user settings; secrets kept in env/secret manager, not code (enforced via .gitignore and history-cleanup guidance)."),
  spacer(40),
  h2("Reliability & operations"),
  bullet("Health endpoints (/live, /ready, /health) for orchestration and uptime checks."),
  bullet("33 versioned Alembic migrations with per-step commits so an interrupted upgrade persists safely."),
  bullet("Database backups and restore scripting; Dockerized, reproducible environments for dev and prod."),
  bullet("Runbook and services documentation for on-call operations (docs/RUNBOOK.md, docs/SERVICES.md)."),
  spacer(40),
  h2("Quality & observability"),
  bullet("~475 backend tests plus frontend tests; GitHub Actions CI pipeline."),
  bullet("Sentry error tracking (frontend + backend), Prometheus metrics, OpenTelemetry tracing, real-user monitoring."),
  bullet("LangSmith tracing for AI calls to monitor quality, latency, and cost of FANI."),
  spacer(40),
  h2("Cost & scalability posture"),
  bullet("pgvector co-locates retrieval with the primary DB — no separate vector-DB cost."),
  bullet("Model-agnostic AI layer (OpenAI / Gemini) enables routing to the cheapest capable model."),
  bullet("Stateless application services behind nginx scale horizontally; Redis offloads hot paths."),
);

// 11. Business model
push(
  h1("11. Business Model & Go-to-Market"),
  h2("Revenue streams"),
  table(
    ["Stream", "Description"],
    [
      ["Freemium subscription", "Free closet + limited FANI; paid tier unlocks unlimited AI styling, advanced analytics, travel planning."],
      ["Affiliate commerce", "Commission on gap-driven, high-intent product recommendations."],
      ["Brand partnerships", "Sponsored placements and styling integrations grounded in real wardrobe fit."],
      ["B2B / data services", "Anonymized wardrobe insights and styling-as-a-service for retailers (longer-term)."],
    ],
    [2600, 6760]
  ),
  spacer(60),
  h2("Go-to-market"),
  bullet("Web-first PWA for fast, install-free acquisition; marketing site already live."),
  bullet("Habit-forming daily loop (Outfit of the Day, tips) to drive retention before monetization."),
  bullet("Content + social sharing as organic acquisition; gap analysis as a natural shopping bridge."),
  spacer(40),
  h2("Why ClozeHive wins"),
  bullet([T("Owned data: ", { bold: true }), T("recommendations grounded in the user's actual wardrobe — competitors selling products can't match the trust or personalization.")]),
  bullet([T("Utilization-first: ", { bold: true }), T("aligned with the user (use what you own) builds loyalty; monetization is additive, not adversarial.")]),
  bullet([T("Real engineering: ", { bold: true }), T("a deployed, tested, observable platform — not a demo — shortens time-to-scale.")]),
);

// 12. Summary / ask
push(
  h1("12. Summary"),
  body("ClozeHive has turned a universal, daily frustration — 'a full closet and nothing to wear' — into an AI product that is already built, deployed, and architecturally ready to scale. FANI delivers grounded, explainable styling over a proprietary wardrobe dataset that compounds in value with every use."),
  callout("Investment thesis in three lines", [
    "1. Big, evergreen problem with no trusted, closet-grounded AI incumbent.",
    "2. A defensible data moat that strengthens with usage and is model-agnostic to AI cost curves.",
    "3. A real, production-grade product today — capital accelerates growth and monetization, not basic build-out.",
  ], C.goodFill, C.good),
  spacer(120),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200 },
    children: [T("ClozeHive — Wardrobe Intelligence, Powered by FANI", { italics: true, color: C.sub, size: 20 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [T("clozehive.netlify.app  ·  cloze-hive.onrender.com", { color: C.brand, size: 18 })],
  })
);

// ---------- assemble ----------
const doc = new Document({
  creator: "ClozeHive",
  title: "ClozeHive Investor Report",
  description: "Investor briefing & technical overview",
  styles: {
    default: { document: { run: { font: "Arial", size: 21, color: C.ink } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, color: C.brandDark, font: "Arial" },
        paragraph: { spacing: { before: 280, after: 200 }, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: C.brand, space: 6 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 25, bold: true, color: C.accent, font: "Arial" },
        paragraph: { spacing: { before: 220, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, color: C.ink, font: "Arial" },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [
        { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { run: { color: C.brand }, paragraph: { indent: { left: 600, hanging: 280 } } } },
        { level: 1, format: LevelFormat.BULLET, text: "◦", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 1080, hanging: 280 } } } },
      ]},
      { reference: "nums", levels: [
        { level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { run: { bold: true, color: C.brand }, paragraph: { indent: { left: 600, hanging: 320 } } } },
      ]},
    ],
  },
  sections: [
    // cover (no header/footer)
    { properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
      children: [...coverChildren, ...tocChildren] },
    // body with header/footer
    { properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
      headers: { default: new Header({ children: [ new Paragraph({
        tabStops: [{ type: TabStopType.RIGHT, position: 9360 }],
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C.line, space: 4 } },
        children: [ T("ClozeHive", { bold: true, color: C.brand, size: 16 }), T("\tInvestor Briefing — Confidential", { color: C.sub, size: 16 }) ],
      }) ] }) },
      footers: { default: new Footer({ children: [ new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [ T("ClozeHive · Confidential   |   Page ", { color: C.sub, size: 16 }),
          new TextRun({ children: [PageNumber.CURRENT], color: C.sub, size: 16, font: "Arial" }) ],
      }) ] }) },
      children: docChildren },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("WROTE", OUT, buf.length, "bytes");
});
