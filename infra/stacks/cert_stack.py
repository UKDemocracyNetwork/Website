from aws_cdk import Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from constructs import Construct


class CertStack(Stack):
    """ACM certificate for CloudFront — must be deployed to us-east-1."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        domain_name: str,
        hosted_zone: route53.IHostedZone,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.certificate = acm.Certificate(
            self,
            "Certificate",
            domain_name=domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )
