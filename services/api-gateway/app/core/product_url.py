"""Product URL → image, for "Shop with FANI".

A user pastes a product link (brand page, marketplace listing, an outfit on a
brand's official page). We pull the product image + metadata WITHOUT running any
scraper infrastructure:

1. Fetch the page HTML once (SSRF-guarded, size-capped).
2. Parse Open Graph / Twitter Card / JSON-LD ``Product`` for an image + name,
   brand, price, description.
3. Download that image and hand the bytes to the existing vision pipeline.
4. If the page exposes no usable image, fall back to a rendered *screenshot*
   via a stateless screenshot service (config: ``product_screenshot_url_template``)
   and run the same vision pipeline on it.

Nothing here parses prices for commerce — metadata is only context for FANI's
verdict and attribution. The honest verdict still comes from the closet match.

Security: we fetch arbitrary user-supplied URLs server-side, so every outbound
request is SSRF-guarded — scheme must be http(s), and the resolved host must not
be private/loopback/link-local/reserved. Redirects are followed manually so each
hop is re-validated.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx

from app.core.config import get_settings
from app.core.exceptions import BadRequestError
from app.core.logging import get_logger
from app.core.upload_service import (
    MAX_UPLOAD_SIZE_BYTES,
    _detect_image_type,
    strip_metadata,
)

logger = get_logger("product_url")

_REQUEST_TIMEOUT_S = 12
_MAX_HTML_BYTES = 3 * 1024 * 1024  # 3 MB of HTML is plenty for the <head>
_MAX_REDIRECTS = 5
# A real browser UA — many brand CDNs serve a bare page (or 403) to bots, which
# would strip the OG tags we need.
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class ProductMetadata:
    source_url: str
    image_url: str | None = None
    title: str | None = None
    description: str | None = None
    brand: str | None = None
    price: str | None = None
    site_name: str | None = None
    extra_image_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "image_url": self.image_url,
            "title": self.title,
            "description": self.description,
            "brand": self.brand,
            "price": self.price,
            "site_name": self.site_name,
        }


# ── SSRF guard ────────────────────────────────────────────────────────────────


def _is_blocked_ip(host: str) -> bool:
    """True if any address ``host`` resolves to is private/loopback/reserved."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Unresolvable host — treat as blocked; the fetch would fail anyway.
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def _validate_url(url: str) -> str:
    """Validate scheme + host for SSRF. Returns the URL or raises BadRequestError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BadRequestError("Only http(s) product URLs are supported.")
    if not parsed.hostname:
        raise BadRequestError("That doesn't look like a valid URL.")
    if _is_blocked_ip(parsed.hostname):
        raise BadRequestError("That URL points to a private or unreachable address.")
    return url


# ── HTML metadata parsing ─────────────────────────────────────────────────────


class _MetaParser(HTMLParser):
    """Collect <meta property/name>, JSON-LD blocks, and <title> from <head>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metas: dict[str, str] = {}
        self.jsonld_blocks: list[str] = []
        self.title: str | None = None
        self._in_title = False
        self._in_jsonld = False
        self._jsonld_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").strip().lower()
            content = a.get("content") or ""
            if key and content and key not in self.metas:
                self.metas[key] = content.strip()
        elif tag == "title":
            self._in_title = True
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            block = "".join(self._jsonld_buf).strip()
            if block:
                self.jsonld_blocks.append(block)

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is None and data.strip():
            self.title = data.strip()
        elif self._in_jsonld:
            self._jsonld_buf.append(data)


def _first_str(value: Any) -> str | None:
    """Coerce a JSON-LD field (str | list | dict) to a single trimmed string."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        for v in value:
            s = _first_str(v)
            if s:
                return s
        return None
    if isinstance(value, dict):
        # e.g. brand: {"name": "Acme"}, image: {"url": "..."}
        for k in ("name", "url", "@id"):
            if k in value:
                s = _first_str(value[k])
                if s:
                    return s
    return None


def _walk_jsonld_products(node: Any):
    """Yield every dict in a JSON-LD tree whose @type looks like a Product."""
    if isinstance(node, list):
        for item in node:
            yield from _walk_jsonld_products(item)
    elif isinstance(node, dict):
        if "@graph" in node:
            yield from _walk_jsonld_products(node["@graph"])
        typ = node.get("@type", "")
        types = [typ] if isinstance(typ, str) else (typ if isinstance(typ, list) else [])
        if any("product" in str(t).lower() for t in types):
            yield node
        for value in node.values():
            if isinstance(value, (list, dict)):
                yield from _walk_jsonld_products(value)


def _parse_jsonld(blocks: list[str], meta: ProductMetadata) -> None:
    """Fill missing metadata fields from the first JSON-LD Product found."""
    for block in blocks:
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        for product in _walk_jsonld_products(data):
            if not meta.image_url:
                img = _first_str(product.get("image"))
                if img:
                    meta.image_url = img
            if not meta.title:
                meta.title = _first_str(product.get("name"))
            if not meta.brand:
                meta.brand = _first_str(product.get("brand"))
            if not meta.description:
                meta.description = _first_str(product.get("description"))
            if not meta.price:
                offers = product.get("offers")
                meta.price = _first_str(offers.get("price")) if isinstance(offers, dict) else _first_str(offers)
            if meta.image_url and meta.title:
                return


def parse_product_html(url: str, html_text: str) -> ProductMetadata:
    """Extract product metadata from page HTML (OG → Twitter → JSON-LD → title)."""
    parser = _MetaParser()
    try:
        parser.feed(html_text)
    except Exception as exc:  # noqa: BLE001 — malformed HTML must not crash the request
        logger.warning("product_html_parse_failed", error=str(exc), url=url[:120])

    m = parser.metas
    meta = ProductMetadata(source_url=url)

    # Open Graph + Twitter Card (preferred — author-curated).
    meta.image_url = m.get("og:image") or m.get("og:image:url") or m.get("twitter:image")
    meta.title = m.get("og:title") or m.get("twitter:title")
    meta.description = m.get("og:description") or m.get("twitter:description") or m.get("description")
    meta.brand = m.get("product:brand") or m.get("og:brand")
    meta.price = m.get("product:price:amount") or m.get("og:price:amount")
    meta.site_name = m.get("og:site_name")

    # JSON-LD fills whatever OG didn't provide.
    _parse_jsonld(parser.jsonld_blocks, meta)

    # Last-ditch human-readable title.
    if not meta.title and parser.title:
        meta.title = parser.title

    # Normalize: unescape entities, resolve relative image URLs, trim.
    if meta.image_url:
        meta.image_url = urljoin(url, html.unescape(meta.image_url.strip()))
    for fld in ("title", "description", "brand", "site_name"):
        val = getattr(meta, fld)
        if val:
            setattr(meta, fld, html.unescape(val.strip())[:500])

    return meta


# ── HTTP fetching ─────────────────────────────────────────────────────────────


async def _get(url: str, *, accept: str) -> httpx.Response:
    """SSRF-guarded GET that follows redirects manually, validating each hop."""
    current = _validate_url(url)
    headers = {"User-Agent": _USER_AGENT, "Accept": accept}
    async with httpx.AsyncClient(
        timeout=_REQUEST_TIMEOUT_S, follow_redirects=False
    ) as client:
        for _ in range(_MAX_REDIRECTS):
            resp = await client.get(current, headers=headers)
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    break
                current = _validate_url(urljoin(current, location))
                continue
            resp.raise_for_status()
            return resp
    raise BadRequestError("That URL redirected too many times.")


async def fetch_product_metadata(url: str) -> ProductMetadata:
    """Fetch a product page and extract its image + metadata. Raises on bad URL."""
    url = _validate_url(url.strip())
    try:
        resp = await _get(url, accept="text/html,application/xhtml+xml")
    except BadRequestError:
        raise
    except httpx.HTTPStatusError as exc:
        logger.info("product_page_http_error", status=exc.response.status_code, url=url[:120])
        raise BadRequestError(f"Couldn't open that page (HTTP {exc.response.status_code}).") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("product_page_fetch_failed", error=str(exc), url=url[:120])
        raise BadRequestError("Couldn't reach that URL. Check the link and try again.") from exc

    # Cap how much HTML we parse (the metadata lives in <head>).
    raw = resp.content[:_MAX_HTML_BYTES]
    encoding = resp.encoding or "utf-8"
    try:
        html_text = raw.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        html_text = raw.decode("utf-8", errors="replace")

    # Final landing URL (after redirects) is the canonical source for the user.
    final_url = str(resp.url) if resp.url else url
    meta = parse_product_html(final_url, html_text)
    meta.source_url = url  # keep what the user actually pasted
    return meta


async def fetch_image_bytes(image_url: str) -> tuple[bytes, str] | None:
    """Download + validate a remote image. Returns (bytes, media_type) or None.

    Re-encodes via Pillow so non-JPEG/PNG/WebP source images (AVIF, GIF) still
    flow into the vision pipeline, and EXIF is stripped along the way.
    """
    try:
        resp = await _get(image_url, accept="image/*")
    except Exception as exc:  # noqa: BLE001 — image is best-effort; caller may screenshot
        logger.info("product_image_fetch_failed", error=str(exc), url=image_url[:120])
        return None

    data = resp.content
    if not data or len(data) > MAX_UPLOAD_SIZE_BYTES:
        return None

    media_type = _detect_image_type(data[:12])
    if media_type is None:
        # Unknown/animated format — try to transcode to JPEG via Pillow.
        converted = _transcode_to_jpeg(data)
        if converted is None:
            return None
        return converted, "image/jpeg"

    return strip_metadata(data, media_type), media_type


def _transcode_to_jpeg(data: bytes) -> bytes | None:
    try:
        import io

        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90, optimize=True)
        out = buf.getvalue()
        return out if 0 < len(out) <= MAX_UPLOAD_SIZE_BYTES else None
    except Exception:  # noqa: BLE001
        return None


async def fetch_page_screenshot(url: str) -> tuple[bytes, str] | None:
    """Render the page to an image via the configured screenshot service.

    Returns (bytes, media_type) or None when no service is configured (the
    "no scraper infrastructure" default) or rendering fails. The template's
    ``{url}`` placeholder is replaced with the URL-encoded page address.
    """
    template = get_settings().product_screenshot_url_template
    if not template:
        return None
    shot_url = template.replace("{url}", quote(url, safe=""))
    try:
        # The screenshot service host is operator-configured (not user input),
        # so this fetch is trusted; we still validate the rendered URL's scheme.
        parsed = urlparse(shot_url)
        if parsed.scheme not in ("http", "https"):
            return None
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S, follow_redirects=True) as client:
            resp = await client.get(shot_url, headers={"User-Agent": _USER_AGENT})
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("product_screenshot_failed", error=str(exc), url=url[:120])
        return None

    data = resp.content
    if not data or len(data) > MAX_UPLOAD_SIZE_BYTES:
        return None
    media_type = _detect_image_type(data[:12])
    if media_type is None:
        converted = _transcode_to_jpeg(data)
        return (converted, "image/jpeg") if converted else None
    return strip_metadata(data, media_type), media_type


_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def looks_like_url(value: str) -> bool:
    return bool(_URL_RE.match(value.strip()))


# Trailing product-id chunks in a slug we don't want in the readable name.
_SLUG_ID_RE = re.compile(r"\b\d{5,}\b")


def product_name_hint_from_url(url: str) -> str | None:
    """Best-effort readable product name from a URL slug — the cheap signal that
    survives even when a bot-blocked page exposes no title. E.g.
    ".../p/premium-heavyweight-20-tee-58965824?..." → "premium heavyweight 20 tee".
    """
    try:
        path = urlparse(url).path
    except ValueError:
        return None
    segments = [s for s in path.split("/") if s and s.lower() not in ("p", "shop", "us", "product", "products")]
    if not segments:
        return None
    slug = segments[-1]
    words = slug.replace("_", "-").split("-")
    words = [w for w in words if w and not _SLUG_ID_RE.fullmatch(w)]
    name = " ".join(words).strip()
    return name or None
