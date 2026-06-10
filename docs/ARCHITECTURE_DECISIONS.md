# Architecture Decisions

## ADR 001: Use ECS Fargate

Use ECS Fargate for Ghost rather than ECS on self-managed EC2.

Reason: this is a side project where low operational burden and repeatable deployment matter more than minimal compute cost.

## ADR 002: Use one AWS account per environment

Use separate dev and prod AWS accounts.

Reason: clean environment boundaries and safer future growth.

## ADR 003: Use RDS per environment

Each environment gets its own RDS MySQL instance.

Reason: avoid public/shared database complexity and preserve account separation.

## ADR 004: Use tiny Single-AZ RDS for MVP

Use tiny Single-AZ RDS instances for MVP.

Reason: most public traffic is cached and the project can tolerate downtime at MVP stage.

## ADR 005: Use S3 for deployed Ghost media

Use S3 via a Ghost storage adapter for deployed media/uploads. Do not use EFS for MVP.

Reason: user preference and cleaner disposable container model.

Risk: Ghost S3 storage depends on adapter behaviour. EFS remains fallback.

## ADR 006: Local dev may use mounted local storage

Local Docker Compose can use local mounted Ghost content storage instead of S3.

Reason: avoid AWS credentials during ordinary local work. S3 behaviour is tested in deployed dev.

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

Use SSM Parameter Store plain String parameters for config/secrets.

Reason: user preference and dedicated per-environment accounts.

Guardrail: do not commit real values. Scope IAM narrowly.

## ADR 011: Use Route 53 in each account

Each environment manages DNS in Route 53.

Reason: CDK can manage DNS/cert validation cleanly.

## ADR 012: Ghost admin remains public at `/ghost/` for MVP

Use Ghost's normal admin path and auth for MVP.

Reason: simple. Cognito/Google Workspace perimeter auth may be added later.
