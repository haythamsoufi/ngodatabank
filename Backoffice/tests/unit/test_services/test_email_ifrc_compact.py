"""Unit tests for IFRC email HTML compaction (gateway body size limits)."""

import base64

from app.services.email.client import _compact_ifrc_html_body


def _utf8_b64_len(html: str) -> int:
    return len(base64.b64encode(html.encode("utf-8")))


def test_compact_preserves_meaningful_content():
    html = "<div>\n  <p>Hello</p>\n  <!-- c -->\n  <p>World</p>\n</div>"
    out = _compact_ifrc_html_body(html)
    assert "<!--" not in out
    assert "Hello" in out and "World" in out
    assert out == "<div><p>Hello</p><p>World</p></div>"


def test_compact_squishes_style_block():
    html = (
        "<html><head><style>\n"
        "body { margin: 0; }\n"
        ".a { color: red; }\n"
        "</style></head><body><p>x</p></body></html>"
    )
    out = _compact_ifrc_html_body(html)
    assert "\n" not in out or out.count("\n") <= 0
    assert "margin:0" in out and "body{" in out
    assert "color:red" in out and ".a{" in out


def test_compact_reduces_utf8_size_on_verbose_template():
    # Mimics pretty-printed email HTML with bulky CSS
    lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<style>",
        "    body { margin: 0; padding: 0; }",
        "    .email-outer { max-width: 960px; }",
        "</style>",
        "</head>",
        "<body>",
        "<div class='email-outer'>",
        "    <p>Line one</p>",
        "    <p>Line two</p>",
        "</div>",
        "</body>",
        "</html>",
    ]
    raw = "\n".join(lines)
    compact = _compact_ifrc_html_body(raw)
    assert len(compact.encode("utf-8")) < len(raw.encode("utf-8"))


def test_compact_empty_and_whitespace():
    assert _compact_ifrc_html_body("") == ""
    assert _compact_ifrc_html_body("   \n  ") == ""


def test_aggressive_compact_drops_zero_px_units_for_smaller_b64():
    html = (
        "<style>.a{margin:0px;padding:0px;border:0px solid #e2e8f0}"
        ".b{margin:0px}</style><p>x</p>"
    )
    normal = _compact_ifrc_html_body(html)
    aggressive = _compact_ifrc_html_body(html, aggressive_css=True)
    assert _utf8_b64_len(aggressive) <= _utf8_b64_len(normal)
    assert "0px" not in aggressive


def test_compact_strips_text_css_type_attribute():
    html = '<html><head><style type="text/css">body{margin:0;}</style></head><body></body></html>'
    out = _compact_ifrc_html_body(html)
    assert 'type="text/css"' not in out.lower()
    assert "<style>" in out


def test_compact_css_minify_saves_bytes_like_verbose_templates():
    """Verbose spacing in CSS (common in admin-edited email HTML) shrinks with minify."""
    html = (
        "<!DOCTYPE html><html><head><style>\n"
        "body { margin: 0; padding: 0; background: #eef2f7; }\n"
        ".email-outer { max-width: 960px; margin: 0 auto; }\n"
        "</style></head><body><div class=\"email-outer\"><p>Hi</p></div></body></html>"
    )
    out = _compact_ifrc_html_body(html)
    assert len(out.encode("utf-8")) < len(html.encode("utf-8"))
    assert "margin:0" in out and "padding:0" in out
