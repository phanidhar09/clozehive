"""
Firebase Admin SDK initialisation and async Firestore client accessor.

Initialisation priority:
  1. FIREBASE_CREDENTIALS_JSON env var  → JSON string of service-account key
  2. GOOGLE_APPLICATION_CREDENTIALS env var → path to service-account JSON file
  3. Application Default Credentials     → works on GCP / Cloud Run automatically
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

import firebase_admin
from firebase_admin import credentials, firestore_async

from app.core.logging import get_logger

if TYPE_CHECKING:
    from google.cloud.firestore_v1.async_client import AsyncClient

logger = get_logger("firestore_client")

_app: firebase_admin.App | None = None
_db: "AsyncClient | None" = None


def init_firestore() -> None:
    """Initialise Firebase Admin SDK exactly once. Call from app lifespan."""
    global _app, _db

    if _app is not None:
        return

    from app.core.config import get_settings
    settings = get_settings()

    cred: credentials.Base | None = None

    if settings.firebase_credentials_json:
        try:
            key_dict = json.loads(settings.firebase_credentials_json)
            logger.info(
                "firestore_credentials_loaded",
                source="FIREBASE_CREDENTIALS_JSON",
                project_id=key_dict.get("project_id"),
                client_email=key_dict.get("client_email"),
            )
            cred = credentials.Certificate(key_dict)
            logger.info("firestore_init", source="env_json")
        except json.JSONDecodeError as exc:
            logger.error("firestore_credentials_invalid_json", source="FIREBASE_CREDENTIALS_JSON", error=str(exc))
            raise
        except Exception as exc:
            logger.error("firestore_init_failed", source="env_json", error=str(exc))
            raise
    elif os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        logger.info("firestore_credentials_loaded", source="GOOGLE_APPLICATION_CREDENTIALS", path=path)
        cred = credentials.ApplicationDefault()
        logger.info("firestore_init", source="GOOGLE_APPLICATION_CREDENTIALS")
    else:
        logger.info("firestore_credentials_loaded", source="application_default_credentials")
        cred = credentials.ApplicationDefault()
        logger.info("firestore_init", source="application_default")

    options: dict = {}
    if settings.firebase_project_id:
        options["projectId"] = settings.firebase_project_id

    _app = firebase_admin.initialize_app(cred, options)
    _db = firestore_async.client()
    logger.info(
        "firestore_ready",
        project=settings.firebase_project_id or "default",
        client_type="async",
        status="connected",
    )


def get_db() -> "AsyncClient":
    """Return the async Firestore client, initialising on first call."""
    global _db
    if _db is None:
        init_firestore()
    assert _db is not None, "Firestore was not initialised"
    return _db


async def close_firestore() -> None:
    """Clean up Firebase app on shutdown."""
    global _app, _db
    if _app is not None:
        try:
            firebase_admin.delete_app(_app)
            logger.info("firestore_closed")
        except Exception as exc:
            logger.warning("firestore_close_failed", error=str(exc))
        _app = None
        _db = None
