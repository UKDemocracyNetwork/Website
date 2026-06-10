from aws_cdk import CfnOutput, Fn, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_route53 as route53
from constructs import Construct


class NetworkStack(Stack):
    def __init__(self, scope: Construct, id: str, *, domain_name: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # No NAT gateways: ECS runs in public subnets with assign_public_ip to reach ECR.
        # RDS runs in isolated subnets (no internet route needed).
        self.vpc = ec2.Vpc(
            self, "Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        self.hosted_zone = route53.HostedZone(
            self, "HostedZone",
            zone_name=domain_name,
        )

        CfnOutput(
            self, "NameServers",
            description="Add these NS records to the parent zone to delegate DNS",
            value=Fn.join(",", self.hosted_zone.hosted_zone_name_servers),
        )
