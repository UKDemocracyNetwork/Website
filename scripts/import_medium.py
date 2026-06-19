"""Import a Medium export into Ghost via the Admin API. Repeatable / idempotent.

For every `posts/*.html` in a Medium export zip this creates (or updates, on a
re-run) a matching Ghost post: same formatting, images re-hosted in Ghost, the
original publish date preserved, and the Medium URL set as the canonical URL.

Idempotency comes from a local state file (default `.medium-import-state.json`,
gitignored) that maps, per target Ghost site:
  - medium post id  -> ghost post id + slug   (so re-runs UPDATE, never duplicate)
  - medium image    -> ghost image url        (so images upload once)

Setup (per environment):
  1. In Ghost: Settings -> Integrations -> Add custom integration. Copy the
     Admin API key (looks like `652f...:b3d9...`) and the API URL.
  2. export GHOST_API_URL=http://localhost:8080
     export GHOST_ADMIN_API_KEY=<id>:<secret>

Usage:
  uv run --group migrate python scripts/import_medium.py --zip EXPORT.zip --dry-run
  uv run --group migrate python scripts/import_medium.py --zip EXPORT.zip --limit 1
  uv run --group migrate python scripts/import_medium.py --zip EXPORT.zip

Routing: every post is tagged "Bulletin"; the committed routes.yaml maps that tag
to /bulletin/<slug>/ (mounted into Ghost via docker-compose locally and baked into
the image for deploys). So imported posts land under /bulletin/ automatically; the
Admin API does not expose routes upload, so routing is config, not done here.

Flags: --dry-run (parse only, no network), --limit N, --only <id-or-filename>.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import jwt
import requests
from bs4 import BeautifulSoup, Tag

UA = {"User-Agent": "Mozilla/5.0 (DN Website Medium->Ghost migration)"}
PUBLIC_TAG = "Bulletin"
INTERNAL_TAG = "#medium-import"  # leading # = Ghost internal tag (not shown publicly)
IMAGE_MAX_WIDTH = 2400  # px; request a high-res variant from Medium's CDN
# Attributes worth keeping; everything else (Medium classes, data-*, ids) is dropped.
KEEP_ATTRS = {"href", "src", "alt", "title", "colspan", "rowspan", "datetime"}


# --------------------------------------------------------------------------- #
# Parsing a Medium post
# --------------------------------------------------------------------------- #
def norm(text: str) -> str:
    """Collapse all whitespace (incl. nbsp/hair spaces Medium loves) to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def medium_id_from_name(filename: str) -> str:
    """The 12-hex id Medium puts at the end of every export filename."""
    m = re.search(r"([0-9a-f]{12})\.html$", filename)
    return m.group(1) if m else slugify(Path(filename).stem)


def image_source(img: Tag) -> str | None:
    """Canonical high-res Medium CDN URL for an <img>, or None if not a Medium image."""
    image_id = img.get("data-image-id")
    if image_id:
        return f"https://cdn-images-1.medium.com/max/{IMAGE_MAX_WIDTH}/{image_id}"
    src = img.get("src", "")
    if "cdn-images" in src:
        # Upscale any /max/NNN/ or /fit/.../ variant to a big one.
        m = re.search(r"(\d+\*[^/]+)$", src)
        if m:
            return f"https://cdn-images-1.medium.com/max/{IMAGE_MAX_WIDTH}/{m.group(1)}"
        return src
    return None


HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def first_child_tag(node: Tag) -> Tag | None:
    """First element child, skipping whitespace-only text nodes."""
    for child in node.children:
        if isinstance(child, Tag):
            return child
        if isinstance(child, str) and child.strip():
            return None  # real text before any tag
    return None


def strip_leading_noise(body: Tag) -> None:
    """Drop Medium's leading divider(s) and the in-body title/subtitle headings.

    Identified by Medium's own classes (graf--title / graf--subtitle), so it works
    even when the in-body title differs from <h1> (it's often richer, e.g. includes
    the month). The title/subtitle are already captured as title/excerpt.
    """
    leading_classes = {"graf--title", "graf--subtitle"}
    while (first := first_child_tag(body)) is not None:
        classes = set(first.get("class", []))
        if first.name == "hr" or (first.name in HEADINGS and classes & leading_classes):
            first.decompose()
        else:
            break


def clean_attrs(node: Tag) -> None:
    """Strip non-essential attributes (Medium classes, data-*, ids) in place."""
    for tag in node.find_all(True):
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in KEEP_ATTRS}


def parse_post(html: str, filename: str) -> dict:
    """Extract title, date, excerpt, canonical URL, body and images from a Medium post."""
    soup = BeautifulSoup(html, "html.parser")
    title_el = soup.find("h1", class_="p-name")
    meta_title = norm(title_el.get_text()) if title_el else Path(filename).stem
    time_el = soup.find("time", class_="dt-published")
    published_at = time_el["datetime"] if time_el and time_el.has_attr("datetime") else None
    canon_el = soup.find("a", class_="p-canonical")
    canonical_url = canon_el["href"] if canon_el else None
    summary_el = soup.find("section", class_="p-summary")
    excerpt = norm(summary_el.get_text()) if summary_el else ""

    # Body is Medium's e-content section (excludes the header and the subtitle).
    body = soup.find("section", class_="e-content") or soup.find("article") or soup
    for junk in body.find_all(["header", "footer", "style", "script"]):
        junk.decompose()
    for wrapper in body.find_all(["section", "div"]):
        wrapper.unwrap()  # flatten Medium's nested section/div layout
    for img in body.find_all("img"):
        if image_source(img) is None:
            img.decompose()  # Medium tracking pixel / non-CDN image

    # Prefer the in-body title heading (Medium's graf--title) — it's often richer
    # than <h1> (includes the month), which also avoids slug collisions.
    title_heading = body.find(class_="graf--title")
    title = norm(title_heading.get_text()) if title_heading else meta_title
    strip_leading_noise(body)

    # Feature image = a genuinely leading image (first content block is a figure/img).
    feature = {"src": None, "alt": "", "caption": ""}
    lead = first_child_tag(body)
    lead_img = lead if (lead and lead.name == "img") else (lead.find("img") if lead else None)
    if lead is not None and lead.name in {"figure", "img"} and lead_img is not None:
        feature["src"] = image_source(lead_img)
        feature["alt"] = lead_img.get("alt", "") or title
        cap = lead.find("figcaption") if lead.name == "figure" else None
        feature["caption"] = cap.get_text(strip=True) if cap else ""
        lead.decompose()

    images = [(img, image_source(img)) for img in body.find_all("img")]
    clean_attrs(body)
    return {
        "medium_id": medium_id_from_name(filename),
        "title": title,
        "excerpt": excerpt,
        "published_at": published_at,
        "canonical_url": canonical_url,
        "article": body,
        "images": images,
        "feature": feature,
    }


# --------------------------------------------------------------------------- #
# Ghost Admin API
# --------------------------------------------------------------------------- #
class Ghost:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.kid, self.secret = key.split(":")

    def _headers(self) -> dict:
        now = int(time.time())
        token = jwt.encode(
            {"iat": now, "exp": now + 300, "aud": "/admin/"},
            bytes.fromhex(self.secret),
            algorithm="HS256",
            headers={"kid": self.kid},
        )
        return {"Authorization": f"Ghost {token}", "Accept-Version": "v5.0"}

    def _api(self, path: str) -> str:
        return f"{self.url}/ghost/api/admin/{path}"

    def upload_image(self, data: bytes, filename: str, content_type: str, ref: str) -> str:
        r = requests.post(
            self._api("images/upload/"),
            headers=self._headers(),
            files={"file": (filename, data, content_type)},
            data={"purpose": "image", "ref": ref},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["images"][0]["url"]

    def create_post(self, post: dict) -> dict:
        r = requests.post(
            self._api("posts/?source=html"),
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"posts": [post]},
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"create failed {r.status_code}: {r.text}")
        return r.json()["posts"][0]

    def update_post(self, post_id: str, post: dict) -> dict:
        cur = requests.get(self._api(f"posts/{post_id}/"), headers=self._headers(), timeout=60)
        cur.raise_for_status()
        body = dict(post)
        body.pop("slug", None)  # keep the existing slug; don't churn URLs
        body["updated_at"] = cur.json()["posts"][0]["updated_at"]  # collision check
        r = requests.put(
            self._api(f"posts/{post_id}/?source=html"),
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"posts": [body]},
            timeout=60,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"update failed {r.status_code}: {r.text}")
        return r.json()["posts"][0]


# --------------------------------------------------------------------------- #
# Image handling
# --------------------------------------------------------------------------- #
# Medium's image proxy can transcode any stored asset to a given format. Used as a
# fallback for formats Ghost won't accept (e.g. AVIF on older Ghost builds).
MIRO_JPEG = "https://miro.medium.com/v2/resize:fit:{w}/format:jpeg/{image_id}"


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """Identify a Ghost-acceptable image from its magic bytes -> (extension, mime).

    Medium's id extension lies (e.g. a `.avif` id is served as JPEG), and Ghost
    validates the *extension* — so we must name files by their real content.
    Returns None for types Ghost may reject (true AVIF/HEIC) or anything unknown.
    """
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg", "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png", "image/png"
    if data[:4] == b"GIF8":
        return ".gif", "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"
    head = data[:512].lstrip()
    if head[:5] == b"<?xml" or head[:4] == b"<svg":
        return ".svg", "image/svg+xml"
    return None


def _download(url: str) -> bytes:
    resp = requests.get(url, headers=UA, timeout=120)
    resp.raise_for_status()
    return resp.content


def rehost_image(ghost: Ghost, cache: dict, medium_url: str) -> str:
    """Download a Medium image and upload it to Ghost (cached). Returns the Ghost URL."""
    if medium_url in cache:
        return cache[medium_url]
    data = _download(medium_url)
    kind = sniff_image(data)
    if kind is None:
        # Unrecognised/AVIF: fetch a JPEG rendition from Medium's image proxy.
        image_id = medium_url.rsplit("/", 1)[-1]
        data = _download(MIRO_JPEG.format(w=IMAGE_MAX_WIDTH, image_id=image_id))
        kind = sniff_image(data) or (".jpg", "image/jpeg")
    ext, mime = kind
    stem = re.sub(r"[^A-Za-z0-9._-]", "", medium_url.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    ghost_url = ghost.upload_image(data, f"{stem}{ext}", mime, ref=medium_url)
    cache[medium_url] = ghost_url
    return ghost_url


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def load_state(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def build_post(parsed: dict, slug: str) -> dict:
    post = {
        "title": parsed["title"],
        "slug": slug,
        "html": parsed["article"].decode_contents(),
        "tags": [{"name": PUBLIC_TAG}, {"name": INTERNAL_TAG}],
    }
    if parsed["canonical_url"]:
        post["canonical_url"] = parsed["canonical_url"]
    if parsed["excerpt"]:
        post["custom_excerpt"] = parsed["excerpt"][:300]
    if parsed["feature"]["src"]:
        post["feature_image"] = parsed["feature"]["src"]
        post["feature_image_alt"] = (parsed["feature"]["alt"] or "")[:125]
        if parsed["feature"]["caption"]:
            post["feature_image_caption"] = parsed["feature"]["caption"]
    if parsed["published_at"]:
        post["status"] = "published"
        post["published_at"] = parsed["published_at"]
    else:
        post["status"] = "draft"  # Medium drafts have no date — import as a draft
    return post


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a Medium export into Ghost.")
    parser.add_argument("--zip", required=True, type=Path, help="Path to the Medium export .zip")
    parser.add_argument("--state", type=Path, default=Path(".medium-import-state.json"))
    parser.add_argument("--dry-run", action="store_true", help="Parse only; no network, no writes.")
    parser.add_argument("--limit", type=int, help="Process at most N posts.")
    parser.add_argument("--only", help="Only the post whose medium id or filename contains this.")
    args = parser.parse_args(argv)

    target = os.environ.get("GHOST_API_URL", "")
    key = os.environ.get("GHOST_ADMIN_API_KEY", "")
    if not args.dry_run and not (target and key):
        print("ERROR: set GHOST_API_URL and GHOST_ADMIN_API_KEY (or use --dry-run).", file=sys.stderr)
        return 2

    ghost = None if args.dry_run else Ghost(target, key)
    state = load_state(args.state)
    scope = state.setdefault(target or "DRY-RUN", {"posts": {}, "images": {}})
    posts_state, image_cache = scope["posts"], scope["images"]
    used_slugs = {info["slug"]: mid for mid, info in posts_state.items()}

    with zipfile.ZipFile(args.zip) as zf:
        names = sorted(n for n in zf.namelist() if n.startswith("posts/") and n.endswith(".html"))
        processed = 0
        for name in names:
            parsed = parse_post(zf.read(name).decode("utf-8"), name)
            mid = parsed["medium_id"]
            if args.only and args.only not in (mid, name):
                continue
            if args.limit and processed >= args.limit:
                break
            processed += 1

            # Stable, de-duplicated slug (titles repeat across months).
            if mid in posts_state:
                slug = posts_state[mid]["slug"]
            else:
                base = slugify(parsed["title"])
                slug = base
                if slug in used_slugs and parsed["published_at"]:
                    slug = f"{base}-{parsed['published_at'][:10]}"
                used_slugs[slug] = mid

            n_img = len(parsed["images"]) + (1 if parsed["feature"]["src"] else 0)
            verb = "update" if mid in posts_state else "create"
            print(f"[{processed}] {verb} {slug}  ({n_img} image(s))  <- {Path(name).name}")
            if args.dry_run:
                continue

            # Re-host images: feature first, then inline, rewriting each <img src>.
            if parsed["feature"]["src"]:
                parsed["feature"]["src"] = rehost_image(ghost, image_cache, parsed["feature"]["src"])
            for img, medium_url in parsed["images"]:
                img["src"] = rehost_image(ghost, image_cache, medium_url)

            post = build_post(parsed, slug)
            if mid in posts_state:
                result = ghost.update_post(posts_state[mid]["ghost_id"], post)
            else:
                result = ghost.create_post(post)
            posts_state[mid] = {"ghost_id": result["id"], "slug": result["slug"]}
            save_state(args.state, state)  # checkpoint after every post so re-runs resume

    print(f"\nDone. {processed} post(s) processed{' (dry run)' if args.dry_run else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
