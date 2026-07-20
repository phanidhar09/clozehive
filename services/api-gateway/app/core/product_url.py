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
from urllib.parse import quote, unquote, urljoin, urlparse

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
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
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


def _validated_public_ip(host: str) -> str:
    """Resolve ``host`` once; return one validated public IP or raise.

    The returned IP is the address the fetch MUST connect to. Validating here
    and letting httpx re-resolve at connect time would be a TOCTOU hole: an
    attacker-controlled resolver can answer the validation lookup with a public
    IP and the connect lookup with 169.254.169.254 (DNS rebinding).
    """
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Unresolvable host — the fetch would fail anyway.
        raise BadRequestError("That URL points to a private or unreachable address.") from None
    blocked = "That URL points to a private or unreachable address."
    if not infos:
        raise BadRequestError(blocked)
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            raise BadRequestError(blocked) from None
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise BadRequestError(blocked)
    return str(infos[0][4][0])


def _validate_url(url: str) -> str:
    """Validate scheme + host for SSRF. Returns the URL or raises BadRequestError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BadRequestError("Only http(s) product URLs are supported.")
    if not parsed.hostname:
        raise BadRequestError("That doesn't look like a valid URL.")
    _validated_public_ip(parsed.hostname)
    return url


def _pinned_request(url: str) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Validate ``url`` and pin the request to the resolved, validated IP.

    Returns ``(request_url, extra_headers, extensions)``: the request URL has
    the hostname replaced by the validated IP so httpx connects to exactly the
    address that passed the SSRF check (no second DNS lookup an attacker's
    resolver could answer differently). The Host header and TLS SNI keep the
    original hostname so virtual hosts and certificate verification still work.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise BadRequestError("Only http(s) product URLs are supported.")
    host = parsed.hostname
    if not host:
        raise BadRequestError("That doesn't look like a valid URL.")
    ip = _validated_public_ip(host)
    ip_netloc = f"[{ip}]" if ":" in ip else ip
    if parsed.port:
        ip_netloc += f":{parsed.port}"
    request_url = parsed._replace(netloc=ip_netloc).geturl()
    host_header = host if parsed.port is None else f"{host}:{parsed.port}"
    extensions: dict[str, Any] = {"sni_hostname": host} if parsed.scheme == "https" else {}
    return request_url, {"Host": host_header}, extensions


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


async def _get(url: str, *, accept: str) -> tuple[httpx.Response, str]:
    """SSRF-guarded GET: follows redirects manually, DNS-pinning every hop.

    Returns ``(response, final_url)`` — ``final_url`` is the hostname form of
    the last hop (``response.url`` is the IP-pinned form and must not be used
    for anything user-facing or for resolving relative URLs).
    """
    current = url
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS):
            request_url, extra_headers, extensions = _pinned_request(current)
            headers = {"User-Agent": _USER_AGENT, "Accept": accept, **extra_headers}
            resp = await client.get(request_url, headers=headers, extensions=extensions)
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    break
                current = urljoin(current, location)
                continue
            resp.raise_for_status()
            return resp, current
    raise BadRequestError("That URL redirected too many times.")


async def fetch_product_metadata(url: str) -> ProductMetadata:
    """Fetch a product page and extract its image + metadata. Raises on bad URL."""
    url = _validate_url(url.strip())
    try:
        resp, final_url = await _get(url, accept="text/html,application/xhtml+xml")
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

    # Final landing URL (after redirects) is the canonical source for the user;
    # _get returns it in hostname form (resp.url is the IP-pinned request URL).
    meta = parse_product_html(final_url, html_text)
    meta.source_url = url  # keep what the user actually pasted
    return meta


async def fetch_image_bytes(image_url: str) -> tuple[bytes, str] | None:
    """Download + validate a remote image. Returns (bytes, media_type) or None.

    Re-encodes via Pillow so non-JPEG/PNG/WebP source images (AVIF, GIF) still
    flow into the vision pipeline, and EXIF is stripped along the way.
    """
    try:
        resp, _ = await _get(image_url, accept="image/*")
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
        img: Image.Image = Image.open(io.BytesIO(data))
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
_PURE_ID_RE = re.compile(r"^\d{3,}$")

# Marketplace / PDP path noise — Myntra ends product URLs with /{id}/buy.
_URL_JUNK_SEGMENTS = frozenset(
    {
        "p",
        "shop",
        "us",
        "uk",
        "en",
        "product",
        "products",
        "buy",
        "cart",
        "checkout",
        "pdp",
        "dp",
        "gp",
        "item",
        "items",
        "detail",
        "details",
        "view",
        "index",
        "html",
        "www",
        "m",
        "mobile",
    }
)

# Single-token titles that are page chrome, not garment names.
_USELESS_PRODUCT_LABELS = frozenset(
    {
        "buy",
        "shop",
        "cart",
        "product",
        "products",
        "item",
        "sale",
        "new",
        "home",
        "unknown",
        "untitled",
        "n/a",
        "na",
        "none",
    }
)

# Path tokens → closet category (used when vision returns "other").
_URL_CATEGORY_HINTS: dict[str, str] = {
    "jeans": "bottoms",
    "trousers": "bottoms",
    "pants": "bottoms",
    "chinos": "bottoms",
    "shorts": "bottoms",
    "skirt": "bottoms",
    "skirts": "bottoms",
    "leggings": "bottoms",
    "shirt": "tops",
    "shirts": "tops",
    "tshirt": "tops",
    "t-shirt": "tops",
    "tee": "tops",
    "tees": "tops",
    "top": "tops",
    "tops": "tops",
    "blouse": "tops",
    "sweater": "tops",
    "hoodie": "tops",
    "polo": "tops",
    "jacket": "outerwear",
    "jackets": "outerwear",
    "coat": "outerwear",
    "coats": "outerwear",
    "blazer": "outerwear",
    "outerwear": "outerwear",
    "shoe": "shoes",
    "shoes": "shoes",
    "sneakers": "shoes",
    "boots": "shoes",
    "sandals": "shoes",
    "heels": "shoes",
    "loafers": "shoes",
    "dress": "dresses",
    "dresses": "dresses",
    "gown": "dresses",
    "jumpsuit": "dresses",
    "bag": "accessories",
    "bags": "accessories",
    "belt": "accessories",
    "watch": "accessories",
    "scarf": "accessories",
}


def is_useless_product_label(value: str | None) -> bool:
    """True for chrome labels like \"Buy\" that must not become closet names."""
    if value is None:
        return True
    cleaned = re.sub(r"\s+", " ", str(value)).strip().lower()
    if not cleaned:
        return True
    if cleaned in _USELESS_PRODUCT_LABELS:
        return True
    # Page titles that are just a CTA word + punctuation.
    return cleaned.strip("!.:-_|") in _USELESS_PRODUCT_LABELS


def _path_segments(url: str) -> list[str]:
    try:
        path = unquote(urlparse(url).path)
    except ValueError:
        return []
    out: list[str] = []
    for raw in path.split("/"):
        seg = raw.strip().lower()
        if not seg or seg in _URL_JUNK_SEGMENTS:
            continue
        if _PURE_ID_RE.fullmatch(seg):
            continue
        out.append(seg)
    return out


def product_name_hint_from_url(url: str) -> str | None:
    """Best-effort readable product name from a URL slug — the cheap signal that
    survives even when a bot-blocked page exposes no title. E.g.
    ".../p/premium-heavyweight-20-tee-58965824?..." → "premium heavyweight 20 tee".

    Skips marketplace tails like ``/buy`` and numeric product ids (Myntra-style
    ``.../stretchable-jeans/25917818/buy``).
    """
    segments = _path_segments(url)
    if not segments:
        return None

    # Prefer the longest descriptive slug (usually the product name segment).
    slug = max(segments, key=lambda s: len(re.sub(r"[-_]+", " ", s).split()))
    words = [w for w in re.split(r"[-_+]+", slug) if w and not _SLUG_ID_RE.fullmatch(w)]
    name = " ".join(words).strip()
    if is_useless_product_label(name):
        return None
    return name or None


def category_hint_from_url(url: str) -> str | None:
    """Infer a closet category from path tokens (e.g. ``/jeans/...`` → bottoms)."""
    for seg in _path_segments(url):
        if seg in _URL_CATEGORY_HINTS:
            return _URL_CATEGORY_HINTS[seg]
        for token in re.split(r"[-_+]+", seg):
            if token in _URL_CATEGORY_HINTS:
                return _URL_CATEGORY_HINTS[token]
    return None
