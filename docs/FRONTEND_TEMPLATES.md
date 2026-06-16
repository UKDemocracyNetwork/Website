# Frontend Template System (design + handover)

Status: implemented (shell + CSS/asset pipeline). This is the design record for
the shared-shell system. The hands-on usage guide lives in
[`frontend/README.md`](../frontend/README.md); this document explains *why* it is
shaped this way and what a future session must not break.

> Commands were renamed when the asset pipeline landed: `make build` (was
> `make templates`) and `make check-build` (was `make check-templates`), plus a new
> `make watch`. The build now produces **both** templates and asset copies.

## What problem this solves

The site must serve one consistent outer HTML page ("the shell": doctype,
landmarks, skip link, `<head>`/foot injection points) from two different
template engines:

- **Now:** Ghost on ECS Fargate, which renders **Handlebars** (`.hbs`).
- **Later:** a Starlette app on Lambda (see SPEC.md "Shared shell direction"),
  which renders **Jinja2**.

We want a single source of truth for that shell so the two runtimes can never
drift into two different page chromes.

## Core decision: generate real files, never symlink

A symlink that points one engine's template at the other's was explicitly
rejected. **`docker COPY` (Ghost image build) and Lambda bundling do not reliably
follow symlinks**, so a symlinked shell would silently break in at least one
deploy target.

Instead: **one canonical source → a build step → real, committed files per
engine.** Every runtime gets a plain file it can copy/bundle with no awareness of
the build system.

## How it works

```
frontend/
  shell/shell.html    SOURCE OF TRUTH for the page shell. Neutral ${slot} tokens.
  assets/             SOURCE OF TRUTH for static assets; ALSO the Lambda static dir.
  build.py            Renders the shell per engine + copies assets into Ghost's theme.
  watch.py            Rebuild-on-save for local dev (stdlib polling, no deps).
  jinja/base.html     GENERATED. Jinja2 base template for Starlette/Lambda.
theme/default.hbs     GENERATED. Ghost Handlebars shell.
theme/assets/         GENERATED. Asset copy served by Ghost at /assets/.
```

`build.py` defines a `TARGETS` list. Each `Target` has: a name, a template output
path, a native comment wrapper (for the "DO NOT EDIT" header), a `bindings` dict
mapping every `${slot}` to that engine's expression, and an **optional**
`asset_root`. Rendering a shell is `string.Template(shell).substitute(bindings)`
plus a prepended comment; assets are a verbatim byte-copy of `frontend/assets/**`
into the asset root of any target that has one. Only Ghost has an `asset_root`.

Current slots: `meta_title`, `head`, `stylesheet_href`, `site_url`, `site_title`,
`body`, `year`, `foot`. See the table in `frontend/README.md` for the per-engine
mapping.

### Assets / media paths (the shared-CSS mechanism)

CSS is wired into both engines **the same way**: one source, referenced through a
binding slot so only the URL resolution differs. How each engine *gets* the file
differs because of one hard constraint — **Ghost cannot serve an arbitrary
directory**.

- Source: `frontend/assets/css/screen.css` (native CSS, no SASS).
- **Ghost** needs a copy: its theme assets must live at `<theme>/assets/` and the
  image is built with `COPY theme/`. The build copies source → `theme/assets/`
  (byte-for-byte, **no** injected header, so do not edit the copy — the drift guard
  catches edits). Editor junk (dotfiles, `*~`) is skipped by the copy.
- **Jinja/Lambda** needs **no** copy: a Starlette app serves a configurable static
  dir, so it points straight at `frontend/assets/` (served at `/static/`). The
  source is real files, so Lambda bundling includes them directly — the no-symlink
  rule still holds. (This is why there is no `frontend/static/`.)
- Reference: the shell's `<link rel="stylesheet" href="${stylesheet_href}">`, bound
  to `{{asset "css/screen.css"}}` for Ghost (cache-busted `/assets/` URL) and
  `/static/css/screen.css` for Jinja.
- A post-processor (PostCSS etc.) can later sit inside the copy step without
  changing how engines reference assets. Today it is a plain copy — deliberately.

## Things to remember (do not relearn the hard way)

1. **Generated files are committed and must stay in sync.** They are real Git
   artifacts (golden-thread principle: everything affecting presentation lives in
   Git). The guard is `python frontend/build.py --check`, wired into `make lint`,
   and `make lint` + `make test` both run in `.github/workflows/ci.yml`. So an
   out-of-sync generated file **fails CI**. If CI fails on this, the fix is
   `make build` then commit — never hand-edit the generated file. This covers both
   templates and asset copies.

2. **Never edit generated files by hand:** `theme/default.hbs`,
   `frontend/jinja/base.html` (carry a `DO NOT EDIT` header) or the asset copy
   under `theme/assets/` (byte-copy, no header). Edit the source under `frontend/`
   and run `make build`.

3. **The shell is the *outer page only*. Page templates stay engine-specific.**
   This is the deliberate seam:
   - Ghost: `theme/index.hbs`, `theme/post.hbs` use `{{!< default}}` to inherit
     the generated `default.hbs`.
   - Starlette (future): page templates `{% extends "base.html" %}` and override
     the `content` (and optionally `head`/`foot`) blocks.
   Do not try to also generate page bodies from the shared shell — only the chrome
   needs to be identical across runtimes.

4. **`string.Template` gotchas.** It uses `$name`/`${name}`. A literal `$` in the
   shell must be written `$$`. `.substitute()` raises if the shell contains a
   `${slot}` with no binding (good — catches typos), and is fine with extra unused
   keys. Today the shell has no `$`; if CSS or inline content later introduces
   one, escape it.

5. **Adding a slot is a 3-step, all-engines change.** (a) add `${new_slot}` to
   `shell.html`; (b) add a binding in **every** target in `build.py` (a missing
   binding raises at build time); (c) `make build` and commit source + regenerated
   outputs together. Adding an asset is simpler: drop it under `frontend/assets/`,
   `make build` (copies into Ghost's `theme/assets/`; Lambda reads the source
   directly), commit source + the Ghost copy.

6. **Runtime contract — the shell only emits syntax/URLs, the runtime supplies the
   rest.**
   - Ghost provides `meta_title`, `ghost_head`/`ghost_foot`, `@site.*`, the `date`
     helper and the `{{asset}}` helper natively, and serves `theme/assets/` at
     `/assets/` — no extra wiring.
   - Starlette/Jinja must pass `meta_title`, `site_url`, `site_title`,
     `current_year` in the context and serve `frontend/assets/` at `/static/`.
     Forgetting a context var renders blank, not an error, so cover it with a test
     when the Starlette app lands.

9. **Local hot reload — two different mechanisms.**
   - **Assets (CSS/images):** `docker-compose.yml` mounts `./frontend/assets` (the
     *source*) directly over the active theme's `assets/` dir. So the container
     serves source assets live — edit, soft-refresh, done. No build, no watch, no
     rebuild. Ghost serves them with `Cache-Control: max-age=0`, so a normal
     refresh revalidates (verified: a conditional request returns 200 with fresh
     content, not 304). The `{{asset}}` `?v=` hash being static does **not** block
     this, because `max-age=0` forces revalidation of the same URL.
   - **Templates:** the served `theme/default.hbs` is generated from the shell, so
     a shell edit needs `make build` (or `make watch`); the `./theme` bind mount
     then makes the new `.hbs` live on refresh.
   - If either the `./frontend/assets` or `./theme` mount is removed, hot reload
     breaks. Keep both. They are dev-only; prod uses the image's baked-in theme.

7. **Fidelity baseline.** When first generated, `theme/default.hbs` was
   byte-identical to the previous hand-written file except for the added comment
   header. If you change the shell, eyeball the Ghost diff to confirm you only
   changed what you intended.

8. **No new dependencies were added.** Generation is stdlib-only
   (`string.Template`). We intentionally did **not** add Jinja2 yet — it arrives
   with the Starlette app. Keep it that way unless the Starlette work needs it.

## Commands

```bash
make build        # regenerate templates + copy assets from frontend/ source
make check-build  # drift guard (also part of `make lint`)
make watch        # rebuild on save during local dev
make test         # includes tests/test_frontend.py
```

Tests in `tests/test_frontend.py` cover: committed outputs (templates + asset
copies) equal a fresh build (drift), all shells share the accessibility landmarks
incl. the stylesheet link, each shell carries its own engine syntax (no
cross-leak), the stylesheet is wired per engine, and the CSS reaches every asset
root.

## Status / next steps

- **Done:** shell system; CSS/asset pipeline; a `body { background: … }` smoke
  style proving the path works end to end; zero-step CSS hot reload via the
  `./frontend/assets` source mount.
- **Validate visually:** `make dev`, activate `dn-theme` in `/ghost/`, load
  `http://localhost:8080/` — body background should match `screen.css`. (Theme must
  be active for the `{{asset}}` link to resolve.)
- **Next CSS work:** replace the smoke style with real styles in
  `frontend/assets/css/screen.css`. Same rules apply: one source, real files at
  Ghost's theme, no symlinks.
- **Possible later:** PostCSS in the build (only when needed — note this would
  introduce a transformed build output that Lambda serves instead of the raw
  source); livereload for full auto-refresh; wire the asset mechanism into the
  Starlette app when it lands (serve `frontend/assets/` at `/static/`, pass the
  context vars).
