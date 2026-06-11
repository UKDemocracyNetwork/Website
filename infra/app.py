#!/usr/bin/env python3
import os
import sys

# Ensure infra/ is on sys.path so `from stacks.xxx import Xxx` works
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aws_cdk as cdk
from stacks.app_stack import AppStack
from stacks.cdn_stack import CdnStack
from stacks.cert_stack import CertStack
from stacks.database_stack import DatabaseStack
from stacks.ecr_stack import EcrStack
from stacks.network_stack import NetworkStack

app = cdk.App()

account = os.environ.get("CDK_DEFAULT_ACCOUNT")
domain_name = app.node.try_get_context("domain")
if not domain_name:
    raise ValueError("Required CDK context 'domain' not set. Pass -c domain=<your-domain>")
image_tag = app.node.try_get_context("imageTag") or "latest"

env_eu = cdk.Environment(account=account, region="eu-west-2")
env_us = cdk.Environment(account=account, region="us-east-1")

ecr_stack = EcrStack(app, "EcrStack", env=env_eu)

network_stack = NetworkStack(app, "NetworkStack", domain_name=domain_name, env=env_eu)

database_stack = DatabaseStack(
    app,
    "DatabaseStack",
    vpc=network_stack.vpc,
    env=env_eu,
)

app_stack = AppStack(
    app,
    "AppStack",
    vpc=network_stack.vpc,
    repository=ecr_stack.repository,
    db_instance=database_stack.instance,
    hosted_zone=network_stack.hosted_zone,
    domain_name=domain_name,
    image_tag=image_tag,
    env=env_eu,
)

# CloudFront cert must live in us-east-1; cross_region_references lets CDK pass the ARN
# to CdnStack (eu-west-2) via a CDK-managed SSM parameter during deployment.
cert_stack = CertStack(
    app,
    "CertStack",
    domain_name=domain_name,
    hosted_zone=network_stack.hosted_zone,
    cross_region_references=True,
    env=env_us,
)

cdn_stack = CdnStack(
    app,
    "CdnStack",
    alb=app_stack.alb,
    certificate=cert_stack.certificate,
    hosted_zone=network_stack.hosted_zone,
    domain_name=domain_name,
    cross_region_references=True,
    env=env_eu,
)

app.synth()
