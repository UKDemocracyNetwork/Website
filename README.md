# UK Democracy Network Website

Ghost CMS deployed on AWS, managed with Python CDK.

## Architecture

- **Ghost 6**, **MySQL 8.4** and **nginx** in Docker on one **Lightsail** server (`deploy/compose.yml`)
- Uploads and the database live on Docker volumes on that server, covered by daily Lightsail snapshots
- **CloudFront** for HTTPS termination and caching. The server's web port only accepts CloudFront's IP ranges
- **Route 53** for DNS
- Five CDK stacks: `EcrStack`, `NetworkStack` (DNS zone), `LightsailStack`, `CertStack`, `CdnStack`

Dev and prod are separate AWS accounts. The same Docker image is built once, deployed to dev, smoke-tested, then promoted to prod after approval.

## Local development

Requires Docker and [uv](https://docs.astral.sh/uv/).

```bash
make install   # install Python dependencies
make dev       # start Ghost + MySQL + nginx at http://localhost:8080
make dev-stop  # stop everything
make dev-logs  # tail Ghost logs
```

On first run, visit `http://localhost:8080/ghost/` to complete Ghost setup, then activate the `dn-theme` under Settings → Design.

## Deploying

### Prerequisites

- AWS CLI configured for the target account
- CDK bootstrapped: `cdk bootstrap aws://ACCOUNT/eu-west-2` and `cdk bootstrap aws://ACCOUNT/us-east-1`
- GitHub OIDC role created (run once per account): `uv run python scripts/setup_oidc.py`
- Mailgun SMTP login in SSM (deploys fail without it): `/ghost/mail/user` as a String and `/ghost/mail/password` as a SecureString

Pushes to `main` deploy automatically. To do the same by hand, there are two steps:

```bash
make deploy-dev                                        # infrastructure (CDK)
make deploy-server IMAGE=<ecr-repo>:<tag>              # run that image on the server
```

Override the domain with `DOMAIN=example.com`. After the first deploy, add the Route 53 nameservers shown in the `NetworkStack` output to the parent DNS zone.

### Setting up a new environment

The first deploy of a new environment must restore data **before** the site is reachable, because a fresh Ghost lets anyone who finds `/ghost/setup` create the owner account:

```bash
cdk deploy EcrStack NetworkStack LightsailStack -c domain=example.com
# push an image to ECR, then:
make restore-server IMAGE=<ecr-repo>:<tag> SQL=backup.sql.gz CONTENT=content.tar.gz DOMAIN=example.com
make deploy-dev DOMAIN=example.com
```

`CONTENT` is a gzipped tar with `images/`, `media/` and `files/` at the top level. `restore-server` replaces all data on the server.

### Getting on the server

No SSH keys or AWS credentials are stored. `scripts/lightsail.sh` asks Lightsail for a short-lived SSH certificate and opens port 22 to your IP address only while it runs:

```bash
scripts/lightsail.sh run "docker ps"
```

The browser SSH client in the Lightsail console also works.

### Changing the server

- `deploy/first_boot.sh` only runs when a server is created, and must stay plain POSIX `sh`.
- Moving to a bigger plan means creating a new server from a snapshot, as `BundleId` can't be updated.

## Running tests

```bash
make test                          # unit tests
make smoke URL=https://example.com # smoke tests against a live URL
```

## Repository structure

```
deploy/        The deployed stack: Compose file, nginx config, first-boot script
docker/        Ghost Dockerfile and local nginx config
docs/          Architecture decisions and specs
infra/         Python CDK stacks
scripts/       Operational scripts (server deploys and restores, OIDC setup, Medium import)
tests/         Smoke tests
theme/         Ghost theme (Handlebars)
```
