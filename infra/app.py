#!/usr/bin/env python3
import os
import sys

# Ensure infra/ is on sys.path so `from stacks.xxx import Xxx` works
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aws_cdk as cdk
from stacks.cdn_stack import CdnStack
from stacks.cert_stack import CertStack
from stacks.ecr_stack import EcrStack
from stacks.lightsail_stack import LightsailStack
from stacks.network_stack import NetworkStack

app = cdk.App()

account = os.environ.get("CDK_DEFAULT_ACCOUNT")
domain_name = app.node.try_get_context("domain")
if not domain_name:
    raise ValueError("Required CDK context 'domain' not set. Pass -c domain=<your-domain>")
origin_domain_name = f"origin.{domain_name}"

env_eu = cdk.Environment(account=account, region="eu-west-2")
env_us = cdk.Environment(account=account, region="us-east-1")

EcrStack(app, "EcrStack", env=env_eu)

network_stack = NetworkStack(app, "NetworkStack", domain_name=domain_name, env=env_eu)

lightsail_stack = LightsailStack(
    app,
    "LightsailStack",
    instance_name="dn-website-ghost",
    hosted_zone=network_stack.hosted_zone,
    origin_domain_name=origin_domain_name,
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
    origin_domain_name=origin_domain_name,
    certificate=cert_stack.certificate,
    hosted_zone=network_stack.hosted_zone,
    domain_name=domain_name,
    cross_region_references=True,
    env=env_eu,
)
cdn_stack.add_stack_dependency(lightsail_stack)

app.synth()
