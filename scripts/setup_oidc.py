#!/usr/bin/env python3
"""
setup_oidc.py — create the GitHub Actions OIDC provider and deploy role.

Run once per AWS account. Safe to re-run (idempotent — existing resources are updated).

Usage:
    uv run python scripts/setup_oidc.py
    uv run python scripts/setup_oidc.py --repo UKDemocracyNetwork/Website
"""

import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError

GITHUB_OIDC_URL = "https://token.actions.githubusercontent.com"
# Trusted root CA thumbprint for token.actions.githubusercontent.com
GITHUB_OIDC_THUMBPRINT = "6938fd4d98bab03faadb97b34396831e3780aea1"
ROLE_NAME = "github-actions-deploy"
REGION = "eu-west-2"


def get_account_id(session: boto3.Session) -> str:
    return session.client("sts").get_caller_identity()["Account"]


def ensure_oidc_provider(iam, account_id: str) -> None:
    arn = f"arn:aws:iam::{account_id}:oidc-provider/token.actions.githubusercontent.com"
    try:
        iam.get_open_id_connect_provider(OpenIDConnectProviderArn=arn)
        print("  OK    OIDC provider already exists")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        iam.create_open_id_connect_provider(
            Url=GITHUB_OIDC_URL,
            ThumbprintList=[GITHUB_OIDC_THUMBPRINT],
            ClientIDList=["sts.amazonaws.com"],
        )
        print("  CREATED OIDC provider")


def trust_policy(account_id: str, repo: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Federated": (f"arn:aws:iam::{account_id}:oidc-provider/token.actions.githubusercontent.com")
                },
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    },
                    # Scope to the main branch only — PRs cannot assume this role.
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": (f"repo:{repo}:ref:refs/heads/main"),
                    },
                },
            }
        ],
    }


def deploy_policy(account_id: str) -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            # CDK deploys by assuming bootstrap roles; the bootstrap roles carry
            # the broad CloudFormation/service permissions, not this role.
            {
                "Sid": "CdkBootstrapRoles",
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Resource": f"arn:aws:iam::{account_id}:role/cdk-*",
            },
            # ECR auth token must target *.
            {
                "Sid": "EcrAuth",
                "Effect": "Allow",
                "Action": "ecr:GetAuthorizationToken",
                "Resource": "*",
            },
            # Push Ghost image to its specific ECR repository.
            {
                "Sid": "EcrPush",
                "Effect": "Allow",
                "Action": [
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:InitiateLayerUpload",
                    "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload",
                    "ecr:PutImage",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                ],
                "Resource": (f"arn:aws:ecr:{REGION}:{account_id}:repository/dn-website-ghost"),
            },
            # Invalidate CloudFront cache after each deploy.
            {
                "Sid": "CloudFrontInvalidation",
                "Effect": "Allow",
                "Action": "cloudfront:CreateInvalidation",
                "Resource": "*",
            },
            # Read CloudFormation outputs (e.g. CloudFront distribution ID).
            {
                "Sid": "CloudFormationDescribe",
                "Effect": "Allow",
                "Action": "cloudformation:DescribeStacks",
                "Resource": "*",
            },
        ],
    }


def ensure_role(iam, account_id: str, repo: str) -> str:
    tp = json.dumps(trust_policy(account_id, repo))
    dp = json.dumps(deploy_policy(account_id))

    try:
        role = iam.get_role(RoleName=ROLE_NAME)
        iam.update_assume_role_policy(RoleName=ROLE_NAME, PolicyDocument=tp)
        iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="deploy", PolicyDocument=dp)
        print(f"  OK    Role '{ROLE_NAME}' already exists — policies updated")
        return role["Role"]["Arn"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise

    role = iam.create_role(
        RoleName=ROLE_NAME,
        AssumeRolePolicyDocument=tp,
        Description="GitHub Actions deploy role for Ghost on AWS",
        MaxSessionDuration=3600,
    )
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="deploy", PolicyDocument=dp)
    print(f"  CREATED role '{ROLE_NAME}'")
    return role["Role"]["Arn"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up GitHub Actions OIDC for this AWS account.")
    parser.add_argument(
        "--repo",
        default="UKDemocracyNetwork/Website",
        help="GitHub repo in owner/name format",
    )
    args = parser.parse_args()

    session = boto3.Session()
    account_id = get_account_id(session)
    iam = session.client("iam")

    print(f"\nAWS account : {account_id}")
    print(f"GitHub repo : {args.repo}\n")
    answer = input("Continue? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    print()
    ensure_oidc_provider(iam, account_id)
    role_arn = ensure_role(iam, account_id, args.repo)

    print(f"\nRole ARN: {role_arn}\n")
    print("Add it as a GitHub Actions secret, then you're ready to push:\n")
    print(f"  gh secret set AWS_DEPLOY_ROLE_ARN --body '{role_arn}' --repo {args.repo}")


if __name__ == "__main__":
    main()
