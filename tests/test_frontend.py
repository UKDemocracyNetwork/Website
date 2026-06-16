"""Tests for the shared-shell template + asset build.

These guard the golden thread: the committed Ghost and Jinja outputs (templates
and copied assets) must stay in sync with the canonical source, both shells must
carry the same accessibility landmarks, and each engine must reference shared
assets through its own binding syntax.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from frontend.build import TARGETS, planned_outputs, render_targets  # noqa: E402

# Structure that every rendered shell must share, regardless of engine.
SHARED_LANDMARKS = [
    "<!DOCTYPE html>",
    'class="skip-link"',
    '<header role="banner">',
    '<main id="main-content"',
    "<footer>",
    '<link rel="stylesheet"',
]


def test_committed_outputs_match_source():
    """Every committed output must equal a fresh build. Run `make build` if this fails."""
    for path, content in planned_outputs().items():
        rel = path.relative_to(REPO_ROOT)
        assert path.exists(), f"{rel} is missing - run `make build`"
        assert path.read_bytes() == content, f"{rel} is stale - run `make build`"


def test_all_shells_share_landmarks():
    for path, content in render_targets().items():
        for landmark in SHARED_LANDMARKS:
            assert landmark in content, f"{path.relative_to(REPO_ROOT)} is missing landmark {landmark!r}"


def test_shells_use_their_own_engine_syntax():
    by_name = {t.name: REPO_ROOT / t.template_output for t in TARGETS}
    ghost = by_name["ghost"].read_text()
    jinja = by_name["jinja"].read_text()

    # Ghost-specific bindings render through, Jinja block syntax does not leak in.
    assert "{{ghost_head}}" in ghost
    assert "{{{body}}}" in ghost
    assert "{% block" not in ghost

    # Jinja exposes overridable blocks and must not carry Ghost helpers.
    assert "{% block content %}{% endblock %}" in jinja
    assert "{{ site_url }}" in jinja
    assert "ghost_head" not in jinja


def test_stylesheet_wired_per_engine():
    by_name = {t.name: REPO_ROOT / t.template_output for t in TARGETS}
    # Ghost resolves the stylesheet via its asset helper (cache-busted theme URL).
    assert '{{asset "css/screen.css"}}' in by_name["ghost"].read_text()
    # Jinja references the same file under its static root.
    assert "/static/css/screen.css" in by_name["jinja"].read_text()


def test_css_copied_to_ghost_theme():
    """Ghost is the only engine needing a copy (fixed theme asset path). The Jinja/
    Lambda app serves frontend/assets/ directly, so it has no asset_root."""
    source = (REPO_ROOT / "frontend" / "assets" / "css" / "screen.css").read_bytes()
    copied = [t for t in TARGETS if t.asset_root]
    assert [t.name for t in copied] == ["ghost"], "only Ghost should copy assets"
    for target in copied:
        copy = REPO_ROOT / target.asset_root / "css" / "screen.css"
        assert copy.exists(), f"{copy.relative_to(REPO_ROOT)} missing - run `make build`"
        assert copy.read_bytes() == source, f"{copy.relative_to(REPO_ROOT)} differs from source"
