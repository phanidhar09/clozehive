"""Unit tests for product URL parsing + SSRF guard (Shop with FANI link paste).

These cover the pure logic — HTML/JSON-LD extraction and the SSRF host guard —
without any network access.
"""

from __future__ import annotations

import pytest

from app.core import product_url
from app.core.exceptions import BadRequestError


def test_parse_open_graph_resolves_relative_image():
    html = """
    <html><head>
      <meta property="og:title" content="Linen Blazer">
      <meta property="og:image" content="/img/blazer.jpg">
      <meta property="og:site_name" content="Acme">
      <meta property="product:brand" content="Acme">
      <meta property="product:price:amount" content="129.00">
    </head></html>
    """
    meta = product_url.parse_product_html("https://shop.example.com/p/123", html)
    assert meta.title == "Linen Blazer"
    assert meta.image_url == "https://shop.example.com/img/blazer.jpg"
    assert meta.brand == "Acme"
    assert meta.price == "129.00"
    assert meta.site_name == "Acme"


def test_parse_jsonld_fills_missing_fields():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Product","name":"Wool Coat",
       "brand":{"name":"NorthCo"},"image":["https://cdn.example.com/coat.jpg"],
       "offers":{"@type":"Offer","price":"249.99","priceCurrency":"USD"}}
      </script>
    </head></html>
    """
    meta = product_url.parse_product_html("https://x.example.com/coat", html)
    assert meta.title == "Wool Coat"
    assert meta.brand == "NorthCo"
    assert meta.image_url == "https://cdn.example.com/coat.jpg"
    assert meta.price == "249.99"


def test_parse_jsonld_graph_wrapper():
    html = """
    <html><head>
      <script type="application/ld+json">
      {"@graph":[{"@type":"WebPage"},
                 {"@type":"Product","name":"Cap","image":"https://c.example.com/c.png"}]}
      </script>
    </head></html>
    """
    meta = product_url.parse_product_html("https://y.example.com/cap", html)
    assert meta.title == "Cap"
    assert meta.image_url == "https://c.example.com/c.png"


def test_og_preferred_over_jsonld_title():
    html = """
    <html><head>
      <meta property="og:title" content="OG Name">
      <script type="application/ld+json">
      {"@type":"Product","name":"LD Name","image":"https://c.example.com/i.jpg"}
      </script>
    </head></html>
    """
    meta = product_url.parse_product_html("https://z.example.com/i", html)
    assert meta.title == "OG Name"  # OG wins
    assert meta.image_url == "https://c.example.com/i.jpg"  # JSON-LD fills the gap


def test_title_fallback_when_no_metadata():
    html = "<html><head><title>Just A Page</title></head></html>"
    meta = product_url.parse_product_html("https://t.example.com", html)
    assert meta.title == "Just A Page"
    assert meta.image_url is None


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
        "http://10.0.0.5/internal",
        "http://192.168.1.1/admin",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "javascript:alert(1)",
    ],
)
def test_ssrf_guard_blocks_dangerous_urls(url):
    with pytest.raises(BadRequestError):
        product_url._validate_url(url)


def test_ssrf_guard_allows_public_https():
    assert product_url._validate_url("https://www.example.com/p") == "https://www.example.com/p"


# ── DNS pinning (rebinding / TOCTOU) ─────────────────────────────────────────


def _fake_getaddrinfo(ip: str):
    def fake(host, port, **kw):
        return [(2, 1, 6, "", (ip, 0))]

    return fake


def test_pinned_request_connects_to_validated_ip(monkeypatch):
    monkeypatch.setattr(product_url.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    request_url, headers, extensions = product_url._pinned_request("https://shop.example.com/p/1?x=1")
    # The connection target is the exact IP that passed validation — no second
    # DNS lookup happens, so a rebinding resolver has nothing left to poison.
    assert request_url == "https://93.184.216.34/p/1?x=1"
    assert headers == {"Host": "shop.example.com"}
    assert extensions == {"sni_hostname": "shop.example.com"}


def test_pinned_request_keeps_port_and_http_has_no_sni(monkeypatch):
    monkeypatch.setattr(product_url.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    request_url, headers, extensions = product_url._pinned_request("http://shop.example.com:8080/p")
    assert request_url == "http://93.184.216.34:8080/p"
    assert headers == {"Host": "shop.example.com:8080"}
    assert extensions == {}


def test_pinned_request_blocks_host_resolving_private(monkeypatch):
    # A rebinding attacker answering with the cloud metadata address is
    # rejected outright at resolution time.
    monkeypatch.setattr(product_url.socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254"))
    with pytest.raises(BadRequestError):
        product_url._pinned_request("https://attacker.example.com/x")


def test_pinned_request_brackets_ipv6(monkeypatch):
    monkeypatch.setattr(product_url.socket, "getaddrinfo", _fake_getaddrinfo("2606:2800:220:1::1"))
    request_url, headers, _ = product_url._pinned_request("https://shop.example.com/p")
    assert request_url == "https://[2606:2800:220:1::1]/p"
    assert headers == {"Host": "shop.example.com"}


def test_looks_like_url():
    assert product_url.looks_like_url("https://brand.com/jacket")
    assert product_url.looks_like_url("http://x.io")
    assert not product_url.looks_like_url("brand.com/jacket")
    assert not product_url.looks_like_url("not a url")


def test_product_name_hint_from_url():
    h = product_url.product_name_hint_from_url
    assert h("https://www.abercrombie.com/shop/us/p/premium-heavyweight-20-tee-58965824?categoryId=12835") == "premium heavyweight 20 tee"
    assert h("https://brand.com/products/charcoal-slim-chinos") == "charcoal slim chinos"
    assert h("https://brand.com/") is None
