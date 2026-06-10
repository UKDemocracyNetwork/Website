# Claude Code Instructions

You are building a starter repository for a Ghost-based AWS deployment golden thread.

Your first task is **not to write code immediately**. First produce a project plan for the user to approve.

## Required first response

Write a project plan that includes:

1. Proposed repository structure.
2. Implementation phases.
3. Key AWS resources.
4. Local development workflow.
5. CI/CD workflow.
6. Risks and assumptions.
7. Questions or trade-offs that must be resolved before implementation.

After the user approves the plan, implement the project incrementally.

## Behaviour rules

- Prefer simple, boring, maintainable solutions.
- Keep the MVP small.
- Do not add Lambda for MVP.
- Do not add JavaScript or CSS for the initial frontend unless explicitly requested.
- Treat this as a golden thread deployment project, not merely a static site.
- Everything that affects behaviour or presentation should live in Git.
- Use `uv` and `pyproject.toml` for Python tooling.
- Use a `Makefile` as the main developer interface.
- Use Python CDK for infrastructure.
- Use GitHub Actions for CI/deployment.
- Use AWS eu-west-2 for application infrastructure.
- Use ACM certificates in us-east-1 where CloudFront requires them.

## MVP summary

The MVP is a single committed homepage rendered by a custom Ghost theme running on ECS Fargate. It is fronted by CloudFront, uses RDS MySQL, and is deployed through GitHub Actions. Dev and prod are separate AWS accounts. The same Docker image is built once, deployed to dev, smoke-tested, then promoted to prod after approval.

Claude should read all files in `docs/` before planning or implementing.
