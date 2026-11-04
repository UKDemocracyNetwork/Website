import json
import urllib.request
from pathlib import Path

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lightsail as lightsail
from aws_cdk import aws_route53 as route53
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parents[2]
IP_RANGES_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"
DEPLOY_ROLE_NAME = "github-actions-deploy"


def cloudfront_origin_cidrs() -> list[str]:
    """The IPv4 ranges CloudFront connects to origins from.

    Lightsail firewalls can't use AWS's managed prefix list, so the rule has to list
    the ranges. Each deploy reads the current ones, which keeps the rule up to date.
    """
    with urllib.request.urlopen(IP_RANGES_URL, timeout=30) as response:
        ranges = json.load(response)
    return sorted({p["ip_prefix"] for p in ranges["prefixes"] if p["service"] == "CLOUDFRONT_ORIGIN_FACING"})


class LightsailStack(Stack):
    """One server running Ghost, MySQL and nginx with Docker (see deploy/compose.yml)."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        instance_name: str,
        hosted_zone: route53.IHostedZone,
        origin_domain_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # Changing the blueprint or bundle here has no effect on a running server:
        # to move to a bigger plan, create a new server from a snapshot.
        instance = lightsail.CfnInstance(
            self,
            "Instance",
            instance_name=instance_name,
            blueprint_id="ubuntu_24_04",
            bundle_id="small_3_0",  # 2GB memory, 2 vCPUs, 60GB disk
            availability_zone=f"{self.region}a",
            user_data=(REPO_ROOT / "deploy" / "first_boot.sh").read_text(),
            add_ons=[
                lightsail.CfnInstance.AddOnProperty(
                    add_on_type="AutoSnapshot",
                    status="Enabled",
                    auto_snapshot_add_on_request=lightsail.CfnInstance.AutoSnapshotAddOnProperty(
                        snapshot_time_of_day="03:00",
                    ),
                ),
            ],
            networking=lightsail.CfnInstance.NetworkingProperty(
                ports=[
                    # Web traffic from CloudFront only.
                    lightsail.CfnInstance.PortProperty(
                        protocol="tcp",
                        from_port=80,
                        to_port=80,
                        cidrs=cloudfront_origin_cidrs(),
                    ),
                    # SSH from the Lightsail console's browser client. Deploys open
                    # port 22 to their own IP address while they run.
                    lightsail.CfnInstance.PortProperty(
                        protocol="tcp",
                        from_port=22,
                        to_port=22,
                        cidr_list_aliases=["lightsail-connect"],
                    ),
                ],
            ),
        )

        # The server holds the database and uploads, so it outlives the stack.
        instance.apply_removal_policy(RemovalPolicy.RETAIN)

        static_ip = lightsail.CfnStaticIp(
            self,
            "StaticIp",
            static_ip_name=f"{instance_name}-ip",
            attached_to=instance.instance_name,
        )
        static_ip.add_resource_dependency(instance)

        # CloudFront origins need a DNS name, not an IP address.
        route53.ARecord(
            self,
            "OriginRecord",
            zone=hosted_zone,
            record_name=origin_domain_name,
            target=route53.RecordTarget.from_ip_addresses(static_ip.attr_ip_address),
        )

        # scripts/lightsail.sh needs these in CI. Most Lightsail actions don't
        # support limiting them to one resource, so this covers the account's servers.
        iam.Policy(
            self,
            "DeployRolePolicy",
            roles=[iam.Role.from_role_name(self, "DeployRole", DEPLOY_ROLE_NAME)],
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "lightsail:GetInstanceAccessDetails",
                        "lightsail:OpenInstancePublicPorts",
                        "lightsail:CloseInstancePublicPorts",
                    ],
                    resources=["*"],
                ),
            ],
        )

        CfnOutput(self, "InstanceName", value=instance_name)
        CfnOutput(self, "OriginDomainName", value=origin_domain_name)
