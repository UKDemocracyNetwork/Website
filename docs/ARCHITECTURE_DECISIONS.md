# Architecture Decisions

## ADR 001: Use ECS Fargate

**Superseded by ADR 013.**

Use ECS Fargate for Ghost rather than ECS on self-managed EC2.

Reason: this is a side project where low operational burden and repeatable deployment matter more than minimal compute cost.

## ADR 002: Use one AWS account per environment

Use separate dev and prod AWS accounts.

Reason: clean environment boundaries and safer future growth.

## ADR 003: Use RDS per environment

**Superseded by ADR 013.** Each environment still has its own database.

Each environment gets its own RDS MySQL instance.

Reason: avoid public/shared database complexity and preserve account separation.

## ADR 004: Use tiny Single-AZ RDS for MVP

**Superseded by ADR 013.**

Use tiny Single-AZ RDS instances for MVP.

Reason: most public traffic is cached and the project can tolerate downtime at MVP stage.

## ADR 005: Use S3 for deployed Ghost media

**Superseded by ADR 013.** The S3 adapter was removed.

Use S3 via a Ghost storage adapter for deployed media/uploads. Do not use EFS for MVP.

Reason: user preference and cleaner disposable container model.

Risk: Ghost S3 storage depends on adapter behaviour. EFS remains fallback.

## ADR 006: Local dev may use mounted local storage

Local Docker Compose can use local mounted Ghost content storage instead of S3.

Reason: avoid AWS credentials during ordinary local work.

## ADR 007: Repo-owned homepage

The MVP homepage is committed in Git and rendered by Ghost theme/template.

Reason: the MVP is a golden thread deployment exercise, not CMS content management.

## ADR 008: Build once, promote same image

Build the Docker image once, deploy exact SHA to dev, smoke test, then promote same image to prod.

Reason: prod should receive exactly what dev tested.

## ADR 009: Shared ECR in dev account

Use one ECR repository in the dev account. Prod pulls cross-account.

Reason: avoids a separate tooling account while supporting build-once promotion.

## ADR 010: Use SSM Parameter Store plain Strings for MVP

**Superseded by ADR 014.**

Use SSM Parameter Store plain String parameters for config/secrets.

Reason: user preference and dedicated per-environment accounts.

Guardrail: do not commit real values. Scope IAM narrowly.

## ADR 011: Use Route 53 in each account

Each environment manages DNS in Route 53.

Reason: CDK can manage DNS/cert validation cleanly.

## ADR 012: Ghost admin remains public at `/ghost/` for MVP

Use Ghost's normal admin path and auth for MVP.

Reason: simple. Cognito/Google Workspace perimeter auth may be added later.

## ADR 013: Run everything on one Lightsail server

Run Ghost, MySQL and nginx with Docker Compose on one Lightsail server, behind CloudFront. Uploads and the database live on Docker volumes on that server.

Reason: the Fargate, ALB and RDS setup cost far more than a demo site justifies, mostly RDS Extended Support on MySQL 8.0. The site is about 95% reads, Ghost doesn't support clustering, and CloudFront absorbs most traffic, so one server fits the load.

Trade-offs: one server is a single point of failure, a resize means creating a new server from a snapshot, and backups are our job. Lightsail snapshots stay on the same AWS service, so off-server backups are still needed before production.

## ADR 014: Secrets stay on the server

Database passwords are generated at first boot and stored only in `/opt/ghost/secrets.env`.

Reason: nothing outside the server needs them, and standard Lightsail servers can't use an IAM role to read SSM. This also means no long-lived AWS keys on the server: each deploy passes a temporary ECR token over SSH.

The SMTP login is the exception, as it comes from outside. It lives in SSM (`/ghost/mail/user` and the SecureString `/ghost/mail/password`), and each deploy copies it to `/opt/ghost/mail.env` over SSH.

## ADR 015: Deploy over SSH with temporary access

Deploys ask Lightsail for a short-lived SSH certificate, open port 22 to the deploy machine's IP address, and close it again afterwards.

Reason: no SSH keys to store or rotate, and port 22 stays closed between deploys. The CloudFormation firewall rules are only ever changed by CDK and these temporary rules.

## ADR 016: Limit the origin to CloudFront's IP ranges

The server's port 80 only accepts AWS's `CLOUDFRONT_ORIGIN_FACING` IPv4 ranges, read at each deploy.

Reason: Lightsail firewalls can't use the managed prefix list. These ranges are shared with other CloudFront customers, and traffic from CloudFront to the server is plain HTTP, so both need improving before production.
