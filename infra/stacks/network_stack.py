from aws_cdk import CfnOutput, Fn, Stack
from aws_cdk import aws_route53 as route53
from constructs import Construct


class NetworkStack(Stack):
    def __init__(self, scope: Construct, id: str, *, domain_name: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        self.hosted_zone = route53.HostedZone(
            self,
            "HostedZone",
            zone_name=domain_name,
        )

        CfnOutput(
            self,
            "NameServers",
            description="Add these NS records to the parent zone to delegate DNS",
            value=Fn.join(",", self.hosted_zone.hosted_zone_name_servers),
        )
