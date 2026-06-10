# Project Plan Request for Claude

Before implementing anything, produce a project plan for the user.

The plan should be concise but complete. Include:

## 1. Repository structure

Propose the file/folder layout.

## 2. Phased implementation

Break the work into small phases. The first phase should produce a runnable local skeleton. Later phases should add AWS/CDK, GitHub Actions, smoke tests, and deployment.

## 3. AWS architecture

Describe the stacks/resources you expect to create, including:

- VPC/networking.
- ECS Fargate service.
- RDS MySQL.
- S3 media bucket.
- CloudFront.
- Route 53.
- ACM certs in us-east-1.
- ECR in dev account.
- IAM/OIDC roles.

## 4. Local development

Describe Docker Compose and Makefile usage.

## 5. CI/CD

Describe the GitHub Actions workflow.

## 6. Safety and data protection

Explain how prod RDS is retained and protected.

## 7. Risks

Call out at least:

- Ghost S3 adapter risk.
- CloudFront certificate region complexity.
- Cross-account ECR pull complexity.
- CDK bootstrapping/OIDC role setup.

## 8. Open questions

Ask only questions that block implementation. Do not ask broad or already-settled questions.
