# Frontend: shared shell + assets

One canonical source, rendered/copied into two template engines so Ghost (now) and
a future Starlette-on-Lambda app share the same outer page **and** the same CSS:
doctype, landmarks, skip link, head/foot injection points, and stylesheet.

## Why a build step (and not symlinks)

The shell and assets must reach two very different runtimes:

- **Ghost on ECS Fargate** — theme copied into the image with `docker COPY`.
- **Starlette on Lambda** (future) — templates/static gathered by Lambda bundling.

Neither `docker COPY` nor Lambda bundling reliably follows symlinks, so we keep
**one source** and generate **real committed files** for each engine.

## Layout

```
frontend/
  shell/shell.html        SOURCE OF TRUTH for the page shell (${slot} tokens)
  assets/                 SOURCE OF TRUTH for static assets; ALSO served directly
    css/screen.css        native CSS (no SASS)   by the Jinja/Lambda app at /static/
  build.py                renders the shell + copies assets into Ghost's theme
  watch.py                rebuild-on-save for local dev
  jinja/base.html         GENERATED  - Jinja base template
theme/default.hbs         GENERATED  - Ghost Handlebars shell
theme/assets/             GENERATED  - asset copy for Ghost (its theme path is fixed)
```

`shell.html` uses neutral `${slot}` tokens (Python `string.Template`, stdlib only).
Each target in `build.py` binds those slots to its engine's syntax.

| slot              | Ghost (Handlebars)        | Jinja (Starlette)                   |
| ----------------- | ------------------------- | ----------------------------------- |
| `meta_title`      | `{{meta_title}}`          | `{{ meta_title }}`                  |
| `head`            | `{{ghost_head}}`          | `{% block head %}{% endblock %}`    |
| `stylesheet_href` | `{{asset "css/screen.css"}}` | `/static/css/screen.css`         |
| `site_url`        | `{{@site.url}}`           | `{{ site_url }}`                    |
| `site_title`      | `{{@site.title}}`         | `{{ site_title }}`                  |
| `body`            | `{{{body}}}`              | `{% block content %}{% endblock %}` |
| `year`            | `{{date format="YYYY"}}`  | `{{ current_year }}`                |
| `foot`            | `{{ghost_foot}}`          | `{% block foot %}{% endblock %}`    |

## Assets / media paths

`frontend/assets/` is the single source. Engines reference assets through the
`stylesheet_href` (and future) binding slots, so the same source file is wired in
the same way — only the URL resolution and *how each engine gets the file* differ:

- **Ghost** cannot serve an arbitrary directory — its theme assets must live at
  `<theme>/assets/`, and the image is built with `COPY theme/`. So the build
  **copies** `frontend/assets/` → `theme/assets/`, served at `/assets/` with a
  cache-busting `{{asset}}` `?v=` hash.
- **Jinja/Lambda** serves a configurable static dir, so it points straight at
  `frontend/assets/` (served at `/static/`). **No copy** — the source dir is real
  files that Lambda bundling includes directly, so the no-symlink rule still holds.

Ghost is the *only* engine that needs a copy; that asymmetry is forced by Ghost,
not a design choice. When a post-processor (e.g. PostCSS) is added later, it will
produce a transformed build output that both engines consume — at that point
Lambda would serve the build output instead of the raw source. Today it is raw.

## CSS structure & design tokens

Pure CSS (no SASS). Files under `frontend/assets/css/`:

- `tokens.css` — the design system. CSS custom properties in two tiers:
  - **Primitives** (`--color-neutral-500`, `--color-brand-500`, `--space-md`,
    `--font-size-lg`): raw, context-free values. Don't use these directly in
    components.
  - **Semantic** (`--color-text`, `--color-link`, `--space-gutter`): roles that map
    to primitives. **Style components with these.** A rebrand or theme change is
    then just a remap of the semantic layer — components never change.
  - **Colours** follow Kevin Powell's modern-CSS-colours guides
    (https://piccalil.li/blog/a-pragmatic-guide-to-modern-css-colours-part-one/):
    the palette is `oklch()` (perceptually uniform, wide-gamut) but you set just
    **one hex** — `--color-brand-base`. `--color-brand-500` *is* that hex; the rest
    of the brand ramp and the neutrals derive from it with relative colour
    (`oklch(from var(--color-brand-base) …)`), so a rebrand is a single hex edit.
    Theming uses `light-dark()` + `color-scheme` (no parallel `@media` block); it
    follows the OS by default, and `<html data-theme="light|dark">` forces one for a
    toggle. Other derived roles use relative colour and `color-mix()`.
- `reset.css` — Andy Bell's "A (more) Modern CSS Reset"
  (https://piccalil.li/blog/a-more-modern-css-reset/), kept close to upstream and
  token-free so it's easy to re-diff against the source.
- `screen.css` — the entry stylesheet the shell links. It `@import`s `tokens.css`
  then `reset.css` (imports must precede style rules), then holds the actual styles.

Add a new CSS file by dropping it in `frontend/assets/css/` and `@import`ing it
near the top of `screen.css` (all `@import`s must precede style rules). `make build`
copies the whole `css/` dir into Ghost's theme; the relative `@import` URL resolves
under both `/assets/` (Ghost) and `/static/` (Lambda).

> Caveat: `@import`ed files don't get Ghost's `{{asset}}` `?v=` cache-bust, so a
> CDN could serve a stale `tokens.css` after a token-only change until invalidation.
> The future PostCSS step will inline `@import`s into one cache-busted bundle. In
> local dev it's a non-issue (`max-age=0`).

Breakpoint values can't be tokens (custom properties don't work inside `@media`
conditions) — `tokens.css` lists the canonical values as a comment to copy.

## Workflow

```bash
make build        # regenerate templates + copy assets
make check-build  # fail if any committed output drifts from source (run in CI)
make watch        # rebuild on save during local dev
```

Generated files are committed (golden thread: everything affecting presentation
lives in Git) and `make lint` runs `check-build` so drift fails the build.
**Never edit generated files by hand** — change the source under `frontend/` and
rebuild.

## Local hot reload

For **assets (CSS/images)** there is nothing to run. `docker-compose.yml` mounts
the asset source straight into the active theme:

```yaml
- ./frontend/assets:/var/lib/ghost/content/themes/dn-theme/assets:ro
```

So the running container serves `frontend/assets/**` directly — edit a file, do a
normal browser refresh, see the change. No `make build`, no `make watch`, no
rebuild, no restart. Ghost serves theme assets with `Cache-Control: max-age=0`, so
a **soft** refresh revalidates and picks up the new file (no hard refresh needed).
This mount shadows the built `theme/assets/` copy in dev; in prod the image's
baked-in copy is used.

For **template/shell changes** (`shell/shell.html` → `theme/default.hbs`) you still
need a build, because the served `.hbs` is generated. `./theme` is bind-mounted, so
once regenerated the new `default.hbs` is live on refresh — run `make watch` to
regenerate on save, or `make build` once.

Full browser livereload (auto-refresh on save) is a possible later addition.

## Adding a slot or asset

- **Slot:** add `${new_slot}` to `shell/shell.html`, add a binding in every target
  in `build.py`, then `make build` and commit source + regenerated outputs.
- **Asset:** drop the file under `frontend/assets/`, `make build` (copies it into
  Ghost's `theme/assets/`), commit source + the Ghost copy. The Jinja/Lambda app
  serves `frontend/assets/` directly, so there is no second copy. Reference it from
  a slot binding if it needs an engine-resolved URL. Editor junk (dotfiles, `*~`)
  is ignored by the copy.

## Runtime contract

The build only emits syntax/URLs; each runtime supplies the values.

- **Ghost** provides `meta_title`, `ghost_head`/`ghost_foot`, `@site.*`, the
  `date` helper, and the `{{asset}}` helper natively. Page templates extend the
  shell with `{{!< default}}`.
- **Starlette/Jinja** must pass `meta_title`, `site_url`, `site_title`,
  `current_year` in the context, serve `frontend/assets/` at `/static/`, and page
  templates `{% extends "base.html" %}` overriding `content` (and optionally
  `head`/`foot`) blocks.
