# Implementation Notes

## Preferred stack

- Python 3.12+.
- uv.
- pyproject.toml.
- Python CDK.
- boto3 for setup scripts.
- ruff.
- pytest.
- Docker Compose.
- GitHub Actions.

## Ghost

Use a pinned Ghost Docker base image. Prefer a single version pin in the Dockerfile, for example an ARG.

Create a minimal custom theme. The homepage should be committed in the theme and should render as the public root page.

Do not rely on Ghost admin/database content for the MVP homepage.

## Accessibility baseline

The initial HTML should be plain and semantic. Add tests to prevent regressions where practical.

## Smoke testing

Create a small Python smoke test tool that accepts `URL` and checks:

- homepage is 200.
- title marker exists.
- h1 marker exists.
- `/ghost/` is reachable.
- `/ghost/` does not return public-cache headers.

## Local Docker Compose

Compose should run Ghost + MySQL + nginx router.

The router should expose `localhost:8080`.

Local Ghost can use a mounted local volume for content/uploads.

## CDK

Claude may choose stack boundaries, but should consider separate stacks for:

- foundational/account setup if needed.
- database.
- app/ECS.
- CDN/DNS/certificates.

Be careful with CloudFront certificates needing us-east-1.

## RDS deletion safety

Prod database must be hard to delete accidentally:

- deletion protection.
- removal policy retain.
- backups.

The app stack should be replaceable without replacing the database.

## GitHub OIDC

`scripts/new_env.py` should create or verify the GitHub OIDC provider and deploy role. It should scope trust to the configured repo and branch.

Do not use long-lived AWS access keys in GitHub Actions.
