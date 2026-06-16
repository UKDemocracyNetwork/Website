"""Generate engine-specific frontend files from one shared source.

Outputs are real committed files (never symlinks) so `docker COPY` (ECS/Ghost) and
Lambda bundling pick them up directly:

1. Templates: the shared shell `frontend/shell/shell.html` (neutral ``${slot}``
   tokens, stdlib ``string.Template``) rendered per engine:
     Ghost -> theme/default.hbs        Jinja -> frontend/jinja/base.html
2. Assets: everything under `frontend/assets/` is the single source. Ghost cannot
   serve an arbitrary dir, so the build copies assets into its theme:
     Ghost -> theme/assets/
   A Starlette/Lambda app serves `frontend/assets/` directly from its static dir,
   so it needs no copy.

Engines reference assets through a binding slot (the stylesheet href), so the same
source file is wired in the same way; only the URL resolution differs (Ghost's
{{asset}} helper vs. /static/...).

Usage::

    python frontend/build.py            # regenerate all outputs
    python frontend/build.py --check    # fail if any output is missing or stale
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from string import Template

REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL = REPO_ROOT / "frontend" / "shell" / "shell.html"
ASSET_SRC = REPO_ROOT / "frontend" / "assets"

GENERATED_NOTE = "GENERATED FILE - DO NOT EDIT. Edit frontend/shell/shell.html and run `make build`."


@dataclass(frozen=True)
class Target:
    """One engine: a rendered shell, its slot bindings, and an optional asset root.

    ``asset_root`` is set only for engines that cannot serve the shared
    ``frontend/assets/`` source directly and therefore need a copy. Ghost is the
    only such engine (its theme assets must live at ``<theme>/assets/`` and the
    image is built with ``COPY theme/``). A Starlette/Lambda app serves
    ``frontend/assets/`` straight from its configurable static dir, so it needs no
    copy and leaves ``asset_root`` as ``None``.
    """

    name: str
    template_output: str  # path relative to repo root
    comment: str  # native comment wrapper; ``%s`` is the generated-file note
    bindings: dict[str, str]
    asset_root: str | None = None  # copy assets here, relative to repo root; None = serve source directly


# Each binding maps a shell slot to the expression the engine evaluates at render
# time. Runtimes must supply the values:
#   Ghost   provides meta_title, ghost_head/ghost_foot, @site.*, the date helper,
#           and the {{asset}} helper (cache-busted URL into theme/assets/).
#   Starlette/Jinja must pass meta_title, site_url, site_title, current_year, and
#           serves the frontend/assets/ source dir at /static/.
TARGETS: list[Target] = [
    Target(
        name="ghost",
        template_output="theme/default.hbs",
        asset_root="theme/assets",
        comment="{{!-- %s --}}",
        bindings={
            "meta_title": "{{meta_title}}",
            "head": "{{ghost_head}}",
            "stylesheet_href": '{{asset "css/screen.css"}}',
            "site_url": "{{@site.url}}",
            "site_title": "{{@site.title}}",
            "body": "{{{body}}}",
            "year": '{{date format="YYYY"}}',
            "foot": "{{ghost_foot}}",
        },
    ),
    Target(
        name="jinja",
        template_output="frontend/jinja/base.html",
        comment="{# %s #}",
        bindings={
            "meta_title": "{{ meta_title }}",
            "head": "{% block head %}{% endblock %}",
            "stylesheet_href": "/static/css/screen.css",
            "site_url": "{{ site_url }}",
            "site_title": "{{ site_title }}",
            "body": "{% block content %}{% endblock %}",
            "year": "{{ current_year }}",
            "foot": "{% block foot %}{% endblock %}",
        },
    ),
]


def render(target: Target, shell_text: str) -> str:
    """Render a single target's shell template from the shell text."""
    body = Template(shell_text).substitute(target.bindings)
    return f"{target.comment % GENERATED_NOTE}\n{body}"


def render_targets() -> dict[Path, str]:
    """Render every target's shell template. Returns absolute path -> text."""
    shell_text = SHELL.read_text()
    return {REPO_ROOT / t.template_output: render(t, shell_text) for t in TARGETS}


def planned_outputs() -> dict[Path, bytes]:
    """Every file the build owns (templates + asset copies). Absolute path -> bytes."""
    outputs: dict[Path, bytes] = {}
    for path, text in render_targets().items():
        outputs[path] = text.encode()
    asset_roots = [t.asset_root for t in TARGETS if t.asset_root]
    if ASSET_SRC.exists() and asset_roots:
        for src in sorted(ASSET_SRC.rglob("*")):
            if src.is_file() and not _is_ignored(src):
                rel = src.relative_to(ASSET_SRC)
                data = src.read_bytes()
                for asset_root in asset_roots:
                    outputs[REPO_ROOT / asset_root / rel] = data
    return outputs


def _is_ignored(path: Path) -> bool:
    """Skip editor/OS junk (dotfiles, vim swap, backup files) when copying assets."""
    name = path.name
    return name.startswith(".") or name.endswith("~")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build frontend templates and assets from source.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if any output is missing or stale. Writes nothing.",
    )
    args = parser.parse_args(argv)

    outputs = planned_outputs()
    stale = [
        path.relative_to(REPO_ROOT)
        for path, content in outputs.items()
        if not path.exists() or path.read_bytes() != content
    ]

    if args.check:
        if stale:
            print("Frontend build is stale. Run `make build`:", file=sys.stderr)
            for path in stale:
                print(f"  - {path}", file=sys.stderr)
            return 1
        print("Frontend build is up to date.")
        return 0

    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
