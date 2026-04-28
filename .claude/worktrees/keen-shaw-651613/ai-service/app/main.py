from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.routes import router

app = FastAPI(
    title="ClozéHive AI Service",
    description="Vision analysis · Outfit recommendations · Travel packing agent",
    version="1.0.0",
)

# ── CORS ───────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ─────────────────────────────────────────────────
app.include_router(router, prefix="/api")


@app.get("/health", tags=["Health"])
def health():
    from app.core.database import fetch_one
    try:
        row = fetch_one("SELECT COUNT(*) AS count FROM closet_items")
        db_status = "ok"
        closet_count = row["count"] if row else 0
    except Exception as e:
        db_status = f"error: {e}"
        closet_count = 0

    return JSONResponse({
        "status": "ok",
        "service": "ClozéHive AI",
        "version": "1.0.0",
        "database": db_status,
        "closet_items": closet_count,
        "llm_provider": settings.llm_provider,
        "openai_model": settings.openai_model,
    })
