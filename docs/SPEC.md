# Ghost Golden Thread MVP Specification

## Goal

Build a minimal but production-shaped deployment path for a self-hosted Ghost platform on AWS.

The MVP is a single page website. The page content is committed in Git and rendered by Ghost through a custom theme. Ghost is used as the runtime/rendering platform now, with the option to use it later for blogging, newsletters, or CMS-managed content.

The project is primarily a golden thread for future work: local development, build, deploy to dev, smoke test, promote to prod, and operate safely.

## Non-goals for MVP

- No Lambda application routes.
- No dynamic interactive elements.
- No CMS-managed homepage.
- No membership/newsletter setup unless required by Ghost defaults.
- No Cognito or Google Workspace auth in front of Ghost admin.
- No Multi-AZ RDS.
- No EFS.
- No frontend framework.
- No JavaScript.
- No CSS initially, unless required for accessibility or browser sanity.

## Runtime architecture

- Ghost runs in a custom Docker image.
- Docker image is based on a pinned Ghost version.
- Ghost runs on ECS Fargate.
- Each environment has its own AWS account.
- Each environment has its own RDS MySQL instance.
- Each environment has its own Route 53 DNS.
- CloudFront fronts the public site.
- Ghost admin is exposed at `/ghost/` for MVP.
- CloudFront must not cache `/ghost/*`.
- Public anonymous HTML can be cached for 10 minutes.
- Static assets/media should have long cache rules where safe.

## Storage decisions

- RDS MySQL stores Ghost data.
- S3 is the target for Ghost media/uploads in deployed environments.
- Local development may use a local mounted Docker volume for Ghost content/uploads.
- EFS is explicitly not part of MVP, but may be reconsidered if the S3 adapter proves unreliable.

## Custom Ghost image

The custom Ghost image should include:

- Pinned Ghost version in one place, preferably a Dockerfile ARG.
- Repo-owned custom theme.
- S3 storage adapter.
- Startup validation script.

The startup script should validate required environment variables/config before launching Ghost.

## Frontend requirements

The initial homepage should use best-in-class accessible semantic HTML:

- Valid HTML document.
- Skip link.
- Header, nav, main, footer landmarks.
- One clear `h1`.
- Sensible heading order.
- Good link text.
- No JavaScript required.
- No CSS initially.

The user will build the frontend from scratch later.

## Shared shell direction

Future Lambda/server-rendered pages should share the same top-level HTML shell as Ghost pages.

Design the repo so this can evolve into a shared shell system:

- A canonical HTML outline/shell can live in a shared package.
- Build scripts can generate Ghost Handlebars and Python/Jinja templates from that shell.
- For MVP, this can be minimal and should not block the first Ghost homepage.

## Local development

Local development should be containerised and resemble production where practical.

Expected local services:

- `nginx-router` or equivalent local path router.
- `ghost` custom image.
- `mysql` local database.

Local routing should mimic production:

- `http://localhost:8080/` -> Ghost.
- Future `/tools/*` routes can later point to a Python app.

Local dev should not require AWS credentials for normal work.

## AWS environments

There are two MVP environments:

- dev account.
- prod account.

Dev is not always-on. It should be possible to stop or destroy dev app runtime where sensible.

Prod uses temporary production domain initially because the final domain already hosts an existing site.

## RDS requirements

Dev and prod each have separate RDS instances.

Prod RDS:

- Tiny instance, likely `db.t4g.micro` to start.
- Single-AZ.
- Deletion protection enabled.
- Removal policy retain.
- Automated backups enabled.
- Not casually deleted by stack deletion.

Dev RDS:

- Tiny instance.
- Single-AZ.
- Short backup retention.
- May be stopped or treated as disposable.

Ghost manages its own schema/migrations on startup.

## CloudFront caching

- Public anonymous HTML: 10 minute cache.
- `/ghost/*`: no cache.
- Preview/editor/session/member routes: no cache.
- Static assets/media: long cache where safe.
- Deployments should invalidate the homepage and key public paths.

## DNS and certificates

- Route 53 in both dev and prod accounts.
- App infrastructure in eu-west-2.
- CloudFront ACM certificates in us-east-1.
- Claude may choose the cleanest CDK stack layout to support this.

## CI/CD

GitHub Actions deploys from `main`:

1. Lint/test/build.
2. Build Ghost Docker image once.
3. Tag image with Git SHA.
4. Push image to shared ECR in the dev AWS account.
5. Deploy exact image SHA to dev.
6. Run dev smoke tests.
7. Wait for manual approval using GitHub Environments.
8. Deploy same image SHA to prod.
9. Run prod smoke tests.

The prod account pulls the image cross-account from the dev account ECR.

## ECR

- Shared ECR lives in the dev account.
- GitHub Actions can push to ECR.
- Dev ECS can pull normally.
- Prod ECS can pull cross-account.
- Add a lifecycle policy to clean old images while preserving recent/prod images.

## Config and parameters

Use AWS SSM Parameter Store plain String parameters for runtime config/secrets for MVP.

Because each AWS account is dedicated to this project/environment, do not include project or environment prefixes in parameter names.

Use account-local paths such as:

- `/ghost/url`
- `/ghost/database/host`
- `/ghost/database/name`
- `/ghost/database/user`
- `/ghost/database/password`
- `/ghost/s3/bucket`
- `/ghost/s3/region`
- `/cache/html_ttl`

Do not commit real parameter values to Git.

## First-time environment setup script

Create `scripts/new_env.py`.

It should:

- Use boto3.
- Confirm the current AWS account/profile before making changes.
- Ask interactively for required values.
- Write SSM parameters.
- Refuse to overwrite existing values unless `--force` is supplied.
- Create or verify the GitHub OIDC provider.
- Create or verify the GitHub Actions deploy role.
- Scope GitHub OIDC trust to the configured GitHub repo and branch.
- Print next-step instructions after completion.

The script prepares the account for GitHub/CDK. CDK owns application infrastructure.

## Developer tooling

- Use `uv`.
- Use `pyproject.toml`.
- Use `ruff`.
- Use `pytest` where useful.
- Use `Makefile` as the main interface.

Expected Makefile targets:

- `make install`
- `make dev`
- `make test`
- `make lint`
- `make format`
- `make synth`
- `make deploy-dev`
- `make new-env`
- `make smoke URL=...`

## Quality checks

Include lightweight checks from day one:

- Smoke test homepage.
- Basic HTML validity check if practical.
- Playwright browser test.
- axe accessibility check.
- No-JS baseline test.

After deployed smoke tests:

- Homepage returns 200.
- Expected title is present.
- Expected h1 is present.
- No obvious Ghost/server error is visible.
- `/ghost/` is reachable and not cached.
