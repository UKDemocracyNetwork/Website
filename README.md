# UK Democracy Network Website

Ghost CMS deployed on AWS, managed with Python CDK.

## Architecture

- **Ghost 5** on ECS Fargate (Alpine), behind an Application Load Balancer
- **RDS MySQL 8.0** in isolated subnets
- **CloudFront** for HTTPS termination and caching
- **S3** for media uploads
- **Route 53** for DNS
- Six CDK stacks: `EcrStack`, `NetworkStack`, `DatabaseStack`, `AppStack`, `CertStack`, `CdnStack`

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
- SSM parameters written (run once per account): `make new-env`
- Ghost image pushed to ECR

### Deploy all stacks

```bash
make deploy-dev                        # uses DOMAIN=website.dn.womblelabs.co.uk
make deploy-dev DOMAIN=example.com     # override domain
```

After the first deploy, add the Route 53 nameservers shown in the `NetworkStack` output to the parent DNS zone.

### Deploy a specific image tag

```bash
cdk deploy --all -c domain=example.com -c imageTag=abc1234
```

## Running tests

```bash
make test                          # unit tests
make smoke URL=https://example.com # smoke tests against a live URL
```

## Repository structure

```
docker/        Dockerfile and nginx config
docs/          Architecture decisions and specs
infra/         Python CDK stacks
scripts/       Operational scripts (new-env setup)
tests/         Smoke tests
theme/         Ghost theme (Handlebars)
```
